"""Module 1: normalization of the LLM proposal and push to the tracker (no network)."""

from app.methods import ProjectMethod
from app.module1 import baseline as m1


def proposal(priorities, milestones=True):
    return m1.Baseline.model_validate({
        "charter": {
            "title": "Portail RH", "context": "c", "objectives": ["o"], "scope_in": ["i"], "scope_out": ["x"],
            "budget": "180 k€", "start_date": "2026-11-23", "end_date": "bad", "stakeholders": [], "constraints": [],
            "success_criteria": [], "risks": [],
        },
        "epics": [{"id": "E1", "name": "Cadrage", "description": "", "start_date": "2026-11-23", "end_date": "2026-12-20"}],
        "milestones": [{"id": "J1", "name": "Sprint 1", "start_date": "2026-11-23", "end_date": "2026-12-06"}] if milestones else [],
        "deliverables": [
            {"id": "M1", "title": f"L{n}", "description": "", "epic_id": "E9" if n == 0 else "E1",
             "milestone_id": "J1", "priority": p, "due_date": "2026-12-06"}
            for n, p in enumerate(priorities)
        ],
    })


def test_moscow_ids_priorities_and_references_are_fixed():
    b = m1.normalize(proposal(["must", "Should", "Could", "nonsense", "Won't"]), ProjectMethod(delivery="scrum"))
    assert [(x.id, x.priority) for x in b.deliverables] == [("M1", "Must"), ("S1", "Should"), ("C1", "Could"), ("S2", "Should"), ("W1", "Won't")]
    assert b.deliverables[0].epic_id == "E1"  # unknown epic reattached
    assert b.charter.end_date == ""  # invalid date dropped
    assert b.epics[0].start_date == ""  # Scrum: epics are not phases


def test_score_methods_keep_a_number():
    b = m1.normalize(proposal(["13", "score: 8,5", "?"]), ProjectMethod(prioritization="wsjf"))
    assert [x.priority for x in b.deliverables] == ["13", "8.5", "0"]


def test_kanban_drops_sprints_waterfall_keeps_phases():
    k = m1.normalize(proposal(["urgent"]), ProjectMethod(delivery="kanban", prioritization="priority"))
    assert k.milestones == [] and k.deliverables[0].milestone_id == ""
    w = m1.normalize(proposal(["Must"]), ProjectMethod(delivery="waterfall"))
    assert w.epics[0].start_date == "2026-11-23" and w.milestones == []


class FakePlane:
    def __init__(self):
        self.calls, self.n = [], 0

    def _id(self):
        self.n += 1
        return f"id{self.n}"

    def enable_features(self, pid, *, modules=True, cycles=False):
        self.calls.append(("features", modules, cycles))

    def list_labels(self, pid):
        return [{"name": "Must", "id": "existing-must"}]

    def create_label(self, pid, name, color):
        self.calls.append(("label", name))
        return {"id": self._id()}

    def create_module(self, pid, name, description="", start_date=None, target_date=None):
        self.calls.append(("module", name, start_date, target_date))
        return {"id": self._id()}

    def create_cycle(self, pid, name, start, end):
        self.calls.append(("cycle", name))
        return {"id": self._id()}

    def create_issue(self, pid, payload):
        self.calls.append(("issue", payload["name"], payload["priority"], tuple(payload.get("labels", []))))
        return {"id": self._id()}

    def add_issues_to_module(self, pid, mid, ids):
        self.calls.append(("in_module", mid, tuple(ids)))

    def add_issues_to_cycle(self, pid, cid, ids):
        self.calls.append(("in_cycle", cid, tuple(ids)))


def test_push_creates_structure_and_reuses_labels():
    method = ProjectMethod(delivery="hybrid")
    b = m1.normalize(proposal(["Must", "Should"]), method)
    fake = FakePlane()
    out = m1.push(fake, "p", b, method)
    assert out["counts"] == {"work_items": 2, "modules": 1, "cycles": 1}
    assert ("module", "Cadrage", "2026-11-23", "2026-12-20") in fake.calls  # hybrid: modules are dated phases
    assert ("label", "Should") in fake.calls and ("label", "Must") not in fake.calls  # existing label reused
    issues = [c for c in fake.calls if c[0] == "issue"]
    assert issues[0] == ("issue", "[M1] L0", "urgent", ("existing-must",))
    assert set(out["work_items"]) == {"M1", "S1"}
    assert fake.calls[0] == ("features", True, True)  # UI-created projects start with modules/cycles off


def test_push_score_method_uses_score_labels():
    method = ProjectMethod(delivery="kanban", prioritization="wsjf")
    fake = FakePlane()
    m1.push(fake, "p", m1.normalize(proposal(["13"]), method), method)
    assert ("label", "WSJF:13") in fake.calls
    assert not any(c[0] == "cycle" for c in fake.calls)
    assert fake.calls[0] == ("features", True, False)  # Kanban: no cycles to turn on
