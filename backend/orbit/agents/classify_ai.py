"""Classify agent: Gemini Flash structured hits for reports the lexicon missed."""

from __future__ import annotations

import logging
from typing import Any

from ..pipeline.extract import direction, extract_level, extract_magnitude
from ..pipeline.lexicon import CATEGORIES, DETECTORS, INDUSTRIES, geo_topic
from .client import AiClient

log = logging.getLogger(__name__)

_DET_BY_VAR = {d['var']: d for d in DETECTORS}
_ALLOWED_VARS = sorted(_DET_BY_VAR)
_IND_SET = set(INDUSTRIES)
_CAT_SET = set(CATEGORIES)


def _missed_reports(reports: list[dict[str, Any]], hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = {h['sl'] for h in hits}
    return [r for r in reports if r['sl'] not in seen]


def _hit_from_gemini(report: dict[str, Any], item: dict[str, Any]) -> dict[str, Any] | None:
    det = _DET_BY_VAR.get(item.get('var'))
    if det is None:
        return None
    head = str(report.get('headline') or '')
    summ = str(report.get('summary') or '')
    text = head + ' ' + summ
    inds = [i for i in item.get('inds') or det['inds'] if i in _IND_SET]
    if not inds:
        inds = list(det['inds'])
    cats = [c for c in item.get('cats') or det['cats'] if c in _CAT_SET]
    if not cats:
        cats = list(det['cats'])
    raw_dir = item.get('dir')
    try:
        d = int(raw_dir)
    except (TypeError, ValueError):
        d = direction(text, det)
    if d not in (-1, 0, 1):
        d = direction(text, det)
    mag, extracted = extract_magnitude(text, det)
    if item.get('mag') is not None and not extracted:
        try:
            mag = abs(float(item['mag']))
            extracted = True
        except (TypeError, ValueError):
            pass
    topic = str(item.get('topic') or '')
    if det['var'] in ('geo_risk', 'freight') and not topic:
        topic = geo_topic(text.lower())
    return dict(
        sl=int(report['sl']),
        when=report['when'],
        date=report['date'],
        type=report['type'],
        machine=bool(report.get('machine')),
        headline=head,
        summary=summ,
        var=det['var'],
        label=det['label'],
        cats=cats,
        inds=inds,
        mag=mag,
        extracted=extracted,
        dir=d,
        unit=det['unit'],
        default=det['default'],
        hit=det['hit'],
        outlook=bool(item.get('outlook')),
        topic=topic,
        level=extract_level(text, det['var']),
        subjPos=0,
        ai=True,
    )


def classify_misses(
    reports: list[dict[str, Any]], hits: list[dict[str, Any]], client: AiClient
) -> list[dict[str, Any]]:
    """Append Gemini hits for reports with no lexicon match. Never replaces lexicon hits."""
    if not client.settings.classify_enabled or not client.ready:
        return hits

    model = client.settings.flash_model
    missed = _missed_reports(reports, hits)[: client.settings.classify_max_reports]
    if not missed:
        return hits

    by_sl = {r['sl']: r for r in missed}
    payload = [
        {
            'sl': r['sl'],
            'headline': r['headline'],
            'summary': (r.get('summary') or '')[:500],
            'section': r.get('type') or '',
        }
        for r in missed
    ]
    system = (
        'You are the Orbit classify agent for Indian SMB strategy news. '
        'Return JSON only: {"hits":[{"sl":int,"var":string,"dir":1|-1|0,"inds":[string],'
        '"cats":[string],"topic":string,"mag":number|null,"outlook":bool}]}. '
        f'var must be one of: {_ALLOWED_VARS}. '
        f'inds subset of {INDUSTRIES}. cats subset of {CATEGORIES}. '
        'Skip stock tips, personal finance, and non-business noise. Empty hits is fine.'
    )
    data = client.generate_json(
        model=model,
        system=system,
        prompt=f'Classify these reports:\n{payload!r}',
    )
    if not isinstance(data, dict):
        return hits

    extra: list[dict[str, Any]] = []
    for item in data.get('hits') or []:
        if not isinstance(item, dict):
            continue
        report = by_sl.get(item.get('sl'))
        if report is None:
            continue
        hit = _hit_from_gemini(report, item)
        if hit is not None:
            extra.append(hit)

    log.info('Classify agent: %s Gemini hit(s) on %s missed report(s)', len(extra), len(missed))
    return hits + extra
