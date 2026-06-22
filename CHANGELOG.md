# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Provider resilience**: configurable request timeout and bounded exponential-backoff
  retries on transient failures (timeouts, rate limits, 5xx) in the LiteLLM provider.
- **Error hierarchy** (`nomaya/errors.py`): `NomayaError`, `ConfigError`, `ProviderError`,
  `ProviderTimeout`, `ProviderRateLimit`.
- **Structured logging** (`nomaya/logging.py`): secret-safe, level via `NOMAYA_LOG_LEVEL`.
- **Bring-your-own content**: `NOMAYA_PLAYBOOKS_DIR` / `NOMAYA_REGISTRY_PATH` overrides and
  `nomaya init` to scaffold a workspace — run your own scenarios without forking.
- **Per-scenario `jurisdiction`** so the agent persona is not hardcoded to the U.S.
- **API hardening**: configurable CORS origins (`NOMAYA_CORS_ORIGINS`), optional `X-API-Key`
  auth (`NOMAYA_API_KEY`), bounded `k`, DB-pinging `/api/health`, structured error responses.
- **Containerization**: `Dockerfile`, `dashboard/Dockerfile`, `docker-compose.yml`.
- **Tooling**: ruff + mypy config, `.pre-commit-config.yaml`, `Makefile`.
- **Docs**: `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`, `docs/DEPLOYMENT.md`.
- **Tests**: API, store, providers (retry/backoff), metrics edge cases, orchestrator error
  isolation — 39 tests total.
- **Dashboard**: run-history view and `fetch` timeouts.

### Changed
- Orchestrator isolates per-scenario failures as *errored* runs instead of aborting the suite;
  `MAX_TOOL_ITERS` is now configurable via `NOMAYA_MAX_TOOL_ITERS`.
- Rules engine degrades a raising evaluator to a failed check instead of crashing.
- Store guarantees connection close (`contextlib.closing`) and enables WAL mode.

## [0.1.0]

### Added
- Initial release: provider-agnostic compliance evaluation harness, deterministic mock mode,
  10 regulation-mapped playbooks, rules engine + PII detector, SQLite history, FastAPI service,
  Next.js dashboard, CI eval gate.
