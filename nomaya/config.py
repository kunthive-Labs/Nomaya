"""Runtime configuration for Nomaya.

Reads from the process environment and an optional `.env` file at the project
root. No external dotenv dependency — we parse the handful of lines we need.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG_DIR = Path(__file__).resolve().parent
# Packaged defaults. Adopters can override these via env (see Settings below) to
# point Nomaya at their own scenarios / regulation registry without forking.
DEFAULT_PLAYBOOKS_DIR = PKG_DIR / "scenarios" / "playbooks"
DEFAULT_REGISTRY_PATH = PKG_DIR / "regulations" / "registry.yaml"


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

    # --- models ------------------------------------------------------------ #
    @property
    def agent_model(self) -> str:
        return os.environ.get("NOMAYA_AGENT_MODEL", "mock/compliant-agent")

    @property
    def judge_model(self) -> str:
        return os.environ.get("NOMAYA_JUDGE_MODEL", "mock/judge")

    # --- storage ----------------------------------------------------------- #
    @property
    def db_path(self) -> str:
        return os.environ.get("NOMAYA_DB_PATH", str(ROOT / "nomaya.sqlite3"))

    # --- content locations (override to run your own scenarios) ------------ #
    @property
    def playbooks_dir(self) -> Path:
        return Path(os.environ.get("NOMAYA_PLAYBOOKS_DIR", str(DEFAULT_PLAYBOOKS_DIR)))

    @property
    def registry_path(self) -> Path:
        return Path(os.environ.get("NOMAYA_REGISTRY_PATH", str(DEFAULT_REGISTRY_PATH)))

    # --- provider resilience ---------------------------------------------- #
    @property
    def request_timeout(self) -> float:
        return _env_float("NOMAYA_REQUEST_TIMEOUT", 60.0)

    @property
    def max_retries(self) -> int:
        return _env_int("NOMAYA_MAX_RETRIES", 3)

    @property
    def retry_backoff(self) -> float:
        """Base seconds for exponential backoff between provider retries."""
        return _env_float("NOMAYA_RETRY_BACKOFF", 1.0)

    @property
    def max_tool_iters(self) -> int:
        return _env_int("NOMAYA_MAX_TOOL_ITERS", 5)

    # --- API --------------------------------------------------------------- #
    @property
    def cors_origins(self) -> list[str]:
        raw = os.environ.get("NOMAYA_CORS_ORIGINS", "*").strip()
        return [o.strip() for o in raw.split(",") if o.strip()] or ["*"]

    @property
    def api_key(self) -> str | None:
        """If set, mutating API routes require a matching `X-API-Key` header."""
        return os.environ.get("NOMAYA_API_KEY") or None

    @property
    def max_k(self) -> int:
        """Upper bound on attempts-per-scenario accepted over the API."""
        return _env_int("NOMAYA_MAX_K", 20)

    @staticmethod
    def is_mock(model: str) -> bool:
        return model.startswith("mock/") or model == "mock"


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


settings = Settings()
