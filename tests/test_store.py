"""SQLite history store — save/list/get/latest against an isolated tmp DB."""

from __future__ import annotations

from nomaya import store
from nomaya.orchestrator import run_suite
from nomaya.scenarios import load_scenarios


def _make_run():
    return run_suite(load_scenarios()[:2], agent_model="mock/compliant-agent", judge_model="mock/judge")


def test_save_list_get_latest(tmp_path):
    db = str(tmp_path / "h.sqlite3")
    run = _make_run()
    store.save_run(run, db_path=db)

    rows = store.list_runs(db_path=db)
    assert len(rows) == 1
    assert rows[0]["run_id"] == run.run_id
    assert rows[0]["agent_model"] == "mock/compliant-agent"

    fetched = store.get_run(run.run_id, db_path=db)
    assert fetched is not None and fetched.run_id == run.run_id

    assert store.latest_run(db_path=db).run_id == run.run_id


def test_get_missing_returns_none(tmp_path):
    db = str(tmp_path / "empty.sqlite3")
    assert store.get_run("nope", db_path=db) is None
    assert store.latest_run(db_path=db) is None
    assert store.list_runs(db_path=db) == []


def test_save_is_idempotent_on_run_id(tmp_path):
    db = str(tmp_path / "idem.sqlite3")
    run = _make_run()
    store.save_run(run, db_path=db)
    store.save_run(run, db_path=db)  # INSERT OR REPLACE -> still one row
    assert len(store.list_runs(db_path=db)) == 1


def test_ping(tmp_path):
    assert store.ping(db_path=str(tmp_path / "p.sqlite3")) is True
