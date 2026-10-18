"""Database models.

Every table is prefixed ``orbit_`` so it sits beside the existing newsroom tables (``jagran_biz``,
``biz_signals`` ...) in the same MySQL database without touching them. The schema itself is owned by the
Alembic migrations in ``backend/migrations``; these classes must stay in step with them
(``flask db check`` fails when they drift).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, SmallInteger, String, Text, UniqueConstraint, false, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .enums import RunStatus
from .extensions import db

TABLE_ARGS = {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4', 'mysql_collate': 'utf8mb4_unicode_ci'}
ISO_UTC = '%Y-%m-%dT%H:%M:%SZ'


def utcnow() -> datetime:
    """Naive UTC, the convention for every DATETIME column here."""
    return datetime.now(UTC).replace(tzinfo=None)


def iso(value: datetime | None) -> str | None:
    return value.strftime(ISO_UTC) if value else None


def _zero() -> Any:
    return text('0')


# --------------------------------------------------------------------------- pipeline output


class PipelineRun(db.Model):
    """One execution of the pipeline.

    Exactly one successful run is active at a time. Readers only ever see a finished run, so a refresh
    never shows half-written events.
    """

    __tablename__ = 'orbit_pipeline_runs'
    __table_args__ = (TABLE_ARGS,)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(40))  # a Source value
    source_detail: Mapped[str] = mapped_column(String(255), default='', server_default='')
    status: Mapped[str] = mapped_column(String(12), default=RunStatus.RUNNING, index=True)  # a RunStatus value
    is_active: Mapped[bool] = mapped_column(default=False, server_default=false(), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    reports_in: Mapped[int] = mapped_column(default=0, server_default=_zero())
    considered: Mapped[int] = mapped_column(default=0, server_default=_zero())
    classified: Mapped[int] = mapped_column(default=0, server_default=_zero())
    events_out: Mapped[int] = mapped_column(default=0, server_default=_zero())
    skipped: Mapped[int] = mapped_column(default=0, server_default=_zero())
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)

    def to_dict(self) -> dict[str, Any]:
        return {
            'id': self.id,
            'source': self.source,
            'source_detail': self.source_detail,
            'status': self.status,
            'is_active': self.is_active,
            'started_at': iso(self.started_at),
            'finished_at': iso(self.finished_at),
            'reports_in': self.reports_in,
            'considered': self.considered,
            'classified': self.classified,
            'events_out': self.events_out,
            'skipped': self.skipped,
            'error': self.error,
        }


class Event(db.Model):
    __tablename__ = 'orbit_events'
    __table_args__ = (
        Index('ix_orbit_events_run_code', 'run_id', 'code'),
        Index('ix_orbit_events_run_var', 'run_id', 'var'),
        Index('ix_orbit_events_run_last', 'run_id', 'last_at'),
        TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey('orbit_pipeline_runs.id'))
    code: Mapped[str] = mapped_column(String(12))  # E0001, as the frontend refers to events
    var: Mapped[str] = mapped_column(String(40))
    topic: Mapped[str] = mapped_column(String(40), default='', server_default='')
    is_index: Mapped[bool] = mapped_column(default=False, server_default=false())
    label: Mapped[str] = mapped_column(String(120))
    unit: Mapped[str] = mapped_column(String(8))
    hit: Mapped[float]
    direction: Mapped[int] = mapped_column(SmallInteger)
    mag: Mapped[float]
    extracted: Mapped[bool] = mapped_column(default=False, server_default=false())
    n_extracted: Mapped[int] = mapped_column(default=0, server_default=_zero())
    n_facts: Mapped[int] = mapped_column(default=0, server_default=_zero())
    report_count: Mapped[int] = mapped_column(default=0, server_default=_zero())
    first_at: Mapped[datetime] = mapped_column(DateTime)
    last_at: Mapped[datetime] = mapped_column(DateTime)
    rep: Mapped[str] = mapped_column(Text)
    rep_summary: Mapped[str] = mapped_column(Text, default='')
    level: Mapped[str | None] = mapped_column(String(60))

    reports: Mapped[list[EventReport]] = relationship(
        back_populates='event', order_by='EventReport.reported_at, EventReport.id'
    )
    tags: Mapped[list[EventTag]] = relationship(back_populates='event')


class EventReport(db.Model):
    __tablename__ = 'orbit_event_reports'
    __table_args__ = (TABLE_ARGS,)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey('orbit_events.id'), index=True)
    sl: Mapped[int] = mapped_column(index=True)  # the report's serial number in the newsroom table
    reported_at: Mapped[datetime] = mapped_column(DateTime)
    section: Mapped[str] = mapped_column(String(80), default='', server_default='')
    headline: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text, default='')
    mag: Mapped[float | None]
    direction: Mapped[int] = mapped_column(SmallInteger, default=0, server_default=_zero())
    outlook: Mapped[bool] = mapped_column(default=False, server_default=false())
    level: Mapped[str | None] = mapped_column(String(60))
    machine: Mapped[bool] = mapped_column(default=False, server_default=false())  # offline machine translation

    event: Mapped[Event] = relationship(back_populates='reports')


class EventTag(db.Model):
    """An event's industries and categories, one row each, so they can be filtered in SQL."""

    __tablename__ = 'orbit_event_tags'
    __table_args__ = (Index('ix_orbit_event_tags_kind_value', 'kind', 'value'), TABLE_ARGS)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey('orbit_events.id'), index=True)
    kind: Mapped[str] = mapped_column(String(12))  # a TagKind value
    value: Mapped[str] = mapped_column(String(40))
    position: Mapped[int] = mapped_column(SmallInteger, default=0, server_default=_zero())

    event: Mapped[Event] = relationship(back_populates='tags')


class Translation(db.Model):
    """English text produced offline for articles that jagran_biz holds only in Hindi.

    Written by ``tools/translate_hindi.py``. Kept apart from jagran_biz so machine output never mixes with
    the human translations and can be redone with a better model.
    """

    __tablename__ = 'orbit_translations'
    __table_args__ = (TABLE_ARGS,)

    id: Mapped[int] = mapped_column(primary_key=True)
    biz_id: Mapped[int] = mapped_column(unique=True)  # jagran_biz.id
    headline_en: Mapped[str] = mapped_column(Text)
    summary_en: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(80))
    translated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# --------------------------------------------------------------------------- owner workspaces


class Workspace(db.Model):
    """An owner's workspace.

    There are no logins yet: the browser holds an unguessable token in an HttpOnly cookie, which is enough to
    get the same data back on every visit.
    """

    __tablename__ = 'orbit_workspaces'
    __table_args__ = (TABLE_ARGS,)

    id: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[str] = mapped_column(String(64), unique=True)
    sector: Mapped[str] = mapped_column(String(20), default='Automotive', server_default='Automotive')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class BusinessProfile(db.Model):
    __tablename__ = 'orbit_business_profiles'
    __table_args__ = (UniqueConstraint('workspace_id', 'sector', name='uq_orbit_profile'), TABLE_ARGS)

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey('orbit_workspaces.id'))
    sector: Mapped[str] = mapped_column(String(20))
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class ActionTask(db.Model):
    __tablename__ = 'orbit_tasks'
    __table_args__ = (UniqueConstraint('workspace_id', 'sector', 'client_id', name='uq_orbit_task'), TABLE_ARGS)

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey('orbit_workspaces.id'), index=True)
    sector: Mapped[str] = mapped_column(String(20))
    client_id: Mapped[str] = mapped_column(String(64))  # the id the browser gave the task
    position: Mapped[int] = mapped_column(default=0, server_default=_zero())
    title: Mapped[str] = mapped_column(String(300))
    owner: Mapped[str] = mapped_column(String(120), default='', server_default='')
    due: Mapped[str] = mapped_column(String(60), default='', server_default='')
    signal: Mapped[str] = mapped_column(String(64), default='', server_default='')
    done: Mapped[bool] = mapped_column(default=False, server_default=false())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            'id': self.client_id,
            'title': self.title,
            'owner': self.owner,
            'due': self.due,
            'signal': self.signal,
            'done': self.done,
        }
