"""The read-only feed endpoints and the pages Flask serves. The snapshot is loaded once for the whole module."""

import gzip
import json

import pytest

from tests.conftest import SEEDED_EVENTS


@pytest.fixture
def client(seeded_readonly_app):
    return seeded_readonly_app.test_client()


def test_health_reports_database_and_feed(client):
    body = client.get('/api/health').get_json()
    assert body['status'] == 'ok'
    assert body['database'] == 'mysql'
    assert body['feed']['events'] == SEEDED_EVENTS


def test_data_matches_the_frontend_shape_and_the_seed(client, snapshot):
    body = client.get('/api/data').get_json()
    assert set(body) == {'meta', 'events'}
    assert len(body['events']) == len(snapshot['events']) == SEEDED_EVENTS
    first, ref = body['events'][0], snapshot['events'][0]
    for field in (
        'id', 'var', 'topic', 'index', 'label', 'unit', 'hit', 'cats', 'inds', 'dir', 'mag', 'extracted',
        'nExtracted', 'nFacts', 'count', 'rep', 'repSummary', 'level',
    ):  # fmt: skip
        assert first[field] == ref[field], field
    assert len(first['reports']) == len(ref['reports'])
    assert first['reports'][0].keys() == ref['reports'][0].keys()
    assert body['meta']['industries'] == snapshot['meta']['industries']


def test_data_supports_etag_revalidation(client):
    etag = client.get('/api/data').headers['ETag']
    again = client.get('/api/data', headers={'If-None-Match': etag})
    assert again.status_code == 304
    assert again.headers['ETag'] == etag


def test_data_is_served_gzipped_when_the_client_accepts_it(client):
    plain = client.get('/api/data')
    packed = client.get('/api/data', headers={'Accept-Encoding': 'gzip'})
    assert packed.headers['Content-Encoding'] == 'gzip'
    assert packed.headers['ETag'] == plain.headers['ETag']
    assert json.loads(gzip.decompress(packed.data)) == plain.get_json()
    assert len(packed.data) <= len(plain.data)


def test_events_filtering_and_paging(client):
    pharma = client.get('/api/events?industry=Pharma&limit=500').get_json()
    assert 0 < pharma['total'] < SEEDED_EVENTS
    assert all('Pharma' in e['inds'] for e in pharma['items'])
    assert 'reports' not in pharma['items'][0]

    page = client.get('/api/events?industry=Pharma&limit=1&offset=0').get_json()
    assert page['total'] == pharma['total']
    assert len(page['items']) == 1
    assert page['items'][0]['id'] == pharma['items'][0]['id']

    by_var = client.get('/api/events?var=crude&include=reports').get_json()
    assert by_var['total'] > 0
    assert all(e['var'] == 'crude' and e['reports'] for e in by_var['items'])

    assert client.get('/api/events?category=Regulation&direction=-1').get_json()['total'] >= 0


def test_events_text_search_and_date_window(client):
    found = client.get('/api/events?q=crude&limit=500').get_json()
    assert found['total'] > 0
    assert all('crude' in (e['rep'] + e['repSummary'] + e['label']).lower() for e in found['items'])

    recent = client.get('/api/events?since=2026-09-15&limit=500').get_json()
    assert 0 < recent['total'] < SEEDED_EVENTS
    assert all(e['last'] >= '2026-09-15' for e in recent['items'])


def test_events_reject_bad_paging(client):
    assert client.get('/api/events?limit=abc').status_code == 400
    assert client.get('/api/events?limit=100000').get_json()['limit'] == 500  # clamped, not rejected


def test_event_detail_and_unknown_event(client):
    event = client.get('/api/events/E0001').get_json()
    assert event['id'] == 'E0001'
    assert event['reports']
    assert client.get('/api/events/E9999').status_code == 404


def test_stats(client):
    stats = client.get('/api/stats').get_json()
    assert stats['events'] == SEEDED_EVENTS
    assert stats['by_category'][0]['name'] == 'Supply disruption'
    assert sum(week['events'] for week in stats['weekly']) == SEEDED_EVENTS


def test_unknown_api_route_is_json(client):
    response = client.get('/api/nope')
    assert response.status_code == 404
    assert response.get_json()['error'] == 'Not Found'


def test_pages_are_served(client):
    assert client.get('/').status_code == 302
    assert b'OrbitAPI.start' in client.get('/owner/').data
    assert client.get('/analyst/').status_code == 200
    assert client.get('/compare/').status_code == 200
    assert client.get('/owner/js/owner.js').status_code == 200
    assert client.get('/nope/').status_code == 404


def test_responses_carry_security_headers(client):
    headers = client.get('/api/health').headers
    assert headers['X-Content-Type-Options'] == 'nosniff'
    assert headers['Referrer-Policy'] == 'same-origin'


def test_no_feed_yet_is_a_clear_503(app):
    response = app.test_client().get('/api/data')
    assert response.status_code == 503
    assert 'Run the pipeline' in response.get_json()['message']
