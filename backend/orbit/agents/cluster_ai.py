"""Cluster agent: asks Gemini which same-variable episodes are really one story.

The rule-based cluster step splits an episode whenever reports are more than four days apart. That is
usually right, but a slow-burning story (a tariff that is announced, delayed, then imposed) ends up as
two or three events. This agent only ever merges; it never splits what the rules joined, and it needs
the model to be fairly sure before it does anything.
"""

from __future__ import annotations

import logging
from statistics import median
from typing import Any

from ..pipeline.lexicon import CATEGORIES, INDUSTRIES
from .client import AiClient

log = logging.getLogger(__name__)

MIN_CONFIDENCE = 0.75
MAX_EVENTS_SHOWN = 80  # enough context without a huge prompt; the newest events come first anyway


def _merge_pair(keep: dict[str, Any], drop: dict[str, Any]) -> dict[str, Any]:
    """Fold ``drop`` into ``keep`` (same shape as pipeline.cluster output)."""
    reports = sorted(
        keep['reports'] + drop['reports'],
        key=lambda r: r['date'],
    )
    dirs = [r['dir'] for r in reports if r['dir'] != 0]
    if dirs:
        total = sum(dirs)
        d = (total > 0) - (total < 0) or keep['dir']
    else:
        d = keep['dir']
    mags = [r['mag'] for r in reports if r.get('mag') is not None]
    mag = float(median(mags)) if mags else keep['mag']
    cats = sorted({*keep['cats'], *drop['cats']}, key=CATEGORIES.index)
    inds = sorted({*keep['inds'], *drop['inds']}, key=INDUSTRIES.index)
    facts = [r for r in reports if not r.get('outlook')]
    extracted_n = sum(1 for r in reports if r.get('mag') is not None)
    out = dict(keep)
    out.update(
        reports=reports,
        count=len(reports),
        first=reports[0]['date'],
        last=reports[-1]['date'],
        dir=d,
        mag=mag,
        cats=cats,
        inds=inds,
        nFacts=len(facts),
        nExtracted=extracted_n,
        extracted=bool(extracted_n),
        aiMerged=True,
    )
    return out


def merge_episodes(events: list[dict[str, Any]], client: AiClient) -> list[dict[str, Any]]:
    """Ask Gemini which same-variable episodes to merge; apply high-confidence pairs only."""
    if not client.settings.cluster_enabled or not client.ready or len(events) < 2:
        return events

    sketch = [
        {
            'id': e['id'],
            'var': e['var'],
            'topic': e.get('topic') or '',
            'dir': e['dir'],
            'rep': e['rep'][:160],
            'first': e['first'],
            'last': e['last'],
        }
        for e in events[:MAX_EVENTS_SHOWN]
    ]
    data = client.generate_json(
        model=client.settings.lite_model,
        system=(
            'You are the Orbit episode agent. Return JSON only: '
            '{"merges":[{"keep":"E0001","drop":"E0002","confidence":0.0-1.0}]}. '
            'Only merge when both share the same var and clearly describe one ongoing episode. '
            'Prefer fewer merges. Empty merges is fine.'
        ),
        prompt=f'Events:\n{sketch!r}',
    )
    if not isinstance(data, dict):
        return events

    by_id = {e['id']: e for e in events}
    dropped: set[str] = set()
    merges = 0
    for item in data.get('merges') or []:
        if not isinstance(item, dict):
            continue
        try:
            conf = float(item.get('confidence') or 0)
        except (TypeError, ValueError):
            conf = 0.0
        if conf < MIN_CONFIDENCE:
            continue
        keep_id, drop_id = item.get('keep'), item.get('drop')
        if keep_id in dropped or drop_id in dropped:
            continue
        keep, drop = by_id.get(keep_id), by_id.get(drop_id)
        if keep is None or drop is None or keep['var'] != drop['var']:
            continue
        by_id[keep_id] = _merge_pair(keep, drop)
        dropped.add(drop_id)
        merges += 1

    if not merges:
        return events

    out = [by_id[e['id']] for e in events if e['id'] not in dropped]
    out.sort(key=lambda e: e['last'], reverse=True)
    for i, event in enumerate(out):
        event['id'] = f'E{i + 1:04d}'
    log.info('Cluster agent: merged %s episode pair(s) → %s events', merges, len(out))
    return out
