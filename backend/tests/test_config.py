import pytest

from orbit.config import DatabaseSettings, Settings
from orbit.errors import ConfigError


def test_defaults_point_at_the_local_xampp_database():
    settings = Settings.from_env({})
    db = settings.database
    assert (db.host, db.port, db.user, db.password, db.name) == ('127.0.0.1', 3306, 'root', '', 'jagran_orbit')
    assert settings.keep_runs == 3
    assert settings.use_machine_translations is False
    assert settings.source_table == 'jagran_biz'


def test_the_url_is_mysql_only_and_escapes_the_password():
    url = DatabaseSettings.from_env({'MYSQL_PASSWORD': 'p@ss/word:1', 'MYSQL_DATABASE': 'orbit_x'}).url()
    assert url.drivername == 'mysql+pymysql'
    assert url.password == 'p@ss/word:1'
    assert '@127.0.0.1' in url.render_as_string(hide_password=False)  # the "@" in the password is percent-encoded
    assert url.database == 'orbit_x'
    assert DatabaseSettings.from_env({}).url(with_database=False).database is None
    hyphen = DatabaseSettings.from_env({'MYSQL_DATABASE': 'example-prod-db'})
    assert hyphen.name == 'example-prod-db'


def test_cloud_sql_unix_socket_replaces_host_and_port():
    url = DatabaseSettings.from_env(
        {
            'MYSQL_USER': 'app',
            'MYSQL_PASSWORD': 's3cret',
            'MYSQL_DATABASE': 'example-prod-db',
            'CLOUD_SQL_CONNECTION_NAME': 'proj:asia-south1:orbit',
        }
    ).url()
    assert url.host is None
    assert url.port is None
    assert url.query['unix_socket'] == '/cloudsql/proj:asia-south1:orbit'


@pytest.mark.parametrize(
    'env',
    [
        {'MYSQL_PORT': 'abc'},
        {'MYSQL_PORT': '0'},
        {'ORBIT_KEEP_RUNS': '0'},
        {'MYSQL_DATABASE': 'bad`name; DROP DATABASE x'},
        {'ORBIT_SOURCE_TABLE': 'jagran_biz; DROP TABLE x'},
    ],
)
def test_bad_values_fail_fast_with_a_clear_error(env):
    with pytest.raises(ConfigError):
        Settings.from_env(env)


@pytest.mark.parametrize(
    ('raw', 'expected'), [('1', True), ('true', True), ('YES', True), ('0', False), ('', False), ('no', False)]
)
def test_flags(raw, expected):
    assert Settings.from_env({'ORBIT_USE_MACHINE_TRANSLATIONS': raw}).use_machine_translations is expected


def test_flask_config_carries_the_connection_uri():
    config = Settings.from_env({'MYSQL_DATABASE': 'orbit_x'}).to_flask()
    assert config['SQLALCHEMY_DATABASE_URI'].startswith('mysql+pymysql://root@127.0.0.1:3306/orbit_x')
