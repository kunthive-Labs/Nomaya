"""Regulation registry loader.

The registry path defaults to the packaged `registry.yaml` but honors
`NOMAYA_REGISTRY_PATH` (via `settings.registry_path`) so adopters can supply
their own regulation set. Results are cached per resolved path, so overriding the
env var at runtime (e.g. in tests) picks up the new file.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from ..config import settings
from ..models import Regulation


@lru_cache(maxsize=8)
def _load_registry_at(path: str) -> dict[str, Regulation]:
    raw = yaml.safe_load(Path(path).read_text()) or []
    return {item["id"]: Regulation(**item) for item in raw}


def load_registry() -> dict[str, Regulation]:
    return _load_registry_at(str(settings.registry_path))


def get_regulation(reg_id: str) -> Regulation:
    return load_registry().get(reg_id, Regulation(id=reg_id, name=reg_id))
