# Security Policy

## Reporting a vulnerability

Please report security issues privately by opening a
[GitHub security advisory](https://github.com/kunthive-Labs/Nomaya/security/advisories/new)
rather than a public issue. We aim to acknowledge reports within a few days.

## Operational guidance

Nomaya evaluates AI agents against compliance scenarios. A few deployment notes:

- **Credentials.** Provider API keys are read from the environment / `.env` and passed to
  LiteLLM. They are never logged — `nomaya/logging.py` masks secrets. Keep `.env` out of
  version control (it is gitignored).
- **The API can spend money.** `POST /api/run` against a real provider consumes tokens. In
  any shared or exposed deployment, set `NOMAYA_API_KEY` (enforces `X-API-Key` on mutating
  routes) and restrict `NOMAYA_CORS_ORIGINS` to your dashboard origin. `k` is bounded
  (`NOMAYA_MAX_K`, default 20) to cap per-request cost.
- **The agent sandbox is not a real backend.** `nomaya/agent/tools.py` operates only on the
  scenario's in-memory fixture; it never reaches a real core-banking system. Do not point it
  at production systems.
- **PII detection is best-effort.** The regex/Luhn detector in `nomaya/rules/pii.py` is an
  orientation aid, not a guarantee. Do not rely on it as your sole DLP control.

## Not legal advice

Regulation summaries are paraphrased for orientation and are **not legal advice**. Mappings
should be reviewed by qualified compliance/legal staff before relying on them for a
deployment decision.
