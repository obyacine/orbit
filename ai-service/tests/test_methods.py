"""Every prioritization and delivery method the PM can pick."""

import pytest

from app.methods import DELIVERIES, FRAMEWORKS, ProjectMethod, catalog, classify
from app.module2.metrics import compute_metrics
from app.module2.reports import build_progress_report, build_situation_report, to_markdown
from app.module2.rules import detect_anomalies
from app.module2.snapshot import Cycle, Module, ProjectSnapshot
from tests.test_metrics_rules import TODAY, d, done_at, issue


def snap(issues, modules=None, cycles=None):
    return ProjectSnapshot(
        project_id="p", name="Demo", identifier="DEMO", issues=issues,
        modules=modules or [Module("m1", "Auth")], cycles=cycles or [], taken_at=done_at(0),
    )


def tiers(s):
    return {i.key: (i.category, i.tier) for i in s.issues}


# ------------------------------------------------------------------ prioritization


def test_kano_labels_and_aliases():
    s = classify(snap([issue("A", "todo", "Basique"), issue("B", "todo", "attractive"),
                       issue("C", "todo", "Indifférent"), issue("D", "todo", None)]),
                 ProjectMethod(prioritization="kano"))
    assert tiers(s) == {"A": ("Basique", "critical"), "B": ("Enthousiasmant", "optional"),
                        "C": ("Indifférent", "excluded"), "D": (None, None)}


def test_moscow_is_tolerant_to_spelling():
    s = classify(snap([issue("A", "todo", "must-have"), issue("B", "todo", "Wont")]), ProjectMethod())
    assert tiers(s) == {"A": ("Must-Have", "critical"), "B": ("Won't-Have", "excluded")}


def test_native_priority_needs_no_label():
    s = classify(snap([issue("A", "todo", None, priority="urgent"), issue("B", "todo", None, priority="low"),
                       issue("C", "todo", None, priority="none")]),
                 ProjectMethod(prioritization="priority"))
    assert tiers(s) == {"A": ("Urgent", "critical"), "B": ("Basse", "optional"), "C": (None, None)}


def test_score_relative_tiers():
    issues = [issue(k, "todo", f"WSJF:{score}") for k, score in zip("ABCDEFGHIJ", range(10, 0, -1))]
    s = classify(snap(issues), ProjectMethod(prioritization="wsjf"))
    t = tiers(s)
    assert t["A"] == ("WSJF 10", "critical") and t["B"] == ("WSJF 9", "critical")  # top 20 %
    assert t["C"][1] == t["E"][1] == "important"  # next 30 %
    assert t["F"][1] == t["J"][1] == "optional"


def test_score_absolute_thresholds():
    s = classify(snap([issue("A", "todo", "RICE: 450"), issue("B", "todo", "rice=120.5"), issue("C", "todo", "RICE:12")]),
                 ProjectMethod(prioritization="rice", score_thresholds={"critical": 300, "important": 100}))
    assert tiers(s) == {"A": ("RICE 450", "critical"), "B": ("RICE 120.5", "important"), "C": ("RICE 12", "optional")}


def test_custom_mapping():
    method = ProjectMethod(prioritization="custom", custom_mapping={"P0": "critical", "P1": "important", "Hors scope": "excluded"})
    s = classify(snap([issue("A", "todo", "P0"), issue("B", "todo", "hors scope")]), method)
    assert tiers(s) == {"A": ("P0", "critical"), "B": ("Hors scope", "excluded")}


def test_rules_speak_the_pm_vocabulary():
    method = ProjectMethod(delivery="scrum", prioritization="kano")
    s = classify(snap([issue("A", "in_progress", "Basique", target=d(-3))]), method)
    a = detect_anomalies(s, compute_metrics(s, TODAY, method), TODAY, method)
    late = next(x for x in a if x.rule == "critical_late")
    assert late.message == "Basique « A » en retard de 3 j"
    assert late.baseline_ref == "Kano / Basique"


def test_unprioritized_items_are_flagged():
    method = ProjectMethod(prioritization="moscow")
    s = classify(snap([issue("A", "todo", None), issue("B", "done", None)]), method)
    a = detect_anomalies(s, compute_metrics(s, TODAY, method), TODAY, method)
    assert [(x.rule, x.severity) for x in a] == [("unprioritized", "info")]
    assert "A" in a[0].message and "B" not in a[0].message


# ------------------------------------------------------------------ delivery


def test_kanban_tracks_wip_and_throughput_not_sprints():
    method = ProjectMethod(delivery="kanban", prioritization="priority", wip_limit=2)
    issues = [issue(k, "in_progress", None, priority="high") for k in "ABC"]
    issues += [issue("D", "done", None, completed=done_at(-10)), issue("E", "done", None, completed=done_at(-9))]
    s = classify(snap(issues, cycles=[Cycle("c1", "Sprint 1", d(-7), d(6))]), method)
    m = compute_metrics(s, TODAY, method)
    assert m.milestones == []  # no sprints in Kanban
    assert (m.wip.current, m.wip.limit, m.wip.exceeded) == (3, 2, True)
    rules = {x.rule for x in detect_anomalies(s, m, TODAY, method)}
    assert {"wip_exceeded", "throughput_drop"} <= rules and "velocity_drop" not in rules


def test_waterfall_phases_and_missed_gate():
    method = ProjectMethod(delivery="waterfall", prioritization="moscow")
    modules = [Module("m1", "Conception", d(-30), d(-5)), Module("m2", "Réalisation", d(-5), d(20))]
    issues = [issue("A", "done", "Must", module="m1", cycle=None, completed=done_at(-6)),
              issue("B", "in_progress", "Must", module="m1", cycle=None),
              issue("C", "todo", "Should", module="m2", cycle=None)]
    s = classify(snap(issues, modules=modules, cycles=[Cycle("c1", "Sprint 1", d(-7), d(6))]), method)
    m = compute_metrics(s, TODAY, method)
    assert m.velocity is None and m.wip is None
    assert [(x.kind, x.name, x.overdue) for x in m.milestones] == [("Phase", "Conception", True), ("Phase", "Réalisation", False)]
    gate = next(x for x in detect_anomalies(s, m, TODAY, method) if x.rule == "milestone_overdue")
    assert gate.severity == "critical"
    assert gate.message == "Phase « Conception » terminé(e) depuis 5 j à 50 % seulement"


def test_every_combination_produces_reports(monkeypatch):
    from app import llm

    monkeypatch.setattr(llm, "write", lambda *a, **k: None)
    issues = [issue("A", "in_progress", "Must", target=d(-1), priority="urgent"), issue("B", "todo", "WSJF:5")]
    modules = [Module("m1", "Conception", d(-10), d(10))]
    for delivery in DELIVERIES:
        for prio in FRAMEWORKS:
            method = ProjectMethod(delivery=delivery, prioritization=prio, wip_limit=1,
                                   custom_mapping={"Must": "critical"} if prio == "custom" else {})
            s = classify(snap([*issues], modules=modules, cycles=[Cycle("c1", "S1", d(-7), d(6))]), method)
            m = compute_metrics(s, TODAY, method)
            a = detect_anomalies(s, m, TODAY, method)
            progress = build_progress_report(s, m, {}, method)
            situation = build_situation_report(s, m, a, progress, method)
            md = to_markdown(situation)
            assert method.framework.name in md and method.delivery_method.name in md
            assert to_markdown(progress).startswith("# Rapport d'avancement")


# ------------------------------------------------------------------ configuration


@pytest.mark.parametrize("bad", [
    {"delivery": "scrumban"},
    {"prioritization": "eisenhower"},
    {"wip_limit": 0},
    {"prioritization": "custom"},
    {"prioritization": "custom", "custom_mapping": {"P0": "urgent"}},
    {"prioritization": "rice", "score_thresholds": {"critical": 10, "important": 50}},
])
def test_invalid_methods_are_rejected(bad):
    with pytest.raises(ValueError):
        ProjectMethod.from_dict(bad)


def test_defaults_and_catalog():
    assert ProjectMethod.from_dict(None).describe() == {"delivery": "Hybride", "prioritization": "MoSCoW"}
    c = catalog()
    assert {f["id"] for f in c["prioritization"]} == set(FRAMEWORKS)
    assert {x["id"] for x in c["delivery"]} == set(DELIVERIES)


def test_method_api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.config import get_settings
    from app.main import app

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "orbit.db"))
    monkeypatch.setenv("ORBIT_INTERNAL_TOKEN", "t")
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        h = {"X-Orbit-Token": "t"}
        assert client.get("/projects/p1/method", headers=h).json()["configured"] is False
        r = client.put("/projects/p1/method", headers=h,
                       json={"delivery": "kanban", "prioritization": "wsjf", "wip_limit": 4, "updated_by": "pm"})
        assert r.status_code == 200 and r.json()["labels"] == {"delivery": "Kanban", "prioritization": "WSJF (SAFe)"}
        got = client.get("/projects/p1/method", headers=h).json()
        assert got["configured"] is True and got["wip_limit"] == 4
        assert client.put("/projects/p1/method", headers=h, json={"delivery": "x", "prioritization": "moscow"}).status_code == 422
        assert client.get("/projects/p1/method").status_code == 401
        assert len(client.get("/methods").json()["prioritization"]) == len(FRAMEWORKS)
    finally:
        get_settings.cache_clear()
