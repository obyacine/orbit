"""Deterministic project metrics computed from a ProjectSnapshot. No LLM here."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta

from app.module2.snapshot import Cycle, Issue, ProjectSnapshot

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
    moscow: str | None
    blocked_by: list[str]  # keys of blocking issues


@dataclass
class MilestoneStatus:
    id: str
    name: str
    end_date: date | None
    done: int
    total: int
    pct_done: int
    pct_time_elapsed: int
    days_left: int | None
    at_risk: bool


@dataclass
class MoscowCoverage:
    category: str
    total: int
    done: int
    in_progress: int
    late: int


@dataclass
class ProjectMetrics:
    as_of: date
    overall_pct: int
    epics: list[EpicProgress]
    velocity: Velocity
    blocked: list[BlockedItem]
    milestones: list[MilestoneStatus]
    moscow: list[MoscowCoverage]
    late: list[str]  # keys

    def to_dict(self) -> dict:
        return asdict(self)


def _pct(part: int, whole: int) -> int:
    return round(100 * part / whole) if whole else 0


def _countable(issues: list[Issue]) -> list[Issue]:
    """Cancelled issues and Won't-haves don't count towards progress."""
    return [i for i in issues if i.status != "cancelled" and i.moscow != "Won't"]


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
            result.append(BlockedItem(i.key, i.title, i.moscow, open_blockers))
    return result


def milestone_status(snapshot: ProjectSnapshot, cycle: Cycle, today: date) -> MilestoneStatus:
    items = _countable([i for i in snapshot.issues if i.cycle_id == cycle.id])
    done = sum(1 for i in items if i.status == "done")
    pct_done = _pct(done, len(items))
    if cycle.start_date and cycle.end_date:
        span = max((cycle.end_date - cycle.start_date).days, 1)
        elapsed = min(max((today - cycle.start_date).days, 0), span)
        pct_time = _pct(elapsed, span)
        days_left = (cycle.end_date - today).days
    else:
        pct_time, days_left = 0, None
    started = cycle.start_date is not None and cycle.start_date <= today
    finished = days_left is not None and days_left < 0
    at_risk = started and not finished and pct_done < pct_time and pct_done < 100
    return MilestoneStatus(
        cycle.id, cycle.name, cycle.end_date, done, len(items), pct_done, pct_time, days_left, at_risk
    )


def moscow_coverage(snapshot: ProjectSnapshot, today: date) -> list[MoscowCoverage]:
    result = []
    for cat in ("Must", "Should", "Could"):
        items = [i for i in snapshot.issues if i.moscow == cat and i.status != "cancelled"]
        result.append(
            MoscowCoverage(
                category=cat,
                total=len(items),
                done=sum(1 for i in items if i.status == "done"),
                in_progress=sum(1 for i in items if i.status == "in_progress"),
                late=sum(1 for i in items if is_late(i, today)),
            )
        )
    return result


def compute_metrics(snapshot: ProjectSnapshot, today: date | None = None) -> ProjectMetrics:
    today = today or date.today()
    countable = _countable(snapshot.issues)
    return ProjectMetrics(
        as_of=today,
        overall_pct=_pct(sum(1 for i in countable if i.status == "done"), len(countable)),
        epics=epic_progress(snapshot),
        velocity=velocity(snapshot, today),
        blocked=blocked_items(snapshot),
        milestones=[milestone_status(snapshot, c, today) for c in snapshot.cycles],
        moscow=moscow_coverage(snapshot, today),
        late=[i.key for i in snapshot.issues if is_late(i, today)],
    )
