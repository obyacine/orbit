"""Fill the PM's own Word template with a baseline: the exported charter keeps the template's title page,
headers, section order, styles and wording, with the project's content in each section.

How it works:
1. placeholders such as [Nom du projet], {{budget}}, «Sponsor» or <date de fin> are replaced everywhere,
   headers and footers included;
2. each heading of the template is matched to a part of the baseline by its words (contexte, objectifs,
   périmètre, parties prenantes, risques, livrables, planning, budget, validation...);
3. the example text under a matched heading is replaced by the project's content, written with the template's
   own styles; unmatched headings are kept as they are;
4. essential parts the template has no heading for (deliverables, risks, planning) are added at the end.

Pure python-docx on the document's XML; nothing is sent to the LLM here.
"""

from __future__ import annotations

import io
import re
import unicodedata
from datetime import date

from docx import Document
from docx.document import Document as DocxDocument
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.methods import DELIVERIES, FRAMEWORKS

# ------------------------------------------------------------------ text helpers


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", text).strip()


def _fmt(d: str | None) -> str:
    if not d:
        return "À préciser"
    try:
        return date.fromisoformat(d[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return d


# ------------------------------------------------------------------ what each section receives

# (key, words that identify it in a heading). Order matters: "hors périmètre" before "périmètre".
SECTION_WORDS: list[tuple[str, tuple[str, ...]]] = [
    ("scope_out", ("hors perimetre", "hors scope", "exclu", "out of scope")),
    ("scope_in", ("perimetre", "scope", "contenu du projet")),
    ("success", ("critere", "succes", "indicateur", "kpi", "mesure de la reussite")),
    ("objectives", ("objectif", "finalite", "but du projet", "goals")),
    ("context", ("contexte", "enjeu", "probleme", "presentation", "description du projet", "introduction", "besoin")),
    ("stakeholders", ("partie prenante", "parties prenantes", "gouvernance", "acteur", "organisation", "equipe",
                      "roles", "stakeholder")),
    ("constraints", ("contrainte", "hypothese", "prerequis", "dependance")),
    ("risks", ("risque", "risk")),
    ("deliverables", ("livrable", "exigence", "backlog", "fonctionnalit", "deliverable")),
    ("planning", ("planning", "jalon", "calendrier", "phase", "decoupage", "sprint", "lot", "macro-planning",
                  "milestone", "echeancier")),
    ("budget", ("budget", "cout", "financ", "ressource")),
    ("validation", ("validation", "approbation", "signature", "visa")),
]
ESSENTIAL = ("deliverables", "risks", "planning")
APPENDIX_TITLES = {"deliverables": "Livrables priorisés", "risks": "Registre des risques", "planning": "Planning"}


def section_keys(heading: str) -> list[str]:
    """Parts of the baseline a heading asks for (a heading may ask for several: 'Objectifs et critères')."""
    text = _norm(heading)
    keys: list[str] = []
    for key, words in SECTION_WORDS:
        if any(w in text for w in words):
            if key == "scope_in" and "scope_out" in keys:
                continue
            keys.append(key)
    return keys


def _blocks(key: str, baseline: dict) -> list[tuple]:
    """Content of one part, as ('p', text) / ('bullets', [..]) / ('table', head, rows) blocks."""
    c = baseline["content"]
    ch = c["charter"]
    epics = {e["id"]: e for e in c["epics"]}
    milestones = {m["id"]: m for m in c["milestones"]}
    fw = FRAMEWORKS.get((baseline.get("method") or {}).get("prioritization", ""))
    if key == "context":
        return [("p", ch.get("context") or "À préciser")]
    if key == "objectives":
        return [("bullets", ch.get("objectives") or ["À préciser"])]
    if key == "success":
        return [("bullets", ch.get("success_criteria") or ["À préciser"])]
    if key == "scope_in":
        return [("bullets", ch.get("scope_in") or ["À préciser"])]
    if key == "scope_out":
        return [("bullets", ch.get("scope_out") or ["À préciser"])]
    if key == "constraints":
        return [("bullets", ch.get("constraints") or ["À préciser"])]
    if key == "stakeholders":
        return [("table", ["Partie prenante", "Rôle", "Influence"],
                 [[s["name"], s["role"], s["influence"]] for s in ch.get("stakeholders", [])])]
    if key == "risks":
        return [("table", ["Id", "Risque", "Probabilité", "Impact", "Mitigation"],
                 [[r["id"], r["description"], r["probability"], r["impact"], r["mitigation"]] for r in ch.get("risks", [])])]
    if key == "deliverables":
        return [("table", ["Id", "Livrable", f"Priorité{f' ({fw.name})' if fw else ''}", "Epic / phase", "Échéance"],
                 [[d["id"], d["title"], d["priority"], epics.get(d["epic_id"], {}).get("name", d["epic_id"]),
                   _fmt(d.get("due_date"))] for d in c["deliverables"]])]
    if key == "planning":
        blocks: list[tuple] = [("table", ["Epic / phase", "Début", "Fin"],
                                [[e["name"], _fmt(e.get("start_date")) if e.get("start_date") else "—",
                                  _fmt(e.get("end_date")) if e.get("end_date") else "—"] for e in c["epics"]])]
        if milestones:
            blocks.append(("table", ["Sprint / jalon", "Début", "Fin"],
                           [[m["name"], _fmt(m["start_date"]), _fmt(m["end_date"])] for m in c["milestones"]]))
        return blocks
    if key == "budget":
        return [("p", (f"Budget : {ch.get('budget') or 'À préciser'}. "
                      f"Période : du {_fmt(ch.get('start_date'))} au {_fmt(ch.get('end_date'))}."))]
    if key == "validation":
        if baseline.get("status") == "validated":
            return [("p", (f"Baseline v{baseline.get('version', 1)} validée par {baseline.get('validated_by')} le "
                          f"{_fmt(baseline.get('validated_at'))}. Elle constitue la référence du projet."))]
        return [("p", "Brouillon, en attente de validation par le chef de projet.")]
    return []


# ------------------------------------------------------------------ placeholders

_PLACEHOLDER = re.compile(r"\{\{\s*([^}]+?)\s*\}\}|\[\s*([^\]]+?)\s*\]|«\s*([^»]+?)\s*»|<\s*([^<>]+?)\s*>")


def _values(baseline: dict) -> list[tuple[tuple[str, ...], str]]:
    c = baseline["content"]
    ch = c["charter"]
    method = baseline.get("method") or {}
    sponsor = next((s["name"] for s in ch.get("stakeholders", []) if "sponsor" in _norm(s.get("role", ""))), "À préciser")
    delivery = DELIVERIES.get(method.get("delivery", ""))
    fw = FRAMEWORKS.get(method.get("prioritization", ""))
    return [
        (("nom du projet", "titre du projet", "intitule", "projet", "titre", "project name"), ch["title"]),
        (("date de debut", "debut", "start"), _fmt(ch.get("start_date"))),
        (("date de fin", "fin", "echeance", "end date", "date de livraison"), _fmt(ch.get("end_date"))),
        (("budget", "montant", "cout"), ch.get("budget") or "À préciser"),
        (("sponsor", "commanditaire"), sponsor),
        (("chef de projet", "cdp", "responsable", "project manager", "pm"),
         baseline.get("validated_by") or baseline.get("created_by") or "À préciser"),
        (("methode", "methodologie"), f"{delivery.name if delivery else ''} · {fw.name if fw else ''}".strip(" ·")),
        (("version",), f"v{baseline.get('version', 1)}"),
        (("date",), date.today().strftime("%d/%m/%Y")),
    ]


def _replacement(label: str, values: list[tuple[tuple[str, ...], str]]) -> str | None:
    text = _norm(label)
    for keys, value in values:  # exact names first, then names contained in the label
        if text in keys:
            return value
    for keys, value in values:
        if any(k in text for k in keys if len(k) > 3):
            return value
    return None


def _fill_paragraph(p: Paragraph, values: list[tuple[tuple[str, ...], str]]) -> bool:
    if not _PLACEHOLDER.search(p.text):
        return False

    def sub(m: re.Match) -> str:
        label = next(g for g in m.groups() if g)
        value = _replacement(label, values)
        return value if value is not None else m.group(0)

    new = _PLACEHOLDER.sub(sub, p.text)
    if new == p.text:
        return False
    runs = p.runs
    if runs:  # keep the first run's formatting, drop the others (placeholders are often split across runs)
        runs[0].text = new
        for r in runs[1:]:
            r._r.getparent().remove(r._r)
    return True


def _all_paragraphs(doc: DocxDocument):
    yield from doc.paragraphs
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                yield from cell.paragraphs
    for section in doc.sections:
        for part in (section.header, section.footer, section.first_page_header, section.first_page_footer):
            if part is not None and not part.is_linked_to_previous:
                yield from part.paragraphs
                for table in part.tables:
                    for row in table.rows:
                        for cell in row.cells:
                            yield from cell.paragraphs


# ------------------------------------------------------------------ document structure


def _heading_level(p: Paragraph) -> int | None:
    """Heading level of a paragraph: Word heading styles (English or French), or a short numbered bold line."""
    name = _norm(p.style.name if p.style is not None else "")
    m = re.match(r"(heading|titre)\s*(\d)", name)
    if m:
        return int(m.group(2))
    text = p.text.strip()
    bold = p.runs and all(r.bold for r in p.runs if r.text.strip())
    if bold and len(text) < 90 and re.match(r"^(\d+(\.\d+)*[.)]?|[IVX]+[.)])\s+\S", text):
        return text.split()[0].count(".") + 1 if "." in text.split()[0].rstrip(".") else 1
    return None


def _is_title(p: Paragraph) -> bool:
    return _norm(p.style.name if p.style is not None else "") in ("title", "titre")


def _style_or(doc: DocxDocument, *names: str) -> str | None:
    available = {s.name for s in doc.styles}
    return next((n for n in names if n in available), None)


def _el(block):
    return block._p if isinstance(block, Paragraph) else block._tbl


def _new_paragraph_after(doc: DocxDocument, anchor, text: str, style: str | None) -> Paragraph:
    p = doc.add_paragraph(text, style=style)
    _el(anchor).addnext(p._p)
    return p


def _new_table_after(doc: DocxDocument, anchor, head: list[str], rows: list[list[str]], style: str | None) -> Table:
    table = doc.add_table(rows=1, cols=len(head))
    if style:
        table.style = style
    for cell, text in zip(table.rows[0].cells, head):
        cell.text = text
        for run in cell.paragraphs[0].runs:
            run.bold = True
    for row in rows:
        for cell, text in zip(table.add_row().cells, row):
            cell.text = str(text or "")
    _el(anchor).addnext(table._tbl)
    return table


def _write_blocks(doc: DocxDocument, anchor, blocks: list[tuple], styles: dict):
    """Writes the blocks after `anchor`, in order; returns the last element written."""
    last = anchor
    for block in blocks:
        if block[0] == "p":
            last = _new_paragraph_after(doc, last, block[1], styles["body"])
        elif block[0] == "bullets":
            for item in block[1]:
                text = item if styles["bullet"] else f"• {item}"
                last = _new_paragraph_after(doc, last, text, styles["bullet"] or styles["body"])
        elif block[0] == "table":
            last = _new_table_after(doc, last, block[1], block[2], styles["table"])
            last = _new_paragraph_after(doc, last, "", styles["body"])  # breathing space after a table
    return last


def _body_after(heading_el, headings: dict) -> list:
    """Example content right under a heading, up to the next heading of any level."""
    out = []
    el = heading_el.getnext()
    while el is not None and el.tag != qn("w:sectPr") and el not in headings:
        out.append(el)
        el = el.getnext()
    return out


# ------------------------------------------------------------------ entry point


def fill_template(template_bytes: bytes, baseline: dict) -> tuple[bytes, dict]:
    """Returns the filled .docx and a report (sections filled, kept, appended, placeholders replaced)."""
    doc = Document(io.BytesIO(template_bytes))
    styles = {
        "body": _style_or(doc, "Normal", "Corps de texte", "Body Text"),
        "bullet": _style_or(doc, "List Bullet", "Liste à puces", "List Paragraph", "Paragraphe de liste"),
        "table": _style_or(doc, "Table Grid", "Grille du tableau", "Light Grid Accent 1"),
    }
    values = _values(baseline)
    report = {"filled": [], "kept": [], "appended": [], "placeholders": 0}

    report["placeholders"] = sum(1 for p in list(_all_paragraphs(doc)) if _fill_paragraph(p, values))

    # The project title goes into the template's title if no placeholder already carried it.
    title_text = baseline["content"]["charter"]["title"]
    title_p = next((p for p in doc.paragraphs if _is_title(p)), None)
    if title_p is not None and title_text not in title_p.text:
        base = re.sub(r"\s*[-—:|]\s*$", "", title_p.text.strip())
        new = f"{base} — {title_text}" if base else title_text
        if title_p.runs:
            title_p.runs[0].text = new
            for r in title_p.runs[1:]:
                r._r.getparent().remove(r._r)

    paragraphs = [p for p in doc.paragraphs if _heading_level(p) is not None]
    headings = {p._p: _heading_level(p) for p in paragraphs}
    keys_of = [section_keys(p.text) for p in paragraphs]
    covered: set[str] = set()
    for i, p in enumerate(paragraphs):
        keys = [k for k in keys_of[i] if k not in covered]
        if not keys:
            report["kept"].append(p.text.strip())
            continue
        # Sub-headings that ask for the same part fill it themselves ("Périmètre" > "Inclus" / "Exclu").
        level, children = headings[p._p], set()
        for j in range(i + 1, len(paragraphs)):
            if headings[paragraphs[j]._p] <= level:
                break
            children.update(keys_of[j])
        if set(keys) & children or (set(keys) == {"scope_in"} and "scope_out" in children):
            continue
        for el in _body_after(p._p, headings):
            el.getparent().remove(el)
        _write_blocks(doc, p, [b for k in keys for b in _blocks(k, baseline)], styles)
        covered.update(keys)
        report["filled"].append(p.text.strip())

    missing = [k for k in ESSENTIAL if k not in covered]
    if missing:
        h_style = _style_or(doc, "Heading 1", "Titre 1")
        anchor = doc.add_paragraph("Annexes Orbit", style=h_style)
        for key in missing:
            sub = _new_paragraph_after(doc, anchor, APPENDIX_TITLES[key], _style_or(doc, "Heading 2", "Titre 2", h_style))
            anchor = _write_blocks(doc, sub, _blocks(key, baseline), styles)
            report["appended"].append(APPENDIX_TITLES[key])

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue(), report

