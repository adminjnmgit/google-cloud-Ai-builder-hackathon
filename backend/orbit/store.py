"""Persisting pipeline output: write a run's events, make one run the active feed, drop old runs."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select, update

from .enums import RunStatus, TagKind
from .extensions import db
from .feed_cache import feed_cache
from .models import Event, EventReport, EventTag, PipelineRun, utcnow
from .pipeline.sources import parse_when


def active_run() -> PipelineRun | None:
    return db.session.scalar(
        select(PipelineRun).where(PipelineRun.is_active.is_(True)).order_by(PipelineRun.id.desc()).limit(1)
    )


def _event_row(run: PipelineRun, data: dict[str, Any]) -> Event:
    event = Event(
        run_id=run.id,
        code=data['id'],
        var=data['var'],
        topic=data['topic'] or '',
        is_index=bool(data['index']),
        label=data['label'],
        unit=data['unit'],
        hit=data['hit'],
        direction=data['dir'],
        mag=data['mag'],
        extracted=bool(data['extracted']),
        n_extracted=data['nExtracted'],
        n_facts=data['nFacts'],
        report_count=data['count'],
        first_at=parse_when(data['first']),
        last_at=parse_when(data['last']),
        rep=data['rep'],
        rep_summary=data.get('repSummary') or '',
        level=data.get('level'),
    )
    event.reports = [
        EventReport(
            sl=r['sl'],
            reported_at=parse_when(r['date']),
            section=r.get('type') or '',
            headline=r['headline'],
            summary=r.get('summary') or '',
            mag=r.get('mag'),
            direction=r['dir'],
            outlook=bool(r.get('outlook')),
            level=r.get('level'),
            machine=bool(r.get('mt')),
        )
        for r in data['reports']
    ]
    event.tags = [EventTag(kind=TagKind.INDUSTRY, value=v, position=i) for i, v in enumerate(data['inds'])] + [
        EventTag(kind=TagKind.CATEGORY, value=v, position=i) for i, v in enumerate(data['cats'])
    ]
    return event


def save_events(run: PipelineRun, result: dict[str, Any]) -> None:
    """Insert the pipeline's ``{meta, events}`` under ``run``. The caller commits."""
    db.session.add_all(_event_row(run, data) for data in result['events'])


def activate(run: PipelineRun, *, keep: int) -> None:
    """Make ``run`` the one readers see, then drop the events of runs older than the newest ``keep``."""
    db.session.execute(update(PipelineRun).where(PipelineRun.id != run.id).values(is_active=False))
    run.is_active = True
    run.status = RunStatus.SUCCESS
    run.finished_at = utcnow()
    db.session.commit()
    prune(keep)
    feed_cache.clear()


def prune(keep: int) -> None:
    """Delete the events (with their reports and tags) of successful runs beyond the newest ``keep``."""
    run_ids = db.session.scalars(
        select(PipelineRun.id).where(PipelineRun.status == RunStatus.SUCCESS).order_by(PipelineRun.id.desc())
    ).all()
    for run_id in run_ids[max(keep, 1) :]:
        event_ids = select(Event.id).where(Event.run_id == run_id)
        db.session.execute(delete(EventReport).where(EventReport.event_id.in_(event_ids)))
        db.session.execute(delete(EventTag).where(EventTag.event_id.in_(event_ids)))
        db.session.execute(delete(Event).where(Event.run_id == run_id))
    db.session.commit()
