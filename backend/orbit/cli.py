"""Command line: ``flask --app wsgi orbit ...``

flask --app wsgi orbit init-db            create the MySQL database if needed and apply migrations
flask --app wsgi orbit pipeline run       build the event feed from the newsroom table
flask --app wsgi orbit export-seed        rebuild the bundled events.json / events.js snapshot
flask --app wsgi db migrate / upgrade     schema migrations (Flask-Migrate)
"""

from __future__ import annotations

import click
from flask import Flask, current_app
from flask.cli import AppGroup
from sqlalchemy import select

from . import database, runs
from .config import Settings
from .enums import Source
from .errors import OrbitError
from .extensions import db
from .models import PipelineRun

orbit = AppGroup('orbit', help='Jagran Orbit database and pipeline commands.')
pipeline = AppGroup('pipeline', help='Build the event feed from reports.')
orbit.add_command(pipeline)

RUNS_SHOWN = 15


def _fail(error: Exception) -> click.ClickException:
    return click.ClickException(str(error))


def register_cli(app: Flask) -> None:
    app.cli.add_command(orbit)


@orbit.command('init-db')
def init_db() -> None:
    """Create the MySQL database if it is missing, then apply all schema migrations."""
    settings: Settings = current_app.extensions['orbit.settings']
    try:
        created = database.create_database(settings.database)
        database.migrate_to_head()
    except OrbitError as error:
        raise _fail(error) from error
    click.echo(f'{"Created" if created else "Found"} database {settings.database.name}; schema is up to date.')


@orbit.command('seed')
@click.option(
    '--file',
    'path',
    type=click.Path(exists=True, dir_okay=False),
    help='Saved feed to load (default: the bundled snapshot).',
)
def seed(path: str | None) -> None:
    """Publish a saved feed (events.json) as the active run, without reading the newsroom table."""
    try:
        run = runs.seed_from_file(path)
    except OrbitError as error:
        raise _fail(error) from error
    click.echo(f'Seeded run {run.id}: {run.events_out} events')


@orbit.command('export-seed')
@click.option(
    '--source',
    type=click.Choice([s.value for s in Source.runnable()]),
    default=Source.JAGRAN_BIZ.value,
    show_default=True,
)
@click.option('--csv', 'csv_path', type=click.Path(exists=True, dir_okay=False), help='CSV path when --source csv.')
@click.option('--machine/--no-machine', default=False, show_default=True, help='Include machine translations.')
@click.option('--file', 'path', type=click.Path(dir_okay=False), help='Where to write events.json (default: bundled).')
def export_seed(source: str, csv_path: str | None, machine: bool, path: str | None) -> None:
    """Rebuild the bundled snapshot (events.json and events.js) from a source, leaving the database alone."""
    try:
        meta = runs.export_snapshot(source, json_path=path, csv_path=csv_path, machine=machine)
    except OrbitError as error:
        raise _fail(error) from error
    click.echo(f'Wrote snapshot: {meta["reports"]} reports, {meta["events"]} events, {len(meta["industries"])} sectors')


@pipeline.command('run')
@click.option(
    '--source',
    type=click.Choice([s.value for s in Source.runnable()]),
    default=Source.JAGRAN_BIZ.value,
    show_default=True,
)
@click.option('--csv', 'csv_path', type=click.Path(exists=True, dir_okay=False), help='CSV path when --source csv.')
@click.option(
    '--machine/--no-machine',
    default=None,
    help='Include offline machine translations of the Hindi-only articles (default: ORBIT_USE_MACHINE_TRANSLATIONS).',
)
def pipeline_run(source: str, csv_path: str | None, machine: bool | None) -> None:
    """Classify reports into events and publish them."""
    try:
        run = runs.execute(source, csv_path=csv_path, machine=machine)
    except OrbitError as error:
        raise _fail(error) from error
    click.echo(
        f'Run {run.id} published from {run.source} ({run.source_detail}): '
        f'{run.reports_in} reports, {run.considered} considered, {run.classified} classified, '
        f'{run.events_out} events, {run.skipped} skipped'
    )


@pipeline.command('runs')
def pipeline_runs() -> None:
    """List recent pipeline runs."""
    rows = db.session.scalars(select(PipelineRun).order_by(PipelineRun.id.desc()).limit(RUNS_SHOWN)).all()
    click.echo(f'{"id":>4} {"status":<8} {"active":<6} {"source":<10} {"reports":>7} {"events":>6}  started')
    for run in rows:
        line = (
            f'{run.id:>4} {run.status:<8} {"yes" if run.is_active else "":<6} {run.source:<10} '
            f'{run.reports_in:>7} {run.events_out:>6}  {run.started_at:%Y-%m-%d %H:%M}'
        )
        click.echo(line + (f'  ! {run.error}' if run.error else ''))
