"""Operational helpers for the one MySQL database: create it, and check it is ready to serve."""

from __future__ import annotations

from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from flask_migrate import upgrade
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from .config import DatabaseSettings
from .errors import DatabaseNotReady
from .extensions import db, migrate

INIT_HINT = 'Run `flask --app wsgi orbit init-db` first.'


def create_database(settings: DatabaseSettings) -> bool:
    """Create the MySQL schema if it does not exist. Returns True when it was created just now."""
    engine = create_engine(settings.url(with_database=False), isolation_level='AUTOCOMMIT')
    try:
        with engine.connect() as conn:
            exists = (
                conn.execute(
                    text('SELECT 1 FROM information_schema.schemata WHERE schema_name = :name'),
                    {'name': settings.name},
                ).first()
                is not None
            )
            if not exists:
                # `name` was validated as a plain identifier when the settings were read.
                conn.execute(
                    text(f'CREATE DATABASE `{settings.name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
                )
            return not exists
    except SQLAlchemyError as error:
        raise DatabaseNotReady(
            f'Cannot reach MySQL at {settings.host}:{settings.port}: {error.__cause__ or error}'
        ) from error
    finally:
        engine.dispose()


def migrate_to_head() -> None:
    """Apply every pending Alembic migration. Needs an application context."""
    upgrade()


def schema_revisions() -> tuple[str | None, str | None]:
    """(revision the database is at, latest revision in the code). Needs an application context."""
    head = ScriptDirectory.from_config(migrate.get_config()).get_current_head()
    with db.engine.connect() as conn:
        current = MigrationContext.configure(conn).get_current_revision()
    return current, head


def ensure_ready() -> None:
    """Raise DatabaseNotReady unless MySQL answers and the schema is at the latest migration."""
    try:
        current, head = schema_revisions()
    except SQLAlchemyError as error:
        raise DatabaseNotReady(f'MySQL is not usable: {error.__cause__ or error}. {INIT_HINT}') from error
    if current != head:
        raise DatabaseNotReady(
            f'The database schema is at {current or "nothing"}, the code expects {head}. {INIT_HINT}'
        )
