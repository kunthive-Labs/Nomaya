"""FastAPI service — serves run history and metrics to the Next.js dashboard,
and can trigger new evaluation runs.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import store
from .config import settings
from .orchestrator import run_suite
from .regulations import load_registry
from .scenarios import load_scenarios

api = FastAPI(title="Nomaya API", version="0.1.0")
api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class RunRequest(BaseModel):
    agent: str | None = None
    judge: str | None = None
    k: int = 1
    tags: list[str] | None = None
    save: bool = True


@api.get("/api/health")
def health():
    return {"status": "ok", "agent_model": settings.agent_model, "judge_model": settings.judge_model}


@api.get("/api/regulations")
def regulations():
    return [r.model_dump() for r in load_registry().values()]


@api.get("/api/scenarios")
def scenarios():
    return [s.model_dump() for s in load_scenarios()]


@api.get("/api/runs")
def runs(limit: int = 50):
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


@api.post("/api/run")
def trigger_run(req: RunRequest):
    scenarios_ = load_scenarios(tags=req.tags)
    if not scenarios_:
        raise HTTPException(400, "No scenarios match the given tags")
    result = run_suite(scenarios_, agent_model=req.agent, judge_model=req.judge, k=req.k)
    if req.save:
        store.save_run(result)
    return result.model_dump()
