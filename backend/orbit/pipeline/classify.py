"""Step 1: turn reports into hits.

A hit is one report that matches one detector. A report can hit several detectors
(for example a Hormuz story moves both crude and freight). Hits are independent of
each other, which is what makes the cluster step deterministic and the whole run
safe to repeat on the same input.
"""

import re

from .extract import direction, extract_level, extract_magnitude
from .lexicon import (
    CATEGORIES,
    DECIDED,
    DETECTORS,
    IND_PATTERNS,
    INDUSTRIES,
    OUTLOOK,
    STOCK_NOISE,
    geo_topic,
)

# Compile once. The lexicon keeps raw pattern strings so they stay easy to edit.
_STOCK_NOISE = re.compile(STOCK_NOISE)
_OUTLOOK = re.compile(OUTLOOK)
_DECIDED = re.compile(DECIDED)
_IND_PATTERNS = {name: re.compile(p) for name, p in IND_PATTERNS.items()}
_HAS_US_A = re.compile(r'\b(US|U\.S\.|USA)\b')
_HAS_US_B = re.compile(r'\b(trump|white house|washington|united states|america|american)\b')
_GEO_WORDS = re.compile(
    r'\b(war|iran|israel|hormuz|strait|russia|ukraine|sanction|houthi|conflict|attack|missile)\w*\b'
)
_SUPPLY_WORDS = re.compile(r'(supply|outage|disruption|opec cut|production cut|hormuz|strait|blockade)')
_TRADE_WORDS = re.compile(r'(duty|safeguard|anti-dumping|tariff|import|export|carbon tax)')
_SHORTAGE_WORDS = re.compile(r'(shortage|crisis)')
_TRADE_DEAL = re.compile(r'(trade deal|trade agreement|tariff)')


def _compiled_detectors():
    out = []
    for det in DETECTORS:
        out.append(
            (
                det,
                re.compile(det['subject']),
                re.compile(det['exclude']) if det['exclude'] else None,
                re.compile(det['context']),
            )
        )
    return out


_DETECTORS = _compiled_detectors()


def classify(reports):
    """reports: iterable of dicts with sl, when (datetime), date (str), type, headline, summary."""
    hits = []
    for r in reports:
        head = str(r.get('headline') or '')
        summ = str(r.get('summary') or '')
        text = head + ' ' + summ
        t = text.lower()
        hl = head.lower()
        if _STOCK_NOISE.search(t):
            continue
        has_us = _HAS_US_A.search(text) is not None or _HAS_US_B.search(t) is not None
        for det, subject, exclude, context in _DETECTORS:
            var = det['var']
            if det.get('headOptional'):
                if not subject.search(t):
                    continue
            else:
                if not subject.search(hl):
                    continue
            if exclude and exclude.search(t):
                continue
            if not context.search(hl if det.get('headContext') else t):
                continue
            if var == 'us_tariff' and not has_us:
                continue
            if var == 'trade_policy' and has_us and _TRADE_DEAL.search(t):
                continue
            # A detector marked `exclusive` names its own sectors; otherwise the industry word lists
            # add any other sector the text mentions (a crude story that names airlines also hits Aviation).
            matched = set() if det.get('exclusive') else {k for k, p in _IND_PATTERNS.items() if p.search(t)}
            inds = [k for k in INDUSTRIES if k in matched | set(det['inds'])]
            if not inds:
                continue
            mag, extracted = extract_magnitude(text, det)
            d = direction(text, det)
            cats = list(det['cats'])
            if var in ('crude', 'fuel_price', 'freight') and _GEO_WORDS.search(t):
                cats.append('Geopolitical event')
            if var == 'crude' and _SUPPLY_WORDS.search(t):
                cats.append('Supply disruption')
            if var in ('steel', 'metals') and _TRADE_WORDS.search(t):
                cats.append('Trade restriction')
            if var == 'fuel_price' and _SHORTAGE_WORDS.search(t):
                cats.append('Supply disruption')
            cats = [c for c in CATEGORIES if c in cats]
            outlook = _OUTLOOK.search(hl) is not None and not _DECIDED.search(hl)
            if var in ('geo_risk', 'freight'):
                topic = geo_topic(t)
            elif var in ('us_tariff', 'trade_policy') and d < 0:
                topic = 'relief'
            else:
                topic = ''
            subj = subject.search(hl)
            hits.append(
                dict(
                    sl=int(r['sl']),
                    when=r['when'],
                    date=r['date'],
                    type=r['type'],
                    machine=bool(r.get('machine')),
                    headline=head,
                    summary=summ,
                    var=var,
                    label=det['label'],
                    cats=cats,
                    inds=inds,
                    mag=mag,
                    extracted=extracted,
                    dir=d,
                    unit=det['unit'],
                    default=det['default'],
                    hit=det['hit'],
                    outlook=outlook,
                    topic=topic,
                    level=extract_level(text, var),
                    subjPos=(subj.start() if subj else 999),
                )
            )
    return hits
