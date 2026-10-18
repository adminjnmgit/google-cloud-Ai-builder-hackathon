"""The full feed, serialised and gzipped once per published run instead of once per request."""

from __future__ import annotations

import gzip
import hashlib
import json
import threading
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .extensions import db
from .models import Event, PipelineRun
from .serialize import date_out, event_dict

GZIP_LEVEL = 6


@dataclass(frozen=True, slots=True)
class Payload:
    run_id: int
    body: bytes
    gzipped: bytes
    etag: str  # quoted, ready to be used as an HTTP header value


def build_payload(run: PipelineRun) -> Payload:
    """Serialise ``run``'s events as the frontend's ORBIT_DATA."""
    events = db.session.scalars(
        select(Event)
        .where(Event.run_id == run.id)
        .order_by(Event.id)
        .options(selectinload(Event.reports), selectinload(Event.tags))
    ).all()
    meta = dict(run.meta or {})
    meta.update(events=len(events), run=run.id, refreshed=date_out(run.finished_at or run.started_at))
    body = json.dumps(
        {'meta': meta, 'events': [event_dict(e) for e in events]},
        ensure_ascii=False,
        separators=(',', ':'),
        allow_nan=False,
    ).encode('utf-8')
    return Payload(
        run_id=run.id,
        body=body,
        gzipped=gzip.compress(body, compresslevel=GZIP_LEVEL),
        etag=f'"{hashlib.sha1(body).hexdigest()[:20]}"',
    )


class FeedCache:
    """Holds the payload of the newest run. A new run id (from any process) replaces it on the next read."""

    def __init__(self) -> None:
        self._payload: Payload | None = None
        self._lock = threading.Lock()

    def get(self, run: PipelineRun) -> Payload:
        payload = self._payload
        if payload is not None and payload.run_id == run.id:
            return payload
        with self._lock:
            if self._payload is None or self._payload.run_id != run.id:
                self._payload = build_payload(run)
            return self._payload

    def clear(self) -> None:
        with self._lock:
            self._payload = None


feed_cache = FeedCache()
