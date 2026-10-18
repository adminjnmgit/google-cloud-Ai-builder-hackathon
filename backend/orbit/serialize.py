"""Database rows to the JSON shapes the frontend has always consumed (``window.ORBIT_DATA``)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .enums import TagKind
from .models import Event, EventReport, EventTag
from .pipeline.lexicon import CATEGORIES, INDUSTRIES

DATE_OUT = '%Y-%m-%d %H:%M'


def date_out(value: datetime) -> str:
    return value.strftime(DATE_OUT)


def _ordered_tags(tags: list[EventTag], kind: TagKind, canonical_order: list[str]) -> list[str]:
    """Tag values of one kind, in the lexicon's canonical order (the order the frontend expects)."""
    values = [tag.value for tag in sorted(tags, key=lambda t: t.position) if tag.kind == kind]
    rank = {name: i for i, name in enumerate(canonical_order)}
    return sorted(values, key=lambda value: rank.get(value, len(rank)))


def report_dict(report: EventReport) -> dict[str, Any]:
    out: dict[str, Any] = {
        'sl': report.sl,
        'date': date_out(report.reported_at),
        'type': report.section,
        'headline': report.headline,
        'summary': report.summary,
        'mag': report.mag,
        'dir': report.direction,
        'outlook': report.outlook,
        'level': report.level,
    }
    if report.machine:  # present only on machine-translated reports
        out['mt'] = True
    return out


def event_dict(event: Event, *, with_reports: bool = True) -> dict[str, Any]:
    out: dict[str, Any] = {
        'var': event.var,
        'topic': event.topic,
        'index': event.is_index,
        'label': event.label,
        'unit': event.unit,
        'hit': event.hit,
        'cats': _ordered_tags(event.tags, TagKind.CATEGORY, CATEGORIES),
        'inds': _ordered_tags(event.tags, TagKind.INDUSTRY, INDUSTRIES),
        'dir': event.direction,
        'mag': event.mag,
        'extracted': event.extracted,
        'nExtracted': event.n_extracted,
        'nFacts': event.n_facts,
        'first': date_out(event.first_at),
        'last': date_out(event.last_at),
        'count': event.report_count,
        'rep': event.rep,
        'repSummary': event.rep_summary,
        'level': event.level,
    }
    if with_reports:
        out['reports'] = [report_dict(r) for r in event.reports]
    out['id'] = event.code
    return out
