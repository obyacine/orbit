"""Word export of a baseline: the project charter the PM can send to the sponsor or the steering committee.

The content already follows the organization's templates (the LLM reused their sections, risk categories and
mandatory deliverables when it drafted the baseline); this module only lays it out as a .docx.
"""

from __future__ import annotations

import io
from datetime import date

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor

from app.methods import DELIVERIES, FRAMEWORKS

_ACCENT = RGBColor(0x4F, 0x46, 0xE5)
_MUTED = RGBColor(0x5A, 0x5E, 0x72)


def _fmt(d: str | None) -> str:
    if not d:
        return "À préciser"
    try:
        return date.fromisoformat(d[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return d


def _heading(doc: Document, text: str, level: int = 1) -> None:
    h = doc.add_heading(text, level=level)
    for run in h.runs:
        run.font.color.rgb = _ACCENT


def _bullets(doc: Document, items: list[str]) -> None:
    if not items:
        doc.add_paragraph("À préciser")
        return
    for item in items:
        doc.add_paragraph(item, style="List Bullet")


def _table(doc: Document, head: list[str], rows: list[list[str]]) -> None:
    table = doc.add_table(rows=1, cols=len(head))
    table.style = "Light Grid Accent 1"
    for cell, text in zip(table.rows[0].cells, head):
        cell.text = text
        for run in cell.paragraphs[0].runs:
            run.bold = True
    for row in rows:
        cells = table.add_row().cells
        for cell, text in zip(cells, row):
            cell.text = str(text or "")
    doc.add_paragraph()


def charter_docx(baseline: dict) -> bytes:
    """A .docx of the baseline: charter, risks, breakdown, prioritized deliverables, validation."""
    content = baseline["content"]
    ch = content["charter"]
    method = baseline.get("method") or {}
    delivery = DELIVERIES.get(method.get("delivery", ""))
    framework = FRAMEWORKS.get(method.get("prioritization", ""))
    epics = {e["id"]: e for e in content["epics"]}
    milestones = {m["id"]: m for m in content["milestones"]}

    doc = Document()
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(10.5)

    # ---------------------------------------------------------------- cover
    title = doc.add_heading(ch["title"], level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.LEFT
    sub = doc.add_paragraph()
    status = "Baseline validée" if baseline.get("status") == "validated" else "Brouillon"
    run = sub.add_run(
        f"Charte projet · {status} v{baseline.get('version', 1)} · "
        f"{delivery.name if delivery else method.get('delivery', '')} · "
        f"priorisation {framework.name if framework else method.get('prioritization', '')}"
    )
    run.font.color.rgb = _MUTED

    _table(doc, ["Budget", "Début", "Fin"], [[ch.get("budget") or "À préciser", _fmt(ch.get("start_date")), _fmt(ch.get("end_date"))]])

    # ---------------------------------------------------------------- charter
    _heading(doc, "1. Contexte")
    doc.add_paragraph(ch.get("context") or "À préciser")

    _heading(doc, "2. Objectifs")
    _bullets(doc, ch.get("objectives", []))

    _heading(doc, "3. Critères de succès")
    _bullets(doc, ch.get("success_criteria", []))

    _heading(doc, "4. Périmètre")
    _heading(doc, "Dans le périmètre", level=2)
    _bullets(doc, ch.get("scope_in", []))
    _heading(doc, "Hors périmètre", level=2)
    _bullets(doc, ch.get("scope_out", []))

    _heading(doc, "5. Parties prenantes")
    _table(doc, ["Partie prenante", "Rôle", "Influence"],
           [[s["name"], s["role"], s["influence"]] for s in ch.get("stakeholders", [])])

    _heading(doc, "6. Contraintes")
    _bullets(doc, ch.get("constraints", []))

    _heading(doc, "7. Registre des risques")
    _table(doc, ["Id", "Risque", "Probabilité", "Impact", "Mitigation"],
           [[r["id"], r["description"], r["probability"], r["impact"], r["mitigation"]] for r in ch.get("risks", [])])

    # ---------------------------------------------------------------- breakdown
    _heading(doc, "8. Découpage")
    _table(doc, ["Id", "Epic / phase", "Description", "Début", "Fin"],
           [[e["id"], e["name"], e.get("description", ""),
             _fmt(e.get("start_date")) if e.get("start_date") else "—",
             _fmt(e.get("end_date")) if e.get("end_date") else "—"] for e in content["epics"]])
    if content["milestones"]:
        _table(doc, ["Sprint / jalon", "Début", "Fin"],
               [[m["name"], _fmt(m["start_date"]), _fmt(m["end_date"])] for m in content["milestones"]])

    _heading(doc, f"9. Livrables priorisés ({framework.name if framework else ''})")
    _table(doc, ["Id", "Livrable", "Priorité", "Epic / phase", "Sprint", "Échéance"],
           [[d["id"], d["title"], d["priority"], epics.get(d["epic_id"], {}).get("name", d["epic_id"]),
             milestones.get(d.get("milestone_id", ""), {}).get("name", "—"), _fmt(d.get("due_date"))]
            for d in content["deliverables"]])

    # ---------------------------------------------------------------- validation
    _heading(doc, "10. Validation")
    if baseline.get("status") == "validated":
        doc.add_paragraph(f"Baseline validée par {baseline.get('validated_by')} le {_fmt(baseline.get('validated_at'))}. "
                          "Elle constitue la référence du projet : les écarts sont suivis par Orbit.")
    else:
        doc.add_paragraph("Brouillon, en attente de validation par le chef de projet.")
    sources = baseline.get("sources") or {}
    used = [*sources.get("documents", []), *sources.get("past_projects", [])]
    if used:
        p = doc.add_paragraph()
        r = p.add_run("Établie à partir des références de l'organisation : " + ", ".join(used) + ".")
        r.font.color.rgb = _MUTED

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def filename(baseline: dict) -> str:
    safe = "".join(ch if ch.isalnum() else "-" for ch in baseline["content"]["charter"]["title"]).strip("-")
    return f"Charte-{safe[:60] or 'projet'}-v{baseline.get('version', 1)}.docx"
