"""FastAPI service — serves run history and metrics to the Next.js dashboard,
and can trigger new evaluation runs.

Production notes:
- CORS origins come from `NOMAYA_CORS_ORIGINS` (comma-separated; default `*` for
  local dev). Set it to your dashboard origin in production.
- If `NOMAYA_API_KEY` is set, mutating routes (`POST /api/run`) require a matching
  `X-API-Key` header — important because a run can spend real money against a live
  provider. Read routes stay open so the dashboard works without a key.
- `RunRequest.k` is bounded to keep a single request from launching an unbounded
  (and unboundedly expensive) number of model calls.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import store
from .config import settings
from .errors import ConfigError, NomayaError
from .logging import configure_logging, get_logger
from .orchestrator import run_suite
from .regulations import load_registry
from .scenarios import load_scenarios

configure_logging()
log = get_logger("api")

api = FastAPI(title="Nomaya API", version="0.1.0")
api.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Dependency: enforce `X-API-Key` when `NOMAYA_API_KEY` is configured."""
    expected = settings.api_key
    if expected and x_api_key != expected:
        raise HTTPException(401, "Missing or invalid API key.")


class RunRequest(BaseModel):
    agent: str | None = None
    judge: str | None = None
    k: int = Field(1, ge=1, le=settings.max_k, description="Attempts per scenario (pass@k).")
    tags: list[str] | None = None
    save: bool = True


@api.get("/api/health")
def health():
    db_ok = store.ping()
    return {
        "status": "ok" if db_ok else "degraded",
        "version": api.version,
        "db": "ok" if db_ok else "unavailable",
        "agent_model": settings.agent_model,
        "judge_model": settings.judge_model,
        "auth_required": settings.api_key is not None,
    }


@api.get("/api/regulations")
def regulations():
    return [r.model_dump() for r in load_registry().values()]


@api.get("/api/scenarios")
def scenarios():
    return [s.model_dump() for s in load_scenarios()]


@api.get("/api/runs")
def runs(limit: int = 50):
    limit = max(1, min(limit, 500))
    return store.list_runs(limit=limit)


@api.get("/api/runs/latest")
def latest():
    run = store.latest_run()
    if not run:
        raise HTTPException(404, "No runs yet")
    return run.model_dump()


@api.get("/api/runs/{run_id}")
def get_run(run_id: str):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run.model_dump()


@api.post("/api/run", dependencies=[Depends(require_api_key)])
def trigger_run(req: RunRequest):
    scenarios_ = load_scenarios(tags=req.tags)
    if not scenarios_:
        raise HTTPException(400, "No scenarios match the given tags")
    log.info("api run trigger · agent=%s judge=%s k=%d", req.agent, req.judge, req.k)
    try:
        result = run_suite(scenarios_, agent_model=req.agent, judge_model=req.judge, k=req.k)
    except ConfigError as exc:
        raise HTTPException(400, str(exc)) from exc
    except NomayaError as exc:
        raise HTTPException(502, f"Evaluation failed: {exc}") from exc
    if req.save:
        store.save_run(result)
    return result.model_dump()
