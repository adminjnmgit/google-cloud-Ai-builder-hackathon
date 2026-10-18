"""Named agents the product exposes (health, docs, UI)."""

from __future__ import annotations

from typing import Any

AGENTS: list[dict[str, Any]] = [
    {
        'id': 'translate',
        'name': 'Translate',
        'model': 'Cloud Translation API (fallback: gemini-3.5-flash-lite)',
        'role': 'Hindi or mixed-language reports → English before classify',
    },
    {
        'id': 'classify',
        'name': 'Classify / Extract',
        'model': 'gemini-3.8-flash',
        'role': 'Structured hits for reports the lexicon misses; lexicon stays the guardrail',
    },
    {
        'id': 'cluster',
        'name': 'Episode merge',
        'model': 'gemini-3.5-flash-lite',
        'role': 'Suggest merging near-duplicate episodes the 4-day rule keeps apart',
    },
    {
        'id': 'brief',
        'name': 'Executive brief',
        'model': 'gemini-3.8-flash',
        'role': 'Owner-facing what / so-what / watch-next for each event',
    },
    {
        'id': 'chat',
        'name': 'Owner Q&A',
        'model': 'gemini-3.8-flash',
        'role': 'Grounded answers over the published event feed and sector context',
    },
    {
        'id': 'search',
        'name': 'Semantic search',
        'model': 'Vertex AI Search (fallback: local keyword)',
        'role': 'Find events by meaning when a Discovery Engine data store is configured',
    },
]
