"""The AI agents, with the model switched off.

Nothing here calls Google. What matters is that the agents are inert unless configured, that turning
them on cannot change the shape of the feed, and that the API never leaks the key.
"""

from datetime import datetime

import pytest

from orbit.agents.catalog import AGENTS
from orbit.agents.client import AiClient, _summarise
from orbit.agents.pipeline import run_pipeline
from orbit.agents.runtime import ai_settings_from_config
from orbit.agents.search import search_events
from orbit.config import Settings

# Shaped like a key (so the masking code paths run) but not one; built at import time so a secret scanner
# never sees a key-looking literal in the repo.
FAKE_KEY = 'AIza' + 'Sy' + 'FAKE' * 7 + 'X1234'


def _report(sl, when, headline, summary=''):
    w = datetime.strptime(when, '%Y-%m-%d %H:%M')
    return dict(sl=sl, when=w, date=when, type='Biz News', headline=headline, summary=summary)


REPORTS = [
    _report(1, '2026-10-01 09:00', 'Brent crude surges 8% as Hormuz tensions rise'),
    _report(2, '2026-10-02 09:00', 'RBI hikes repo rate by 25 bps'),
]


# --------------------------------------------------------------------------- configuration


def test_ai_is_off_unless_enabled_and_a_backend_is_given():
    assert Settings.from_env({}).ai.enabled is False
    assert Settings.from_env({'ORBIT_AI_ENABLED': '1'}).ai.enabled is False  # no project, no key
    assert Settings.from_env({'ORBIT_AI_ENABLED': '1', 'GCP_PROJECT': 'p'}).ai.enabled is True
    assert Settings.from_env({'ORBIT_AI_ENABLED': '1', 'GEMINI_API_KEY': FAKE_KEY}).ai.enabled is True


def test_vertex_defaults_to_the_global_endpoint():
    assert Settings.from_env({}).ai.location == 'global'
    assert Settings.from_env({'ORBIT_VERTEX_LOCATION': 'us-central1'}).ai.location == 'us-central1'


def test_the_api_key_is_never_in_a_repr_and_is_masked_for_display():
    ai = Settings.from_env({'ORBIT_AI_ENABLED': '1', 'GEMINI_API_KEY': FAKE_KEY}).ai
    assert FAKE_KEY not in repr(ai)
    assert FAKE_KEY not in repr(ai_settings_from_config(ai))
    assert ai.masked_key == 'AIza…1234'
    assert len(FAKE_KEY) == 39  # same length as a real key, so the mask is representative
    assert Settings.from_env({}).ai.masked_key is None


def test_error_summaries_mask_anything_that_looks_like_a_token():
    line = _summarise(Exception(f'403 denied for key {FAKE_KEY}'), model='m', backend='vertex')
    assert FAKE_KEY not in line
    assert '***' in line


# --------------------------------------------------------------------------- pipeline


def test_pipeline_without_ai_is_the_plain_lexicon_pipeline():
    plain = run_pipeline(REPORTS)
    with_disabled_ai = run_pipeline(REPORTS, ai=ai_settings_from_config(Settings.from_env({}).ai))
    assert plain['events'] == with_disabled_ai['events']
    assert plain['meta']['agents'] == {'enabled': False, 'translated': 0, 'geminiHits': 0, 'briefs': 0}
    assert plain['meta']['briefs'] == {}


def test_a_client_that_is_not_ready_makes_no_calls():
    client = AiClient(ai_settings_from_config(Settings.from_env({}).ai))
    assert client.ready is False
    assert client.generate_text(model='x', prompt='hello') is None
    assert client.translate_to_english('कच्चा तेल') is None


def test_local_search_ranks_by_keyword_overlap():
    events = run_pipeline(REPORTS)['events']
    client = AiClient(ai_settings_from_config(Settings.from_env({}).ai))
    hit = search_events(client, 'crude oil hormuz', events)
    assert hit['engine'] == 'local'
    assert hit['items']
    assert hit['items'][0]['label'] == 'Crude oil price'
    assert search_events(client, '', events)['items'] == []


# --------------------------------------------------------------------------- HTTP


@pytest.fixture
def client(seeded_readonly_app):
    return seeded_readonly_app.test_client()


def test_agents_endpoint_lists_the_catalog_and_hides_the_key(client):
    body = client.get('/api/agents').get_json()
    assert [a['id'] for a in body['agents']] == [a['id'] for a in AGENTS]
    assert body['ai']['enabled'] is False
    assert FAKE_KEY not in client.get('/api/agents').get_data(as_text=True)


def test_chat_requires_a_question(client):
    assert client.post('/api/agents/chat', json={}).status_code == 400


def test_chat_explains_when_ai_is_not_configured(client):
    body = client.post('/api/agents/chat', json={'question': 'What moved crude?'}).get_json()
    assert 'not configured' in body['answer']
    assert body['citations'] == []


def test_search_falls_back_to_keywords(client):
    assert client.get('/api/agents/search').status_code == 400
    body = client.get('/api/agents/search?q=crude').get_json()
    assert body['engine'] == 'local'


def test_brief_is_unavailable_without_ai(client, snapshot):
    code = snapshot['events'][0]['id']
    response = client.post(f'/api/agents/brief/{code}')
    assert response.status_code == 503
    assert client.post('/api/agents/brief/E9999').status_code == 404
