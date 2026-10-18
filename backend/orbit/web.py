"""The HTTP layer around the API: the three frontend pages, JSON error responses and response headers."""

from __future__ import annotations

import gzip
import logging

from flask import Blueprint, Flask, Response, current_app, jsonify, redirect, request, send_from_directory
from werkzeug.exceptions import HTTPException

from .errors import ClientError, DatabaseNotReady, NoEventsProduced, PipelineBusy, SourceError
from .extensions import db

log = logging.getLogger(__name__)

# Pages served from the frontend folder, and the default file of each.
PAGES = {'owner': 'index.html', 'analyst': 'orbit-dashboard.html', 'compare': 'orbit-compare.html'}
GZIP_MIN_BYTES = 1024

frontend = Blueprint('frontend', __name__)


def _frontend_root():
    return current_app.config['FRONTEND_DIR']


@frontend.get('/')
def home() -> Response:
    return redirect('/owner/')


@frontend.get('/favicon.ico')
def favicon() -> tuple[str, int]:
    return '', 204


@frontend.get('/<page>/')
def page_index(page: str) -> Response:
    if page not in PAGES:
        return jsonify(error='Not Found', message='No such page'), 404
    return send_from_directory(_frontend_root() / page, PAGES[page])


@frontend.get('/<path:path>')
def static_file(path: str) -> Response:
    return send_from_directory(_frontend_root(), path)


def _wants_json() -> bool:
    return request.path.startswith('/api/')


def _error(status: int, name: str, message: str) -> Response:
    response = jsonify(error=name, message=message)
    response.status_code = status
    return response


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(HTTPException)
    def http_error(error: HTTPException):
        if _wants_json():
            return _error(error.code or 500, error.name, error.description or '')
        return error

    @app.errorhandler(ClientError)
    def client_error(error: ClientError):
        return _error(error.status, 'Not Found' if error.status == 404 else 'Bad Request', str(error))

    @app.errorhandler(PipelineBusy)
    def busy(error: PipelineBusy):
        return _error(409, 'Conflict', str(error))

    @app.errorhandler(SourceError)
    @app.errorhandler(NoEventsProduced)
    def unprocessable(error: Exception):
        return _error(422, 'Unprocessable Entity', str(error))

    @app.errorhandler(DatabaseNotReady)
    def database_not_ready(error: DatabaseNotReady):
        log.error('%s', error)
        return _error(503, 'Service Unavailable', 'The database is not ready')

    @app.errorhandler(Exception)
    def unexpected(error: Exception):
        log.exception('Unhandled error on %s', request.path)
        db.session.rollback()
        if _wants_json():
            return _error(500, 'Internal Server Error', 'Something went wrong on the server')
        return 'Internal Server Error', 500


def _compressible(response: Response) -> bool:
    return bool(
        response.mimetype == 'application/json'
        and not response.direct_passthrough
        and response.status_code == 200
        and 'gzip' in request.headers.get('Accept-Encoding', '')
        and (response.content_length or 0) > GZIP_MIN_BYTES
        and 'Content-Encoding' not in response.headers
    )


def register_hooks(app: Flask) -> None:
    @app.after_request
    def finish(response: Response) -> Response:
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('Referrer-Policy', 'same-origin')
        if _compressible(response):
            response.set_data(gzip.compress(response.get_data(), compresslevel=5))
            response.headers['Content-Encoding'] = 'gzip'
            response.headers['Vary'] = 'Accept-Encoding'
        return response

    @app.teardown_appcontext
    def release_session(_exc: BaseException | None) -> None:
        db.session.remove()
