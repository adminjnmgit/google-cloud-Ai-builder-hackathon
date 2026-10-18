"""The owner's workspace endpoints.

Identity is an HttpOnly cookie holding a random token. State-changing requests must be JSON, which a
cross-site form cannot send, and the cookie is SameSite=Lax. The rules live in ``orbit.workspaces``.
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, Response, abort, current_app, g, jsonify, request

from .. import workspaces

bp = Blueprint('workspace', __name__, url_prefix='/workspace')

COOKIE = 'orbit_ws'
COOKIE_MAX_AGE = 60 * 60 * 24 * 730  # two years


def _json_body() -> Any:
    if not request.is_json:
        abort(415, description='Send application/json')
    body = request.get_json(silent=True)
    if body is None:
        abort(400, description='Body is not valid JSON')
    return body


@bp.before_request
def _load_workspace() -> None:
    """Find the browser's workspace. Every method but DELETE creates one on first contact."""
    token = request.cookies.get(COOKIE, '')
    workspace = workspaces.find_workspace(token)
    if workspace is None and request.method != 'DELETE':
        workspace = workspaces.create_workspace()
    if workspace is None:
        abort(404, description='No workspace for this browser yet')
    g.workspace = workspace
    g.issue_cookie = workspace.token != token


@bp.after_request
def _issue_cookie(response: Response) -> Response:
    if g.get('issue_cookie'):
        response.set_cookie(
            COOKIE,
            g.workspace.token,
            max_age=COOKIE_MAX_AGE,
            httponly=True,
            samesite='Lax',
            secure=current_app.config['COOKIE_SECURE'],
        )
    return response


@bp.get('')
def snapshot() -> Response:
    response = jsonify(workspaces.snapshot(g.workspace))
    response.headers['Cache-Control'] = 'no-store'
    return response


@bp.put('/sector')
def put_sector() -> Response:
    body = _json_body()
    sector = workspaces.set_sector(g.workspace, body.get('sector') if isinstance(body, dict) else None)
    return jsonify(sector=sector)


@bp.put('/profile/<sector>')
def put_profile(sector: str) -> Response:
    profile = workspaces.save_profile(g.workspace, sector, _json_body())
    return jsonify(sector=sector, profile=profile)


@bp.put('/tasks/<sector>')
def put_tasks(sector: str) -> Response:
    return jsonify(sector=sector, tasks=workspaces.replace_tasks(g.workspace, sector, _json_body()))


@bp.delete('/<sector>')
def reset_sector(sector: str) -> tuple[str, int]:
    """?part=profile|tasks|all (default all)."""
    workspaces.reset(g.workspace, sector, request.args.get('part', 'all'))
    return '', 204
