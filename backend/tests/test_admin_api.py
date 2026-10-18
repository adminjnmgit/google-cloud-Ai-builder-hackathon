"""Pipeline control over HTTP: uploads, failed runs, pruning, authorisation, concurrency."""

import io

from sqlalchemy import text

from orbit import runs
from orbit.enums import RunStatus
from orbit.extensions import db
from orbit.models import Event, PipelineRun
from tests.conftest import SEEDED_REPORTS

CSV = (
    'Sl No,Type,Date,Headline,Summary\n'
    '1,Biz News,2026-10-01 9:00,Crude oil prices surge 4% on supply fears,Brent up\n'
    '2,Biz News,2026-10-02 9:00,Petrol and diesel prices hiked by Rs 3 per litre,Pump prices up\n'
)
NOTHING_RELEVANT = 'Sl No,Type,Date,Headline,Summary\n1,Biz News,2026-10-01 9:00,Local fair opens,Nothing here\n'


def upload(client, text, **kwargs):
    return client.post(
        '/api/admin/pipeline/run',
        data={'file': (io.BytesIO(text.encode()), 'news.csv')},
        content_type='multipart/form-data',
        **kwargs,
    )


def listed_runs(client):
    return client.get('/api/admin/pipeline/runs').get_json()['runs']


def test_uploading_a_csv_publishes_a_new_feed(seeded_client):
    response = upload(seeded_client, CSV)
    assert response.status_code == 201
    run = response.get_json()
    assert (run['source'], run['status'], run['is_active']) == ('upload', 'success', True)
    assert run['reports_in'] == 2
    assert run['events_out'] >= 2

    data = seeded_client.get('/api/data').get_json()
    assert data['meta']['reports'] == 2
    assert len(data['events']) == run['events_out']
    assert [r['is_active'] for r in listed_runs(seeded_client)] == [True, False]


def test_a_run_that_finds_nothing_keeps_the_current_feed(seeded_client):
    response = upload(seeded_client, NOTHING_RELEVANT)
    assert response.status_code == 422
    assert seeded_client.get('/api/data').get_json()['meta']['reports'] == SEEDED_REPORTS

    newest, previous = listed_runs(seeded_client)[:2]
    assert newest['status'] == 'failed'
    assert 'no events' in newest['error']
    assert newest['is_active'] is False
    assert previous['is_active'] is True


def test_bad_input_is_a_clean_422(client):
    assert upload(client, 'a,b\n1,2\n').status_code == 422
    assert client.post('/api/admin/pipeline/run', json={'source': 'csv'}).status_code == 422
    assert client.post('/api/admin/pipeline/run', json={'source': 'csv', 'path': 'no/such/file.csv'}).status_code == 422


def test_non_utf8_uploads_are_a_clean_422(client):
    response = client.post(
        '/api/admin/pipeline/run',
        data={'file': (io.BytesIO(b'Sl No,Type,Date,Headline,Summary\n1,Biz,2026-10-01,\xff\xfe,x\n'), 'bad.csv')},
        content_type='multipart/form-data',
    )
    assert response.status_code == 422
    assert 'UTF-8' in response.get_json()['message']


def test_unknown_source_is_a_400(client):
    assert client.post('/api/admin/pipeline/run', json={'source': 'ftp'}).status_code == 400
    assert client.post('/api/admin/pipeline/run', json={'source': 'seed'}).status_code == 400


def test_an_empty_newsroom_table_is_a_clean_422(app):
    with app.app_context():
        db.session.execute(
            text(
                'CREATE TABLE jagran_biz (id INT PRIMARY KEY, source_no INT, section VARCHAR(80) NOT NULL, '
                'headline TEXT, summary TEXT, published_at VARCHAR(32) NOT NULL, headline_en TEXT, summary_en TEXT)'
            )
        )
        db.session.commit()
    response = app.test_client().post('/api/admin/pipeline/run', json={'source': 'jagran_biz'})
    assert response.status_code == 422
    assert 'no usable English reports' in response.get_json()['message']


def test_old_runs_are_pruned(app):
    app.config['KEEP_RUNS'] = 2
    client = app.test_client()
    for _ in range(3):
        assert upload(client, CSV).status_code == 201
    with app.app_context():
        assert len({run_id for (run_id,) in db.session.query(Event.run_id).distinct()}) == 2
        assert db.session.query(PipelineRun).filter_by(is_active=True).count() == 1


def test_a_second_run_is_refused_while_one_is_in_progress(app):
    """The pipeline lock is a MySQL advisory lock, so it also protects against a run from another process."""
    with app.app_context(), db.engine.connect() as other_process:
        assert other_process.execute(text('SELECT GET_LOCK(:n, 0)'), {'n': runs.LOCK_NAME}).scalar() == 1
        try:
            response = upload(app.test_client(), CSV)
            assert response.status_code == 409
            assert 'already in progress' in response.get_json()['message']
        finally:
            other_process.execute(text('SELECT RELEASE_LOCK(:n)'), {'n': runs.LOCK_NAME})
    assert upload(app.test_client(), CSV).status_code == 201  # and the lock is released afterwards


def test_a_failed_run_is_recorded_with_its_error(app):
    upload(app.test_client(), NOTHING_RELEVANT)
    with app.app_context():
        run = db.session.query(PipelineRun).one()
        assert run.status == RunStatus.FAILED
        assert run.error.startswith('NoEventsProduced')
        assert run.finished_at is not None


def test_admin_requires_a_token_when_configured(app):
    app.config['ADMIN_TOKEN'] = 's3cret'
    client = app.test_client()
    url = '/api/admin/pipeline/runs'
    assert client.get(url).status_code == 401
    assert client.get(url, headers={'X-Admin-Token': 'wrong'}).status_code == 401
    assert client.get(url, headers={'X-Admin-Token': 's3cret'}).status_code == 200
    assert client.get(url, headers={'Authorization': 'Bearer s3cret'}).status_code == 200


def test_admin_is_local_only_without_a_token(client):
    remote = client.get('/api/admin/pipeline/runs', environ_base={'REMOTE_ADDR': '10.1.2.3'})
    assert remote.status_code == 403
    assert client.get('/api/admin/pipeline/runs').status_code == 200
