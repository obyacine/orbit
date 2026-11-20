from app import llm
from app.module2.metrics import compute_metrics
from app.module2.reports import build_progress_report, build_situation_report, to_markdown, weather
from app.module2.rules import detect_anomalies
from tests.test_metrics_rules import TODAY, snapshot


def test_reports_without_llm(monkeypatch):
    monkeypatch.setattr(llm, "write", lambda *a, **k: None)  # force template fallback
    snap = snapshot()
    m = compute_metrics(snap, TODAY)
    anomalies = detect_anomalies(snap, m, TODAY)

    progress = build_progress_report(snap, m, {"E": "Attente fournisseur"})
    assert progress["summary_source"] == "template"
    assert progress["blocked"][0]["reason"] == "Attente fournisseur"
    assert "43 %" in to_markdown(progress)

    situation = build_situation_report(snap, m, anomalies, progress)
    assert situation["weather"] == weather(anomalies) == "red"
    assert any("Assigner" in r for r in situation["recommendations"])
    assert "## Plan vs réel" in to_markdown(situation)


def test_llm_text_is_used_when_available(monkeypatch):
    monkeypatch.setattr(llm, "write", lambda *a, **k: "Texte rédigé.")
    snap = snapshot()
    m = compute_metrics(snap, TODAY)
    assert build_progress_report(snap, m, {})["summary"] == "Texte rédigé."
