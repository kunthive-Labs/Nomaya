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
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from . import store
from .config import settings
from .models import RunResult
from .orchestrator import EvaluationCancelled, EvaluationLimitExceeded, run_suite
from .redaction import redact_run
from .regulations import load_registry
from .scenarios import load_scenarios

logger = logging.getLogger("nomaya.api")

_bearer = HTTPBearer(auto_error=False)


def require_auth(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> str:
    """Authenticate a request and return its effective API role.

    Authentication remains intentionally disabled when no token is configured
    for local development. Production validation rejects that configuration.
    """
    tokens = settings.auth_tokens  # read per-request so tests can monkeypatch env
    if not tokens:
        return "admin"
    if creds is None:
        raise HTTPException(401, "Invalid or missing bearer token")
    for token, role in tokens.items():
        if secrets.compare_digest(creds.credentials, token):
            return role
    raise HTTPException(401, "Invalid or missing bearer token")


def require_runner(role: str = Depends(require_auth)) -> None:
    """Only a runner or admin may create/cancel evaluations."""
    if role not in {"runner", "admin"}:
        raise HTTPException(403, "This token is not permitted to run evaluations")


def require_admin(role: str = Depends(require_auth)) -> None:
    """Administrative review endpoints require an admin credential."""
    if role != "admin":
        raise HTTPException(403, "This token is not permitted to administer Nomaya")


class RunRequest(BaseModel):
    agent: str | None = None
    judge: str | None = None
    k: int = Field(1, ge=1, le=10)
    tags: list[str] | None = None
    save: bool = True
    max_cost_usd: float | None = Field(None, ge=0)
    max_duration_seconds: float | None = Field(None, gt=0)


JobStatus = Literal["queued", "running", "completed", "failed", "cancelled"]


@dataclass
class _Job:
    job_id: str
    request: RunRequest
    agent: str
    judge: str
    scenarios: list
    status: JobStatus = "queued"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    started_at: str | None = None
    completed_at: str | None = None
    completed_work: int = 0
    total_work: int = 0
    result: dict | None = None
    error: str | None = None
    cancel_requested: threading.Event = field(default_factory=threading.Event)
    future: Future | None = None


class JobManager:
    """Small in-process queue for development and single-process deployments.

    State lives in memory deliberately; durable distributed execution belongs in
    a deployment-specific worker system. Cancellation is cooperative because a
    provider call already in flight cannot be safely interrupted.
    """

    def __init__(self, max_workers: int, max_queued: int):
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="nomaya-run")
        self._max_queued = max_queued
        self._jobs: dict[str, _Job] = {}
        self._lock = threading.Lock()

    def submit(self, request: RunRequest, agent: str, judge: str, scenarios: list) -> _Job:
        with self._lock:
            active = sum(job.status in {"queued", "running"} for job in self._jobs.values())
            if active >= self._max_queued:
                raise HTTPException(429, "Evaluation queue is full; try again later.")
            job = _Job(
                job_id=f"job_{uuid.uuid4().hex}",
                request=request,
                agent=agent,
                judge=judge,
                scenarios=scenarios,
                total_work=len(scenarios) * request.k,
            )
            self._jobs[job.job_id] = job
            job.future = self._executor.submit(self._execute, job)
            return job

    def _execute(self, job: _Job) -> None:
        with self._lock:
            if job.cancel_requested.is_set():
                job.status = "cancelled"
                job.completed_at = datetime.now(UTC).isoformat()
                return
            job.status = "running"
            job.started_at = datetime.now(UTC).isoformat()

        def progress(completed: int, total: int) -> None:
            with self._lock:
                job.completed_work, job.total_work = completed, total

        try:
            result = run_suite(
                job.scenarios,
                agent_model=job.agent,
                judge_model=job.judge,
                k=job.request.k,
                max_cost_usd=_effective_limit(job.request.max_cost_usd, settings.max_run_cost_usd),
                max_duration_seconds=_effective_limit(
                    job.request.max_duration_seconds, settings.max_run_duration_seconds
                ),
                cancelled=job.cancel_requested.is_set,
                on_progress=progress,
            )
            if job.request.save:
                store.save_run(result)
            with self._lock:
                job.status = "completed"
                job.result = result.model_dump()
        except EvaluationCancelled:
            with self._lock:
                job.status = "cancelled"
                job.error = "Evaluation was cancelled."
        except EvaluationLimitExceeded as exc:
            with self._lock:
                job.status = "failed"
                job.error = str(exc)
        except Exception:
            logger.exception("Evaluation job failed (agent=%s judge=%s)", job.agent, job.judge)
            with self._lock:
                job.status = "failed"
                job.error = "Evaluation run failed; see server logs."
        finally:
            with self._lock:
                job.completed_at = datetime.now(UTC).isoformat()

    def get(self, job_id: str) -> _Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> _Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if job.status in {"completed", "failed", "cancelled"}:
                return job
            job.cancel_requested.set()
            if job.status == "queued" and job.future and job.future.cancel():
                job.status = "cancelled"
                job.completed_at = datetime.now(UTC).isoformat()
            return job

    def payload(self, job: _Job) -> dict:
        with self._lock:
            # Job results are returned to the browser/API caller as well as
            # persisted. Do not make the asynchronous API a bypass around the
            # default durable-artifact redaction policy.
            result = job.result
            if result and settings.storage_redact_pii:
                result = redact_run(RunResult.model_validate(result)).model_dump(mode="json")
            return {
                "job_id": job.job_id,
                "status": job.status,
                "created_at": job.created_at,
                "started_at": job.started_at,
                "completed_at": job.completed_at,
                "progress": {"completed": job.completed_work, "total": job.total_work},
                "result": result,
                "error": job.error,
            }

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)


def _effective_limit(requested: float | None, configured: float) -> float:
    """A caller can tighten a configured limit but never loosen one."""
    if requested is None:
        return configured
    if configured == 0:
        return requested
    return min(requested, configured)


def _check_allowed(model: str) -> None:
    allowed = settings.allowed_models
    if "*" in allowed or model in allowed:
        return
    raise HTTPException(400, f"Model '{model}' is not in NOMAYA_ALLOWED_MODELS")


def create_app() -> FastAPI:
    validator = getattr(settings, "validate_production_settings", None)
    if validator:
        validator()
    jobs = JobManager(settings.max_concurrent_runs, settings.max_queued_runs)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        jobs.shutdown()

    app = FastAPI(title="Nomaya API", version="0.1.0", lifespan=lifespan)
    app.state.jobs = jobs
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
            len(store.list_runs(limit=1))
            db_status = "connected"
        except Exception:
            db_status = "error"
        return {
            "status": "ok",
            "database": db_status,
            "agent_model": settings.agent_model,
            "judge_model": settings.judge_model,
            "allowed_models": settings.allowed_models,
            "max_concurrent_runs": settings.max_concurrent_runs,
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
            scenarios = {s.id: s.tags for s in load_scenarios()}
            filtered = []
            for r in all_runs:
                payload = store.get_run(r["run_id"])
                if payload:
                    has_tag = any(tag in scenarios.get(sr.scenario_id, []) for sr in payload.scenario_runs)
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

    @router.get("/api/audit-events", dependencies=[Depends(require_admin)])
    def audit_events(limit: int = Query(100, ge=1, le=500)):
        return store.list_audit_events(limit=limit)

    @router.post("/api/run", dependencies=[Depends(require_runner)])
    def trigger_run(req: RunRequest):
        agent = req.agent or settings.agent_model
        judge = req.judge or settings.judge_model
        _check_allowed(agent)
        _check_allowed(judge)
        scenarios_ = load_scenarios(tags=req.tags)
        if not scenarios_:
            raise HTTPException(400, "No scenarios match the given tags")
        if len(scenarios_) * req.k > settings.max_run_scenarios:
            raise HTTPException(400, "Requested evaluation exceeds NOMAYA_MAX_RUN_SCENARIOS")
        job = jobs.submit(req, agent, judge, scenarios_)
        try:
            assert job.future is not None
            job.future.result()
        except Exception:  # _execute translates errors into the job state
            logger.exception("Unexpected evaluation worker error")
        payload = jobs.payload(job)
        if payload["status"] == "completed":
            return payload["result"]
        detail = payload["error"] or "Evaluation run failed; see server logs."
        status = 409 if payload["status"] == "cancelled" else 422
        raise HTTPException(status, detail)

    @router.post("/api/jobs", status_code=202, dependencies=[Depends(require_runner)])
    def submit_job(req: RunRequest):
        agent = req.agent or settings.agent_model
        judge = req.judge or settings.judge_model
        _check_allowed(agent)
        _check_allowed(judge)
        scenarios_ = load_scenarios(tags=req.tags)
        if not scenarios_:
            raise HTTPException(400, "No scenarios match the given tags")
        if len(scenarios_) * req.k > settings.max_run_scenarios:
            raise HTTPException(400, "Requested evaluation exceeds NOMAYA_MAX_RUN_SCENARIOS")
        job = jobs.submit(req, agent, judge, scenarios_)
        store.append_audit_event("job_submitted", {"job_id": job.job_id, "agent": agent, "judge": judge})
        return jobs.payload(job)

    @router.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        return jobs.payload(job)

    @router.delete("/api/jobs/{job_id}", dependencies=[Depends(require_runner)])
    def cancel_job(job_id: str):
        job = jobs.cancel(job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        store.append_audit_event("job_cancel_requested", {"job_id": job_id})
        return jobs.payload(job)

    app.include_router(router)

    return app


api = create_app()
