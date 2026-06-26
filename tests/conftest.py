import pytest

from nomaya.orchestrator import run_suite
from nomaya.scenarios import load_scenarios


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Point the store at a throwaway SQLite file (Settings reads env lazily)."""
    path = tmp_path / "nomaya-test.sqlite3"
    monkeypatch.setenv("NOMAYA_DB_PATH", str(path))
    return path


@pytest.fixture(scope="session")
def sample_run():
    """A small real RunResult produced by the deterministic mock pipeline."""
    scenarios = load_scenarios()[:2]
    return run_suite(scenarios, agent_model="mock/compliant-agent", judge_model="mock/judge")


@pytest.fixture
def make_client(tmp_db, monkeypatch):
    """Factory for API test clients with per-test env (token, allow-list)."""

    def _make(token: str | None = None, allowed: str | None = None):
        from fastapi.testclient import TestClient

        from nomaya.api import create_app

        if token is not None:
            monkeypatch.setenv("NOMAYA_API_TOKEN", token)
        else:
            monkeypatch.delenv("NOMAYA_API_TOKEN", raising=False)
        if allowed is not None:
            monkeypatch.setenv("NOMAYA_ALLOWED_MODELS", allowed)
        else:
            monkeypatch.delenv("NOMAYA_ALLOWED_MODELS", raising=False)
        return TestClient(create_app())

    return _make
