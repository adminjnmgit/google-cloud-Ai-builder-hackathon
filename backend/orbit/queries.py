"""Read-side queries for the feed endpoints."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import selectinload

from .enums import TagKind
from .errors import ClientError
from .extensions import db
from .models import Event, EventTag, PipelineRun
from .pipeline.lexicon import CATEGORIES, INDUSTRIES
from .pipeline.sources import parse_when

DEFAULT_LIMIT, MAX_LIMIT = 50, 500
MAX_SEARCH_CHARS = 80


def _page_number(args: Mapping[str, str], name: str, default: int, *, minimum: int, maximum: int | None = None) -> int:
    try:
        value = int(args.get(name, default))
    except ValueError:
        raise ClientError('limit and offset must be integers') from None
    value = max(value, minimum)
    return min(value, maximum) if maximum is not None else value


@dataclass(frozen=True, slots=True)
class EventFilter:
    """The filters and paging the ``/api/events`` endpoint accepts."""

    industry: str | None = None
    category: str | None = None
    var: str | None = None
    direction: int | None = None
    since: datetime | None = None
    until: datetime | None = None
    min_reports: int | None = None
    search: str = ''
    limit: int = DEFAULT_LIMIT
    offset: int = 0
    include_reports: bool = False

    @classmethod
    def from_args(cls, args: Mapping[str, str]) -> EventFilter:
        direction = args.get('direction')
        min_reports = args.get('min_reports', '')
        return cls(
            industry=args.get('industry') or None,
            category=args.get('category') or None,
            var=args.get('var') or None,
            direction=int(direction) if direction in ('1', '-1') else None,
            since=parse_when(args.get('since')),
            until=parse_when(args.get('until')),
            min_reports=int(min_reports) if min_reports.isdigit() else None,
            search=(args.get('q') or '').strip()[:MAX_SEARCH_CHARS],
            limit=_page_number(args, 'limit', DEFAULT_LIMIT, minimum=1, maximum=MAX_LIMIT),
            offset=_page_number(args, 'offset', 0, minimum=0),
            include_reports=args.get('include') == 'reports',
        )

    def apply(self, query: Select, run: PipelineRun) -> Select:
        query = query.where(Event.run_id == run.id)
        for kind, value in ((TagKind.INDUSTRY, self.industry), (TagKind.CATEGORY, self.category)):
            if value:
                tagged = select(EventTag.event_id).where(EventTag.kind == kind, EventTag.value == value)
                query = query.where(Event.id.in_(tagged))
        if self.var:
            query = query.where(Event.var == self.var)
        if self.direction is not None:
            query = query.where(Event.direction == self.direction)
        if self.since:
            query = query.where(Event.last_at >= self.since)
        if self.until:
            query = query.where(Event.first_at < self.until + timedelta(days=1))
        if self.min_reports is not None:
            query = query.where(Event.report_count >= self.min_reports)
        if self.search:
            like = f'%{self.search}%'
            query = query.where(or_(Event.rep.ilike(like), Event.rep_summary.ilike(like), Event.label.ilike(like)))
        return query


def find_events(run: PipelineRun, flt: EventFilter) -> tuple[int, list[Event]]:
    """(total matching, one page of events newest first)."""
    matching = flt.apply(select(Event), run)
    total = db.session.scalar(select(func.count()).select_from(matching.subquery())) or 0
    eager = [selectinload(Event.tags)] + ([selectinload(Event.reports)] if flt.include_reports else [])
    page = db.session.scalars(
        matching.order_by(Event.last_at.desc(), Event.id).limit(flt.limit).offset(flt.offset).options(*eager)
    ).all()
    return total, list(page)


def find_event(run: PipelineRun, code: str) -> Event | None:
    return db.session.scalar(
        select(Event)
        .where(Event.run_id == run.id, Event.code == code)
        .options(selectinload(Event.reports), selectinload(Event.tags))
    )


def event_stats(run: PipelineRun) -> dict[str, Any]:
    """Counts the analyst view starts from: by category, industry and variable, plus a weekly timeline."""
    events = db.session.scalars(select(Event).where(Event.run_id == run.id).options(selectinload(Event.tags))).all()
    by_category: Counter[str] = Counter()
    by_industry: Counter[str] = Counter()
    by_variable: Counter[str] = Counter()
    weekly: Counter = Counter()
    labels: dict[str, str] = {}
    for event in events:
        for tag in event.tags:
            (by_category if tag.kind == TagKind.CATEGORY else by_industry)[tag.value] += 1
        by_variable[event.var] += 1
        labels[event.var] = event.label
        weekly[(event.first_at - timedelta(days=event.first_at.weekday())).date()] += 1
    return {
        'run': run.id,
        'events': len(events),
        'reports': {'total': (run.meta or {}).get('reports'), 'classified': run.classified},
        'by_category': [{'name': name, 'events': by_category.get(name, 0)} for name in CATEGORIES],
        'by_industry': [{'name': name, 'events': by_industry.get(name, 0)} for name in INDUSTRIES],
        'by_variable': [{'var': var, 'label': labels[var], 'events': n} for var, n in by_variable.most_common()],
        'weekly': [{'week_start': week.isoformat(), 'events': n} for week, n in sorted(weekly.items())],
    }
