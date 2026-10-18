"""Pipeline runs: read reports from a source, classify them, and publish the result atomically."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Any

from flask import current_app
from sqlalchemy import text

from . import store
from .enums import RunStatus, Source
from .errors import NoEventsProduced, PipelineBusy, SourceError
from .extensions import db
from .models import PipelineRun, utcnow
from .pipeline.engine import run_pipeline
from .pipeline.sources import Report, reports_from_csv, reports_from_csv_path, reports_from_table

log = logging.getLogger(__name__)

# A MySQL advisory lock, so two runs cannot overlap even across processes (the web server and the CLI).
# MySQL releases it by itself if the holder's connection drops.
LOCK_NAME = 'orbit.pipeline'
MAX_DETAIL = 255
MAX_ERROR = 2000


@contextmanager
def _exclusive() -> Iterator[None]:
    with db.engine.connect() as lock_connection:
        acquired = lock_connection.execute(text('SELECT GET_LOCK(:name, 0)'), {'name': LOCK_NAME}).scalar()
        if not acquired:
            raise PipelineBusy('A pipeline run is already in progress')
        try:
            yield
        finally:
            lock_connection.execute(text('SELECT RELEASE_LOCK(:name)'), {'name': LOCK_NAME})


def _load_reports(
    run: PipelineRun, source: Source, *, csv_path: str | None, fileobj: IO[str] | None, machine: bool | None
) -> tuple[list[Report], int]:
    """Read the reports for ``source`` and record on ``run`` what they came from."""
    config = current_app.config
    if source is Source.JAGRAN_BIZ:
        table = config['SOURCE_TABLE']
        use_machine = config['USE_MACHINE_TRANSLATIONS'] if machine is None else machine
        run.source_detail = table + (' + machine translations' if use_machine else '')
        return reports_from_table(db.session.connection(), table, machine=use_machine)
    if source is Source.CSV:
        path = csv_path or config['SOURCE_CSV']
        if not path:
            raise SourceError('No CSV path given and ORBIT_SOURCE_CSV is not set')
        run.source_detail = str(path)[:MAX_DETAIL]
        return reports_from_csv_path(path)
    if source is Source.UPLOAD:
        if fileobj is None:
            raise SourceError('No file was uploaded')
        return reports_from_csv(fileobj)
    raise SourceError(f'A pipeline run cannot read from {source.value!r}')


def _publish(run: PipelineRun, result: dict[str, Any], skipped: int) -> None:
    meta = result['meta']
    run.reports_in = meta['reports']
    run.considered = meta['considered']
    run.classified = meta['classified']
    run.events_out = meta['events']
    run.skipped = skipped
    run.meta = meta
    store.save_events(run, result)
    store.activate(run, keep=current_app.config['KEEP_RUNS'])


def _record_failure(run_id: int, error: Exception) -> None:
    db.session.rollback()
    run = db.session.get(PipelineRun, run_id)
    run.status = RunStatus.FAILED
    run.finished_at = utcnow()
    run.error = f'{type(error).__name__}: {error}'[:MAX_ERROR]
    db.session.commit()


def execute(
    source: Source | str,
    *,
    csv_path: str | None = None,
    fileobj: IO[str] | None = None,
    detail: str = '',
    machine: bool | None = None,
) -> PipelineRun:
    """Run the pipeline on ``source`` and publish the result.

    ``machine`` includes offline machine translations for the ``jagran_biz`` source (default: configuration).

    The previously active run keeps serving until the new one is complete, and a run that produces no events
    fails instead of replacing good data with nothing.

    Raises PipelineBusy, SourceError or NoEventsProduced.
    """
    source = Source(source)
    with _exclusive():
        run = PipelineRun(source=source, source_detail=detail[:MAX_DETAIL], status=RunStatus.RUNNING)
        db.session.add(run)
        db.session.commit()
        run_id = run.id
        try:
            reports, skipped = _load_reports(run, source, csv_path=csv_path, fileobj=fileobj, machine=machine)
            if not reports:
                raise SourceError('The source has no usable English reports')
            result = run_pipeline(reports)
            if not result['events']:
                raise NoEventsProduced('The pipeline produced no events; keeping the current data')
            _publish(run, result, skipped)
        except UnicodeDecodeError as error:
            _record_failure(run_id, error)
            raise SourceError('The file is not valid UTF-8 text') from error
        except Exception as error:
            _record_failure(run_id, error)
            raise
        log.info(
            'Run %s published from %s: %s events from %s reports', run.id, source.value, run.events_out, run.reports_in
        )
        return run


def seed_from_file(path: str | Path | None = None) -> PipelineRun:
    """Publish a saved feed (the frontend's ``events.json``) as the active run, without reading any source table."""
    path = Path(path or current_app.config['SEED_FILE'])
    try:
        saved = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise SourceError(f'Cannot read the saved feed {path}: {error}') from error
    run = PipelineRun(source=Source.SEED, source_detail=path.name[:MAX_DETAIL], status=RunStatus.RUNNING)
    db.session.add(run)
    db.session.commit()
    _publish(run, {'meta': dict(saved['meta']), 'events': saved['events']}, 0)
    return run


def export_snapshot(
    source: Source | str = Source.JAGRAN_BIZ,
    *,
    json_path: str | Path | None = None,
    csv_path: str | None = None,
    machine: bool = False,
) -> dict[str, Any]:
    """Run the pipeline on ``source`` and write the result as the bundled snapshot, without touching the database.

    Writes ``events.json`` (read by ``orbit seed`` and the tests) and the ``events.js`` twin the static pages load.
    The snapshot is the feed a fresh install starts from and the fallback the pages use when the API is down.
    """
    source = Source(source)
    json_path = Path(json_path or current_app.config['SEED_FILE'])
    run = PipelineRun(source=source, source_detail='')  # only used by _load_reports to describe the source
    reports, _ = _load_reports(run, source, csv_path=csv_path, fileobj=None, machine=machine)
    if not reports:
        raise SourceError('The source has no usable English reports')
    result = run_pipeline(reports)
    if not result['events']:
        raise NoEventsProduced('The pipeline produced no events; the snapshot was not written')
    body = json.dumps(result, ensure_ascii=False)
    json_path.write_text(body, encoding='utf-8')
    json_path.with_suffix('.js').write_text(f'window.ORBIT_DATA={body};\n', encoding='utf-8')
    return result['meta']
