# Nomaya API service.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Dependency layer — cached until the lockfile changes.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project

COPY nomaya/ nomaya/
RUN uv sync --locked --no-dev

# ROOT resolves next to the installed package, so anchor mutable state explicitly.
ENV NOMAYA_DB_PATH=/data/nomaya.sqlite3
VOLUME /data
EXPOSE 8000

CMD ["uv", "run", "--no-sync", "uvicorn", "nomaya.api:api", "--host", "0.0.0.0", "--port", "8000"]
