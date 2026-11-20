"""SQLite storage for Orbit's own data: reports now, baselines and anomalies later.

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
"""


def _connect() -> sqlite3.Connection:
    path = Path(get_settings().database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
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
