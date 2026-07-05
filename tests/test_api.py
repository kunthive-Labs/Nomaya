"""FastAPI service: endpoints, validation bounds, allow-list, and auth."""


def test_health_reports_models(make_client):
    res = make_client().get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert "mock/compliant-agent" in body["allowed_models"]


def test_regulations_and_scenarios_listings(make_client):
    client = make_client()
    regs = client.get("/api/regulations").json()
    assert any(r["id"] == "DORA" for r in regs)
    scenarios = client.get("/api/scenarios").json()
    assert len(scenarios) >= 11


def test_latest_404_when_empty(make_client):
    assert make_client().get("/api/runs/latest").status_code == 404


def test_get_run_404_for_unknown_id(make_client):
    assert make_client().get("/api/runs/nope").status_code == 404


def test_limit_bounds(make_client):
    client = make_client()
    assert client.get("/api/runs?limit=0").status_code == 422
    assert client.get("/api/runs?limit=999").status_code == 422
    assert client.get("/api/runs?limit=200").status_code == 200


def test_k_bounds(make_client):
    client = make_client()
    assert client.post("/api/run", json={"k": 0}).status_code == 422
    assert client.post("/api/run", json={"k": 11}).status_code == 422


def test_model_allow_list(make_client):
    client = make_client()
    res = client.post("/api/run", json={"agent": "openai/gpt-4o"})
    assert res.status_code == 400
    assert "NOMAYA_ALLOWED_MODELS" in res.json()["detail"]


def test_allow_list_wildcard_permits_any_model_string(make_client):
    client = make_client(allowed="*")
    # mock/anything routes to the deterministic provider, so no network happens
    res = client.post("/api/run", json={"agent": "mock/compliant-agent", "save": False})
    assert res.status_code == 200


def test_unknown_tags_rejected(make_client):
    res = make_client().post("/api/run", json={"tags": ["no-such-tag"]})
    assert res.status_code == 400


def test_run_and_history_round_trip(make_client):
    client = make_client()
    res = client.post("/api/run", json={"agent": "mock/compliant-agent", "k": 1})
    assert res.status_code == 200
    run_id = res.json()["run_id"]
    assert res.json()["metrics"]["pass_rate"] == 1.0

    listed = client.get("/api/runs").json()
    assert [r["run_id"] for r in listed] == [run_id]
    assert client.get(f"/api/runs/{run_id}").json()["run_id"] == run_id
    assert client.get("/api/runs/latest").json()["run_id"] == run_id


def test_auth_disabled_when_no_token(make_client):
    assert make_client().get("/api/runs").status_code == 200


def test_auth_enforced_when_token_set(make_client):
    client = make_client(token="sekret")
    assert client.get("/api/runs").status_code == 401
    assert client.get("/api/runs", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/api/runs", headers={"Authorization": "Bearer sekret"}).status_code == 200
    # liveness probe stays open
    assert client.get("/api/health").status_code == 200


def test_runs_tag_filter(make_client):
    client = make_client()
    res = client.post("/api/run", json={"agent": "mock/compliant-agent", "tags": ["lending"], "save": True})
    assert res.status_code == 200
    listed_filtered = client.get("/api/runs?tag=lending").json()
    assert len(listed_filtered) >= 1
    listed_empty = client.get("/api/runs?tag=no-such-tag").json()
    assert len(listed_empty) == 0
