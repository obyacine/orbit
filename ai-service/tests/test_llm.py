"""LLM resilience: retries, fallback model, template fallback. No network."""

from types import SimpleNamespace

import pytest
from google import genai

from app import llm
from app.config import get_settings


class FakeError(Exception):
    def __init__(self, code):
        super().__init__(f"error {code}")
        self.code = code


@pytest.fixture
def fake_gemini(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "main")
    monkeypatch.setenv("GEMINI_FALLBACK_MODEL", "backup")
    monkeypatch.setattr(llm, "BACKOFF_SECONDS", 0)
    get_settings.cache_clear()
    calls: list[str] = []
    behaviour: dict[str, object] = {}

    def generate_content(model, contents, config):
        calls.append(model)
        result = behaviour[model]
        if isinstance(result, Exception):
            raise result
        return SimpleNamespace(text=result)

    monkeypatch.setattr(genai, "Client", lambda **kw: SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)))
    yield calls, behaviour
    get_settings.cache_clear()


def test_main_model_answers(fake_gemini):
    calls, behaviour = fake_gemini
    behaviour.update(main=" Synthèse. ", backup="never")
    assert llm.write("x", {}) == "Synthèse."
    assert calls == ["main"]


def test_overloaded_main_falls_back_to_backup_model(fake_gemini):
    calls, behaviour = fake_gemini
    behaviour.update(main=FakeError(503), backup="Texte du modèle de secours.")
    assert llm.write("x", {}) == "Texte du modèle de secours."
    assert calls == ["main"] * (llm.RETRIES + 1) + ["backup"]


def test_non_transient_error_skips_retries(fake_gemini):
    calls, behaviour = fake_gemini
    behaviour.update(main=FakeError(404), backup="ok")
    assert llm.write("x", {}) == "ok"
    assert calls == ["main", "backup"]


def test_everything_down_returns_none_for_template_fallback(fake_gemini):
    _, behaviour = fake_gemini
    behaviour.update(main=FakeError(503), backup=FakeError(429))
    assert llm.write("x", {}) is None
