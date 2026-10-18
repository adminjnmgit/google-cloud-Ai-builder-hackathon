"""Configuration, read once from environment variables (optionally from backend/.env).

There is exactly one database: the MySQL schema named by ``MYSQL_DATABASE``. Everything the application
owns lives in tables prefixed ``orbit_`` beside the newsroom tables (``jagran_biz`` and friends).
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import URL

from .errors import ConfigError

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent

# Letters, digits, underscore and hyphen. Hyphen is allowed so Cloud SQL names such as `example-prod-db` work.
# Always interpolated inside backticks, so a hyphen cannot break out of the identifier.
_IDENTIFIER = re.compile(r'^[A-Za-z_][A-Za-z0-9_-]*$')
_TRUE = frozenset({'1', 'true', 'yes', 'on'})


def _text(env: Mapping[str, str], name: str, default: str = '') -> str:
    return env.get(name, default).strip()


def _flag(env: Mapping[str, str], name: str, default: bool = False) -> bool:
    return _text(env, name, '1' if default else '0').lower() in _TRUE


def _int(env: Mapping[str, str], name: str, default: int, *, minimum: int = 0) -> int:
    raw = _text(env, name, str(default))
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f'{name} must be a whole number, got {raw!r}') from None
    if value < minimum:
        raise ConfigError(f'{name} must be at least {minimum}, got {value}')
    return value


def _identifier(env: Mapping[str, str], name: str, default: str) -> str:
    value = _text(env, name, default)
    if not _IDENTIFIER.match(value):
        raise ConfigError(f'{name} must be a plain MySQL identifier (letters, digits, underscore), got {value!r}')
    return value


@dataclass(frozen=True, slots=True)
class DatabaseSettings:
    """Connection details for the one MySQL database."""

    host: str
    port: int
    user: str
    password: str
    name: str
    unix_socket: str

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> DatabaseSettings:
        socket = _text(env, 'MYSQL_UNIX_SOCKET')
        if not socket:
            connection = _text(env, 'CLOUD_SQL_CONNECTION_NAME')
            if connection:
                socket = f'/cloudsql/{connection}'
        return cls(
            host=_text(env, 'MYSQL_HOST', '127.0.0.1'),
            port=_int(env, 'MYSQL_PORT', 3306, minimum=1),
            user=_text(env, 'MYSQL_USER', 'root'),
            password=env.get('MYSQL_PASSWORD', ''),
            name=_identifier(env, 'MYSQL_DATABASE', 'jagran_orbit'),
            unix_socket=socket,
        )

    def url(self, *, with_database: bool = True) -> URL:
        """SQLAlchemy URL. ``with_database=False`` connects to the server only (used to create the schema)."""
        query = {'charset': 'utf8mb4'}
        if self.unix_socket:
            query['unix_socket'] = self.unix_socket
        return URL.create(
            'mysql+pymysql',
            username=self.user,
            password=self.password or None,
            host=None if self.unix_socket else self.host,
            port=None if self.unix_socket else self.port,
            database=self.name if with_database else None,
            query=query,
        )


@dataclass(frozen=True, slots=True)
class Settings:
    database: DatabaseSettings
    admin_token: str
    source_table: str
    source_csv: str
    use_machine_translations: bool
    frontend_dir: Path
    seed_file: Path
    keep_runs: int
    max_upload_mb: int
    cookie_secure: bool
    debug: bool

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        frontend_dir = Path(_text(env, 'ORBIT_FRONTEND_DIR') or ROOT_DIR / 'frontend')
        return cls(
            database=DatabaseSettings.from_env(env),
            admin_token=_text(env, 'ORBIT_ADMIN_TOKEN'),
            source_table=_identifier(env, 'ORBIT_SOURCE_TABLE', 'jagran_biz'),
            source_csv=_text(env, 'ORBIT_SOURCE_CSV'),
            use_machine_translations=_flag(env, 'ORBIT_USE_MACHINE_TRANSLATIONS'),
            frontend_dir=frontend_dir,
            seed_file=Path(_text(env, 'ORBIT_SEED_FILE') or frontend_dir / 'owner' / 'data' / 'events.json'),
            keep_runs=_int(env, 'ORBIT_KEEP_RUNS', 3, minimum=1),
            max_upload_mb=_int(env, 'ORBIT_MAX_UPLOAD_MB', 80, minimum=1),
            cookie_secure=_flag(env, 'ORBIT_COOKIE_SECURE'),
            debug=_flag(env, 'FLASK_DEBUG'),
        )

    def to_flask(self) -> dict[str, object]:
        """The subset the Flask app reads through ``app.config``."""
        return {
            'SQLALCHEMY_DATABASE_URI': self.database.url().render_as_string(hide_password=False),
            'SQLALCHEMY_ENGINE_OPTIONS': {'pool_pre_ping': True, 'pool_recycle': 280},
            'MAX_CONTENT_LENGTH': self.max_upload_mb * 1024 * 1024,
            'ADMIN_TOKEN': self.admin_token,
            'SOURCE_TABLE': self.source_table,
            'SOURCE_CSV': self.source_csv,
            'USE_MACHINE_TRANSLATIONS': self.use_machine_translations,
            'FRONTEND_DIR': self.frontend_dir,
            'SEED_FILE': self.seed_file,
            'KEEP_RUNS': self.keep_runs,
            'COOKIE_SECURE': self.cookie_secure,
            'DEBUG': self.debug,
        }
