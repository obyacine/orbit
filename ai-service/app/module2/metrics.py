"""Deterministic project metrics computed from a classified ProjectSnapshot. No LLM here.

What is measured depends on the PM's method (app.methods): sprints and velocity for Scrum,
throughput and WIP for Kanban, phases for Waterfall, all of them for hybrid.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta

from app.methods import CRITICAL, EXCLUDED, IMPORTANT, OPTIONAL, ProjectMethod
from app.module2.snapshot import Issue, ProjectSnapshot

ACTIVE = ("backlog", "todo", "in_progress")


@dataclass
class EpicProgress:
    id: str
    name: str
    done: int
    total: int
    pct: int


@dataclass
class Velocity:
    this_period: int
    previous_period: int
    change_pct: int | None  # None when previous period is 0


@dataclass
class BlockedItem:
    key: str
    title: str
    category: str | None
    blocked_by: list[str]  # keys of blocking issues


@dataclass
class MilestoneStatus:
    id: str
    name: str
    kind: str  # Sprint | Phase | Jalon
    end_date: date | None
    done: int
    total: int
    pct_done: int
    pct_time_elapsed: int
    days_left: int | None
    at_risk: bool
    overdue: bool  # end date passed and not finished


@dataclass
class PriorityCoverage:
    tier: str
    category: str  # tier name in the PM's framework
    total: int
    done: int
    in_progress: int
    late: int


@dataclass
class WipStatus:
    current: int
    limit: int | None
    exceeded: bool


@dataclass
class ProjectMetrics:
    as_of: date
    overall_pct: int
    epics: list[EpicProgress]
    velocity: Velocity | None
    blocked: list[BlockedItem]
    milestones: list[MilestoneStatus]
    coverage: list[PriorityCoverage]
    unclassified: list[str]  # active issues with no priority in the PM's framework
    wip: WipStatus | None
    late: list[str]  # keys

    def to_dict(self) -> dict:
        return asdict(self)


def _pct(part: int, whole: int) -> int:
    return round(100 * part / whole) if whole else 0


def _countable(issues: list[Issue]) -> list[Issue]:
    """Cancelled and excluded (Won't, Indifférent...) issues don't count towards progress."""
    return [i for i in issues if i.status != "cancelled" and i.tier != EXCLUDED]


def is_late(issue: Issue, today: date) -> bool:
    return issue.status in ACTIVE and issue.target_date is not None and issue.target_date < today


def epic_progress(snapshot: ProjectSnapshot) -> list[EpicProgress]:
    result = []
    for m in snapshot.modules:
        items = _countable([i for i in snapshot.issues if m.id in i.module_ids])
        done = sum(1 for i in items if i.status == "done")
        result.append(EpicProgress(m.id, m.name, done, len(items), _pct(done, len(items))))
    return result


def velocity(snapshot: ProjectSnapshot, today: date, period_days: int = 7) -> Velocity:
    start = today - timedelta(days=period_days)
    prev_start = start - timedelta(days=period_days)
    done_dates = [i.completed_at.date() for i in snapshot.issues if i.status == "done" and i.completed_at]
    this_p = sum(1 for d in done_dates if start < d <= today)
    prev_p = sum(1 for d in done_dates if prev_start < d <= start)
    change = round(100 * (this_p - prev_p) / prev_p) if prev_p else None
    return Velocity(this_p, prev_p, change)


def blocked_items(snapshot: ProjectSnapshot) -> list[BlockedItem]:
    by_id = {i.id: i for i in snapshot.issues}
    result = []
    for i in snapshot.issues:
        if i.status not in ACTIVE:
            continue
        open_blockers = [by_id[b].key for b in i.blocked_by if b in by_id and by_id[b].status in ACTIVE]
        if open_blockers or "Bloqué" in i.labels:
            result.append(BlockedItem(i.key, i.title, i.category, open_blockers))
    return result


def _milestone(
    mid: str, name: str, kind: str, start: date | None, end: date | None, issues: list[Issue], today: date
) -> MilestoneStatus:
    items = _countable(issues)
    done = sum(1 for i in items if i.status == "done")
    pct_done = _pct(done, len(items))
    if start and end:
        span = max((end - start).days, 1)
        elapsed = min(max((today - start).days, 0), span)
        pct_time = _pct(elapsed, span)
    else:
        pct_time = 0
    days_left = (end - today).days if end else None
    started = start is not None and start <= today
    finished = days_left is not None and days_left < 0
    at_risk = started and not finished and pct_done < pct_time and pct_done < 100
    overdue = finished and bool(items) and pct_done < 100
    return MilestoneStatus(mid, name, kind, end, done, len(items), pct_done, pct_time, days_left, at_risk, overdue)


def milestones(snapshot: ProjectSnapshot, method: ProjectMethod, today: date) -> list[MilestoneStatus]:
    d = method.delivery_method
    out: list[MilestoneStatus] = []
    if d.uses_phases:
        for m in snapshot.modules:
            if m.start_date and m.end_date:
                items = [i for i in snapshot.issues if m.id in i.module_ids]
                out.append(_milestone(m.id, m.name, "Phase", m.start_date, m.end_date, items, today))
    if d.uses_cycles:
        kind = "Sprint" if d.id == "scrum" else "Jalon"
        for c in snapshot.cycles:
            items = [i for i in snapshot.issues if i.cycle_id == c.id]
            out.append(_milestone(c.id, c.name, kind, c.start_date, c.end_date, items, today))
    return out


def priority_coverage(snapshot: ProjectSnapshot, method: ProjectMethod, today: date) -> list[PriorityCoverage]:
    labels = method.framework.tier_labels
    result = []
    for tier in (CRITICAL, IMPORTANT, OPTIONAL):
        items = [i for i in snapshot.issues if i.tier == tier and i.status != "cancelled"]
        result.append(
            PriorityCoverage(
                tier=tier,
                category=labels[tier],
                total=len(items),
                done=sum(1 for i in items if i.status == "done"),
                in_progress=sum(1 for i in items if i.status == "in_progress"),
                late=sum(1 for i in items if is_late(i, today)),
            )
        )
    return result


def compute_metrics(snapshot: ProjectSnapshot, today: date | None = None, method: ProjectMethod | None = None) -> ProjectMetrics:
    """`snapshot` must have been classified with the same `method` (app.methods.classify)."""
    today = today or date.today()
    method = method or ProjectMethod()
    d = method.delivery_method
    countable = _countable(snapshot.issues)
    wip = None
    if d.tracks_wip:
        current = sum(1 for i in snapshot.issues if i.status == "in_progress")
        limit = method.wip_limit
        wip = WipStatus(current, limit, limit is not None and current > limit)
    return ProjectMetrics(
        as_of=today,
        overall_pct=_pct(sum(1 for i in countable if i.status == "done"), len(countable)),
        epics=epic_progress(snapshot),
        velocity=velocity(snapshot, today) if d.tracks_velocity else None,
        blocked=blocked_items(snapshot),
        milestones=milestones(snapshot, method, today),
        coverage=priority_coverage(snapshot, method, today),
        unclassified=[i.key for i in snapshot.issues if i.status in ACTIVE and i.tier is None],
        wip=wip,
        late=[i.key for i in snapshot.issues if is_late(i, today)],
    )
