"""SQLite run-history persistence."""

from datetime import UTC, datetime
from stat import S_IMODE

from nomaya import store
from nomaya.models import RunResult, ScenarioLabel, ScenarioRun, ToolCall, Transcript, Turn


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


def test_persisted_payload_is_redacted_without_mutating_run(tmp_path):
    db = str(tmp_path / "t.sqlite3")
    secret = "412-55-9931"
    original = _run("run-pii", "2026-07-03T10:00:00")
    original.scenario_runs = [
        ScenarioRun(
            scenario_id="pii",
            title="PII test",
            label=ScenarioLabel.VIOLATION_EXPECTED,
            transcript=Transcript(
                turns=[
                    Turn(role="customer", content=f"My SSN is {secret}"),
                    Turn(role="agent", content="I will use your details.", tool_calls=[]),
                ]
            ),
        )
    ]
    store.save_run(original, db_path=db)

    assert secret in original.scenario_runs[0].transcript.turns[0].content
    assert secret not in (tmp_path / "t.sqlite3").read_bytes().decode("latin-1")
    restored = store.get_run("run-pii", db_path=db)
    assert restored is not None
    assert "[REDACTED:SSN]" in restored.scenario_runs[0].transcript.turns[0].content


def test_persisted_payload_redacts_opaque_values_from_sensitive_context_keys(tmp_path):
    db = str(tmp_path / "t.sqlite3")
    recovery_code = "R-8291-4492"
    original = _run("run-recovery", "2026-07-03T10:00:00")
    original.scenario_runs = [
        ScenarioRun(
            scenario_id="fraud",
            title="Fraud test",
            label=ScenarioLabel.VIOLATION_EXPECTED,
            transcript=Transcript(
                turns=[
                    Turn(
                        role="agent",
                        content=f"Your recovery code is {recovery_code}",
                        tool_calls=[ToolCall(name="get_account", result={"recovery_code": recovery_code})],
                    )
                ]
            ),
        )
    ]
    store.save_run(original, db_path=db)
    restored = store.get_run("run-recovery", db_path=db)
    assert restored is not None
    assert recovery_code not in restored.model_dump_json()
    assert "[REDACTED:SENSITIVE]" in restored.model_dump_json()


def test_purge_runs_removes_only_older_records(tmp_path):
    db = str(tmp_path / "t.sqlite3")
    store.save_run(_run("run-old", "2020-01-01T00:00:00+00:00"), db_path=db)
    store.save_run(_run("run-current", "2030-01-01T00:00:00+00:00"), db_path=db)

    deleted = store.purge_runs(datetime(2025, 1, 1, tzinfo=UTC), db_path=db)

    assert deleted == 1
    assert [row["run_id"] for row in store.list_runs(db_path=db)] == ["run-current"]


def test_purge_runs_requires_timezone_aware_cutoff(tmp_path):
    try:
        store.purge_runs(datetime(2025, 1, 1), db_path=str(tmp_path / "t.sqlite3"))
    except ValueError as exc:
        assert "timezone-aware" in str(exc)
    else:
        raise AssertionError("Expected timezone validation")


def test_database_is_owner_only_by_default_on_posix(tmp_path, monkeypatch):
    db = tmp_path / "t.sqlite3"
    monkeypatch.delenv("NOMAYA_ENFORCE_PRIVATE_STORAGE", raising=False)
    store.save_run(_run("run-private", "2026-07-03T10:00:00"), db_path=str(db))
    assert S_IMODE(db.stat().st_mode) == 0o600


def test_audit_events_are_redacted_and_newest_first(tmp_path):
    db = str(tmp_path / "t.sqlite3")
    store.append_audit_event("first", {"password": "do-not-store"}, db_path=db)
    store.append_audit_event("second", {"run_id": "run-2"}, db_path=db)
    events = store.list_audit_events(db_path=db)
    assert [event["event_type"] for event in events] == ["second", "first"]
    assert events[-1]["details"]["password"] == "[REDACTED:SENSITIVE]"
