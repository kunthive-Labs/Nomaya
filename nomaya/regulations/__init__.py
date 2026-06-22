"""Regulation registry loader."""

from __future__ import annotations

from functools import lru_cache

import yaml

from ..config import REGISTRY_PATH
from ..models import Regulation


@lru_cache(maxsize=1)
def load_registry() -> dict[str, Regulation]:
    raw = yaml.safe_load(REGISTRY_PATH.read_text()) or []
    return {item["id"]: Regulation(**item) for item in raw}


def get_regulation(reg_id: str) -> Regulation:
    return load_registry().get(reg_id, Regulation(id=reg_id, name=reg_id))
