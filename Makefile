# Nomaya — one entry point for the whole monorepo.
# Python backend (uv) + Next.js dashboard live in one repo; these targets drive both.

.DEFAULT_GOAL := help
.PHONY: help install lint typecheck test eval run serve dashboard docker-up docker-down clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Create venv and install backend (dev) + dashboard deps
	uv venv --python 3.12
	uv pip install -e ".[dev]"
	cd dashboard && npm install

lint: ## Ruff lint
	uv run ruff check nomaya tests

typecheck: ## Mypy
	uv run mypy

test: ## Unit + integration tests
	uv run pytest -q

eval: ## Compliance gate: compliant agent passes 100%, naive agent is caught
	uv run nomaya run --agent mock/compliant-agent --fail-under 1.0 --no-save
	uv run nomaya run --agent mock/naive-agent --no-save --no-report

run: ## Run the suite (mock compliant agent)
	uv run nomaya run

serve: ## Start the FastAPI dashboard backend on :8000
	uv run nomaya serve

dashboard: ## Start the Next.js dashboard on :3000 (needs backend running)
	cd dashboard && npm run dev

docker-up: ## Build & start API + dashboard via docker compose
	docker compose up --build

docker-down: ## Stop the docker compose stack
	docker compose down

clean: ## Remove caches, build artifacts, and local run data
	rm -rf .pytest_cache .mypy_cache .ruff_cache *.egg-info build dist
	rm -f nomaya.sqlite3 nomaya.sqlite3-wal nomaya.sqlite3-shm
	rm -rf reports/*.html reports/*.json
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
