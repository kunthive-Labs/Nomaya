"""Run-history persistence (SQLite, stdlib only).

Each evaluation run is stored as a row: indexed summary columns for fast listing
plus the full RunResult JSON blob so the API/dashboard can render any past run.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from .config import settings
from .logging import get_logger
from .models import RunResult

log = get_logger("store")

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
    conn = sqlite3.connect(path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    # WAL lets readers and a writer coexist without blocking — safer when the CLI
    # and the API touch the same DB. Best-effort: harmless if the backend rejects it.
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.DatabaseError:  # pragma: no cover - depends on filesystem
        pass
    conn.execute(_SCHEMA)
    return conn


def ping(db_path: str | None = None) -> bool:
    """Cheap connectivity check for health endpoints."""
    try:
        with closing(_connect(db_path)) as conn:
            conn.execute("SELECT 1").fetchone()
        return True
    except sqlite3.DatabaseError as exc:
        log.error("db ping failed: %s", exc)
        return False


def save_run(run: RunResult, db_path: str | None = None) -> None:
    with closing(_connect(db_path)) as conn:
        with conn:  # transaction: commits on success, rolls back on error
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
    log.info("saved run %s (%s)", run.run_id, run.agent_model)


def list_runs(limit: int = 50, db_path: str | None = None) -> list[dict]:
    with closing(_connect(db_path)) as conn:
        rows = conn.execute(
            "SELECT run_id, created_at, agent_model, judge_model, pass_rate, total_runs, violations "
            "FROM runs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_run(run_id: str, db_path: str | None = None) -> RunResult | None:
    with closing(_connect(db_path)) as conn:
        row = conn.execute("SELECT payload FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if not row:
        return None
    return RunResult.model_validate_json(row["payload"])


def latest_run(db_path: str | None = None) -> RunResult | None:
    runs = list_runs(limit=1, db_path=db_path)
    return get_run(runs[0]["run_id"], db_path=db_path) if runs else None
