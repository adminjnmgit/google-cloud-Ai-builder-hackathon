"""Pipeline control.

Protected by ORBIT_ADMIN_TOKEN (header ``X-Admin-Token`` or ``Authorization: Bearer``). With no token
configured, only requests from the same machine are accepted.
"""

from __future__ import annotations

import hmac
import io

from flask import Blueprint, Response, abort, current_app, jsonify, request
from sqlalchemy import select

from .. import runs
from ..enums import Source
from ..extensions import db
from ..models import PipelineRun

bp = Blueprint('admin', __name__, url_prefix='/admin')

LOOPBACK = frozenset({'127.0.0.1', '::1'})
RUNS_LISTED = 25


@bp.before_request
def _authorise() -> None:
    token = current_app.config['ADMIN_TOKEN']
    if not token:
        if request.remote_addr not in LOOPBACK:
            abort(403, description='Set ORBIT_ADMIN_TOKEN to use admin endpoints remotely')
        return
    given = (
        request.headers.get('X-Admin-Token') or request.headers.get('Authorization', '').removeprefix('Bearer ').strip()
    )
    if not hmac.compare_digest(given.encode(), token.encode()):
        abort(401, description='Admin token required')


@bp.get('/pipeline/runs')
def list_runs() -> Response:
    rows = db.session.scalars(select(PipelineRun).order_by(PipelineRun.id.desc()).limit(RUNS_LISTED)).all()
    return jsonify(runs=[row.to_dict() for row in rows])


@bp.post('/pipeline/run')
def start_run() -> tuple[Response, int]:
    """Run on ``{"source": "jagran_biz"}``, ``{"source": "csv", "path": "..."}``, or a multipart upload in ``file``."""
    if 'file' in request.files:
        upload = request.files['file']
        handle = io.TextIOWrapper(upload.stream, encoding='utf-8-sig', newline='')
        run = runs.execute(Source.UPLOAD, fileobj=handle, detail=upload.filename or 'upload')
    else:
        body = request.get_json(silent=True) or {}
        source = body.get('source', Source.JAGRAN_BIZ)
        if source not in Source.runnable():
            abort(400, description='source must be jagran_biz or csv (or upload a file)')
        run = runs.execute(source, csv_path=body.get('path'))
    return jsonify(run.to_dict()), 201
