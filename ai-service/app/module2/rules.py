"""Deterministic anomaly rules (PRD §6). Each anomaly points to what it violates.

Rules reason on common tiers (critical / important / optional), never on a given framework,
so they work with MoSCoW, Kano, RICE, WSJF, native priority or the PM's own labels.
Which rules run depends on the delivery method (Scrum, Kanban, Waterfall, hybrid).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date

from app import methods as m
from app.module2.metrics import ProjectMetrics, is_late
from app.module2.snapshot import ProjectSnapshot

CRITICAL, WARNING, INFO = "critical", "warning", "info"
_ORDER = {CRITICAL: 0, WARNING: 1, INFO: 2}


@dataclass
class Anomaly:
    rule: str
    severity: str
    message: str
    issue_key: str | None = None
    baseline_ref: str | None = None  # e.g. "MoSCoW / Must-Have"; the baseline item id once Module 1 exists
    source: str = "tracker"

    def to_dict(self) -> dict:
        return asdict(self)


def detect_anomalies(
    snapshot: ProjectSnapshot,
    metrics: ProjectMetrics,
    today: date | None = None,
    method: m.ProjectMethod | None = None,
    unassigned_window_days: int = 7,
    velocity_drop_pct: int = 20,
) -> list[Anomaly]:
    today = today or metrics.as_of
    method = method or m.ProjectMethod()
    fw, delivery = method.framework, method.delivery_method
    cycles = {c.id: c for c in snapshot.cycles}
    blocked_keys = {b.key for b in metrics.blocked}
    out: list[Anomaly] = []

    # ---- priority-driven rules (any framework)
    for i in snapshot.issues:
        if i.status in ("done", "cancelled") or i.tier in (None, m.EXCLUDED):
            continue
        ref = f"Baseline {i.baseline_id} · {fw.name} / {i.category}" if i.baseline_id else f"{fw.name} / {i.category}"
        what = f"{i.category} « {i.title} »"
        cycle = cycles.get(i.cycle_id) if i.cycle_id else None
        deadline = i.target_date or (cycle.end_date if cycle else None)
        late_days = (today - i.target_date).days if is_late(i, today) else 0

        if i.tier == m.CRITICAL:
            if not i.assignees and deadline and (deadline - today).days <= unassigned_window_days:
                out.append(Anomaly("critical_unassigned", CRITICAL,
                                   f"{what} non assigné, échéance dans {(deadline - today).days} j", i.key, ref))
            if late_days:
                out.append(Anomaly("critical_late", CRITICAL, f"{what} en retard de {late_days} j", i.key, ref))
            if i.key in blocked_keys:
                out.append(Anomaly("critical_blocked", CRITICAL, f"{what} bloqué", i.key, ref))
        elif i.tier == m.IMPORTANT and late_days:
            out.append(Anomaly("important_late", WARNING, f"{what} en retard de {late_days} j", i.key, ref))
        elif i.tier == m.OPTIONAL and late_days:
            out.append(Anomaly("optional_late", INFO, f"{what} reporté", i.key, ref))

    # ---- delivery-driven rules
    v = metrics.velocity
    if v and v.change_pct is not None and v.change_pct <= -velocity_drop_pct:
        rule = "throughput_drop" if delivery.id == "kanban" else "velocity_drop"
        out.append(Anomaly(rule, WARNING,
                           f"{delivery.flow_word} en baisse de {-v.change_pct} % ({v.this_period} vs {v.previous_period})"))

    if metrics.wip and metrics.wip.exceeded:
        out.append(Anomaly("wip_exceeded", WARNING,
                           f"Travail en cours au-dessus de la limite : {metrics.wip.current} éléments pour une limite de "
                           f"{metrics.wip.limit}", baseline_ref=f"{delivery.name} / limite WIP"))

    for ms in metrics.milestones:
        ref = f"{ms.kind} / {ms.name}"
        if ms.at_risk:
            out.append(Anomaly("milestone_at_risk", WARNING,
                               f"{ms.kind} « {ms.name} » à risque : {ms.pct_done} % réalisé pour "
                               f"{ms.pct_time_elapsed} % du temps écoulé ({ms.days_left} j restants)", baseline_ref=ref))
        if ms.overdue:
            # A phase gate missed blocks the next phase; an unfinished sprint is carried over.
            severity = CRITICAL if ms.kind == "Phase" else WARNING
            out.append(Anomaly("milestone_overdue", severity,
                               f"{ms.kind} « {ms.name} » terminé(e) depuis {-ms.days_left} j à {ms.pct_done} % seulement",
                               baseline_ref=ref))

    if metrics.unclassified:
        n = len(metrics.unclassified)
        out.append(Anomaly("unprioritized", INFO,
                           f"{n} élément(s) actif(s) sans priorité {fw.name} : {', '.join(metrics.unclassified[:5])}"
                           + ("…" if n > 5 else ""), baseline_ref=fw.name))

    return sorted(out, key=lambda a: _ORDER[a.severity])
