"""Step 2: group hits into episodes (events)."""

import re
from collections import defaultdict
from statistics import median

from .lexicon import CATEGORIES, DET_INDEX, INDUSTRIES

DATE_FORMAT = '%Y-%m-%d %H:%M'
_MARKET_HEAD = re.compile(r'(stock market|share market|nifty|sensex|market|gold)')


def fmt(when):
    return when.strftime(DATE_FORMAT)


def cluster(hits, gap_days=4):
    """Episodes: reports on the same variable, sub-topic and direction, with no gap
    longer than gap_days between consecutive reports."""
    groups = defaultdict(list)
    for h in hits:
        groups[(h['var'], h['topic'])].append(h)

    episodes = []
    for var, topic in sorted(groups):
        rows = sorted(groups[(var, topic)], key=lambda h: h['when'])
        open_eps = {}
        for row in rows:
            if row['dir'] != 0:
                key = row['dir']
            elif open_eps:
                key = max(open_eps, key=lambda k: open_eps[k]['last'])
            else:
                key = 1
            ep = open_eps.get(key)
            if ep is None or (row['when'] - ep['last']).days > gap_days:
                ep = dict(rows=[], last=row['when'])
                open_eps[key] = ep
                episodes.append((var, topic, key, ep))
            ep['rows'].append(row)
            ep['last'] = row['when']

    def score(r):
        return (
            1 if r.get('machine') else 0,  # prefer a human-translated headline as the event's face
            0 if r['extracted'] else 1,
            0 if not r['outlook'] else 1,
            1 if _MARKET_HEAD.match(r['headline'].lower()) else 0,
            r['subjPos'],
            -len(r['summary']),
        )

    out = []
    for var, topic, key, ep in episodes:
        rows = ep['rows']
        dirs = [r['dir'] for r in rows if r['dir'] != 0]
        if dirs:
            total = sum(dirs)
            d = (total > 0) - (total < 0)
        else:
            d = 1 if rows[0]['default'] > 0 else -1
        if d == 0:
            d = key if key in (1, -1) else 1
        ext = [r for r in rows if r['extracted']]
        mag = float(median([r['mag'] for r in ext])) if ext else float(abs(rows[0]['default']))
        facts = [r for r in rows if not r['outlook']]
        rep_row = sorted(rows, key=score)[0]
        cats = sorted({c for r in rows for c in r['cats']}, key=CATEGORIES.index)
        inds = sorted({i for r in rows for i in r['inds']}, key=INDUSTRIES.index)
        reports = [
            dict(
                sl=int(r['sl']),
                date=fmt(r['when']),
                type=r['type'],
                headline=r['headline'],
                summary=r['summary'],
                mag=(float(r['mag']) if r['extracted'] else None),
                dir=int(r['dir']),
                outlook=bool(r['outlook']),
                level=r['level'],
                **({'mt': True} if r.get('machine') else {}),  # only present on machine-translated reports
                _when=r['when'],
            )
            for r in sorted(rows, key=lambda r: r['when'])
        ]
        level = next((r['level'] for r in reversed(reports) if r['level']), None)
        first, last = reports[0]['_when'], reports[-1]['_when']
        for r in reports:
            del r['_when']
        out.append(
            dict(
                var=var,
                topic=topic,
                index=bool(DET_INDEX.get(var)),
                label=rows[0]['label'],
                unit=rows[0]['unit'],
                hit=float(rows[0]['hit']),
                weight=float(rows[0].get('weight', rows[0]['hit'])),
                cats=cats,
                inds=inds,
                dir=d,
                mag=mag,
                extracted=bool(ext),
                nExtracted=len(ext),
                nFacts=len(facts),
                first=fmt(first),
                last=fmt(last),
                count=len(reports),
                rep=rep_row['headline'],
                repSummary=rep_row['summary'],
                level=level,
                reports=reports,
                _last=last,
            )
        )
    out.sort(key=lambda e: e['_last'], reverse=True)
    for k, e in enumerate(out):
        e['id'] = f'E{k + 1:04d}'
        del e['_last']
    return out
