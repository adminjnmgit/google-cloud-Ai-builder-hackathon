"""The ten sectors added after the first five: every one has drivers that reach it, and detectors stay in their lane."""

import json

import pytest
from sqlalchemy import func, select

from orbit import runs
from orbit.extensions import db
from orbit.models import PipelineRun
from orbit.pipeline.engine import run_pipeline
from orbit.pipeline.lexicon import DETECTORS, IND_PATTERNS, INDUSTRIES
from orbit.pipeline.sources import parse_when

ORIGINAL = ['Automotive', 'Energy', 'Banking', 'Pharma', 'Technology']
ADDED = [name for name in INDUSTRIES if name not in ORIGINAL]


def report(sl, headline, summary='', section='Biz News', when='2026-10-01 9:00'):
    w = parse_when(when)
    return dict(sl=sl, when=w, date=w.strftime('%Y-%m-%d %H:%M'), type=section, headline=headline, summary=summary)


def one_event(headline, summary=''):
    events = run_pipeline([report(1, headline, summary)])['events']
    assert len(events) >= 1, f'no event for: {headline}'
    return events


def test_there_are_fifteen_sectors_that_fit_the_database_columns():
    assert len(INDUSTRIES) == 15
    assert len(set(INDUSTRIES)) == 15
    assert INDUSTRIES[:5] == ORIGINAL  # the first five keep their place; stored workspaces refer to them by name
    assert max(map(len, INDUSTRIES)) <= 20  # String(20) on the workspace tables


def test_every_sector_has_a_word_list_or_its_own_detector():
    for name in ADDED:
        assert name in IND_PATTERNS, name
        assert any(name in det['inds'] for det in DETECTORS), name


@pytest.mark.parametrize(
    ('headline', 'var', 'sector'),
    [
        ('Gold price rises 2% to a record high as demand picks up', 'gold', 'Gems & Jewellery'),
        ('Airfares jump 15% as airlines cut capacity', 'travel_demand', 'Aviation & Travel'),
        ('Housing sales fall 8% in the top cities as prices climb', 'housing_demand', 'Real Estate'),
        ('Cement prices to rise by 3% from next month', 'cement', 'Cement & Infra'),
        (
            'Government raises infrastructure spending outlay by 10 lakh crore in the budget',
            'infra_spend',
            'Cement & Infra',
        ),
        ('Monsoon rainfall below normal, kharif sowing falls 6%', 'monsoon', 'Agriculture'),
        ('Fertiliser subsidy hiked as urea prices surge 12%', 'fertiliser', 'Agriculture'),
        ('Cabinet raises MSP for kharif crops by 7%', 'farm_policy', 'Agriculture'),
        ('Edible oil prices rise 9% after import duty hike', 'food_prices', 'FMCG & Food'),
        ('Telecom companies hike mobile tariffs by 15%', 'telecom_tariff', 'Telecom & Media'),
        ('Festive sales jump 20% as retail demand surges', 'retail_demand', 'Retail & E-commerce'),
        ('Air conditioner sales rise 25% in the summer', 'durables_demand', 'Consumer Durables'),
    ],
)
def test_new_driver_produces_an_event_in_its_sector(headline, var, sector):
    events = [e for e in one_event(headline) if e['var'] == var]
    assert events, f'{var} was not detected in: {headline}'
    assert sector in events[0]['inds']


def test_sector_drivers_do_not_leak_into_other_sectors():
    # "oil" is an Energy word, but an edible-oil price story is a food story.
    (event,) = [e for e in one_event('Edible oil prices rise 9% after import duty hike') if e['var'] == 'food_prices']
    assert 'Energy' not in event['inds']
    assert event['inds'] == ['FMCG & Food', 'Agriculture']


def test_commodity_and_policy_drivers_reach_the_new_sectors():
    crude = next(e for e in one_event('Brent crude surges 8% on supply fears') if e['var'] == 'crude')
    assert {'Energy', 'Aviation & Travel'} <= set(crude['inds'])
    repo = next(e for e in one_event('RBI cuts repo rate by 25 bps to boost lending') if e['var'] == 'rate')
    assert 'Real Estate' in repo['inds']
    steel = next(e for e in one_event('Steel prices rise 6% on iron ore costs') if e['var'] == 'steel')
    assert {'Metals & Mining', 'Cement & Infra'} <= set(steel['inds'])


def test_the_industry_word_lists_tag_sectors_a_driver_only_mentions():
    events = one_event('ATF price hike hits airline margins', 'Petrol and diesel prices also rise 3%')
    fuel = next(e for e in events if e['var'] == 'fuel_price')
    assert 'Aviation & Travel' in fuel['inds']


@pytest.mark.parametrize(
    'headline',
    [
        'Gold loan demand rises 20% at NBFCs',  # a lending story, not a gold-price story
        'Housing loan EMIs cheaper as RBI repo rate cut',  # belongs to the repo-rate detector
        'Heavy rains cause waterlogging and traffic jams in Mumbai',  # weather, not crops
        'Vodafone Idea chairman resigns after board meeting',  # corporate news, not tariffs
        'Retail inflation rises to 5% in July',  # CPI is not retail demand
        'Fuel consumption jumps 10% as demand recovers',  # fuel, not retail demand
    ],
)
def test_look_alike_headlines_are_not_sector_events(headline):
    new_vars = {d['var'] for d in DETECTORS} - {'crude', 'fuel_price'}
    events = run_pipeline([report(1, headline)])['events']
    flagged = {e['var'] for e in events} & {
        'gold', 'housing_demand', 'monsoon', 'telecom_tariff', 'retail_demand',
    }  # fmt: skip
    assert new_vars  # the lexicon is not empty
    assert flagged == set(), headline


def test_snapshot_lists_every_sector(snapshot):
    assert snapshot['meta']['industries'] == INDUSTRIES
    seen = {name for event in snapshot['events'] for name in event['inds']}
    assert seen
    assert seen <= set(INDUSTRIES)


def test_export_snapshot_writes_matching_files_and_leaves_the_database_alone(app, tmp_path):
    source = tmp_path / 'reports.csv'
    source.write_text(
        'Sl No,Type,Date,Headline,Summary\n1,Biz News,2026-10-01 12:20:00,Gold price rises 2% to a record high,Demand up\n',
        encoding='utf-8',
    )
    target = tmp_path / 'events.json'
    with app.app_context():
        meta = runs.export_snapshot('csv', json_path=target, csv_path=str(source))
        assert db.session.scalar(select(func.count()).select_from(PipelineRun)) == 0

    saved = json.loads(target.read_text(encoding='utf-8'))
    assert saved['meta'] == meta
    assert meta['industries'] == INDUSTRIES
    assert [e['var'] for e in saved['events']] == ['gold']
    assert (tmp_path / 'events.js').read_text(
        encoding='utf-8'
    ) == f'window.ORBIT_DATA={target.read_text(encoding="utf-8")};\n'
