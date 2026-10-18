"""Test fixtures.

The suite runs against the same MySQL server as the application, but in its own schema (``jagran_orbit_test``
by default, rebuilt from the Alembic migrations at the start of every session). The schema name must end in
``_test``: the suite refuses to run otherwise, so it can never touch the real ``jagran_orbit`` data.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from dotenv import load_dotenv
from flask import Flask
from sqlalchemy import create_engine, text

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / '.env')  # the developer's MySQL host and credentials
# Tests always use a local `_test` schema. Never inherit the production Cloud SQL host from `.env`.
os.environ['MYSQL_HOST'] = os.environ.get('MYSQL_TEST_HOST', '127.0.0.1')
os.environ['MYSQL_PORT'] = os.environ.get('MYSQL_TEST_PORT', '3306')
os.environ['MYSQL_USER'] = os.environ.get('MYSQL_TEST_USER', 'root')
os.environ['MYSQL_PASSWORD'] = os.environ.get('MYSQL_TEST_PASSWORD', '')
os.environ['MYSQL_DATABASE'] = os.environ.get('MYSQL_TEST_DATABASE', 'jagran_orbit_test')

from orbit import create_app, runs  # noqa: E402
from orbit.config import Settings  # noqa: E402
from orbit.database import create_database, migrate_to_head  # noqa: E402
from orbit.extensions import db  # noqa: E402
from orbit.feed_cache import feed_cache  # noqa: E402

SEED_FILE = BACKEND_DIR / 'tests' / 'fixtures' / 'seed.json'
SEEDED_EVENTS = 3
SEEDED_REPORTS = 3


def _settings() -> Settings:
    """Settings for the test schema, ignoring any admin token or feature flags in the developer's environment."""
    env = {k: v for k, v in os.environ.items() if k.startswith('MYSQL_')}
    settings = Settings.from_env(env)
    if not settings.database.name.endswith('_test'):
        pytest.exit(f'Refusing to run: test schema {settings.database.name!r} must end in "_test"', returncode=2)
    return settings


@pytest.fixture(scope='session')
def settings() -> Settings:
    return _settings()


@pytest.fixture(scope='session', autouse=True)
def schema(settings: Settings) -> None:
    """A brand-new test schema built by the migrations (which therefore get exercised on every run)."""
    engine = create_engine(settings.database.url(with_database=False), isolation_level='AUTOCOMMIT')
    with engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS `{settings.database.name}`'))
    engine.dispose()
    create_database(settings.database)
    app = create_app(settings, {'TESTING': True})
    with app.app_context():
        migrate_to_head()
        db.engine.dispose()


def _clean(app: Flask) -> None:
    """Empty every table, and drop the newsroom stand-in a previous test may have created."""
    with app.app_context(), db.engine.begin() as conn:
        conn.execute(text('SET FOREIGN_KEY_CHECKS = 0'))
        conn.execute(text('DROP TABLE IF EXISTS jagran_biz'))
        for table in db.metadata.sorted_tables:
            conn.execute(text(f'TRUNCATE TABLE `{table.name}`'))
        conn.execute(text('SET FOREIGN_KEY_CHECKS = 1'))
    feed_cache.clear()


@pytest.fixture
def app(settings: Settings) -> Iterator[Flask]:
    """An app on an empty database."""
    app = create_app(settings, {'TESTING': True})
    _clean(app)
    yield app
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.fixture
def seeded_app(app: Flask) -> Flask:
    """An app whose active feed is the synthetic test snapshot (3 events from 3 reports)."""
    with app.app_context():
        runs.seed_from_file(SEED_FILE)
    return app


@pytest.fixture(scope='module')
def seeded_readonly_app(settings: Settings) -> Iterator[Flask]:
    """The seeded app, built once per test module. Only for modules whose tests never write."""
    app = create_app(settings, {'TESTING': True})
    _clean(app)
    with app.app_context():
        runs.seed_from_file(SEED_FILE)
    yield app
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.fixture
def client(app: Flask):
    return app.test_client()


@pytest.fixture
def seeded_client(seeded_app: Flask):
    return seeded_app.test_client()


@pytest.fixture(scope='session')
def snapshot() -> dict:
    return json.loads(SEED_FILE.read_text(encoding='utf-8'))
