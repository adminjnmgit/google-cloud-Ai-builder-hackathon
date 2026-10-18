"""Chat agent: answers an owner's question from the published events, and nothing else.

The model is shown the newest events (with their briefs when present) and told to cite the ones it
used. If the answer is not in the feed it is expected to say so rather than guess.
"""

from __future__ import annotations

from typing import Any

from .client import AiClient


def answer_question(
    client: AiClient,
    *,
    question: str,
    sector: str = '',
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    if not client.ready:
        return {
            'answer': 'AI is not configured. Set ORBIT_AI_ENABLED=1 and GCP_PROJECT, then retry.',
            'model': None,
            'citations': [],
        }

    context = [
        {
            'id': e.get('id') or e.get('code'),
            'label': e.get('label'),
            'inds': e.get('inds'),
            'dir': e.get('dir'),
            'mag': e.get('mag'),
            'rep': e.get('rep'),
            'repSummary': (e.get('repSummary') or '')[:280],
            'brief': e.get('brief'),
        }
        for e in events[:40]
    ]
    data = client.generate_json(
        model=client.settings.flash_model,
        system=(
            'You are Orbit, a strategy aide for Indian SMB owners. '
            'Answer only from the provided events. If unsure, say so. '
            'Return JSON: {"answer":str,"citations":["E0001",...]}'
        ),
        prompt=(f'Sector focus: {sector or "general"}\nQuestion: {question}\nEvents: {context!r}'),
        temperature=0.3,
    )
    if not isinstance(data, dict):
        text = client.generate_text(
            model=client.settings.flash_model,
            system='Answer from the events only. Be concise.',
            prompt=f'Sector: {sector}\nQuestion: {question}\nEvents: {context!r}',
        )
        out: dict[str, Any] = {'answer': text or 'No answer.', 'model': client.settings.flash_model, 'citations': []}
        if not text and client.last_error:
            out['error'] = client.last_error
        return out

    citations = [str(c) for c in (data.get('citations') or []) if c]
    return {
        'answer': str(data.get('answer') or '').strip() or 'No answer.',
        'model': client.settings.flash_model,
        'citations': citations,
    }
