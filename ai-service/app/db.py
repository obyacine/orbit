"""SQLite storage for Orbit's own data: reports and project methods now, baselines and anomalies later.

Kept outside Plane's schema on purpose (no Django migrations). Reports are never overwritten:
approval only changes their status.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    type TEXT NOT NULL,              -- progress | situation | minutes
    status TEXT NOT NULL,            -- draft | approved
    content TEXT NOT NULL,           -- JSON
    markdown TEXT NOT NULL,
    parent_id TEXT,                  -- situation report built from this progress report
    created_at TEXT NOT NULL,
    approved_at TEXT,
    approved_by TEXT
);
CREATE INDEX IF NOT EXISTS reports_project ON reports(project_id, type, created_at);
CREATE TABLE IF NOT EXISTS baselines (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    status TEXT NOT NULL,            -- draft | validated
    brief TEXT NOT NULL,
    method TEXT NOT NULL,            -- JSON: method used to generate it
    content TEXT NOT NULL,           -- JSON of module1.baseline.Baseline
    work_items TEXT,                 -- JSON: deliverable id -> work item id, once pushed
    created_at TEXT NOT NULL,
    created_by TEXT,
    validated_at TEXT,
    validated_by TEXT
);
CREATE INDEX IF NOT EXISTS baselines_project ON baselines(project_id, version);
CREATE TABLE IF NOT EXISTS reference_documents (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    kind TEXT NOT NULL,              -- PDF | Word | texte | Markdown
    role TEXT NOT NULL,              -- template | past_project | standard
    text TEXT NOT NULL,
    characters INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT
);
CREATE TABLE IF NOT EXISTS project_methods (
    project_id TEXT PRIMARY KEY,
    config TEXT NOT NULL,            -- JSON of app.methods.ProjectMethod
    updated_at TEXT NOT NULL,
    updated_by TEXT
);
"""


_MIGRATIONS = (
    "ALTER TABLE baselines ADD COLUMN sources TEXT",  # references the draft was generated from
    "ALTER TABLE reference_documents ADD COLUMN original BLOB",  # the .docx itself, to fill it at export
)


def _connect() -> sqlite3.Connection:
    path = Path(get_settings().database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    for statement in _MIGRATIONS:  # additive, idempotent
        try:
            conn.execute(statement)
        except sqlite3.OperationalError:
            pass
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row(r: sqlite3.Row | None) -> dict[str, Any] | None:
    if r is None:
        return None
    d = dict(r)
    d["content"] = json.loads(d["content"])
    return d


def save_report(project_id: str, rtype: str, content: dict, markdown: str, parent_id: str | None = None) -> dict:
    rid = str(uuid.uuid4())
    with _connect() as c:
        c.execute(
            "INSERT INTO reports (id, project_id, type, status, content, markdown, parent_id, created_at) "
            "VALUES (?, ?, ?, 'draft', ?, ?, ?, ?)",
            (rid, project_id, rtype, json.dumps(content, ensure_ascii=False, default=str), markdown, parent_id, _now()),
        )
    return get_report(rid)


def get_report(report_id: str) -> dict | None:
    with _connect() as c:
        return _row(c.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone())


def list_reports(project_id: str, rtype: str | None = None) -> list[dict]:
    q, args = "SELECT * FROM reports WHERE project_id = ?", [project_id]
    if rtype:
        q, args = q + " AND type = ?", [*args, rtype]
    with _connect() as c:
        return [_row(r) for r in c.execute(q + " ORDER BY created_at DESC", args).fetchall()]


def latest_report(project_id: str, rtype: str, status: str | None = None) -> dict | None:
    q, args = "SELECT * FROM reports WHERE project_id = ? AND type = ?", [project_id, rtype]
    if status:
        q, args = q + " AND status = ?", [*args, status]
    with _connect() as c:
        return _row(c.execute(q + " ORDER BY created_at DESC LIMIT 1", args).fetchone())


def approve_report(report_id: str, approved_by: str, markdown: str | None = None) -> dict | None:
    with _connect() as c:
        if markdown is not None:  # the human may edit the draft before approving
            c.execute("UPDATE reports SET markdown = ? WHERE id = ?", (markdown, report_id))
        c.execute(
            "UPDATE reports SET status = 'approved', approved_at = ?, approved_by = ? WHERE id = ?",
            (_now(), approved_by, report_id),
        )
    return get_report(report_id)


def get_method(project_id: str) -> dict | None:
    """The PM's method for a project (None: not configured yet, defaults apply)."""
    with _connect() as c:
        r = c.execute("SELECT * FROM project_methods WHERE project_id = ?", (project_id,)).fetchone()
    if r is None:
        return None
    d = dict(r)
    d["config"] = json.loads(d["config"])
    return d


def save_method(project_id: str, config: dict, updated_by: str | None = None) -> dict:
    with _connect() as c:
        c.execute(
            "INSERT INTO project_methods (project_id, config, updated_at, updated_by) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(project_id) DO UPDATE SET config = excluded.config, updated_at = excluded.updated_at, "
            "updated_by = excluded.updated_by",
            (project_id, json.dumps(config, ensure_ascii=False), _now(), updated_by),
        )
    return get_method(project_id)


# ------------------------------------------------------------------ baselines (Module 1)


def _baseline_row(r: sqlite3.Row | None) -> dict[str, Any] | None:
    if r is None:
        return None
    d = dict(r)
    for key in ("method", "content", "work_items", "sources"):
        d[key] = json.loads(d[key]) if d[key] else None
    return d


def save_baseline_draft(
    project_id: str, brief: str, method: dict, content: dict, created_by: str | None, sources: dict | None = None
) -> dict:
    """A new draft version. Earlier versions are kept; validated ones are never modified."""
    bid = str(uuid.uuid4())
    with _connect() as c:
        version = c.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM baselines WHERE project_id = ?", (project_id,)).fetchone()[0]
        c.execute(
            "INSERT INTO baselines (id, project_id, version, status, brief, method, content, created_at, created_by, sources) "
            "VALUES (?, ?, ?, 'draft', ?, ?, ?, ?, ?, ?)",
            (bid, project_id, version, brief, json.dumps(method, ensure_ascii=False),
             json.dumps(content, ensure_ascii=False), _now(), created_by,
             json.dumps(sources or {}, ensure_ascii=False)),
        )
    return get_baseline(bid)


def get_baseline(baseline_id: str) -> dict | None:
    with _connect() as c:
        return _baseline_row(c.execute("SELECT * FROM baselines WHERE id = ?", (baseline_id,)).fetchone())


def list_baselines(project_id: str) -> list[dict]:
    with _connect() as c:
        rows = c.execute("SELECT * FROM baselines WHERE project_id = ? ORDER BY version DESC", (project_id,)).fetchall()
    return [_baseline_row(r) for r in rows]


def latest_validated_baseline(project_id: str) -> dict | None:
    with _connect() as c:
        return _baseline_row(c.execute(
            "SELECT * FROM baselines WHERE project_id = ? AND status = 'validated' ORDER BY version DESC LIMIT 1",
            (project_id,),
        ).fetchone())


def update_baseline_content(baseline_id: str, content: dict) -> dict | None:
    with _connect() as c:
        c.execute("UPDATE baselines SET content = ? WHERE id = ? AND status = 'draft'",
                  (json.dumps(content, ensure_ascii=False), baseline_id))
    return get_baseline(baseline_id)


def validate_baseline(baseline_id: str, validated_by: str, content: dict, work_items: dict) -> dict | None:
    with _connect() as c:
        c.execute(
            "UPDATE baselines SET status = 'validated', content = ?, work_items = ?, validated_at = ?, validated_by = ? "
            "WHERE id = ? AND status = 'draft'",
            (json.dumps(content, ensure_ascii=False), json.dumps(work_items), _now(), validated_by, baseline_id),
        )
    return get_baseline(baseline_id)



def past_validated_baselines(exclude_project_id: str | None = None, limit: int = 3) -> list[dict]:
    """Latest validated baseline of other projects: the organization's own examples."""
    with _connect() as c:
        rows = c.execute(
            "SELECT * FROM baselines b WHERE status = 'validated' AND project_id != ? AND version = ("
            "  SELECT MAX(version) FROM baselines WHERE project_id = b.project_id AND status = 'validated'"
            ") ORDER BY validated_at DESC LIMIT ?",
            (exclude_project_id or "", limit),
        ).fetchall()
    return [_baseline_row(r) for r in rows]


# ------------------------------------------------------------------ organization library (Module 1)


def add_reference(
    filename: str, kind: str, role: str, text: str, created_by: str | None, original: bytes | None = None
) -> dict:
    """`original` is kept for Word templates, so exports can be laid out in the PM's own document."""
    rid = str(uuid.uuid4())
    with _connect() as c:
        c.execute(
            "INSERT INTO reference_documents (id, filename, kind, role, text, characters, created_at, created_by, original) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (rid, filename, kind, role, text, len(text), _now(), created_by, original),
        )
    return next(r for r in list_references() if r["id"] == rid)


def list_references(with_text: bool = False) -> list[dict]:
    cols = ("id, filename, kind, role, text, characters, created_at, created_by" if with_text
            else "id, filename, kind, role, characters, created_at, created_by")
    with _connect() as c:
        rows = c.execute(
            f"SELECT {cols}, original IS NOT NULL AS has_layout FROM reference_documents ORDER BY created_at DESC"
        ).fetchall()
    return [{**dict(r), "has_layout": bool(r["has_layout"])} for r in rows]


def latest_word_template() -> dict | None:
    """The most recent Word template of the library, with its file."""
    with _connect() as c:
        r = c.execute(
            "SELECT id, filename, original FROM reference_documents WHERE role = 'template' AND original IS NOT NULL "
            "ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    return dict(r) if r else None


def delete_reference(reference_id: str) -> bool:
    with _connect() as c:
        return c.execute("DELETE FROM reference_documents WHERE id = ?", (reference_id,)).rowcount > 0
