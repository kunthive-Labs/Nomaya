"""Run-history persistence (SQLite, stdlib only).

Each evaluation run is stored as a row: indexed summary columns for fast listing
plus the full RunResult JSON blob so the API/dashboard can render any past run.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .config import settings
from .models import RunResult

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
"""


def _connect(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or settings.db_path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=getattr(settings, "db_timeout", 5.0))
    conn.row_factory = sqlite3.Row
    conn.execute(_SCHEMA)
    return conn


def save_run(run: RunResult, db_path: str | None = None) -> None:
    conn = _connect(db_path)
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO runs "
            "(run_id, created_at, agent_model, judge_model, pass_rate, total_runs, violations, payload) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                run.run_id,
                run.created_at,
                run.agent_model,
                run.judge_model,
                run.metrics.get("pass_rate"),
                run.metrics.get("total_runs"),
                run.metrics.get("total_violations"),
                run.model_dump_json(),
            ),
        )
    conn.close()


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
