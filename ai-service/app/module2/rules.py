"""Deterministic anomaly rules (PRD §6). Each anomaly points to what it violates."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date

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
    baseline_ref: str | None = None  # e.g. "MoSCoW / Must"; set to the baseline item id once Module 1 exists
    source: str = "tracker"

    def to_dict(self) -> dict:
        return asdict(self)


def detect_anomalies(
    snapshot: ProjectSnapshot,
    metrics: ProjectMetrics,
    today: date | None = None,
    unassigned_window_days: int = 7,
    velocity_drop_pct: int = 20,
) -> list[Anomaly]:
    today = today or metrics.as_of
    cycles = {c.id: c for c in snapshot.cycles}
    blocked_keys = {b.key for b in metrics.blocked}
    out: list[Anomaly] = []

    for i in snapshot.issues:
        if i.status in ("done", "cancelled"):
            continue
        ref = f"MoSCoW / {i.moscow}" if i.moscow else None
        cycle = cycles.get(i.cycle_id) if i.cycle_id else None
        deadline = i.target_date or (cycle.end_date if cycle else None)

        if i.moscow == "Must":
            if not i.assignees and deadline and (deadline - today).days <= unassigned_window_days:
                out.append(Anomaly("must_unassigned", CRITICAL,
                                   f"Must-Have « {i.title} » non assigné, échéance dans {(deadline - today).days} j",
                                   i.key, ref))
            if is_late(i, today):
                out.append(Anomaly("must_late", CRITICAL,
                                   f"Must-Have « {i.title} » en retard de {(today - i.target_date).days} j",
                                   i.key, ref))
            if i.key in blocked_keys:
                out.append(Anomaly("must_blocked", CRITICAL, f"Must-Have « {i.title} » bloqué", i.key, ref))
        elif i.moscow == "Should" and is_late(i, today):
            out.append(Anomaly("should_late", WARNING,
                               f"Should-Have « {i.title} » en retard de {(today - i.target_date).days} j",
                               i.key, ref))
        elif i.moscow == "Could" and is_late(i, today):
            out.append(Anomaly("could_late", INFO, f"Could-Have « {i.title} » reporté", i.key, ref))

    v = metrics.velocity
    if v.change_pct is not None and v.change_pct <= -velocity_drop_pct:
        out.append(Anomaly("velocity_drop", WARNING,
                           f"Vélocité en baisse de {-v.change_pct} % ({v.this_period} vs {v.previous_period})"))

    for m in metrics.milestones:
        if m.at_risk:
            out.append(Anomaly("milestone_at_risk", WARNING,
                               f"Jalon « {m.name} » à risque : {m.pct_done} % réalisé pour "
                               f"{m.pct_time_elapsed} % du temps écoulé ({m.days_left} j restants)",
                               baseline_ref=f"Jalon / {m.name}"))

    return sorted(out, key=lambda a: _ORDER[a.severity])
