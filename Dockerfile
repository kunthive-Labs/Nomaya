# Nomaya API + CLI image. Uses uv for fast, reproducible installs.
FROM python:3.12-slim AS base

# uv: fast Python package manager
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    NOMAYA_DB_PATH=/data/nomaya.sqlite3

WORKDIR /app

# Install dependencies first (better layer caching) then the package.
COPY pyproject.toml README.md ./
COPY nomaya ./nomaya
RUN uv pip install --system -e .

# Run data (SQLite + reports) lives on a volume so it survives restarts.
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8000

# Default: serve the dashboard API. Override CMD to run the CLI (`nomaya run ...`).
CMD ["uvicorn", "nomaya.api:api", "--host", "0.0.0.0", "--port", "8000"]
