"""Build a normalized, tracker-agnostic snapshot of a project from the Plane API.

Everything downstream (metrics, anomaly rules, reports) works on this snapshot only,
never on raw Plane payloads.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any

from app.plane_client import PlaneClient


@dataclass
class Issue:
    id: str
    key: str  # e.g. BANK-12
    title: str
    status: str  # todo | in_progress | done | cancelled | backlog
    state_name: str
    labels: list[str]
    priority: str
    assignees: list[str]
    module_ids: list[str] = field(default_factory=list)
    cycle_id: str | None = None
    start_date: date | None = None
    target_date: date | None = None
    completed_at: datetime | None = None
    blocked_by: list[str] = field(default_factory=list)
    # Set by app.methods.classify() according to the PM's prioritization method
    category: str | None = None  # PM's vocabulary: "Must-Have", "Basique", "WSJF 13"...
    tier: str | None = None  # critical | important | optional | excluded
    baseline_id: str | None = None  # deliverable of the validated baseline (M2, D5...), set by Module 1


@dataclass
class Module:
    id: str
    name: str
    start_date: date | None = None  # dated modules are phases in Waterfall / hybrid
    end_date: date | None = None


@dataclass
class Cycle:
    id: str
    name: str
    start_date: date | None
    end_date: date | None


@dataclass
class ProjectSnapshot:
    project_id: str
    name: str
    identifier: str
    issues: list[Issue]
    modules: list[Module]
    cycles: list[Cycle]
    taken_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Plane state groups -> Orbit status
_GROUP_TO_STATUS = {
    "backlog": "backlog",
    "unstarted": "todo",
    "started": "in_progress",
    "completed": "done",
    "cancelled": "cancelled",
    "triage": "backlog",
}


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value[:10])


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _blocked_by_ids(relations: Any) -> list[str]:
    """The relations endpoint returns either a dict keyed by relation type or a list."""
    if isinstance(relations, dict):
        items = relations.get("blocked_by", [])
        return [i if isinstance(i, str) else (i.get("issue_id") or i.get("id")) for i in items]
    if isinstance(relations, list):
        return [r.get("issue_id") or r.get("id") for r in relations if r.get("relation_type") == "blocked_by"]
    return []


def build_snapshot(client: PlaneClient, project_id: str, with_relations: bool = True) -> ProjectSnapshot:
    project = client.get_project(project_id)
    states = {s["id"]: s for s in client.list_states(project_id)}
    labels = {lab["id"]: lab["name"] for lab in client.list_labels(project_id)}

    modules = [
        Module(
            id=m["id"],
            name=m["name"],
            start_date=_parse_date(m.get("start_date")),
            end_date=_parse_date(m.get("target_date")),
        )
        for m in client.list_modules(project_id)
    ]
    cycles = [
        Cycle(
            id=c["id"],
            name=c["name"],
            start_date=_parse_date(c.get("start_date")),
            end_date=_parse_date(c.get("end_date")),
        )
        for c in client.list_cycles(project_id)
    ]

    issue_modules: dict[str, list[str]] = {}
    for m in modules:
        for mi in client.list_module_issues(project_id, m.id):
            issue_modules.setdefault(mi.get("id") or mi.get("issue"), []).append(m.id)

    issue_cycle: dict[str, str] = {}
    for c in cycles:
        for ci in client.list_cycle_issues(project_id, c.id):
            issue_cycle[ci.get("id") or ci.get("issue")] = c.id

    issues: list[Issue] = []
    for raw in client.list_issues(project_id):
        state = states.get(raw.get("state"), {})
        label_names = [labels[lid] for lid in raw.get("labels", []) if lid in labels]
        issues.append(
            Issue(
                id=raw["id"],
                key=f"{project['identifier']}-{raw.get('sequence_id')}",
                title=raw["name"],
                status=_GROUP_TO_STATUS.get(state.get("group", ""), "backlog"),
                state_name=state.get("name", "?"),
                labels=label_names,
                priority=raw.get("priority") or "none",
                assignees=list(raw.get("assignees", [])),
                module_ids=issue_modules.get(raw["id"], []),
                cycle_id=issue_cycle.get(raw["id"]),
                start_date=_parse_date(raw.get("start_date")),
                target_date=_parse_date(raw.get("target_date")),
                completed_at=_parse_dt(raw.get("completed_at")),
                blocked_by=_blocked_by_ids(client.list_relations(project_id, raw["id"])) if with_relations else [],
            )
        )

    return ProjectSnapshot(
        project_id=project_id,
        name=project["name"],
        identifier=project["identifier"],
        issues=issues,
        modules=modules,
        cycles=cycles,
        taken_at=datetime.now().astimezone(),
    )
