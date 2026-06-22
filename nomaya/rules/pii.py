"""Lightweight PII / NPI detector.

Targets the categories that matter for financial-services privacy rules
(GLBA Safeguards, Reg P, NYDFS 500): Social Security numbers, payment card
numbers (Luhn-validated to cut false positives), bank account & routing
numbers, email, phone, and date of birth.

Regex-first by design: deterministic, dependency-free, and fast enough to run
on every transcript. For production you'd layer an ML model (e.g. Presidio) on
top; the detector interface here is the seam where that would plug in.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_PATTERNS: dict[str, re.Pattern[str]] = {
    "ssn": re.compile(r"\b(?!000|666|9\d\d)\d{3}[-\s]?(?!00)\d{2}[-\s]?(?!0000)\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]?){13,19}\b"),
    "routing_number": re.compile(r"\b(?:routing|aba|rtn)\D{0,12}(\d{9})\b", re.IGNORECASE),
    "bank_account": re.compile(r"\b(?:account|acct|a/c)\D{0,12}(\d{8,17})\b", re.IGNORECASE),
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "phone": re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    "dob": re.compile(r"\b(?:0?[1-9]|1[0-2])[/-](?:0?[1-9]|[12]\d|3[01])[/-](?:19|20)\d{2}\b"),
}


@dataclass
class PIIFinding:
    type: str
    value: str

    @property
    def redacted(self) -> str:
        """A safe-to-log preview: keep last 4 chars, mask the rest."""
        digits = re.sub(r"\D", "", self.value)
        if len(digits) >= 4:
            return f"{self.type}:****{digits[-4:]}"
        return f"{self.type}:****"


def _luhn_ok(number: str) -> bool:
    digits = [int(d) for d in re.sub(r"\D", "", number)]
    if not 13 <= len(digits) <= 19:
        return False
    checksum, parity = 0, len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def detect_pii(text: str, types: list[str] | None = None) -> list[PIIFinding]:
    """Find PII in `text`. If `types` is given, only those categories are scanned."""
    findings: list[PIIFinding] = []
    seen: set[tuple[str, str]] = set()

    for kind, pattern in _PATTERNS.items():
        if types and kind not in types:
            continue
        for match in pattern.finditer(text):
            # capture-group patterns (routing/account) expose the number in group 1
            value = match.group(1) if match.groups() else match.group(0)
            value = value.strip()

            # Validate card numbers via Luhn to avoid flagging arbitrary digit runs.
            if kind == "credit_card" and not _luhn_ok(value):
                continue
            # A bare 9-digit run alone is too noisy; require the routing context (handled by regex).

            key = (kind, value)
            if key in seen:
                continue
            seen.add(key)
            findings.append(PIIFinding(type=kind, value=value))

    return findings
