"""Runtime configuration for Nomaya.

Reads from the process environment and an optional `.env` file at the project
root. No external dotenv dependency — we parse the handful of lines we need.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT / "reports"
PLAYBOOKS_DIR = Path(__file__).resolve().parent / "scenarios" / "playbooks"
REGISTRY_PATH = Path(__file__).resolve().parent / "regulations" / "registry.yaml"


def _load_dotenv(path: Path) -> None:
    """Populate os.environ from a .env file without clobbering existing vars."""
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


_load_dotenv(ROOT / ".env")


class Settings:
    """Lazily-read settings so tests can monkeypatch the environment."""

    @property
    def agent_model(self) -> str:
        return os.environ.get("NOMAYA_AGENT_MODEL", "mock/compliant-agent")

    @property
    def judge_model(self) -> str:
        return os.environ.get("NOMAYA_JUDGE_MODEL", "mock/judge")

    @property
    def db_path(self) -> str:
        return os.environ.get("NOMAYA_DB_PATH", str(ROOT / "nomaya.sqlite3"))

    @property
    def db_timeout(self) -> float:
        return float(os.environ.get("NOMAYA_DB_TIMEOUT", "5.0"))

    @property
    def storage_redact_pii(self) -> bool:
        """Whether durable artifacts are scrubbed before being written.

        This is on by default.  It can be disabled only for a controlled local
        debugging environment where retaining raw evaluation data is intended.
        """
        return _bool_env("NOMAYA_STORAGE_REDACT_PII", default=True)

    @property
    def retention_days(self) -> int | None:
        """Maximum age of saved runs, or ``None`` when retention is unmanaged."""
        raw = os.environ.get("NOMAYA_RETENTION_DAYS", "").strip()
        if not raw:
            return None
        try:
            days = int(raw)
        except ValueError as exc:
            raise ValueError("NOMAYA_RETENTION_DAYS must be a positive integer") from exc
        if days < 1:
            raise ValueError("NOMAYA_RETENTION_DAYS must be a positive integer")
        return days

    @property
    def enforce_private_storage(self) -> bool:
        """Apply owner-only permissions to newly opened SQLite databases on POSIX."""
        return _bool_env("NOMAYA_ENFORCE_PRIVATE_STORAGE", default=True)

    @property
    def api_token(self) -> str:
        """Bearer token for the API. Empty (the default) disables auth for local dev."""
        return os.environ.get("NOMAYA_API_TOKEN", "")

    @property
    def auth_tokens(self) -> dict[str, str]:
        """Configured bearer tokens mapped to the least-privilege role they grant.

        ``NOMAYA_API_TOKEN`` remains an admin-compatible convenience for existing
        deployments. Scoped tokens are useful when a proxy or deployment secret
        manager issues separate credentials to dashboards and automation.
        """
        tokens: dict[str, str] = {}
        for env_name, role in (
            ("NOMAYA_READ_TOKEN", "reader"),
            ("NOMAYA_RUN_TOKEN", "runner"),
            ("NOMAYA_ADMIN_TOKEN", "admin"),
            ("NOMAYA_API_TOKEN", "admin"),
        ):
            token = os.environ.get(env_name, "").strip()
            if token:
                tokens[token] = role
        return tokens

    @property
    def allowed_models(self) -> list[str]:
        """Models POST /api/run may target. "*" allows any model string."""
        raw = os.environ.get(
            "NOMAYA_ALLOWED_MODELS",
            "mock/compliant-agent,mock/naive-agent,mock/judge",
        )
        return [m.strip() for m in raw.split(",") if m.strip()]

    @property
    def cors_origins(self) -> list[str]:
        raw = os.environ.get(
            "NOMAYA_CORS_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000",
        )
        return [o.strip() for o in raw.split(",") if o.strip()]

    @property
    def max_concurrent_runs(self) -> int:
        """Maximum active evaluation jobs in this process."""
        return max(1, int(os.environ.get("NOMAYA_MAX_CONCURRENT_RUNS", "2")))

    @property
    def max_queued_runs(self) -> int:
        """Maximum queued plus running jobs accepted by one API process."""
        return max(1, int(os.environ.get("NOMAYA_MAX_QUEUED_RUNS", "20")))

    @property
    def max_run_cost_usd(self) -> float:
        """Hard spending ceiling for an evaluation. Zero disables the ceiling."""
        return max(0.0, float(os.environ.get("NOMAYA_MAX_RUN_COST_USD", "0")))

    @property
    def max_run_duration_seconds(self) -> float:
        """Wall-clock ceiling for an evaluation. Zero disables the ceiling."""
        return max(0.0, float(os.environ.get("NOMAYA_MAX_RUN_DURATION_SECONDS", "900")))

    @property
    def max_run_scenarios(self) -> int:
        """Upper bound on expanded scenario attempts accepted by the API."""
        return max(1, int(os.environ.get("NOMAYA_MAX_RUN_SCENARIOS", "100")))

    @property
    def suite_version(self) -> str:
        """Version identifier recorded with every evaluation for reproducibility."""
        return os.environ.get("NOMAYA_SUITE_VERSION", "2026.1").strip() or "2026.1"

    @staticmethod
    def is_mock(model: str) -> bool:
        return model.startswith("mock/") or model == "mock"

    @property
    def environment(self) -> str:
        """Deployment environment; production enables stricter validation."""
        return os.environ.get("NOMAYA_ENV", "development").strip().lower()

    def validate_production_settings(self) -> None:
        """Fail closed for unsafe API settings in an explicitly production deployment.

        The API layer calls this at startup.  Keeping the policy here makes it
        straightforward for non-HTTP deployment paths to use the same guard.
        """
        if self.environment != "production":
            return
        errors: list[str] = []
        if not self.auth_tokens:
            errors.append("NOMAYA_API_TOKEN or a scoped NOMAYA_*_TOKEN must be set in production")
        if "*" in self.allowed_models:
            errors.append("NOMAYA_ALLOWED_MODELS must not contain '*' in production")
        if "*" in self.cors_origins:
            errors.append("NOMAYA_CORS_ORIGINS must not contain '*' in production")
        if errors:
            raise ValueError("; ".join(errors))


def _bool_env(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be one of true/false, yes/no, 1/0, or on/off")


settings = Settings()
