"""The JSON API, mounted under /api. Errors are rendered as JSON by the handlers in ``orbit.web``."""

from flask import Blueprint

from . import admin, feed, workspace

api = Blueprint('api', __name__, url_prefix='/api')
api.register_blueprint(feed.bp)
api.register_blueprint(workspace.bp)
api.register_blueprint(admin.bp)
