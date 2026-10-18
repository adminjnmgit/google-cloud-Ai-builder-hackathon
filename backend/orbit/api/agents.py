"""Live AI agent endpoints: status, chat, on-demand brief, search."""

from __future__ import annotations

from flask import Blueprint, Response, abort, current_app, jsonify, request

from .. import queries, store
from ..agents.brief import brief_event
from ..agents.catalog import AGENTS
from ..agents.chat import answer_question
from ..agents.runtime import client_from_settings
from ..agents.search import search_events
from ..serialize import event_dict

bp = Blueprint('agents', __name__, url_prefix='/agents')


def _settings():
    return current_app.extensions['orbit.settings']


def _active_events(*, limit: int = 80) -> list[dict]:
    run = store.active_run()
    if run is None:
        abort(503, description='No feed has been published yet. Run the pipeline.')
    flt = queries.EventFilter(limit=limit, offset=0, include_reports=False)
    _total, page = queries.find_events(run, flt)
    meta_briefs = (run.meta or {}).get('briefs') or {}
    out = []
    for event in page:
        row = event_dict(event, with_reports=False)
        if event.code in meta_briefs:
            row['brief'] = meta_briefs[event.code]
        out.append(row)
    return out


@bp.get('')
def list_agents() -> Response:
    settings = _settings()
    ai = settings.ai
    return jsonify(
        agents=AGENTS,
        ai={
            'enabled': ai.enabled,
            'backend': 'gemini-api' if ai.api_key else 'vertex',
            'apiKey': ai.masked_key,  # masked; the real key never leaves the server
            'project': ai.project or None,
            'location': ai.location,
            'flashModel': ai.flash_model,
            'liteModel': ai.lite_model,
            'proModel': ai.pro_model,
            'translate': ai.translate_enabled,
            'classify': ai.classify_enabled,
            'cluster': ai.cluster_enabled,
            'brief': ai.brief_enabled,
            'searchDataStore': ai.search_data_store or None,
        },
    )


@bp.post('/chat')
def chat() -> Response:
    body = request.get_json(silent=True) or {}
    question = str(body.get('question') or '').strip()
    if not question:
        abort(400, description='question is required')
    sector = str(body.get('sector') or '').strip()
    client = client_from_settings(_settings())
    result = answer_question(client, question=question, sector=sector, events=_active_events())
    return jsonify(result)


@bp.post('/brief/<code>')
def brief(code: str) -> Response:
    run = store.active_run()
    if run is None:
        abort(503, description='No feed has been published yet. Run the pipeline.')
    found = queries.find_event(run, code)
    if found is None:
        abort(404, description='No such event')
    cached = ((run.meta or {}).get('briefs') or {}).get(code)
    if cached:
        return jsonify(event=code, brief=cached, cached=True)
    client = client_from_settings(_settings())
    row = event_dict(found, with_reports=False)
    generated = brief_event(row, client)
    if generated is None:
        abort(503, description='Brief agent is unavailable (enable ORBIT_AI_ENABLED and GCP_PROJECT)')
    meta = dict(run.meta or {})
    briefs = dict(meta.get('briefs') or {})
    briefs[code] = generated
    meta['briefs'] = briefs
    run.meta = meta
    from ..extensions import db
    from ..feed_cache import feed_cache

    db.session.commit()
    feed_cache.clear()
    return jsonify(event=code, brief=generated, cached=False)


@bp.get('/search')
def search() -> Response:
    query = str(request.args.get('q') or '').strip()
    if not query:
        abort(400, description='q is required')
    try:
        limit = min(max(int(request.args.get('limit') or 20), 1), 50)
    except ValueError:
        limit = 20
    client = client_from_settings(_settings())
    return jsonify(search_events(client, query, _active_events(limit=200), limit=limit))
