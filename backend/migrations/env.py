"""Alembic environment, driven by Flask-Migrate: the connection and the metadata come from the Flask app.

Which objects are managed (only ``orbit_*`` tables) is decided by ``orbit.extensions.include_object``.
"""

import logging
from logging.config import fileConfig

from alembic import context
from flask import current_app

config = context.config
fileConfig(config.config_file_name)
logger = logging.getLogger('alembic.env')

migrate_ext = current_app.extensions['migrate']
db = migrate_ext.db
config.set_main_option('sqlalchemy.url', db.engine.url.render_as_string(hide_password=False).replace('%', '%%'))


def skip_empty_revision(context, revision, directives):
    """Do not write a migration file when autogenerate found no schema changes."""
    if getattr(config.cmd_opts, 'autogenerate', False) and directives[0].upgrade_ops.is_empty():
        directives[:] = []
        logger.info('No changes in schema detected.')


def configure_args():
    args = dict(migrate_ext.configure_args)
    args.setdefault('process_revision_directives', skip_empty_revision)
    return args


def run_migrations_offline():
    """Emit the SQL to the console instead of running it (``flask db upgrade --sql``)."""
    context.configure(
        url=config.get_main_option('sqlalchemy.url'),
        target_metadata=db.metadata,
        literal_binds=True,
        **configure_args(),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    with db.engine.connect() as connection:
        context.configure(connection=connection, target_metadata=db.metadata, **configure_args())
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
