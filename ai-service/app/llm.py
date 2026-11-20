"""Gemini wrapper. The LLM only writes prose from already-computed JSON; it never computes numbers.

If GEMINI_API_KEY is missing or the call fails, `write()` returns None and callers fall back
to deterministic templates, so the demo never breaks on quota or network issues.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.config import get_settings

log = logging.getLogger(__name__)

SYSTEM = (
    "Tu es l'assistant d'un chef de projet dans une grande organisation. "
    "Tu rédiges en français, de façon factuelle, concise et professionnelle. "
    "Tu n'inventes AUCUN chiffre, nom ou fait : tu utilises uniquement les données JSON fournies. "
    "Si une information manque, tu ne la mentionnes pas."
)


def is_enabled() -> bool:
    return bool(get_settings().gemini_api_key)


def write(instruction: str, data: dict[str, Any], max_words: int = 150) -> str | None:
    settings = get_settings()
    if not settings.gemini_api_key:
        return None
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.gemini_api_key)
        prompt = (
            f"{instruction}\n\nLimite : {max_words} mots maximum. Texte brut, sans titre.\n\n"
            f"Données :\n{json.dumps(data, ensure_ascii=False, default=str, indent=1)}"
        )
        resp = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(system_instruction=SYSTEM, temperature=0.3),
        )
        return (resp.text or "").strip() or None
    except Exception as exc:  # noqa: BLE001 - any LLM failure must fall back to templates
        log.warning("LLM call failed, using template fallback: %s", exc)
        return None
