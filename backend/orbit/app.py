"""Application factory.

Building the app only wires components together. It never touches the database: creating the schema,
migrating it and loading data are explicit steps (``flask orbit init-db``, ``flask orbit seed``,
``flask orbit pipeline run``).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from dotenv import load_dotenv
from flask import Flask

from . import models  # noqa: F401  (registers the tables on the metadata)
from .api import api
from .cli import register_cli
from .config import BACKEND_DIR, Settings
from .extensions import db, migrate
from .web import frontend, register_error_handlers, register_hooks

MIGRATIONS_DIR = BACKEND_DIR / 'migrations'
LOG_FORMAT = '%(asctime)s %(levelname)-7s %(name)s: %(message)s'


def configure_logging(debug: bool) -> None:
    """One consistent format for the whole process, unless the host already configured logging."""
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=logging.DEBUG if debug else logging.INFO, format=LOG_FORMAT)


def create_app(settings: Settings | None = None, overrides: Mapping[str, Any] | None = None) -> Flask:
    """Build the app. ``settings`` defaults to the environment (and backend/.env); ``overrides`` is for tests."""
    if settings is None:
        load_dotenv(BACKEND_DIR / '.env')
        settings = Settings.from_env()
    configure_logging(settings.debug)

    app = Flask(__name__, static_folder=None)
    app.config.from_mapping(settings.to_flask())
    if overrides:
        app.config.update(overrides)
    app.extensions['orbit.settings'] = settings
    app.json.sort_keys = False
    app.json.ensure_ascii = False

    db.init_app(app)
    migrate.init_app(app, db, directory=str(MIGRATIONS_DIR))

    app.register_blueprint(api)
    app.register_blueprint(frontend)
    register_error_handlers(app)
    register_hooks(app)
    register_cli(app)
    return app
