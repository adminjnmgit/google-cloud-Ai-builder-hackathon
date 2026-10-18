"""The owner's workspace: sector, business profile and action list, kept per browser."""

from urllib.parse import quote

import pytest

from orbit.pipeline.lexicon import INDUSTRIES

PROFILE = {
    'company': 'Medivista', 'industry': 'Generic', 'location': 'Ahmedabad', 'revenue': 70, 'margin': 14,
    'passThrough': 25, 'loans': 120, 'materials': 35, 'freight': 6, 'power': 5, 'imports': 25, 'exports': 30,
}  # fmt: skip
TASKS = [
    {'id': 'a0_E0003', 'title': 'Review US tariff exposure', 'owner': 'Finance', 'due': 'Today', 'signal': 'E0003', 'done': False},
    {'id': 't1', 'title': 'Call supplier', 'owner': 'Ops', 'due': 'This week', 'signal': '', 'done': True},
]  # fmt: skip


def test_workspace_round_trip(client):
    snapshot = client.get('/api/workspace')
    assert snapshot.get_json() == {'sector': 'Automotive', 'profiles': {}, 'tasks': {}}
    cookie = snapshot.headers['Set-Cookie']
    assert 'HttpOnly' in cookie
    assert 'SameSite=Lax' in cookie

    assert client.put('/api/workspace/sector', json={'sector': 'Pharma'}).status_code == 200
    assert client.put('/api/workspace/profile/Pharma', json=PROFILE).status_code == 200
    assert client.put('/api/workspace/tasks/Pharma', json=TASKS).status_code == 200

    snapshot = client.get('/api/workspace').get_json()
    assert snapshot['sector'] == 'Pharma'
    assert snapshot['profiles']['Pharma']['company'] == 'Medivista'
    assert snapshot['tasks']['Pharma'] == TASKS  # order and done flags preserved


def test_the_cookie_is_only_issued_once(client):
    assert 'Set-Cookie' in client.get('/api/workspace').headers
    assert 'Set-Cookie' not in client.get('/api/workspace').headers


def test_workspaces_are_isolated_between_browsers(app):
    one, other = app.test_client(), app.test_client()
    one.get('/api/workspace')
    one.put('/api/workspace/profile/Energy', json=PROFILE)
    assert other.get('/api/workspace').get_json()['profiles'] == {}


def test_tasks_are_replaced_not_appended(client):
    client.put('/api/workspace/tasks/Banking', json=TASKS)
    client.put('/api/workspace/tasks/Banking', json=TASKS[:1])
    assert client.get('/api/workspace').get_json()['tasks']['Banking'] == TASKS[:1]


def test_reset_can_target_profile_or_tasks(client):
    client.put('/api/workspace/profile/Energy', json=PROFILE)
    client.put('/api/workspace/tasks/Energy', json=TASKS)
    assert client.delete('/api/workspace/Energy?part=profile').status_code == 204
    snapshot = client.get('/api/workspace').get_json()
    assert 'Energy' not in snapshot['profiles']
    assert len(snapshot['tasks']['Energy']) == 2

    client.delete('/api/workspace/Energy')
    assert 'Energy' not in client.get('/api/workspace').get_json()['tasks']
    assert client.delete('/api/workspace/Energy?part=x').status_code == 400


def test_reset_without_a_workspace_is_a_404(client):
    assert client.delete('/api/workspace/Energy').status_code == 404


@pytest.mark.parametrize(
    ('method', 'url', 'payload'),
    [
        ('put', '/api/workspace/sector', {'sector': 'Mining'}),
        ('put', '/api/workspace/profile/Nope', PROFILE),
        ('put', '/api/workspace/tasks/Nope', TASKS),
    ],
)
def test_unknown_sector_is_a_404(client, method, url, payload):
    client.get('/api/workspace')
    assert getattr(client, method)(url, json=payload).status_code == 404


@pytest.mark.parametrize(
    'profile',
    [
        {**PROFILE, 'materials': 80, 'freight': 30},  # cost shares total over 100
        {**PROFILE, 'margin': 95},
        {**PROFILE, 'revenue': 'lots'},
        {**PROFILE, 'revenue': True},  # a bool is not a number
        {**PROFILE, 'revenue': -1},
        {**PROFILE, 'company': 7},
        [1],
    ],
)
def test_invalid_profiles_are_rejected(client, profile):
    client.get('/api/workspace')
    assert client.put('/api/workspace/profile/Pharma', json=profile).status_code == 400


@pytest.mark.parametrize(
    'tasks',
    [{'a': 1}, [{'id': 'x'}], [TASKS[0], TASKS[0]], [{'title': ' '}], 'text', [{'title': 't'}] * 501],
)
def test_invalid_task_lists_are_rejected(client, tasks):
    client.get('/api/workspace')
    assert client.put('/api/workspace/tasks/Pharma', json=tasks).status_code == 400


def test_bodies_must_be_json(client):
    client.get('/api/workspace')
    assert client.put('/api/workspace/tasks/Pharma', data='x', content_type='text/plain').status_code == 415
    assert client.put('/api/workspace/tasks/Pharma', data='{bad', content_type='application/json').status_code == 400


def test_profile_drops_unknown_fields_and_truncates_text(client):
    body = client.put('/api/workspace/profile/Pharma', json={**PROFILE, 'evil': '<x>', 'company': 'A' * 500}).get_json()
    assert 'evil' not in body['profile']
    assert len(body['profile']['company']) == 160


def test_a_forged_token_is_not_accepted(app):
    client = app.test_client()
    client.set_cookie('orbit_ws', 'x' * 43)
    snapshot = client.get('/api/workspace')
    assert snapshot.get_json()['profiles'] == {}
    assert 'Set-Cookie' in snapshot.headers  # a new workspace and token were issued instead


@pytest.mark.parametrize('sector', INDUSTRIES)
def test_every_sector_can_hold_a_workspace(client, sector):
    """Sector names such as "FMCG & Food" travel in the URL, so they must survive encoding."""
    client.get('/api/workspace')
    name = quote(sector, safe='')
    assert client.put('/api/workspace/sector', json={'sector': sector}).status_code == 200
    assert client.put(f'/api/workspace/profile/{name}', json=PROFILE).status_code == 200
    assert client.put(f'/api/workspace/tasks/{name}', json=TASKS).status_code == 200

    snapshot = client.get('/api/workspace').get_json()
    assert snapshot['sector'] == sector
    assert snapshot['profiles'][sector]['company'] == 'Medivista'
    assert snapshot['tasks'][sector] == TASKS
    assert client.delete(f'/api/workspace/{name}').status_code == 204
