"""Thin wrappers around Vertex Gemini and Cloud Translation.

Uses Application Default Credentials. When AI is disabled or a call fails, callers fall back
to the lexicon pipeline so local/dev always works without GCP.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

_KEYISH = re.compile(r'AIza[0-9A-Za-z_-]{20,}|ya29\.[0-9A-Za-z_-]+')


def _summarise(error: Exception, *, model: str, backend: str) -> str:
    """One line for operators: status + message, with any token-like strings masked."""
    message = str(error).replace('\n', ' ')
    message = _KEYISH.sub('***', message)
    return f'{backend} {model}: {type(error).__name__}: {message[:300]}'


@dataclass(frozen=True, slots=True)
class AiSettings:
    enabled: bool
    project: str
    api_key: str = field(repr=False)  # Gemini API key; when set, Gemini calls skip Vertex. Never logged.
    location: str
    flash_model: str  # gemini-3.8-flash — classify, brief, chat
    lite_model: str  # gemini-3.5-flash-lite — cluster, translate fallback
    pro_model: str
    translate_with_gemini: bool
    classify_enabled: bool
    cluster_enabled: bool
    brief_enabled: bool
    translate_enabled: bool
    search_data_store: str
    classify_max_reports: int
    brief_max_events: int


class AiClient:
    """Lazy Vertex / Translation clients shared across one pipeline run or request."""

    def __init__(self, settings: AiSettings) -> None:
        self.settings = settings
        self._genai = None
        self._translate = None
        self.last_error: str | None = None  # short, secret-free summary of the most recent failure

    @property
    def ready(self) -> bool:
        return bool(self.settings.enabled and (self.settings.api_key or self.settings.project))

    @property
    def backend(self) -> str:
        return 'gemini-api' if self.settings.api_key else 'vertex'

    def generate_text(
        self,
        *,
        model: str,
        prompt: str,
        system: str = '',
        temperature: float = 0.2,
        json_mode: bool = False,
    ) -> str | None:
        if not self.ready:
            return None
        try:
            client = self._gemini()
            from google.genai import types

            config_kwargs: dict[str, Any] = {'temperature': temperature}
            if json_mode:
                config_kwargs['response_mime_type'] = 'application/json'
            if system:
                config_kwargs['system_instruction'] = system
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(**config_kwargs),
            )
            text = (response.text or '').strip()
            self.last_error = None
            return text or None
        except Exception as error:
            log.exception('Gemini generate_content failed (model=%s)', model)
            self.last_error = _summarise(error, model=model, backend=self.backend)
            return None

    def generate_json(
        self,
        *,
        model: str,
        prompt: str,
        system: str = '',
        temperature: float = 0.1,
    ) -> Any | None:
        raw = self.generate_text(model=model, prompt=prompt, system=system, temperature=temperature, json_mode=True)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r'\{[\s\S]*\}|\[[\s\S]*\]', raw)
            if not match:
                log.warning('Gemini returned non-JSON: %s', raw[:200])
                return None
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                log.warning('Gemini JSON repair failed: %s', raw[:200])
                return None

    def translate_to_english(self, text: str, *, source_language: str | None = None) -> str | None:
        if not text.strip():
            return text
        # Cloud Translation needs a billed project; without one, Gemini does the translating.
        if self.settings.translate_with_gemini or not self.settings.project:
            return self.generate_text(
                model=self.settings.lite_model,
                system='You translate business news into clear English. Return only the translation.',
                prompt=text,
                temperature=0.0,
            )
        if not self.ready:
            return None
        try:
            client = self._translation()
            kwargs: dict[str, Any] = {'target_language': 'en'}
            if source_language:
                kwargs['source_language'] = source_language
            result = client.translate(text, **kwargs)
            if isinstance(result, list):
                result = result[0]
            return result.get('translatedText') or None
        except Exception:
            log.exception('Cloud Translation failed; trying Gemini lite')
            return self.generate_text(
                model=self.settings.lite_model,
                system='You translate business news into clear English. Return only the translation.',
                prompt=text,
                temperature=0.0,
            )

    def _gemini(self):
        if self._genai is None:
            from google import genai

            if self.settings.api_key:
                self._genai = genai.Client(api_key=self.settings.api_key)
            else:
                self._genai = genai.Client(
                    vertexai=True,
                    project=self.settings.project,
                    location=self.settings.location,
                )
        return self._genai

    def _translation(self):
        if self._translate is None:
            from google.cloud import translate_v2 as translate

            self._translate = translate.Client()
        return self._translate
