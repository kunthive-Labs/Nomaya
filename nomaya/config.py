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
    def api_token(self) -> str:
        """Bearer token for the API. Empty (the default) disables auth for local dev."""
        return os.environ.get("NOMAYA_API_TOKEN", "")

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

    @staticmethod
    def is_mock(model: str) -> bool:
        return model.startswith("mock/") or model == "mock"


settings = Settings()
