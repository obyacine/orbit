import re

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from app import db, llm
from app.config import get_settings
from app.methods import ProjectMethod, catalog, classify
from app.module1 import baseline as m1
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


def _link_baseline(snapshot: ProjectSnapshot) -> None:
    """Tie each work item to the deliverable of the validated baseline it comes from."""
    validated = db.latest_validated_baseline(snapshot.project_id)
    if validated and validated["work_items"]:
        by_issue = {issue_id: deliverable for deliverable, issue_id in validated["work_items"].items()}
        for i in snapshot.issues:
            i.baseline_id = by_issue.get(i.id)


def _load(project_id: str, with_comments: bool = False) -> tuple[ProjectSnapshot, dict[str, str], ProjectMethod]:
    """Snapshot classified with the PM's method, plus the last comment of each blocked issue (reason of the block)."""
    method = _method(project_id)
    try:
        with PlaneClient() as client:
            snapshot = classify(build_snapshot(client, project_id), method)
            _link_baseline(snapshot)
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


# ------------------------------------------------------------------ Module 1: brief -> baseline


class DraftBody(BaseModel):
    brief: str
    created_by: str | None = None


@app.post("/projects/{project_id}/baseline/draft")
def draft_baseline(project_id: str, body: DraftBody, x_orbit_token: str | None = Header(default=None)) -> dict:
    """The LLM turns the PM's brief into a draft baseline, in the project's method. Nothing is created yet."""
    _check_internal_token(x_orbit_token)
    method = _method(project_id)
    try:
        proposal = m1.generate(body.brief, method)
    except m1.BaselineError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return db.save_baseline_draft(project_id, body.brief, method.to_dict(), proposal.model_dump(), body.created_by)


@app.get("/projects/{project_id}/baselines")
def list_project_baselines(project_id: str, x_orbit_token: str | None = Header(default=None)) -> list:
    _check_internal_token(x_orbit_token)
    return db.list_baselines(project_id)


class BaselineContentBody(BaseModel):
    content: dict


def _draft_or_error(baseline_id: str) -> dict:
    found = db.get_baseline(baseline_id)
    if not found:
        raise HTTPException(status_code=404, detail="Baseline introuvable")
    if found["status"] != "draft":
        raise HTTPException(status_code=409, detail="Cette baseline est validée : elle ne peut plus être modifiée")
    return found


@app.put("/baselines/{baseline_id}")
def edit_baseline(baseline_id: str, body: BaselineContentBody, x_orbit_token: str | None = Header(default=None)) -> dict:
    """The PM edits the draft (charter, deliverables, priorities...)."""
    _check_internal_token(x_orbit_token)
    found = _draft_or_error(baseline_id)
    try:
        content = m1.normalize(m1.Baseline.model_validate(body.content), ProjectMethod.from_dict(found["method"]))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Baseline invalide : {exc}") from exc
    return db.update_baseline_content(baseline_id, content.model_dump())


class ValidateBody(BaseModel):
    validated_by: str
    content: dict | None = None  # last edits, if any


@app.post("/baselines/{baseline_id}/validate")
def validate_and_push_baseline(baseline_id: str, body: ValidateBody, x_orbit_token: str | None = Header(default=None)) -> dict:
    """Freeze the baseline and create it in the tracker: labels, modules, cycles, work items."""
    _check_internal_token(x_orbit_token)
    found = _draft_or_error(baseline_id)
    if db.latest_validated_baseline(found["project_id"]):
        raise HTTPException(status_code=409, detail="Ce projet a déjà une baseline validée")
    method = ProjectMethod.from_dict(found["method"])
    try:
        baseline = m1.normalize(m1.Baseline.model_validate(body.content or found["content"]), method)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Baseline invalide : {exc}") from exc
    try:
        with PlaneClient() as client:
            pushed = m1.push(client, found["project_id"], baseline, method)
    except PlaneError as exc:
        raise HTTPException(status_code=502, detail=f"Création dans Orbit impossible : {exc}") from exc
    # The project is now run with the method the baseline was built for.
    db.save_method(found["project_id"], method.to_dict(), body.validated_by)
    result = db.validate_baseline(baseline_id, body.validated_by, baseline.model_dump(), pushed["work_items"])
    return {**result, "counts": pushed["counts"]}
