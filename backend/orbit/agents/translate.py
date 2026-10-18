"""Translate agent: Cloud Translation API (or Gemini Flash) for non-English report text."""

from __future__ import annotations

import logging
import re
from typing import Any

from .client import AiClient

log = logging.getLogger(__name__)

# Devanagari and common Indic blocks — enough to catch Hindi Jagran copy.
_INDIC = re.compile(r'[\u0900-\u097F\u0980-\u09FF\u0A00-\u0A7F\u0A80-\u0AFF\u0B00-\u0B7F]')


def needs_translation(text: str) -> bool:
    if not text or not text.strip():
        return False
    return _INDIC.search(text) is not None


def translate_reports(reports: list[dict[str, Any]], client: AiClient) -> tuple[list[dict[str, Any]], int]:
    """Return reports with English headline/summary where needed. Counts how many were translated."""
    if not client.settings.translate_enabled or not client.ready:
        return reports, 0

    out: list[dict[str, Any]] = []
    translated = 0
    for report in reports:
        row = dict(report)
        head = str(row.get('headline') or '')
        summ = str(row.get('summary') or '')
        changed = False
        if needs_translation(head):
            en = client.translate_to_english(head, source_language='hi')
            if en:
                row['headline'] = en
                changed = True
        if needs_translation(summ):
            en = client.translate_to_english(summ, source_language='hi')
            if en:
                row['summary'] = en
                changed = True
        if changed:
            row['machine'] = True
            translated += 1
        out.append(row)
    log.info('Translate agent: %s report(s) translated', translated)
    return out, translated
