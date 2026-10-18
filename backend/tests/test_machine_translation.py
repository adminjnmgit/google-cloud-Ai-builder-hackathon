"""Articles with no English of their own can use offline machine translations, clearly flagged."""

import pytest
from sqlalchemy import text

from orbit import runs
from orbit.extensions import db
from orbit.models import EventReport
from orbit.pipeline.sources import reports_from_table

HUMAN = 'Crude oil prices surge 4% on supply fears'
MACHINE = 'Petrol and diesel prices hiked by Rs. 3 per litre'


@pytest.fixture
def newsroom(app):
    """jagran_biz with: a human-English row, a Hindi-only row that has a machine translation, one that has none."""
    with app.app_context():
        db.session.execute(
            text(
                'CREATE TABLE jagran_biz (id INT PRIMARY KEY, source_no INT, section VARCHAR(80) NOT NULL, '
                'published_at VARCHAR(32) NOT NULL, headline TEXT, summary TEXT, headline_en TEXT, summary_en TEXT) '
                'DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci'  # not our collation, on purpose
            )
        )
        db.session.execute(
            text(
                'INSERT INTO jagran_biz VALUES '
                f"(1, 101, 'Biz News', '2026-10-01 9:00', 'hi1', 'hi1', '{HUMAN}', 'Brent up'),"
                "(2, 102, 'Biz News', '2021-03-05 8:30', 'hi2', 'hi2', '', ''),"
                "(3, 103, 'Biz News', '2021-03-06 8:30', 'hi3', 'hi3', '', '')"
            )
        )
        db.session.execute(
            text(
                'INSERT INTO orbit_translations (biz_id, headline_en, summary_en, model, translated_at) VALUES '
                f"(2, '{MACHINE}', 'Pump prices up', 'test-model', '2026-10-16 00:00:00'),"
                "(1, 'GARBLED machine text that must not replace the human translation', 'x', 'test-model', '2026-10-16 00:00:00')"
            )
        )
        db.session.commit()
    return app


def load(app, *, machine):
    with app.app_context():
        reports, _skipped = reports_from_table(db.session.connection(), machine=machine)
    return {r['sl']: r for r in reports}


def test_default_reads_only_human_english(newsroom):
    reports = load(newsroom, machine=False)
    assert list(reports) == [101]
    assert reports[101]['machine'] is False


def test_machine_translations_fill_the_gaps_and_are_flagged(newsroom):
    reports = load(newsroom, machine=True)
    assert sorted(reports) == [101, 102]  # 103 has no English at all, so it stays out
    assert reports[102]['machine'] is True
    assert reports[102]['headline'] == MACHINE
    assert reports[101]['machine'] is False  # human English wins over a machine row for the same article
    assert 'GARBLED' not in reports[101]['headline']


def test_translations_copied_into_the_table_are_still_machine_text(newsroom):
    """After `translate_hindi.py apply`, jagran_biz.headline_en holds the machine text; it must stay flagged."""
    with newsroom.app_context():
        db.session.execute(
            text(
                'UPDATE jagran_biz j JOIN orbit_translations t ON t.biz_id = j.id '
                'SET j.headline_en = t.headline_en, j.summary_en = t.summary_en WHERE j.id = 2'
            )
        )
        db.session.commit()
    assert list(load(newsroom, machine=False)) == [101]  # copied machine text is NOT mistaken for human English
    both = load(newsroom, machine=True)
    assert sorted(both) == [101, 102]
    assert both[102]['machine'] is True
    assert both[101]['machine'] is False


def test_the_flag_survives_a_pipeline_run_and_reaches_the_api(newsroom):
    with newsroom.app_context():
        run = runs.execute('jagran_biz', machine=True)
        assert run.meta['machineTranslated'] == 1
        assert 'machine translations' in run.source_detail
        assert db.session.query(EventReport).filter_by(machine=True).count() >= 1

    events = newsroom.test_client().get('/api/data').get_json()['events']
    flags = [r.get('mt', False) for e in events for r in e['reports']]
    assert any(flags)
    assert not all(flags)  # flagged only where it is true
    assert all('mt' not in r for e in events for r in e['reports'] if not r.get('mt'))


def test_configuration_can_turn_machine_translations_on_by_default(newsroom):
    newsroom.config['USE_MACHINE_TRANSLATIONS'] = True
    with newsroom.app_context():
        assert runs.execute('jagran_biz').meta['machineTranslated'] == 1
