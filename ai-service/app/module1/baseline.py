"""Module 1 — the contract.

brief  --LLM-->  draft baseline (charter + epics/phases + milestones/sprints + prioritized deliverables)
       --PM edits & validates-->  frozen baseline  --push-->  labels, modules, cycles and work items in Orbit.

The LLM only *proposes*; `normalize()` makes the proposal consistent with the PM's method
(allowed priorities, ids, references, dates) before any human sees it, and nothing reaches the
tracker without validation.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from app import llm
from app.methods import CRITICAL, EXCLUDED, IMPORTANT, OPTIONAL, ProjectMethod
from app.plane_client import PlaneClient

# ------------------------------------------------------------------ schema (also sent to the LLM)


class Stakeholder(BaseModel):
    name: str = Field(description="Nom ou fonction (ex. « DSI », « Direction marketing »)")
    role: str = Field(description="Rôle dans le projet (sponsor, utilisateur, valideur...)")
    influence: str = Field(description="haute | moyenne | faible")


class Risk(BaseModel):
    id: str = Field(description="R1, R2...")
    description: str
    probability: str = Field(description="haute | moyenne | faible")
    impact: str = Field(description="haut | moyen | faible")
    mitigation: str


class Charter(BaseModel):
    title: str
    context: str = Field(description="Contexte et problème à résoudre, 2 à 4 phrases")
    objectives: list[str] = Field(description="Objectifs SMART")
    scope_in: list[str] = Field(description="Ce qui est dans le périmètre")
    scope_out: list[str] = Field(description="Ce qui est explicitement hors périmètre")
    budget: str = Field(description="Budget du brief, ou « À préciser »")
    start_date: str = Field(description="AAAA-MM-JJ")
    end_date: str = Field(description="AAAA-MM-JJ")
    stakeholders: list[Stakeholder]
    constraints: list[str]
    success_criteria: list[str]
    risks: list[Risk]


class Epic(BaseModel):
    id: str = Field(description="E1, E2...")
    name: str
    description: str
    start_date: str = Field(description="AAAA-MM-JJ, ou chaîne vide si la méthode n'utilise pas de phases")
    end_date: str = Field(description="AAAA-MM-JJ, ou chaîne vide si la méthode n'utilise pas de phases")


class Milestone(BaseModel):
    id: str = Field(description="J1, J2... (sprints ou jalons)")
    name: str
    start_date: str = Field(description="AAAA-MM-JJ")
    end_date: str = Field(description="AAAA-MM-JJ")


class Deliverable(BaseModel):
    id: str
    title: str
    description: str
    epic_id: str
    milestone_id: str = Field(description="Id du sprint / jalon, ou chaîne vide")
    priority: str
    due_date: str = Field(description="AAAA-MM-JJ")


class Baseline(BaseModel):
    charter: Charter
    epics: list[Epic]
    milestones: list[Milestone]
    deliverables: list[Deliverable]


class BaselineError(RuntimeError):
    pass


# ------------------------------------------------------------------ method-specific instructions


def _priority_rules(method: ProjectMethod) -> tuple[str, list[str] | None]:
    """Instruction for the `priority` field, and the allowed values (None = numeric score)."""
    fw = method.framework
    if fw.source == "label":
        allowed = [c.label for c in fw.categories]
        meaning = ", ".join(f"« {c.label} » = {fw.tier_labels[c.tier]}" for c in fw.categories)
        return f"Méthode {fw.name}. `priority` vaut exactement une de ces valeurs : {meaning}.", allowed
    if fw.source == "priority":
        return ("Priorité native. `priority` vaut exactement : urgent, high, medium ou low.",
                ["urgent", "high", "medium", "low"])
    if fw.source == "custom":
        allowed = list(method.custom_mapping)
        return f"Labels du PM. `priority` vaut exactement une de ces valeurs : {', '.join(allowed)}.", allowed
    formula = {
        "rice": "RICE = (Reach × Impact × Confidence) / Effort",
        "wsjf": "WSJF = (valeur métier + criticité temporelle + réduction de risque) / taille du job, échelle Fibonacci",
        "ice": "ICE = Impact × Confidence × Ease, chacun de 1 à 10",
    }[fw.id]
    return f"Méthode {fw.name} ({formula}). `priority` est le score calculé, un nombre seul (ex. « 13 »).", None


def _delivery_rules(method: ProjectMethod, today: date) -> str:
    d = method.delivery_method
    if d.id == "scrum":
        return ("Pilotage Scrum : `milestones` = sprints consécutifs de 2 semaines couvrant le projet. "
                "Chaque livrable est affecté à un sprint (`milestone_id`) et `due_date` = fin de ce sprint. "
                "Les epics n'ont pas de dates (chaînes vides).")
    if d.id == "kanban":
        return ("Pilotage Kanban : flux continu, `milestones` = liste vide, `milestone_id` = chaîne vide. "
                "Les epics n'ont pas de dates. Chaque livrable a une `due_date` réaliste.")
    if d.id == "waterfall":
        return ("Pilotage cycle en V / Waterfall : les `epics` sont les phases séquentielles (ex. Cadrage, "
                "Spécifications, Réalisation, Recette, Déploiement), avec des dates qui se suivent sans se chevaucher. "
                "`milestones` = liste vide, `milestone_id` = chaîne vide. La `due_date` d'un livrable tombe dans sa phase.")
    return ("Pilotage hybride : les `epics` sont des phases datées et séquentielles ; `milestones` = sprints de "
            "2 semaines consécutifs. Chaque livrable a une phase, un sprint et une `due_date` = fin du sprint.")


_ROLE_LABEL = {"template": "modèle de l'organisation", "past_project": "document d'un projet passé", "standard": "standard interne"}
MAX_REFERENCE_CHARS = 12_000  # per document
MAX_REFERENCES_CHARS = 36_000  # all documents together


def summarize_baseline(b: dict) -> str:
    """Compact view of a validated baseline of another project, used as an example."""
    c = b["content"]
    ch = c["charter"]
    lines = [
        (f"Projet « {ch['title']} » ({ch.get('start_date') or '?'} → {ch.get('end_date') or '?'}), "
         f"méthode {b['method'].get('delivery')} + {b['method'].get('prioritization')}."),
        "Epics : " + " ; ".join(e["name"] for e in c["epics"]),
        "Livrables : " + " ; ".join(f"[{d['priority']}] {d['title']}" for d in c["deliverables"][:25]),
        "Risques : " + " ; ".join(r["description"] for r in ch.get("risks", [])[:8]),
    ]
    return "\n".join(lines)


def reference_section(references: list[dict], past: list[dict]) -> str:
    """What the organization already wrote: the agent reuses its structure and habits, never its facts."""
    if not references and not past:
        return ""
    parts = [
        ("Bibliothèque de l'organisation. Inspire-toi de ces documents pour la structure et les rubriques de la "
         "charte, le vocabulaire, le niveau de détail, les livrables et risques habituels, et des durées réalistes. "
         "N'en recopie JAMAIS les faits (budget, dates, noms, chiffres) : les faits viennent uniquement du brief."),
    ]
    budget = MAX_REFERENCES_CHARS
    for i, r in enumerate(references, 1):
        if budget <= 0:
            break
        text = r["text"][: min(MAX_REFERENCE_CHARS, budget)]
        budget -= len(text)
        parts.append(f'=== Référence {i} : {r["filename"]} ({_ROLE_LABEL.get(r["role"], r["role"])}) ===\n{text}')
    for b in past:
        parts.append(f"=== Projet passé validé ===\n{summarize_baseline(b)}")
    return "\n\n".join(parts) + "\n\n"


def build_prompt(
    brief: str,
    method: ProjectMethod,
    today: date,
    references: list[dict] | None = None,
    past: list[dict] | None = None,
) -> str:
    rules, _ = _priority_rules(method)
    id_rule = (
        "Ids des livrables : la première lettre de la catégorie suivie d'un numéro (M1, M2, S1, C1, W1...)."
        if method.prioritization == "moscow"
        else "Ids des livrables : D1, D2, D3..."
    )
    return f"""Date du jour : {today.isoformat()}. Si le brief ne donne pas de date de début, le projet commence le
prochain lundi. Toutes les dates sont au format AAAA-MM-JJ.

Méthodes choisies par le chef de projet :
- {rules}
- {_delivery_rules(method, today)}
- {id_rule}

Consignes :
- Entre 8 et 25 livrables, couvrant tout le périmètre, chacun rattaché à un epic existant (`epic_id`).
- Entre 3 et 6 epics. Entre 3 et 8 risques. Priorités réalistes : tout ne peut pas être critique.
- Les livrables hors périmètre ou abandonnés reçoivent la priorité la plus basse (ou « Won't » en MoSCoW).

{reference_section(references or [], past or [])}Brief du projet :
\"\"\"
{brief.strip()}
\"\"\"
"""


# ------------------------------------------------------------------ consistency checks on the LLM proposal


def _valid_date(value: str | None) -> str:
    try:
        return date.fromisoformat((value or "")[:10]).isoformat()
    except ValueError:
        return ""


def _score(value: str) -> str:
    m = re.search(r"-?\d+(?:[.,]\d+)?", value or "")
    if not m:
        return "0"
    n = float(m.group(0).replace(",", "."))
    return str(int(n)) if n == int(n) else f"{n:g}"


def normalize(baseline: Baseline, method: ProjectMethod) -> Baseline:
    _, allowed = _priority_rules(method)
    d = method.delivery_method

    epics = baseline.epics or [Epic(id="E1", name="Général", description="", start_date="", end_date="")]
    for i, e in enumerate(epics, 1):
        e.id = e.id or f"E{i}"
        e.start_date, e.end_date = (_valid_date(e.start_date), _valid_date(e.end_date)) if d.uses_phases else ("", "")
    epic_ids = {e.id for e in epics}

    milestones = [m for m in baseline.milestones if _valid_date(m.start_date) and _valid_date(m.end_date)]
    milestones = milestones if d.uses_cycles else []
    for i, m in enumerate(milestones, 1):
        m.id, m.start_date, m.end_date = m.id or f"J{i}", _valid_date(m.start_date), _valid_date(m.end_date)
    milestone_ids = {m.id for m in milestones}

    seen: set[str] = set()
    lookup = {a.casefold(): a for a in allowed} if allowed else {}
    for n, x in enumerate(baseline.deliverables, 1):
        if allowed:
            x.priority = lookup.get((x.priority or "").strip().casefold(), allowed[min(1, len(allowed) - 1)])
        else:
            x.priority = _score(x.priority)
        x.epic_id = x.epic_id if x.epic_id in epic_ids else epics[0].id
        x.milestone_id = x.milestone_id if x.milestone_id in milestone_ids else ""
        x.due_date = _valid_date(x.due_date)
        x.id = x.id if x.id and x.id not in seen else f"D{n}"
        seen.add(x.id)
    if method.prioritization == "moscow":  # ids carry the category: M1, M2, S1, C1, W1...
        counters: dict[str, int] = {}
        for x in baseline.deliverables:
            letter = x.priority[0].upper()
            counters[letter] = counters.get(letter, 0) + 1
            x.id = f"{letter}{counters[letter]}"

    baseline.epics, baseline.milestones = epics, milestones
    baseline.charter.start_date = _valid_date(baseline.charter.start_date)
    baseline.charter.end_date = _valid_date(baseline.charter.end_date)
    return baseline


def generate(
    brief: str,
    method: ProjectMethod,
    today: date | None = None,
    references: list[dict] | None = None,
    past: list[dict] | None = None,
) -> Baseline:
    if len(brief.strip()) < 30:
        raise BaselineError("Le brief est trop court : décrivez au moins le besoin, le périmètre et l'échéance.")
    prompt = build_prompt(brief, method, today or date.today(), references, past)
    proposal = llm.generate_json(prompt, Baseline)
    if proposal is None:
        raise BaselineError("L'IA n'a pas pu générer la baseline (clé absente ou service indisponible). Réessayez.")
    return normalize(proposal, method)


# ------------------------------------------------------------------ push the validated baseline to Orbit

_LABEL_COLORS = {CRITICAL: "#dc2626", IMPORTANT: "#f59e0b", OPTIONAL: "#3b82f6", EXCLUDED: "#6b7280"}
_TIER_TO_NATIVE = {CRITICAL: "urgent", IMPORTANT: "high", OPTIONAL: "medium", EXCLUDED: "low"}


def _label_and_priority(x: Deliverable, method: ProjectMethod) -> tuple[str | None, str, str]:
    """(label to put on the work item, native priority, tier) for a deliverable."""
    fw = method.framework
    if fw.source == "priority":
        return None, x.priority, {"urgent": CRITICAL, "high": IMPORTANT}.get(x.priority, OPTIONAL)
    if fw.source == "label":
        tier = next(c.tier for c in fw.categories if c.label == x.priority)
        return x.priority, _TIER_TO_NATIVE[tier], tier
    if fw.source == "custom":
        tier = method.custom_mapping.get(x.priority, OPTIONAL)
        return x.priority, _TIER_TO_NATIVE[tier], tier
    return f"{fw.score_prefix}:{x.priority}", "none", OPTIONAL


def _html(text: str) -> str:
    return "<p>" + (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") + "</p>"


def push(client: PlaneClient, project_id: str, baseline: Baseline, method: ProjectMethod) -> dict[str, Any]:
    """Create the validated baseline in the tracker. Returns the deliverable -> work item mapping."""
    d = method.delivery_method
    client.enable_features(project_id, modules=bool(baseline.epics), cycles=d.uses_cycles and bool(baseline.milestones))
    existing_labels = {lab["name"].casefold(): lab["id"] for lab in client.list_labels(project_id)}

    def label_id(name: str, tier: str) -> str:
        key = name.casefold()
        if key not in existing_labels:
            existing_labels[key] = client.create_label(project_id, name, _LABEL_COLORS.get(tier, "#6b7280"))["id"]
        return existing_labels[key]

    module_ids = {
        e.id: client.create_module(
            project_id, e.name, e.description,
            start_date=(e.start_date or None) if d.uses_phases else None,
            target_date=(e.end_date or None) if d.uses_phases else None,
        )["id"]
        for e in baseline.epics
    }
    cycle_ids = {
        m.id: client.create_cycle(project_id, m.name, m.start_date, m.end_date)["id"] for m in baseline.milestones
    } if d.uses_cycles else {}

    work_items: dict[str, str] = {}
    by_module: dict[str, list[str]] = {}
    by_cycle: dict[str, list[str]] = {}
    for x in baseline.deliverables:
        label, native, tier = _label_and_priority(x, method)
        payload: dict[str, Any] = {
            "name": f"[{x.id}] {x.title}",
            "description_html": _html(x.description),
            "priority": native,
        }
        if label:
            payload["labels"] = [label_id(label, tier)]
        if x.due_date:
            payload["target_date"] = x.due_date
        issue = client.create_issue(project_id, payload)
        work_items[x.id] = issue["id"]
        by_module.setdefault(module_ids[x.epic_id], []).append(issue["id"])
        if x.milestone_id in cycle_ids:
            by_cycle.setdefault(cycle_ids[x.milestone_id], []).append(issue["id"])

    for mid, ids in by_module.items():
        client.add_issues_to_module(project_id, mid, ids)
    for cid, ids in by_cycle.items():
        client.add_issues_to_cycle(project_id, cid, ids)

    return {
        "work_items": work_items,
        "counts": {"work_items": len(work_items), "modules": len(module_ids), "cycles": len(cycle_ids)},
    }

