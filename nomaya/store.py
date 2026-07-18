"""Run-history persistence (SQLite, stdlib only).

Each evaluation run is stored as a row: indexed summary columns for fast listing
plus the full RunResult JSON blob so the API/dashboard can render any past run.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .config import settings
from .models import RunResult
from .redaction import redact_run, redact_value

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id       TEXT PRIMARY KEY,
    created_at   TEXT NOT NULL,
    agent_model  TEXT NOT NULL,
    judge_model  TEXT NOT NULL,
    pass_rate    REAL,
    total_runs   INTEGER,
    violations   INTEGER,
    payload      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
    event_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at   TEXT NOT NULL,
    event_type   TEXT NOT NULL,
    details      TEXT NOT NULL
);
"""


def _connect(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or settings.db_path
    if path != ":memory:" and not path.startswith("file:"):
        Path(path).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    conn = sqlite3.connect(path, timeout=getattr(settings, "db_timeout", 5.0))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {int(settings.db_timeout * 1000)}")
    conn.executescript(_SCHEMA)
    _restrict_database_permissions(path)
    return conn


def _restrict_database_permissions(path: str) -> None:
    """Keep the local run history owner-readable only on POSIX systems."""
    if not settings.enforce_private_storage or os.name != "posix" or path == ":memory:" or path.startswith("file:"):
        return
    try:
        os.chmod(path, 0o600)
    except OSError as exc:
        raise RuntimeError(f"Unable to secure Nomaya database permissions: {path}") from exc


def save_run(run: RunResult, db_path: str | None = None) -> None:
    stored_run = redact_run(run) if settings.storage_redact_pii else run
    conn = _connect(db_path)
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO runs "
            "(run_id, created_at, agent_model, judge_model, pass_rate, total_runs, violations, payload) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                stored_run.run_id,
                stored_run.created_at,
                stored_run.agent_model,
                stored_run.judge_model,
                stored_run.metrics.get("pass_rate"),
                stored_run.metrics.get("total_runs"),
                stored_run.metrics.get("total_violations"),
                stored_run.model_dump_json(),
            ),
        )
        _append_audit_event(conn, "run_saved", {"run_id": stored_run.run_id, "agent_model": stored_run.agent_model})
        if settings.retention_days is not None:
            deleted = _purge_runs_before(conn, datetime.now(UTC) - timedelta(days=settings.retention_days))
            if deleted:
                _append_audit_event(conn, "runs_retention_purged", {"count": deleted})
    conn.close()


def _purge_runs_before(conn: sqlite3.Connection, before: datetime) -> int:
    """Delete saved runs older than an aware UTC timestamp; caller owns transaction."""
    cutoff = before.astimezone(UTC).isoformat()
    cursor = conn.execute("DELETE FROM runs WHERE created_at < ?", (cutoff,))
    return cursor.rowcount


def _append_audit_event(conn: sqlite3.Connection, event_type: str, details: dict) -> None:
    """Append an application audit record using a caller-owned transaction."""
    safe_details = redact_value(details)
    conn.execute(
        "INSERT INTO audit_events (created_at, event_type, details) VALUES (?,?,?)",
        (datetime.now(UTC).isoformat(), event_type, json.dumps(safe_details, sort_keys=True)),
    )


def append_audit_event(event_type: str, details: dict, db_path: str | None = None) -> None:
    """Record an operational event; values are redacted before storage."""
    conn = _connect(db_path)
    with conn:
        _append_audit_event(conn, event_type, details)
    conn.close()


def list_audit_events(limit: int = 100, db_path: str | None = None) -> list[dict]:
    """Return newest-first, redacted application audit records."""
    conn = _connect(db_path)
    rows = conn.execute(
        "SELECT event_id, created_at, event_type, details FROM audit_events ORDER BY event_id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [{**dict(row), "details": json.loads(row["details"])} for row in rows]


def purge_runs(before: datetime, db_path: str | None = None) -> int:
    """Permanently delete runs created before ``before`` and return the count.

    This explicit primitive is suitable for a scheduled retention job.  Normal
    saves also apply ``NOMAYA_RETENTION_DAYS`` when configured.
    """
    if before.tzinfo is None:
        raise ValueError("Retention cutoff must be timezone-aware")
    conn = _connect(db_path)
    with conn:
        deleted = _purge_runs_before(conn, before)
        if deleted:
            _append_audit_event(conn, "runs_purged", {"count": deleted, "before": before.isoformat()})
    conn.close()
    return deleted


def list_runs(limit: int = 50, db_path: str | None = None) -> list[dict]:
    conn = _connect(db_path)
    rows = conn.execute(
        "SELECT run_id, created_at, agent_model, judge_model, pass_rate, total_runs, violations "
        "FROM runs ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_run(run_id: str, db_path: str | None = None) -> RunResult | None:
    conn = _connect(db_path)
    row = conn.execute("SELECT payload FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    conn.close()
    if not row:
        return None
    return RunResult.model_validate_json(row["payload"])


def latest_run(db_path: str | None = None) -> RunResult | None:
    runs = list_runs(limit=1, db_path=db_path)
    return get_run(runs[0]["run_id"], db_path=db_path) if runs else None
