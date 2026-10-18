from datetime import datetime

import pytest

from orbit.pipeline.engine import run_pipeline
from orbit.pipeline.sources import parse_when


def report(sl, when, headline, summary='', section='Biz News'):
    w = parse_when(when)
    return dict(sl=sl, when=w, date=w.strftime('%Y-%m-%d %H:%M'), type=section, headline=headline, summary=summary)


def events_for(var, reports):
    return [e for e in run_pipeline(reports)['events'] if e['var'] == var]


def test_crude_report_becomes_an_energy_event_with_extracted_magnitude():
    out = events_for('crude', [report(1, '2026-10-01 9:00', 'Brent crude surges 8% as Hormuz tensions rise')])
    assert len(out) == 1
    e = out[0]
    assert (e['dir'], e['mag'], e['extracted']) == (1, 8.0, True)
    assert 'Energy' in e['inds']
    assert 'Commodity shock' in e['cats']
    assert 'Geopolitical event' in e['cats']


def test_stock_market_chatter_is_ignored():
    assert events_for('crude', [report(1, '2026-10-01 9:00', 'Oil India shares jumped as crude surges 5%')]) == []


def test_personal_finance_sections_are_not_considered():
    res = run_pipeline(
        [
            report(1, '2026-10-01 9:00', 'Crude oil prices surge 4% on supply fears', section='Personal Finance'),
            report(2, '2026-10-01 10:00', 'Crude oil prices surge 4% on supply fears'),
        ]
    )
    assert res['meta']['reports'] == 2
    assert res['meta']['considered'] == 1
    assert res['meta']['classified'] == 1


def test_reports_close_in_time_form_one_episode_and_a_long_gap_starts_another():
    rows = [
        report(1, '2026-10-01 9:00', 'Crude oil prices surge 4% on supply fears'),
        report(2, '2026-10-02 9:00', 'Crude oil prices climb 5% again'),
        report(3, '2026-10-20 9:00', 'Crude oil prices surge 6% after OPEC cut'),
    ]
    out = events_for('crude', rows)
    assert sorted(e['count'] for e in out) == [1, 2]
    two = next(e for e in out if e['count'] == 2)
    assert two['mag'] == 4.5  # median of the extracted magnitudes
    assert [r['sl'] for r in two['reports']] == [1, 2]


def test_opposite_directions_are_separate_episodes():
    out = events_for(
        'crude',
        [
            report(1, '2026-10-01 9:00', 'Crude oil prices surge 4% on supply fears'),
            report(2, '2026-10-02 9:00', 'Crude oil prices fall 3% on demand worries'),
        ],
    )
    assert sorted(e['dir'] for e in out) == [-1, 1]


def test_event_ids_run_newest_first_and_are_unique():
    res = run_pipeline(
        [
            report(1, '2026-09-01 9:00', 'Crude oil prices surge 4% on supply fears'),
            report(2, '2026-10-05 9:00', 'Petrol and diesel prices hiked by Rs 3 per litre'),
        ]
    )
    ids = [e['id'] for e in res['events']]
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)
    assert res['events'][0]['last'] >= res['events'][-1]['last']


def test_empty_input_is_an_error():
    with pytest.raises(ValueError, match='No reports'):
        run_pipeline([])


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        ('2026-10-16 9:40', datetime(2026, 10, 16, 9, 40)),
        ('2026-10-16 13:47:00', datetime(2026, 10, 16, 13, 47)),
        ('2026-10-16T13:47', datetime(2026, 10, 16, 13, 47)),
        ('2026-10-16', datetime(2026, 10, 16)),
        ('', None),
        ('not a date', None),
    ],
)
def test_parse_when(raw, expected):
    assert parse_when(raw) == expected


def test_golden_rerun_reproduces_the_shipped_feed(snapshot):
    """Every report behind the shipped events.json, run through the pipeline again, gives the same events."""
    by_sl = {}
    for ev in snapshot['events']:
        for r in ev['reports']:
            when = parse_when(r['date'])
            by_sl[r['sl']] = dict(
                sl=r['sl'],
                when=when,
                date=when.strftime('%Y-%m-%d %H:%M'),
                type=r['type'],
                headline=r['headline'],
                summary=r['summary'],
            )
    res = run_pipeline(by_sl.values())

    def key(e):
        return (e['var'], e['topic'], e['dir'], e['first'][:10], e['last'][:10], e['count'], e['rep'], e['mag'])

    assert sorted(map(key, res['events'])) == sorted(map(key, snapshot['events']))
    assert res['meta']['classified'] == snapshot['meta']['classified']
