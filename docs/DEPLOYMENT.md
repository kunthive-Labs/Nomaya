# Deployment

Nomaya ships as one monorepo with two runnable pieces: the **API + CLI** (Python)
and the **dashboard** (Next.js). The CLI alone needs nothing but Python; the
dashboard talks to the API over HTTP.

## Option 1 — Docker Compose (recommended)

Brings up the API on `:8000` and the dashboard on `:3000`, wired together:

```bash
docker compose up --build
# dashboard → http://localhost:3000   API → http://localhost:8000/api/health
```

By default both run in deterministic **mock** mode (no API keys). To evaluate a
real model, pass the relevant key and model strings through the environment:

```bash
OPENAI_API_KEY=sk-... \
NOMAYA_AGENT_MODEL=openai/gpt-4o-mini \
NOMAYA_JUDGE_MODEL=openai/gpt-4o-mini \
docker compose up --build
```

Run data (the SQLite history) persists in the `nomaya-data` named volume.

### Hardening for a shared/public deployment

Set these on the `api` service (see `SECURITY.md` for the rationale):

| Variable | Purpose |
|---|---|
| `NOMAYA_API_KEY` | Require `X-API-Key` on `POST /api/run` (runs can cost money). |
| `NOMAYA_CORS_ORIGINS` | Comma-separated allowlist; set to your dashboard origin. |
| `NOMAYA_MAX_K` | Cap attempts-per-scenario per request (default 20). |
| `NOMAYA_LOG_LEVEL` | `DEBUG` / `INFO` / `WARNING`. |

When `NEXT_PUBLIC_API_URL` differs from `http://127.0.0.1:8000`, set it as a build
arg for the dashboard (it is baked into the client bundle at build time):

```bash
NEXT_PUBLIC_API_URL=https://api.example.com docker compose build dashboard
```

## Option 2 — Run the pieces directly

```bash
# API
uv pip install -e .
nomaya serve --host 0.0.0.0 --port 8000

# Dashboard (separate shell)
cd dashboard && npm install
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npm run build && npm start
```

## Option 3 — CLI / CI only (no services)

For a deployment gate you don't need the API or dashboard at all:

```bash
uv pip install -e ".[dev]"
nomaya run --agent mock/compliant-agent --fail-under 1.0   # gate the build
```

This is exactly what `.github/workflows/eval.yml` does. To gate against a real
model, add a provider key as a repo secret and change `--agent`.

## Provider resilience knobs

Tune how Nomaya treats a flaky live provider:

| Variable | Default | Meaning |
|---|---|---|
| `NOMAYA_REQUEST_TIMEOUT` | `60` | Per-call timeout (seconds). |
| `NOMAYA_MAX_RETRIES` | `3` | Retries on transient errors (timeouts, 429, 5xx). |
| `NOMAYA_RETRY_BACKOFF` | `1.0` | Base seconds for exponential backoff. |
| `NOMAYA_MAX_TOOL_ITERS` | `5` | Max agent tool-calling iterations per turn. |
