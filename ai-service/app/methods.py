"""Project-management methods chosen by the PM, per project.

Two independent choices:

- **Prioritization** (MoSCoW, Kano, native priority, RICE, WSJF, ICE, value/effort, custom labels):
  every framework maps an issue to one of four common *tiers* (critical, important, optional,
  excluded). Anomaly rules reason on tiers, so they work with any framework, while messages keep
  the PM's own vocabulary ("Must-Have", "Basique", "WSJF 13"...).
- **Delivery** (Scrum, Kanban, Waterfall, hybrid): decides which metrics and rules apply and the
  words used in reports (sprint, phase, milestone).

No LLM here: classification is deterministic.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.module2.snapshot import Issue, ProjectSnapshot

CRITICAL, IMPORTANT, OPTIONAL, EXCLUDED = "critical", "important", "optional", "excluded"
TIERS = (CRITICAL, IMPORTANT, OPTIONAL, EXCLUDED)


# ------------------------------------------------------------------ prioritization frameworks


@dataclass(frozen=True)
class Category:
    label: str  # label to put on the issue in the tracker
    tier: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class Framework:
    id: str
    name: str
    description: str
    source: str  # "label" | "priority" | "score" | "custom"
    tier_labels: dict[str, str]  # how each tier is called in this framework
    categories: tuple[Category, ...] = ()
    score_prefix: str | None = None  # score frameworks: label "WSJF:13"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["categories"] = [c.label for c in self.categories]
        return d


FRAMEWORKS: dict[str, Framework] = {
    f.id: f
    for f in (
        Framework(
            "moscow", "MoSCoW", "Labels Must / Should / Could / Won't sur chaque élément.", "label",
            {CRITICAL: "Must-Have", IMPORTANT: "Should-Have", OPTIONAL: "Could-Have", EXCLUDED: "Won't-Have"},
            (
                Category("Must", CRITICAL, ("Must-Have", "Must have")),
                Category("Should", IMPORTANT, ("Should-Have", "Should have")),
                Category("Could", OPTIONAL, ("Could-Have", "Could have")),
                Category("Won't", EXCLUDED, ("Wont", "Won't-Have", "Won't have")),
            ),
        ),
        Framework(
            "kano", "Kano", "Labels Basique / Performance / Enthousiasmant / Indifférent.", "label",
            {CRITICAL: "Basique", IMPORTANT: "Performance", OPTIONAL: "Enthousiasmant", EXCLUDED: "Indifférent"},
            (
                Category("Basique", CRITICAL, ("Must-be", "Must be", "Basic")),
                Category("Performance", IMPORTANT, ("One-dimensional", "Linéaire")),
                Category("Enthousiasmant", OPTIONAL, ("Attractive", "Attractif", "Excitement", "Delighter")),
                Category("Indifférent", EXCLUDED, ("Indifferent", "Reverse", "Rejet")),
            ),
        ),
        Framework(
            "priority", "Priorité native", "Champ priorité d'Orbit (Urgent, Haute, Moyenne, Basse) — aucun label requis.",
            "priority",
            {CRITICAL: "Urgent", IMPORTANT: "Haute", OPTIONAL: "Moyenne / Basse", EXCLUDED: "Exclu"},
        ),
        Framework(
            "value_effort", "Matrice valeur / effort", "Labels Quick win / Gros projet / Bouche-trou / Ingrat.", "label",
            {CRITICAL: "Quick win", IMPORTANT: "Gros projet", OPTIONAL: "Bouche-trou", EXCLUDED: "Ingrat"},
            (
                Category("Quick win", CRITICAL, ("Quick-win", "Quick wins")),
                Category("Gros projet", IMPORTANT, ("Major project", "Big bet")),
                Category("Bouche-trou", OPTIONAL, ("Fill-in", "Fill in")),
                Category("Ingrat", EXCLUDED, ("Thankless", "Money pit", "Time sink")),
            ),
        ),
        Framework(
            "rice", "RICE", "Label « RICE:<score> » (Reach × Impact × Confidence / Effort).", "score",
            {CRITICAL: "RICE élevé", IMPORTANT: "RICE moyen", OPTIONAL: "RICE faible", EXCLUDED: "Exclu"},
            score_prefix="RICE",
        ),
        Framework(
            "wsjf", "WSJF (SAFe)", "Label « WSJF:<score> » (coût du délai / taille du job).", "score",
            {CRITICAL: "WSJF élevé", IMPORTANT: "WSJF moyen", OPTIONAL: "WSJF faible", EXCLUDED: "Exclu"},
            score_prefix="WSJF",
        ),
        Framework(
            "ice", "ICE", "Label « ICE:<score> » (Impact × Confidence × Ease).", "score",
            {CRITICAL: "ICE élevé", IMPORTANT: "ICE moyen", OPTIONAL: "ICE faible", EXCLUDED: "Exclu"},
            score_prefix="ICE",
        ),
        Framework(
            "custom", "Personnalisée", "Les labels du PM, chacun associé à un niveau (critique, important, optionnel, exclu).",
            "custom",
            {CRITICAL: "Critique", IMPORTANT: "Important", OPTIONAL: "Optionnel", EXCLUDED: "Exclu"},
        ),
    )
}

_PRIORITY_TIER = {"urgent": CRITICAL, "high": IMPORTANT, "medium": OPTIONAL, "low": OPTIONAL}
_PRIORITY_LABEL = {"urgent": "Urgent", "high": "Haute", "medium": "Moyenne", "low": "Basse"}


# ------------------------------------------------------------------ delivery methods


@dataclass(frozen=True)
class Delivery:
    id: str
    name: str
    description: str
    milestone_word: str  # how a time box is called in reports
    uses_cycles: bool  # Orbit cycles are sprints / milestones
    uses_phases: bool  # Orbit modules with dates are phases
    tracks_velocity: bool
    tracks_wip: bool
    flow_word: str = "Vélocité"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DELIVERIES: dict[str, Delivery] = {
    d.id: d
    for d in (
        Delivery("scrum", "Scrum", "Sprints (cycles), vélocité, sprint à risque.", "Sprint",
                 uses_cycles=True, uses_phases=False, tracks_velocity=True, tracks_wip=False),
        Delivery("kanban", "Kanban", "Flux continu : débit, limite de travail en cours (WIP), pas de sprint.", "Jalon",
                 uses_cycles=False, uses_phases=False, tracks_velocity=True, tracks_wip=True, flow_word="Débit"),
        Delivery("waterfall", "Cycle en V / Waterfall", "Phases séquentielles (modules datés), jalons, phase en retard.",
                 "Phase", uses_cycles=False, uses_phases=True, tracks_velocity=False, tracks_wip=False),
        Delivery("hybrid", "Hybride", "Phases et sprints à la fois, vélocité et WIP si une limite est définie.", "Jalon",
                 uses_cycles=True, uses_phases=True, tracks_velocity=True, tracks_wip=True),
    )
}


# ------------------------------------------------------------------ the PM's choice for a project


@dataclass
class ProjectMethod:
    delivery: str = "hybrid"
    prioritization: str = "moscow"
    wip_limit: int | None = None  # Kanban / hybrid
    # Score frameworks: absolute thresholds {"critical": 300, "important": 100}.
    # When absent, tiers are relative: top 20 % critical, next 30 % important, the rest optional.
    score_thresholds: dict[str, float] | None = None
    # Custom framework: {"label in the tracker": "critical" | "important" | "optional" | "excluded"}
    custom_mapping: dict[str, str] = field(default_factory=dict)

    @property
    def framework(self) -> Framework:
        return FRAMEWORKS[self.prioritization]

    @property
    def delivery_method(self) -> Delivery:
        return DELIVERIES[self.delivery]

    def validate(self) -> ProjectMethod:
        if self.delivery not in DELIVERIES:
            raise ValueError(f"Méthode de pilotage inconnue : {self.delivery!r} (choix : {', '.join(DELIVERIES)})")
        if self.prioritization not in FRAMEWORKS:
            raise ValueError(f"Méthode de priorisation inconnue : {self.prioritization!r} (choix : {', '.join(FRAMEWORKS)})")
        if self.wip_limit is not None and self.wip_limit < 1:
            raise ValueError("La limite WIP doit être au moins 1")
        if self.prioritization == "custom" and not self.custom_mapping:
            raise ValueError("La méthode personnalisée demande au moins un label associé à un niveau")
        bad = {t for t in self.custom_mapping.values() if t not in TIERS}
        if bad:
            raise ValueError(f"Niveaux inconnus : {', '.join(sorted(bad))} (choix : {', '.join(TIERS)})")
        if self.score_thresholds:
            crit, imp = self.score_thresholds.get(CRITICAL), self.score_thresholds.get(IMPORTANT)
            if crit is None or imp is None or crit < imp:
                raise ValueError("Seuils de score : il faut « critical » et « important », avec critical ≥ important")
        return self

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ProjectMethod:
        data = data or {}
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known).validate()

    def describe(self) -> dict[str, str]:
        return {"delivery": self.delivery_method.name, "prioritization": self.framework.name}


# ------------------------------------------------------------------ classification


def _norm(text: str) -> str:
    return re.sub(r"[\s_\-']+", "", text).casefold()


def _score(issue: Issue, prefix: str) -> float | None:
    pattern = re.compile(rf"^\s*{re.escape(prefix)}\s*[:=]\s*(-?\d+(?:[.,]\d+)?)\s*$", re.IGNORECASE)
    for label in issue.labels:
        m = pattern.match(label)
        if m:
            return float(m.group(1).replace(",", "."))
    return None


def _fmt(score: float) -> str:
    return str(int(score)) if score == int(score) else f"{score:g}"


def classify(snapshot: ProjectSnapshot, method: ProjectMethod) -> ProjectSnapshot:
    """Set `category` (PM's vocabulary) and `tier` (common level) on every issue, in place."""
    fw = method.framework

    if fw.source == "label":
        lookup = {_norm(alias): c for c in fw.categories for alias in (c.label, *c.aliases)}
        for i in snapshot.issues:
            cat = next((lookup[_norm(lab)] for lab in i.labels if _norm(lab) in lookup), None)
            i.category, i.tier = (fw.tier_labels[cat.tier], cat.tier) if cat else (None, None)

    elif fw.source == "priority":
        for i in snapshot.issues:
            tier = _PRIORITY_TIER.get(i.priority)
            i.category, i.tier = (_PRIORITY_LABEL[i.priority], tier) if tier else (None, None)

    elif fw.source == "custom":
        lookup = {_norm(lab): (lab, tier) for lab, tier in method.custom_mapping.items()}
        for i in snapshot.issues:
            hit = next((lookup[_norm(lab)] for lab in i.labels if _norm(lab) in lookup), None)
            i.category, i.tier = hit if hit else (None, None)

    else:  # score
        scored = [(i, s) for i in snapshot.issues if (s := _score(i, fw.score_prefix or "")) is not None]
        for i in snapshot.issues:
            i.category, i.tier = None, None
        if method.score_thresholds:
            crit, imp = method.score_thresholds[CRITICAL], method.score_thresholds[IMPORTANT]
            tier_of = {id(i): CRITICAL if s >= crit else IMPORTANT if s >= imp else OPTIONAL for i, s in scored}
        else:  # relative: top 20 % critical, next 30 % important
            ranked = sorted(scored, key=lambda p: p[1], reverse=True)
            n_crit, n_top = math.ceil(len(ranked) * 0.2), math.ceil(len(ranked) * 0.5)
            tier_of = {id(i): CRITICAL if r < n_crit else IMPORTANT if r < n_top else OPTIONAL
                       for r, (i, _) in enumerate(ranked)}
        for i, s in scored:
            i.category, i.tier = f"{fw.score_prefix} {_fmt(s)}", tier_of[id(i)]

    return snapshot


def catalog() -> dict[str, Any]:
    """Everything the PM can choose from (for the settings screen)."""
    return {
        "prioritization": [f.to_dict() for f in FRAMEWORKS.values()],
        "delivery": [d.to_dict() for d in DELIVERIES.values()],
        "tiers": list(TIERS),
        "default": ProjectMethod().to_dict(),
    }
