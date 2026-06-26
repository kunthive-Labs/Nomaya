"""SQLite run-history persistence."""

from nomaya import store
from nomaya.models import RunResult


def _run(run_id: str, created_at: str, pass_rate: float = 1.0) -> RunResult:
    return RunResult(
        run_id=run_id,
        created_at=created_at,
        agent_model="mock/compliant-agent",
        judge_model="mock/judge",
        metrics={"pass_rate": pass_rate, "total_runs": 11, "total_violations": 0},
    )


def test_save_and_get_round_trip(tmp_path):
    db = str(tmp_path / "t.sqlite3")
    original = _run("run-1", "2026-07-03T10:00:00")
    store.save_run(original, db_path=db)
    loaded = store.get_run("run-1", db_path=db)
    assert loaded is not None
    assert loaded.model_dump() == original.model_dump()


def test_get_run_miss_returns_none(tmp_path):
    db = str(tmp_path / "t.sqlite3")
    assert store.get_run("missing", db_path=db) is None


def test_list_runs_ordering_and_limit(tmp_path):
    db = str(tmp_path / "t.sqlite3")
    store.save_run(_run("run-old", "2026-07-01T10:00:00"), db_path=db)
    store.save_run(_run("run-new", "2026-07-03T10:00:00"), db_path=db)
    rows = store.list_runs(db_path=db)
    assert [r["run_id"] for r in rows] == ["run-new", "run-old"]
    assert len(store.list_runs(limit=1, db_path=db)) == 1


def test_latest_run(tmp_path):
    db = str(tmp_path / "t.sqlite3")
    assert store.latest_run(db_path=db) is None
    store.save_run(_run("run-old", "2026-07-01T10:00:00"), db_path=db)
    store.save_run(_run("run-new", "2026-07-03T10:00:00"), db_path=db)
    latest = store.latest_run(db_path=db)
    assert latest is not None and latest.run_id == "run-new"


def test_save_is_idempotent_per_run_id(tmp_path):
    db = str(tmp_path / "t.sqlite3")
    store.save_run(_run("run-1", "2026-07-03T10:00:00", pass_rate=1.0), db_path=db)
    store.save_run(_run("run-1", "2026-07-03T10:00:00", pass_rate=0.5), db_path=db)
    rows = store.list_runs(db_path=db)
    assert len(rows) == 1
    assert rows[0]["pass_rate"] == 0.5
