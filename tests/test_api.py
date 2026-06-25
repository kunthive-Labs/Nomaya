"""API surface tests via FastAPI's TestClient — fully offline (mock models, tmp DB).

Covers the contract the dashboard depends on plus the production guards added for
hardening: a DB-pinging health check, k bounds, and optional API-key auth.
"""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


def _client(monkeypatch, tmp_path, **env):
    """Build a TestClient with a fresh module import so env-driven settings apply.

    api.py reads CORS/auth config at import time, so we reimport per-config.
    """
    monkeypatch.setenv("NOMAYA_DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("NOMAYA_AGENT_MODEL", "mock/compliant-agent")
    monkeypatch.setenv("NOMAYA_JUDGE_MODEL", "mock/judge")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import nomaya.api as api_module

    importlib.reload(api_module)
    return TestClient(api_module.api)


def test_health_pings_db(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    body = c.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["auth_required"] is False


def test_scenarios_and_regulations_listed(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    assert len(c.get("/api/scenarios").json()) >= 1
    assert len(c.get("/api/regulations").json()) >= 1


def test_run_happy_path_and_persistence(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    r = c.post("/api/run", json={"agent": "mock/compliant-agent", "k": 1, "save": True})
    assert r.status_code == 200
    run_id = r.json()["run_id"]

    # the run is now retrievable through the history endpoints
    assert c.get("/api/runs/latest").json()["run_id"] == run_id
    assert c.get(f"/api/runs/{run_id}").json()["run_id"] == run_id
    assert any(row["run_id"] == run_id for row in c.get("/api/runs").json())


def test_k_is_bounded(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    assert c.post("/api/run", json={"k": 0}).status_code == 422
    assert c.post("/api/run", json={"k": 9999}).status_code == 422


def test_unknown_run_is_404(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    assert c.get("/api/runs/does-not-exist").status_code == 404


def test_api_key_enforced_on_mutations(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path, NOMAYA_API_KEY="s3cret")
    # read routes stay open
    assert c.get("/api/health").json()["auth_required"] is True
    # mutating route rejects without / with wrong key, accepts the right one
    assert c.post("/api/run", json={"k": 1, "save": False}).status_code == 401
    assert c.post("/api/run", json={"k": 1, "save": False},
                  headers={"X-API-Key": "wrong"}).status_code == 401
    ok = c.post("/api/run", json={"agent": "mock/compliant-agent", "k": 1, "save": False},
                headers={"X-API-Key": "s3cret"})
    assert ok.status_code == 200


@pytest.fixture(autouse=True)
def _restore_api_module():
    """Reload api with the ambient env after each test so other modules see defaults."""
    yield
    import nomaya.api as api_module

    importlib.reload(api_module)
