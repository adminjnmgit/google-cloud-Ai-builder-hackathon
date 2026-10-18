"""Read-only feed endpoints: the data the owner, analyst and compare pages render."""

from __future__ import annotations

from flask import Blueprint, Response, abort, jsonify, request
from sqlalchemy import select

from .. import queries, store
from ..agents.catalog import AGENTS
from ..extensions import db
from ..feed_cache import feed_cache
from ..models import PipelineRun, iso
from ..serialize import event_dict

bp = Blueprint('feed', __name__)


def _active_run() -> PipelineRun:
    run = store.active_run()
    if run is None:
        abort(503, description='No feed has been published yet. Run the pipeline.')
    return run


@bp.get('/health')
def health() -> Response:
    run = store.active_run()
    db.session.execute(select(1))
    feed = None
    if run is not None:
        feed = {'run': run.id, 'source': run.source, 'events': run.events_out, 'refreshed': iso(run.finished_at)}
    return jsonify(status='ok', database=db.engine.dialect.name, feed=feed, agents=len(AGENTS))


@bp.get('/data')
def data() -> Response:
    """The complete feed in the shape the frontend has always used (``window.ORBIT_DATA``)."""
    payload = feed_cache.get(_active_run())
    if request.if_none_match.contains(payload.etag.strip('"')):
        response = Response(status=304)
    elif 'gzip' in request.headers.get('Accept-Encoding', ''):
        response = Response(payload.gzipped, mimetype='application/json')
        response.headers['Content-Encoding'] = 'gzip'
    else:
        response = Response(payload.body, mimetype='application/json')
    response.headers['Vary'] = 'Accept-Encoding'
    response.headers['ETag'] = payload.etag
    response.headers['Cache-Control'] = 'no-cache'
    return response


@bp.get('/events')
def events() -> Response:
    run = _active_run()
    flt = queries.EventFilter.from_args(request.args)
    total, page = queries.find_events(run, flt)
    return jsonify(
        total=total,
        limit=flt.limit,
        offset=flt.offset,
        items=[event_dict(e, with_reports=flt.include_reports) for e in page],
    )


@bp.get('/events/<code>')
def event(code: str) -> Response:
    found = queries.find_event(_active_run(), code)
    if found is None:
        abort(404, description='No such event')
    return jsonify(event_dict(found))


@bp.get('/stats')
def stats() -> Response:
    return jsonify(queries.event_stats(_active_run()))
