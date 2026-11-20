import re

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from app import db, llm
from app.config import get_settings
from app.methods import ProjectMethod, catalog, classify
from app.module2.metrics import compute_metrics
from app.module2.reports import build_progress_report, build_situation_report, to_markdown
from app.module2.rules import detect_anomalies
from app.module2.snapshot import ProjectSnapshot, build_snapshot
from app.plane_client import PlaneClient, PlaneError

app = FastAPI(title="Orbit AI service", version="0.2.0")


def _check_internal_token(token: str | None) -> None:
    if token != get_settings().orbit_internal_token:
        raise HTTPException(status_code=401, detail="Invalid X-Orbit-Token")


def _method(project_id: str) -> ProjectMethod:
    saved = db.get_method(project_id)
    return ProjectMethod.from_dict(saved["config"] if saved else None)


def _load(project_id: str, with_comments: bool = False) -> tuple[ProjectSnapshot, dict[str, str], ProjectMethod]:
    """Snapshot classified with the PM's method, plus the last comment of each blocked issue (reason of the block)."""
    method = _method(project_id)
    try:
        with PlaneClient() as client:
            snapshot = classify(build_snapshot(client, project_id), method)
            comments: dict[str, str] = {}
            if with_comments:
                for b in compute_metrics(snapshot, method=method).blocked:
                    issue = next(i for i in snapshot.issues if i.key == b.key)
                    items = client.list_comments(project_id, issue.id)
                    if items:
                        last = items[-1]
                        text = last.get("comment_stripped") or re.sub(r"<[^>]+>", "", last.get("comment_html", ""))
                        comments[b.key] = text.strip()
            return snapshot, comments, method
    except PlaneError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "llm": "gemini" if llm.is_enabled() else "templates"}


@app.get("/methods")
def list_methods() -> dict:
    """Prioritization and delivery methods the PM can choose from."""
    return catalog()


@app.get("/projects/{project_id}/method")
def get_project_method(project_id: str, x_orbit_token: str | None = Header(default=None)) -> dict:
    _check_internal_token(x_orbit_token)
    saved = db.get_method(project_id)
    method = ProjectMethod.from_dict(saved["config"] if saved else None)
    return {"project_id": project_id, "configured": saved is not None, **method.to_dict(), "labels": method.describe()}


class MethodBody(BaseModel):
    delivery: str
    prioritization: str
    wip_limit: int | None = None
    score_thresholds: dict[str, float] | None = None
    custom_mapping: dict[str, str] = {}
    updated_by: str | None = None


@app.put("/projects/{project_id}/method")
def set_project_method(project_id: str, body: MethodBody, x_orbit_token: str | None = Header(default=None)) -> dict:
    """The PM chooses how the project is prioritized and run. Applies to every later analysis and report."""
    _check_internal_token(x_orbit_token)
    try:
        method = ProjectMethod.from_dict(body.model_dump(exclude={"updated_by"}))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.save_method(project_id, method.to_dict(), body.updated_by)
    return {"project_id": project_id, "configured": True, **method.to_dict(), "labels": method.describe()}


@app.get("/projects/{project_id}/snapshot")
def project_snapshot(project_id: str, x_orbit_token: str | None = Header(default=None)) -> dict:
    """Normalized view of a Plane project (debug / input of metrics and reports)."""
    _check_internal_token(x_orbit_token)
    return _load(project_id)[0].to_dict()


@app.get("/projects/{project_id}/analysis")
def project_analysis(project_id: str, x_orbit_token: str | None = Header(default=None)) -> dict:
    """Computed metrics + anomaly register for a project."""
    _check_internal_token(x_orbit_token)
    snapshot, _, method = _load(project_id)
    metrics = compute_metrics(snapshot, method=method)
    anomalies = detect_anomalies(snapshot, metrics, method=method)
    return {
        "project": {"id": snapshot.project_id, "name": snapshot.name},
        "method": method.describe(),
        "metrics": metrics.to_dict(),
        "anomalies": [a.to_dict() for a in anomalies],
    }


@app.post("/projects/{project_id}/reports/progress")
def generate_progress_report(project_id: str, x_orbit_token: str | None = Header(default=None)) -> dict:
    """Draft progress report (Team Lead -> PM)."""
    _check_internal_token(x_orbit_token)
    snapshot, comments, method = _load(project_id, with_comments=True)
    report = build_progress_report(snapshot, compute_metrics(snapshot, method=method), comments, method)
    return db.save_report(project_id, "progress", report, to_markdown(report))


@app.post("/projects/{project_id}/reports/situation")
def generate_situation_report(project_id: str, x_orbit_token: str | None = Header(default=None)) -> dict:
    """Draft situation report (PM -> COPIL), built on the latest approved progress report if any."""
    _check_internal_token(x_orbit_token)
    snapshot, _, method = _load(project_id)
    metrics = compute_metrics(snapshot, method=method)
    parent = db.latest_report(project_id, "progress", status="approved")
    anomalies = detect_anomalies(snapshot, metrics, method=method)
    report = build_situation_report(snapshot, metrics, anomalies, parent["content"] if parent else None, method)
    return db.save_report(project_id, "situation", report, to_markdown(report), parent["id"] if parent else None)


@app.get("/projects/{project_id}/reports")
def list_project_reports(project_id: str, type: str | None = None, x_orbit_token: str | None = Header(default=None)) -> list:
    _check_internal_token(x_orbit_token)
    return db.list_reports(project_id, type)


@app.get("/reports/{report_id}")
def get_report(report_id: str, x_orbit_token: str | None = Header(default=None)) -> dict:
    _check_internal_token(x_orbit_token)
    report = db.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


class ApproveBody(BaseModel):
    approved_by: str
    markdown: str | None = None  # edited version, if the human changed the draft


@app.post("/reports/{report_id}/approve")
def approve_report(report_id: str, body: ApproveBody, x_orbit_token: str | None = Header(default=None)) -> dict:
    """Human validation. Approving a progress report makes it the input of the next situation report."""
    _check_internal_token(x_orbit_token)
    if not db.get_report(report_id):
        raise HTTPException(status_code=404, detail="Report not found")
    return db.approve_report(report_id, body.approved_by, body.markdown)
