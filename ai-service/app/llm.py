"""Gemini wrapper. The LLM only writes prose from already-computed JSON; it never computes numbers.

Resilience, from best to worst case:
1. the main model (GEMINI_MODEL) answers;
2. it is overloaded or rate-limited: short retries, then the fallback model (GEMINI_FALLBACK_MODEL);
3. no key, or every model fails: `write()` returns None and callers use deterministic templates.
Every call has a timeout, so a report is never blocked by the LLM.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.config import get_settings

log = logging.getLogger(__name__)

TRANSIENT_CODES = {429, 500, 503}  # rate limit, internal error, overloaded: worth a short retry
# A timeout (504) is not retried on the same model: it already cost TIMEOUT_SECONDS, so we move on.
RETRIES = 2  # per model
BACKOFF_SECONDS = 1.0  # 1 s, 2 s
TIMEOUT_SECONDS = 15  # per call

SYSTEM = (
    "Tu es l'assistant d'un chef de projet dans une grande organisation. "
    "Tu rédiges en français, de façon factuelle, concise et professionnelle. "
    "Tu n'inventes AUCUN chiffre, nom ou fait : tu utilises uniquement les données JSON fournies. "
    "Si une information manque, tu ne la mentionnes pas."
)


def is_enabled() -> bool:
    return bool(get_settings().gemini_api_key)


def _models() -> list[str]:
    s = get_settings()
    return [m for m in dict.fromkeys((s.gemini_model, s.gemini_fallback_model)) if m]


def write(instruction: str, data: dict[str, Any], max_words: int = 150) -> str | None:
    settings = get_settings()
    if not settings.gemini_api_key:
        return None
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(
            api_key=settings.gemini_api_key,
            http_options=types.HttpOptions(timeout=TIMEOUT_SECONDS * 1000),  # milliseconds
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("LLM client unavailable, using template fallback: %s", exc)
        return None

    prompt = (
        f"{instruction}\n\nLimite : {max_words} mots maximum. Texte brut, sans titre.\n\n"
        f"Données :\n{json.dumps(data, ensure_ascii=False, default=str, indent=1)}"
    )
    config = types.GenerateContentConfig(system_instruction=SYSTEM, temperature=0.3)

    for model in _models():
        for attempt in range(RETRIES + 1):
            try:
                resp = client.models.generate_content(model=model, contents=prompt, config=config)
                return (resp.text or "").strip() or None
            except Exception as exc:  # noqa: BLE001 - any LLM failure must fall back
                code = getattr(exc, "code", None)
                if code in TRANSIENT_CODES and attempt < RETRIES:
                    log.info("LLM %s busy (%s), retry %d/%d", model, code, attempt + 1, RETRIES)
                    time.sleep(BACKOFF_SECONDS * 2**attempt)
                    continue
                log.warning("LLM %s failed (%s): %s", model, code, str(exc)[:200])
                break  # next model
    log.warning("No LLM model answered, using template fallback")
    return None
