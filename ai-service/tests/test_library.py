"""Organization library: reference documents and past validated projects feed the next cadrage."""

from datetime import date

import pytest

from app import db
from app.config import get_settings
from app.methods import ProjectMethod
from app.module1 import baseline as m1
from tests.test_baseline import proposal
from tests.test_documents import make_docx


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "orbit.db"))
    monkeypatch.setenv("ORBIT_INTERNAL_TOKEN", "t")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def validated(project_id: str, title: str) -> dict:
    content = proposal(["Must", "Should"]).model_dump()
    content["charter"]["title"] = title
    b = db.save_baseline_draft(project_id, "brief", {"delivery": "scrum", "prioritization": "moscow"}, content, "pm")
    return db.validate_baseline(b["id"], "pm", content, {})


def test_prompt_reuses_structure_but_forbids_copying_facts():
    refs = [{"filename": "modele_charte.docx", "role": "template", "text": "1. Contexte 2. Objectifs 3. Gouvernance"}]
    past = [{"content": proposal(["Must"]).model_dump(), "method": {"delivery": "scrum", "prioritization": "moscow"}}]
    prompt = m1.build_prompt("Nouveau projet de portail client pour 2027", ProjectMethod(), date(2026, 11, 20), refs, past)
    assert "Référence 1 : modele_charte.docx (modèle de l'organisation)" in prompt
    assert "1. Contexte 2. Objectifs 3. Gouvernance" in prompt
    assert "Projet passé validé" in prompt and "[Must] L0" in prompt
    assert "N'en recopie JAMAIS les faits" in prompt
    assert prompt.index("Bibliothèque") < prompt.index("Brief du projet")


def test_prompt_without_library_is_unchanged():
    prompt = m1.build_prompt("Nouveau projet de portail client pour 2027", ProjectMethod(), date(2026, 11, 20))
    assert "Bibliothèque" not in prompt


def test_reference_size_is_bounded():
    big = [{"filename": f"d{i}.pdf", "role": "standard", "text": "x" * 50_000} for i in range(5)]
    section = m1.reference_section(big, [])
    assert section.count("x") <= m1.MAX_REFERENCES_CHARS


def test_past_projects_exclude_current_and_drafts(fresh_db):
    validated("p1", "Portail RH")
    validated("p2", "App mobile")
    db.save_baseline_draft("p3", "brief", {}, proposal(["Must"]).model_dump(), "pm")  # draft only
    titles = [b["content"]["charter"]["title"] for b in db.past_validated_baselines(exclude_project_id="p2")]
    assert titles == ["Portail RH"]


def test_library_endpoints(fresh_db):
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    h = {"X-Orbit-Token": "t"}
    added = client.post("/library?role=template&created_by=pm", headers=h, files={"file": ("charte.docx", make_docx())})
    assert added.status_code == 200 and added.json()["role"] == "template"
    assert client.post("/library?role=nope", headers=h, files={"file": ("c.docx", make_docx())}).status_code == 422
    listed = client.get("/library", headers=h).json()
    assert [d["filename"] for d in listed["documents"]] == ["charte.docx"]
    assert "text" not in listed["documents"][0]  # list stays light
    assert client.delete(f"/library/{added.json()['id']}", headers=h).status_code == 200
    assert client.get("/library", headers=h).json()["documents"] == []


def test_draft_records_its_sources(fresh_db, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    validated("old", "Portail RH")
    db.add_reference("modele.docx", "Word", "template", "Rubriques : contexte, objectifs", "pm")
    seen = {}

    def fake_generate(brief, method, today=None, references=None, past=None):
        seen["refs"], seen["past"] = references, past
        return m1.normalize(proposal(["Must"]), method)

    monkeypatch.setattr(m1, "generate", fake_generate)
    r = TestClient(app).post("/projects/new/baseline/draft", headers={"X-Orbit-Token": "t"},
                             json={"brief": "Un nouveau projet suffisamment décrit pour passer."})
    assert r.status_code == 200
    assert r.json()["sources"] == {"documents": ["modele.docx"], "past_projects": ["Portail RH"]}
    assert seen["refs"][0]["text"].startswith("Rubriques") and len(seen["past"]) == 1
