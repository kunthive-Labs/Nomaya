"""FastAPI service — serves run history and metrics to the Next.js dashboard,
and can trigger new evaluation runs.

Hardening:
  * Optional bearer-token auth (NOMAYA_API_TOKEN; unset = open, for local dev).
    /api/health stays unauthenticated as a liveness probe.
  * POST /api/run only accepts models on the NOMAYA_ALLOWED_MODELS allow-list,
    so an unauthenticated caller can't burn paid-provider credits.
  * Bounded k and limit parameters; CORS restricted to NOMAYA_CORS_ORIGINS.
"""

from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from . import store
from .config import settings
from .orchestrator import run_suite
from .regulations import load_registry
from .scenarios import load_scenarios

logger = logging.getLogger("nomaya.api")

_bearer = HTTPBearer(auto_error=False)


def require_auth(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> None:
    token = settings.api_token  # read per-request so tests can monkeypatch env
    if not token:
        return
    if creds is None or not secrets.compare_digest(creds.credentials, token):
        raise HTTPException(401, "Invalid or missing bearer token")


class RunRequest(BaseModel):
    agent: str | None = None
    judge: str | None = None
    k: int = Field(1, ge=1, le=10)
    tags: list[str] | None = None
    save: bool = True


def _check_allowed(model: str) -> None:
    allowed = settings.allowed_models
    if "*" in allowed or model in allowed:
        return
    raise HTTPException(400, f"Model '{model}' is not in NOMAYA_ALLOWED_MODELS")


def create_app() -> FastAPI:
    app = FastAPI(title="Nomaya API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health():
        try:
            # Quick check to ensure database access works
            runs_count = len(store.list_runs(limit=1))
            db_status = "connected"
        except Exception:
            db_status = "error"
        return {
            "status": "ok",
            "database": db_status,
            "agent_model": settings.agent_model,
            "judge_model": settings.judge_model,
            "allowed_models": settings.allowed_models,
        }

    router = APIRouter(dependencies=[Depends(require_auth)])

    @router.get("/api/regulations")
    def regulations():
        return [r.model_dump() for r in load_registry().values()]

    @router.get("/api/scenarios")
    def scenarios():
        return [s.model_dump() for s in load_scenarios()]

    @router.get("/api/runs")
    def runs(limit: int = Query(50, ge=1, le=200), tag: str | None = None):
        all_runs = store.list_runs(limit=limit)
        if tag:
            filtered = []
            for r in all_runs:
                payload = store.get_run(r["run_id"])
                if payload:
                    has_tag = any(tag in (sr.tags or []) for sr in payload.scenario_runs)
                    if has_tag:
                        filtered.append(r)
            return filtered
        return all_runs

    @router.get("/api/runs/latest")
    def latest():
        run = store.latest_run()
        if not run:
            raise HTTPException(404, "No runs yet")
        return run.model_dump()

    @router.get("/api/runs/{run_id}")
    def get_run(run_id: str):
        run = store.get_run(run_id)
        if not run:
            raise HTTPException(404, "Run not found")
        return run.model_dump()

    @router.post("/api/run")
    def trigger_run(req: RunRequest):
        agent = req.agent or settings.agent_model
        judge = req.judge or settings.judge_model
        _check_allowed(agent)
        _check_allowed(judge)
        scenarios_ = load_scenarios(tags=req.tags)
        if not scenarios_:
            raise HTTPException(400, "No scenarios match the given tags")
        try:
            result = run_suite(scenarios_, agent_model=agent, judge_model=judge, k=req.k)
            if req.save:
                store.save_run(result)
        except HTTPException:
            raise
        except Exception:
            logger.exception("Evaluation run failed (agent=%s judge=%s)", agent, judge)
            raise HTTPException(500, "Evaluation run failed; see server logs") from None
        return result.model_dump()

    app.include_router(router)
    return app


api = create_app()
