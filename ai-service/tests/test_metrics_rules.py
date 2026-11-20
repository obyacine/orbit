from datetime import date, datetime, timedelta, timezone

from app.methods import ProjectMethod, classify
from app.module2.metrics import compute_metrics
from app.module2.rules import detect_anomalies
from app.module2.snapshot import Cycle, Issue, Module, ProjectSnapshot

TODAY = date(2026, 11, 20)
METHOD = ProjectMethod(delivery="scrum", prioritization="moscow")


def d(offset: int) -> date:
    return TODAY + timedelta(days=offset)


def done_at(offset: int) -> datetime:
    return datetime.combine(d(offset), datetime.min.time(), tzinfo=timezone.utc)


def issue(key, status, label, module="m1", cycle="c2", assignees=("u1",), target=None, completed=None,
          blocked_by=(), priority="high"):
    return Issue(
        id=key, key=key, title=key, status=status, state_name=status,
        labels=[label] if label else [], priority=priority, assignees=list(assignees),
        module_ids=[module], cycle_id=cycle, target_date=target, completed_at=completed,
        blocked_by=list(blocked_by),
    )


def snapshot(method: ProjectMethod = METHOD) -> ProjectSnapshot:
    issues = [
        issue("A", "done", "Must", completed=done_at(-10)),
        issue("B", "done", "Must", completed=done_at(-9)),
        issue("C", "done", "Should", completed=done_at(-3)),
        issue("D", "in_progress", "Must", target=d(-2)),  # late Must
        issue("E", "todo", "Must", assignees=(), target=d(5), blocked_by=["F"]),  # unassigned + blocked
        issue("F", "in_progress", "Must", target=d(1)),
        issue("G", "todo", "Should", module="m2", target=d(-1)),  # late Should
        issue("H", "backlog", "Won't", module="m2", cycle=None),  # excluded from progress
    ]
    snap = ProjectSnapshot(
        project_id="p", name="Demo", identifier="DEMO", issues=issues,
        modules=[Module("m1", "Auth"), Module("m2", "Paiement")],
        cycles=[Cycle("c2", "Sprint MVP", d(-7), d(6))],
        taken_at=done_at(0),
    )
    return classify(snap, method)


def test_metrics():
    m = compute_metrics(snapshot(), TODAY, METHOD)
    assert m.overall_pct == 43  # 3 done / 7 countable (Won't excluded)
    assert [(e.name, e.done, e.total) for e in m.epics] == [("Auth", 3, 6), ("Paiement", 0, 1)]
    assert (m.velocity.this_period, m.velocity.previous_period, m.velocity.change_pct) == (1, 2, -50)
    assert [b.key for b in m.blocked] == ["E"]
    ms = m.milestones[0]
    assert (ms.kind, ms.pct_done, ms.pct_time_elapsed, ms.days_left, ms.at_risk) == ("Sprint", 43, 54, 6, True)
    must = next(c for c in m.coverage if c.tier == "critical")
    assert (must.category, must.total, must.done, must.late) == ("Must-Have", 5, 2, 1)
    assert sorted(m.late) == ["D", "G"]
    assert m.wip is None  # Scrum doesn't track WIP
    assert m.unclassified == []


def test_anomalies():
    snap = snapshot()
    anomalies = detect_anomalies(snap, compute_metrics(snap, TODAY, METHOD), TODAY, METHOD)
    found = {(a.rule, a.issue_key) for a in anomalies}
    assert ("critical_late", "D") in found
    assert ("critical_unassigned", "E") in found
    assert ("critical_blocked", "E") in found
    assert ("important_late", "G") in found
    assert ("velocity_drop", None) in found
    assert ("milestone_at_risk", None) in found
    assert anomalies[0].severity == "critical"
    assert all(a.baseline_ref for a in anomalies if a.issue_key)
    late_d = next(a for a in anomalies if a.rule == "critical_late")
    assert late_d.message == "Must-Have « D » en retard de 2 j"
    assert late_d.baseline_ref == "MoSCoW / Must-Have"
