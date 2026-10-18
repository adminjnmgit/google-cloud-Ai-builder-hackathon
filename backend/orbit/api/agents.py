"""The agent endpoints the pages call at request time: status, chat, an on-demand brief, search.

The batch agents (translate, classify, cluster, brief-on-publish) run inside the pipeline, not here.
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, Response, abort, current_app, jsonify, request

from .. import queries, store
from ..agents.brief import brief_event
from ..agents.catalog import AGENTS
from ..agents.chat import answer_question
from ..agents.runtime import client_from_settings
from ..agents.search import search_events
from ..config import Settings
from ..extensions import db
from ..feed_cache import feed_cache
from ..models import PipelineRun
from ..serialize import event_dict

bp = Blueprint('agents', __name__, url_prefix='/agents')

# How much of the feed a question or search gets to see. The newest events come first.
CHAT_CONTEXT_EVENTS = 80
SEARCH_CANDIDATE_EVENTS = 200
SEARCH_MAX_RESULTS = 50


def _settings() -> Settings:
    return current_app.extensions['orbit.settings']


def _active_run() -> PipelineRun:
    run = store.active_run()
    if run is None:
        abort(503, description='No feed has been published yet. Run the pipeline.')
    return run


def _active_events(run: PipelineRun, *, limit: int) -> list[dict[str, Any]]:
    """The newest events as the frontend sees them, with any brief the pipeline already wrote."""
    _total, page = queries.find_events(run, queries.EventFilter(limit=limit))
    briefs = (run.meta or {}).get('briefs') or {}
    out = []
    for event in page:
        row = event_dict(event, with_reports=False)
        if event.code in briefs:
            row['brief'] = briefs[event.code]
        out.append(row)
    return out


@bp.get('')
def list_agents() -> Response:
    ai = _settings().ai
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
    """Answer a question from the published feed only. Body: ``{"question": ..., "sector": ...}``."""
    body = request.get_json(silent=True) or {}
    question = str(body.get('question') or '').strip()
    if not question:
        abort(400, description='question is required')
    sector = str(body.get('sector') or '').strip()
    run = _active_run()
    client = client_from_settings(_settings())
    events = _active_events(run, limit=CHAT_CONTEXT_EVENTS)
    return jsonify(answer_question(client, question=question, sector=sector, events=events))


@bp.post('/brief/<code>')
def brief(code: str) -> Response:
    """Write (or return the stored) brief for one event. Briefs live in the run's meta so a redeploy keeps them."""
    run = _active_run()
    found = queries.find_event(run, code)
    if found is None:
        abort(404, description='No such event')

    briefs = dict((run.meta or {}).get('briefs') or {})
    if code in briefs:
        return jsonify(event=code, brief=briefs[code], cached=True)

    client = client_from_settings(_settings())
    generated = brief_event(event_dict(found, with_reports=False), client)
    if generated is None:
        reason = client.last_error or 'enable ORBIT_AI_ENABLED and set GCP_PROJECT or GEMINI_API_KEY'
        abort(503, description=f'Brief agent is unavailable: {reason}')

    briefs[code] = generated
    run.meta = {**(run.meta or {}), 'briefs': briefs}
    db.session.commit()
    feed_cache.clear()  # /api/data serves briefs inline, so it must be rebuilt
    return jsonify(event=code, brief=generated, cached=False)


@bp.get('/search')
def search() -> Response:
    """Vertex AI Search when a data store is configured; otherwise a keyword match over recent events."""
    query = str(request.args.get('q') or '').strip()
    if not query:
        abort(400, description='q is required')
    try:
        limit = int(request.args.get('limit') or 20)
    except ValueError:
        limit = 20
    limit = min(max(limit, 1), SEARCH_MAX_RESULTS)
    run = _active_run()
    client = client_from_settings(_settings())
    candidates = _active_events(run, limit=SEARCH_CANDIDATE_EVENTS)
    return jsonify(search_events(client, query, candidates, limit=limit))
