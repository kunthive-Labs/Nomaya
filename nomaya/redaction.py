"""Redaction for data that leaves the in-memory evaluation result.

Evaluation transcripts may deliberately contain the very data a scenario is
testing for.  Keep the original :class:`RunResult` available to the caller so
checks and live debugging remain accurate, but never use it directly for
durable artifacts such as SQLite history or exported reports.
"""

from __future__ import annotations

import re
from typing import Any

from .models import RunResult
from .rules.pii import detect_pii

_SENSITIVE_KEY = re.compile(
    r"(?:^|[_ -])(?:api[-_ ]?key|authorization|cookie|password|passcode|secret|"
    r"access[-_ ]?token|refresh[-_ ]?token|credit[-_ ]?card|card[-_ ]?number|"
    r"cvv|pin|routing|account|ssn|dob|recovery(?:[-_ ]?code)?)(?:$|[_ -])",
    re.IGNORECASE,
)


def redact_text(text: str, sensitive_values: set[str] | None = None) -> str:
    """Replace detected PII with a category marker without retaining digits.

    The detector intentionally recognises values even when they appear inside
    a larger transcript.  Replacing longer values first also avoids partial
    replacements where two detector categories overlap.
    """
    # Structured fixtures can contain opaque values (for example recovery
    # codes) that a generic PII detector cannot safely recognise alone. Match
    # them only when they appeared under a sensitive key in this same run.
    for value in sorted(sensitive_values or set(), key=len, reverse=True):
        if value:
            text = text.replace(value, "[REDACTED:SENSITIVE]")
    findings = detect_pii(text)
    for finding in sorted(findings, key=lambda item: len(item.value), reverse=True):
        text = text.replace(finding.value, f"[REDACTED:{finding.type.upper()}]")
    return text


def redact_value(value: Any, *, key: str | None = None, sensitive_values: set[str] | None = None) -> Any:
    """Return a recursively redacted copy of a JSON-compatible value.

    In addition to text scanning, redact values held under conventional secret
    or financial-data keys.  Tool arguments and tool results are arbitrary
    JSON, so key-based protection is important when the value itself does not
    match a PII pattern (for example, an opaque access token).
    """
    if key is not None and _SENSITIVE_KEY.search(key):
        return "[REDACTED:SENSITIVE]"
    if isinstance(value, str):
        return redact_text(value, sensitive_values)
    if isinstance(value, list):
        return [redact_value(item, sensitive_values=sensitive_values) for item in value]
    if isinstance(value, tuple):
        return [redact_value(item, sensitive_values=sensitive_values) for item in value]
    if isinstance(value, dict):
        return {
            str(item_key): redact_value(item_value, key=str(item_key), sensitive_values=sensitive_values)
            for item_key, item_value in value.items()
        }
    return value


def _sensitive_values(value: Any, *, key: str | None = None) -> set[str]:
    """Collect scalar values held under sensitive field names in a run dump."""
    values: set[str] = set()
    if key is not None and _SENSITIVE_KEY.search(key) and isinstance(value, (str, int, float)):
        values.add(str(value))
    if isinstance(value, dict):
        for item_key, item_value in value.items():
            values.update(_sensitive_values(item_value, key=str(item_key)))
    elif isinstance(value, (list, tuple)):
        for item in value:
            values.update(_sensitive_values(item, key=key))
    return values


def redact_run(run: RunResult) -> RunResult:
    """Create a redacted copy suitable for persistence or export.

    ``model_dump`` creates an independent plain-data representation before the
    redaction pass, so the caller's live run and its transcript remain intact.
    """
    payload = run.model_dump(mode="json")
    return RunResult.model_validate(redact_value(payload, sensitive_values=_sensitive_values(payload)))
