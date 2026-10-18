"""Pure pipeline: reports in, {meta, events} out. No database, no I/O.

reports -> drop non-business sections -> classify (hits) -> cluster (events)
"""

from collections import Counter

from .classify import classify
from .cluster import cluster
from .lexicon import CATEGORIES, INDUSTRIES

EXCLUDED_SECTIONS = frozenset({'Personal Finance', 'Mutual Funds', 'Insurance'})


def run_pipeline(reports, excluded_sections=EXCLUDED_SECTIONS, gap_days=4):
    reports = list(reports)
    if not reports:
        raise ValueError('No reports to process')
    considered = [r for r in reports if r['type'] not in excluded_sections]
    hits = classify(considered)
    events = cluster(hits, gap_days=gap_days)
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
    )
    return dict(meta=meta, events=events)
