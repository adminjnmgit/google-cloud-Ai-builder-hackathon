"""Search agent: Vertex AI Search when configured, else local keyword ranking."""

from __future__ import annotations

import logging
import re
from typing import Any

from .client import AiClient

log = logging.getLogger(__name__)

_WORD = re.compile(r'[a-z0-9]{2,}')


def _local_search(query: str, events: list[dict[str, Any]], *, limit: int = 20) -> list[dict[str, Any]]:
    tokens = set(_WORD.findall(query.lower()))
    if not tokens:
        return []
    scored: list[tuple[int, dict[str, Any]]] = []
    for event in events:
        blob = ' '.join(str(event.get(k) or '') for k in ('rep', 'repSummary', 'label', 'var', 'topic')).lower()
        inds = ' '.join(event.get('inds') or []).lower()
        text = blob + ' ' + inds
        score = sum(1 for t in tokens if t in text)
        if score:
            scored.append((score, event))
    scored.sort(key=lambda item: (-item[0], item[1].get('last') or ''))
    return [
        {
            'id': e.get('id') or e.get('code'),
            'score': score,
            'rep': e.get('rep'),
            'label': e.get('label'),
            'inds': e.get('inds'),
            'source': 'local',
        }
        for score, e in scored[:limit]
    ]


def _vertex_search(client: AiClient, query: str, *, limit: int = 20) -> list[dict[str, Any]] | None:
    data_store = client.settings.search_data_store
    if not data_store or not client.ready:
        return None
    try:
        from google.cloud import discoveryengine_v1 as discoveryengine

        # data_store may be a full resource name or a bare id.
        if data_store.startswith('projects/'):
            serving_config = f'{data_store}/servingConfigs/default_search'
        else:
            serving_config = (
                f'projects/{client.settings.project}/locations/{client.settings.location}'
                f'/collections/default_collection/dataStores/{data_store}/servingConfigs/default_search'
            )
        search_client = discoveryengine.SearchServiceClient()
        request = discoveryengine.SearchRequest(
            serving_config=serving_config,
            query=query,
            page_size=limit,
        )
        response = search_client.search(request)
        results: list[dict[str, Any]] = []
        for item in response.results:
            doc = item.document
            struct = dict(doc.struct_data) if doc.struct_data else {}
            results.append(
                {
                    'id': struct.get('id') or doc.id,
                    'score': None,
                    'rep': struct.get('rep') or struct.get('title') or '',
                    'label': struct.get('label') or '',
                    'inds': struct.get('inds') or [],
                    'source': 'vertex_ai_search',
                }
            )
        return results
    except Exception:
        log.exception('Vertex AI Search failed; falling back to local search')
        return None


def search_events(client: AiClient, query: str, events: list[dict[str, Any]], *, limit: int = 20) -> dict[str, Any]:
    query = (query or '').strip()
    if not query:
        return {'query': query, 'engine': 'none', 'items': []}

    vertex = _vertex_search(client, query, limit=limit)
    if vertex is not None:
        return {'query': query, 'engine': 'vertex_ai_search', 'items': vertex}

    return {'query': query, 'engine': 'local', 'items': _local_search(query, events, limit=limit)}
