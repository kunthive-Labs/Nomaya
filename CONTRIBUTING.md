# Contributing to Nomaya

Thanks for your interest. Nomaya is a compliance-evaluation harness — contributions
that add scenarios, regulations, check types, or providers are especially welcome.

## Development setup

```bash
uv venv --python 3.12 && uv pip install -e ".[dev]"
source .venv/bin/activate
pre-commit install        # optional but recommended
```

## The golden rule: stay deterministic in CI

The whole suite runs offline in `mock` mode with **no API keys**. Every test and the
CI eval gate must pass without network access. When you add a feature that calls a
provider, gate the real call behind a model string and add a `mock/` path so the
behavior can be regression-tested for free.

## Before you open a PR

```bash
make lint        # ruff
make typecheck   # mypy
make test        # pytest
make eval        # compliant agent must pass 100%, naive agent must be caught
```

All four must be green. CI runs the same checks.

## Adding your own scenarios / regulations

You do **not** need to fork to run your own playbooks — see the
["Add your own scenarios" section of the README](README.md). For contributions back
to the shared suite, add a YAML playbook under `nomaya/scenarios/playbooks/` and, if
it references a new obligation, an entry in `nomaya/regulations/registry.yaml`. Ship
both a `compliant` and a `naive` mock script so the harness can prove it clears the
good agent and catches the bad one.

## Adding a check type

1. Add the variant to `CheckType` in `nomaya/models.py`.
2. Implement the evaluator in `nomaya/rules/checks.py`.
3. Wire it into the dispatcher in `nomaya/rules/engine.py`.
4. Add a unit test in `tests/test_engine.py`.

## Code style

Ruff (lint + format) and mypy are the source of truth; their config lives in
`pyproject.toml`. Keep functions small, type-hinted, and documented with a short
docstring explaining *why*, not *what*.

## Commit messages

Conventional-commit prefixes (`feat:`, `fix:`, `test:`, `docs:`, `ci:`, `chore:`)
keep the history scannable and the changelog easy to assemble.
