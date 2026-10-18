"""Brief agent: Gemini executive summaries for published events."""

from __future__ import annotations

import logging
from typing import Any

from .client import AiClient

log = logging.getLogger(__name__)


def _brief_prompt(event: dict[str, Any]) -> str:
    return (
        f'Variable: {event.get("label")} ({event.get("var")})\n'
        f'Direction: {event.get("dir")} magnitude: {event.get("mag")} {event.get("unit")}\n'
        f'Industries: {event.get("inds")}\n'
        f'Categories: {event.get("cats")}\n'
        f'Headline: {event.get("rep")}\n'
        f'Summary: {event.get("repSummary")}\n'
        f'Window: {event.get("first")} → {event.get("last")} ({event.get("count")} reports)\n'
        'Return JSON: {"what":str,"soWhat":str,"watchNext":str,"impact":1-5}'
    )


def brief_event(event: dict[str, Any], client: AiClient) -> dict[str, Any] | None:
    if not client.settings.brief_enabled or not client.ready:
        return None
    data = client.generate_json(
        model=client.settings.flash_model,
        system=('You write short strategy briefs for Indian SMB owners. Be concrete, no hype, JSON only.'),
        prompt=_brief_prompt(event),
        temperature=0.3,
    )
    if not isinstance(data, dict):
        return None
    try:
        impact = int(data.get('impact') or 3)
    except (TypeError, ValueError):
        impact = 3
    impact = max(1, min(5, impact))
    return {
        'what': str(data.get('what') or '').strip(),
        'soWhat': str(data.get('soWhat') or '').strip(),
        'watchNext': str(data.get('watchNext') or '').strip(),
        'impact': impact,
        'model': client.settings.flash_model,
    }


def brief_events(events: list[dict[str, Any]], client: AiClient) -> dict[str, dict[str, Any]]:
    """Generate briefs for the newest events. Returns map event id → brief."""
    if not client.settings.brief_enabled or not client.ready:
        return {}
    briefs: dict[str, dict[str, Any]] = {}
    for event in events[: client.settings.brief_max_events]:
        brief = brief_event(event, client)
        if brief and (brief['what'] or brief['soWhat']):
            briefs[event['id']] = brief
            event['brief'] = brief
    log.info('Brief agent: %s brief(s)', len(briefs))
    return briefs
