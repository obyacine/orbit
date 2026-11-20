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
    """Main model, then each fallback (GEMINI_FALLBACK_MODEL may list several, comma-separated)."""
    s = get_settings()
    fallbacks = [m.strip() for m in s.gemini_fallback_model.split(",")]
    return [m for m in dict.fromkeys([s.gemini_model, *fallbacks]) if m]


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


def generate_json(instruction: str, schema: type, timeout_seconds: int = 45) -> Any | None:
    """Structured generation: returns an instance of the pydantic `schema`, or None if no model answered.

    Used for extraction (brief -> baseline), where the LLM proposes and a human validates.
    Longer timeout than `write()` (the output is a whole document), but short enough to move on to the
    next model quickly when one is overloaded.
    """
    settings = get_settings()
    if not settings.gemini_api_key:
        return None
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(
            api_key=settings.gemini_api_key,
            http_options=types.HttpOptions(timeout=timeout_seconds * 1000),
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("LLM client unavailable: %s", exc)
        return None

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_BASELINE,
        temperature=0.2,
        response_mime_type="application/json",
        response_schema=schema,
    )
    for model in _models():
        for attempt in range(RETRIES + 1):
            try:
                resp = client.models.generate_content(model=model, contents=instruction, config=config)
                if resp.parsed is not None:
                    return resp.parsed
                return schema.model_validate_json(resp.text or "")
            except Exception as exc:  # noqa: BLE001
                code = getattr(exc, "code", None)
                if code in TRANSIENT_CODES and attempt < RETRIES:
                    log.info("LLM %s busy (%s), retry %d/%d", model, code, attempt + 1, RETRIES)
                    time.sleep(BACKOFF_SECONDS * 2**attempt)
                    continue
                log.warning("LLM %s failed on structured output (%s): %s", model, code, str(exc)[:300])
                break
    return None


SYSTEM_BASELINE = (
    "Tu es un chef de projet senior (PMP, PRINCE2, Scrum) dans une grande organisation. "
    "À partir d'un brief, tu prépares le cadrage formel du projet en français : charte, livrables priorisés, "
    "découpage et planning. Tu restes fidèle au brief : tu n'inventes ni budget, ni date, ni nom de personne "
    "absents du brief ; si une information manque, tu écris « À préciser ». Tu proposes des livrables concrets, "
    "vérifiables, formulés comme des tâches livrables par une équipe."
)
