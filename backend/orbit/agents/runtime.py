"""Build an AiClient from app Settings."""

from __future__ import annotations

from ..config import AiConfig, Settings
from .client import AiClient, AiSettings


def ai_settings_from_config(ai: AiConfig) -> AiSettings:
    return AiSettings(
        enabled=ai.enabled,
        project=ai.project,
        api_key=ai.api_key,
        location=ai.location,
        flash_model=ai.flash_model,
        lite_model=ai.lite_model,
        pro_model=ai.pro_model,
        translate_with_gemini=ai.translate_with_gemini,
        classify_enabled=ai.classify_enabled,
        cluster_enabled=ai.cluster_enabled,
        brief_enabled=ai.brief_enabled,
        translate_enabled=ai.translate_enabled,
        search_data_store=ai.search_data_store,
        classify_max_reports=ai.classify_max_reports,
        brief_max_events=ai.brief_max_events,
    )


def client_from_settings(settings: Settings) -> AiClient:
    return AiClient(ai_settings_from_config(settings.ai))
