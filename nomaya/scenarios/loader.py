"""Load scenario playbooks (YAML) into validated `Scenario` models."""

from __future__ import annotations

from pathlib import Path

import yaml

from ..config import PLAYBOOKS_DIR
from ..models import Scenario


def load_scenario(path: str | Path) -> Scenario:
    data = yaml.safe_load(Path(path).read_text())
    return Scenario(**data)


def load_scenarios(directory: str | Path | None = None, tags: list[str] | None = None) -> list[Scenario]:
    """Load every *.yaml playbook in `directory`, optionally filtered by tag."""
    directory = Path(directory) if directory else PLAYBOOKS_DIR
    scenarios: list[Scenario] = []
    for path in sorted(directory.glob("*.yaml")):
        scenario = load_scenario(path)
        if tags and not (set(tags) & set(scenario.tags)):
            continue
        scenarios.append(scenario)
    return scenarios
