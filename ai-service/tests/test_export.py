"""Word export of the charter."""

import io

from docx import Document

from app import db
from app.config import get_settings
from app.module1 import export
from tests.test_baseline import proposal


def test_charter_docx_contains_every_section():
    content = proposal(["Must", "Should"]).model_dump()
    content["charter"]["risks"] = [{"id": "R1", "description": "[Technique] Intégration SIRH", "probability": "haute",
                                    "impact": "haut", "mitigation": "POC"}]
    baseline = {"content": content, "method": {"delivery": "scrum", "prioritization": "moscow"}, "status": "validated",
                "version": 2, "validated_by": "pm", "validated_at": "2026-11-21T10:00:00",
                "sources": {"documents": ["modele.docx"], "past_projects": []}}
    doc = Document(io.BytesIO(export.charter_docx(baseline)))
    text = "\n".join(p.text for p in doc.paragraphs)
    cells = " ".join(c.text for t in doc.tables for row in t.rows for c in row.cells)
    assert "Portail RH" in text and "Baseline validée v2 · Scrum · priorisation MoSCoW" in text
    for section in ("1. Contexte", "4. Périmètre", "7. Registre des risques", "9. Livrables priorisés (MoSCoW)", "10. Validation"):
        assert section in text
    assert "[Technique] Intégration SIRH" in cells and "180 k€" in cells and "L0" in cells
    assert "modele.docx" in text
    assert export.filename(baseline) == "Charte-Portail-RH-v2.docx"


def test_export_endpoint(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "orbit.db"))
    monkeypatch.setenv("ORBIT_INTERNAL_TOKEN", "t")
    get_settings.cache_clear()
    try:
        b = db.save_baseline_draft("p", "brief", {"delivery": "scrum", "prioritization": "moscow"},
                                   proposal(["Must"]).model_dump(), "pm")
        client = TestClient(app)
        r = client.get(f"/baselines/{b['id']}/export.docx", headers={"X-Orbit-Token": "t"})
        assert r.status_code == 200 and r.content[:2] == b"PK"  # a .docx is a zip
        assert "Charte-Portail-RH-v1.docx" in r.headers["content-disposition"]
        assert client.get("/baselines/nope/export.docx", headers={"X-Orbit-Token": "t"}).status_code == 404
    finally:
        get_settings.cache_clear()


# ------------------------------------------------------------------ the PM's own Word template

from docx.shared import RGBColor  # noqa: E402

from app.module1 import template_fill  # noqa: E402


def make_template() -> bytes:
    """A company charter template: header with placeholders, title, numbered headings, sub-headings, example text."""
    doc = Document()
    doc.sections[0].header.paragraphs[0].text = "DSI Groupe · Charte projet · [Nom du projet] · {{version}}"
    doc.add_paragraph("Charte projet", style="Title")
    doc.add_paragraph("Sponsor : «Sponsor» — Échéance : <date de fin> — Budget : [budget]")
    h = doc.add_heading("1. Contexte et enjeux", level=1)
    h.runs[0].font.color.rgb = RGBColor(0xC0, 0x00, 0x00)  # the company's own heading color
    doc.add_paragraph("Décrire ici le contexte du projet (exemple à remplacer).")
    doc.add_heading("2. Objectifs et critères de succès", level=1)
    doc.add_paragraph("Lister les objectifs SMART.")
    doc.add_heading("3. Périmètre", level=1)
    doc.add_heading("3.1 Dans le périmètre", level=2)
    doc.add_paragraph("…")
    doc.add_heading("3.2 Hors périmètre", level=2)
    doc.add_paragraph("…")
    doc.add_heading("4. Gouvernance", level=1)
    doc.add_paragraph("Comité de pilotage, rôles.")
    doc.add_heading("5. Règles de communication interne", level=1)
    doc.add_paragraph("Texte propre à l'entreprise, à conserver tel quel.")
    doc.add_heading("6. Validation", level=1)
    doc.add_paragraph("Signatures.")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def validated_baseline() -> dict:
    content = proposal(["Must", "Should"]).model_dump()
    content["charter"]["stakeholders"] = [{"name": "DRH", "role": "Sponsor", "influence": "haute"}]
    content["charter"]["scope_out"] = ["Notes de frais"]
    content["charter"]["end_date"] = "2027-03-31"
    return {"content": content, "method": {"delivery": "scrum", "prioritization": "moscow"}, "status": "validated",
            "version": 1, "validated_by": "obyacine73", "validated_at": "2026-11-21T10:00:00", "sources": {}}


def test_section_matching():
    assert template_fill.section_keys("2. Objectifs et critères de succès") == ["success", "objectives"]
    assert template_fill.section_keys("3.2 Hors périmètre") == ["scope_out"]
    assert template_fill.section_keys("Gouvernance du projet") == ["stakeholders"]
    assert template_fill.section_keys("Règles de communication interne") == []


def test_fill_keeps_the_template_and_puts_the_project_in_it():
    out, report = template_fill.fill_template(make_template(), validated_baseline())
    doc = Document(io.BytesIO(out))
    text = "\n".join(p.text for p in doc.paragraphs)
    cells = " ".join(c.text for t in doc.tables for row in t.rows for c in row.cells)

    # placeholders, header included
    assert doc.sections[0].header.paragraphs[0].text == "DSI Groupe · Charte projet · Portail RH · v1"
    assert "Sponsor : DRH — Échéance : 31/03/2027 — Budget : 180 k€" in text
    assert "Charte projet — Portail RH" in text  # template title + project title

    # the template's headings, order and styling are kept
    headings = [p.text for p in doc.paragraphs if p.style.name.startswith("Heading")]
    assert headings[:9] == ["1. Contexte et enjeux", "2. Objectifs et critères de succès", "3. Périmètre",
                            "3.1 Dans le périmètre", "3.2 Hors périmètre", "4. Gouvernance",
                            "5. Règles de communication interne", "6. Validation", "Annexes Orbit"]
    first = next(p for p in doc.paragraphs if p.text == "1. Contexte et enjeux")
    assert first.runs[0].font.color.rgb == RGBColor(0xC0, 0x00, 0x00)

    # example text replaced by the project; company text kept
    assert "exemple à remplacer" not in text and "Lister les objectifs" not in text
    assert "Texte propre à l'entreprise, à conserver tel quel." in text
    assert "Notes de frais" in text and "DRH" in cells
    assert "validée par obyacine73" in text

    # what the template had no place for is appended
    assert report["appended"] == ["Livrables priorisés", "Registre des risques", "Planning"]
    assert "L0" in cells
    assert "5. Règles de communication interne" in report["kept"]


def test_export_uses_the_library_template(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "orbit.db"))
    monkeypatch.setenv("ORBIT_INTERNAL_TOKEN", "t")
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        h = {"X-Orbit-Token": "t"}
        client.post("/library?role=template", headers=h, files={"file": ("charte_dsi.docx", make_template())})
        b = db.save_baseline_draft("p", "brief", {"delivery": "scrum", "prioritization": "moscow"},
                                   proposal(["Must"]).model_dump(), "pm")
        r = client.get(f"/baselines/{b['id']}/export.docx", headers=h)
        assert r.status_code == 200 and r.headers["x-orbit-layout"] == "charte_dsi.docx"
        doc = Document(io.BytesIO(r.content))
        assert doc.sections[0].header.paragraphs[0].text.startswith("DSI Groupe · Charte projet · Portail RH")
    finally:
        get_settings.cache_clear()
