"""Logging setup for Nomaya — stdlib only, secret-safe.

`configure_logging()` is idempotent and reads the level from `NOMAYA_LOG_LEVEL`
(default `INFO`). The CLI and the API call it once at startup; library code just
does `logging.getLogger(__name__)` and never configures handlers itself, so an
embedding application keeps full control of its own logging.

We deliberately never log message contents, transcripts, account fixtures, or
API keys — only structural events (which scenario, which model, attempt N,
cost, pass/fail). `mask_secret()` is provided for the rare case a value must be
referenced in a message.
"""

from __future__ import annotations

import logging
import os

_CONFIGURED = False
_LOGGER_NAME = "nomaya"


def configure_logging(level: str | None = None) -> None:
    """Attach a single stream handler to the `nomaya` logger. Idempotent."""
    global _CONFIGURED
    if _CONFIGURED:
        if level:
            logging.getLogger(_LOGGER_NAME).setLevel(_resolve_level(level))
        return

    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(_resolve_level(level or os.environ.get("NOMAYA_LOG_LEVEL", "INFO")))
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s · %(message)s", "%H:%M:%S")
    )
    logger.addHandler(handler)
    logger.propagate = False
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a child of the `nomaya` logger (e.g. `nomaya.orchestrator`)."""
    return logging.getLogger(name if name.startswith(_LOGGER_NAME) else f"{_LOGGER_NAME}.{name}")


def mask_secret(value: str, keep: int = 4) -> str:
    """Mask all but the last `keep` characters of a secret for safe display."""
    if not value:
        return ""
    if len(value) <= keep:
        return "*" * len(value)
    return "*" * (len(value) - keep) + value[-keep:]


def _resolve_level(level: str) -> int:
    return getattr(logging, level.upper(), logging.INFO) if isinstance(level, str) else level
