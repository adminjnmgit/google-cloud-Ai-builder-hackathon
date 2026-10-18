"""The batch pipeline with the AI agents slotted in around the rule-based core.

    reports -> translate -> classify (lexicon, then Gemini for the misses) -> cluster (+ merge) -> brief

Every agent step is optional. With AI off, or when a model call fails, this is exactly the old
lexicon pipeline, so a bad day at the model provider can never take the feed down.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from ..pipeline.classify import classify
from ..pipeline.cluster import cluster
from ..pipeline.lexicon import CATEGORIES, INDUSTRIES
from .brief import brief_events
from .classify_ai import classify_misses
from .client import AiClient, AiSettings
from .cluster_ai import merge_episodes
from .translate import translate_reports

log = logging.getLogger(__name__)

EXCLUDED_SECTIONS = frozenset({'Personal Finance', 'Mutual Funds', 'Insurance'})


def run_pipeline(
    reports,
    excluded_sections=EXCLUDED_SECTIONS,
    gap_days=4,
    *,
    ai: AiSettings | AiClient | None = None,
):
    """Reports in, ``{meta, events}`` out. Touches no database; the only I/O is the model calls, if enabled."""
    reports = list(reports)
    if not reports:
        raise ValueError('No reports to process')

    client: AiClient | None = None
    if isinstance(ai, AiClient):
        client = ai
    elif isinstance(ai, AiSettings) and ai.enabled:
        client = AiClient(ai)

    agent_meta: dict[str, Any] = {
        'enabled': bool(client and client.ready),
        'translated': 0,
        'geminiHits': 0,
        'briefs': 0,
    }

    if client and client.ready:
        reports, translated = translate_reports(reports, client)
        agent_meta['translated'] = translated

    considered = [r for r in reports if r['type'] not in excluded_sections]
    hits = classify(considered)
    lexicon_hits = len(hits)

    if client and client.ready:
        before = len(hits)
        hits = classify_misses(considered, hits, client)
        agent_meta['geminiHits'] = len(hits) - before

    events = cluster(hits, gap_days=gap_days)

    if client and client.ready:
        events = merge_episodes(events, client)
        briefs = brief_events(events, client)
        agent_meta['briefs'] = len(briefs)
    else:
        briefs = {}

    types = Counter(r['type'] for r in reports)
    meta = dict(
        reports=len(reports),
        considered=len(considered),
        classified=len({h['sl'] for h in hits}),
        machineTranslated=sum(1 for r in reports if r.get('machine')),
        events=len(events),
        first=min(r['when'] for r in reports).strftime('%Y-%m-%d %H:%M:%S'),
        last=max(r['when'] for r in reports).strftime('%Y-%m-%d %H:%M:%S'),
        industries=list(INDUSTRIES),
        categories=list(CATEGORIES),
        types=dict(types.most_common()),
        agents=agent_meta,
        briefs=briefs,
        lexiconHits=lexicon_hits,
    )
    log.info(
        'Pipeline done: %s events (lexicon_hits=%s gemini_hits=%s briefs=%s)',
        len(events),
        lexicon_hits,
        agent_meta['geminiHits'],
        agent_meta['briefs'],
    )
    return dict(meta=meta, events=events)
