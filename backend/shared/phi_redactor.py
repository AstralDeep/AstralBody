"""HIPAA / PHI redactor used by the chat-step recorder before any
tool argument or result summary is rendered to the user or persisted to chat
history.

See:

* ``specs/014-progress-notifications/spec.md`` (FR-009b, SC-008) for the
  user-facing redaction contract.
* ``specs/014-progress-notifications/research.md`` (R4, R5) for the design
  rationale: pattern-based redaction over JSON, defense-in-depth at both the
  recorder write boundary and the REST read boundary, dependency-free per
  Constitution V.

Two layers of detection:

1. **Field-key heuristics.** Any ``dict`` key whose lower-cased name contains a
   known PHI label has its value replaced wholesale with a typed marker. This
   protects against names, addresses, MRNs, and other identifiers that have no
   reliable surface-level regex but always live in well-named fields.
2. **Value-pattern matching.** Free-form string values are scanned for SSN /
   email / phone / IP / full-precision date / MRN-like spans, which are
   replaced in place.

After redaction the value is JSON-serialised and truncated to
``TRUNCATION_LIMIT`` characters (FR-009a's "applied consistently across all
step types" requirement). Failures are caught, structured-logged, and replaced
with ``"[redaction failed]"`` — the function never raises and never returns
unsanitised content.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional, Tuple

logger = logging.getLogger("PHIRedactor")

TRUNCATION_LIMIT = 512
TRUNCATION_MARKER = "…"

# Field keys (case-insensitive substring match) whose values are masked
# wholesale. Covers the HIPAA Safe Harbor identifier categories that don't
# have reliable surface-level regex shapes.
PHI_FIELD_PATTERNS: Tuple[str, ...] = (
    "name",  # first_name, last_name, full_name, patient_name, ...
    "dob",
    "birth",
    "birthdate",
    "ssn",
    "social_security",
    "mrn",
    "medical_record",
    "patient_id",
    "address",
    "street",
    "city",
    "zip",
    "postal",
    "phone",
    "telephone",
    "fax",
    "email",
    "ip_address",
    "url",
    "photo",
    "image_url",
    "biometric",
    "fingerprint",
    "voiceprint",
    "device_id",
    "device_serial",
    "vehicle_id",
    "license_plate",
    "license_number",
    "certificate",
    "account_number",
    "credit_card",
    "ccn",
    "card_number",
    "health_plan_id",
    "beneficiary",
    "insurance_id",
)

# Free-form string patterns. Order matters when patterns could overlap.
PHI_VALUE_PATTERNS: Tuple[Tuple[re.Pattern[str], str], ...] = (
    # SSN
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED:ssn]"),
    # Email
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[REDACTED:email]"),
    # Phone — covers (123) 456-7890, 123-456-7890, +1 123 456 7890, etc.
    (
        re.compile(r"\b(?:\+?\d{1,2}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b"),
        "[REDACTED:phone]",
    ),
    # IPv4
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[REDACTED:ip]"),
    # Full-precision dates (Safe Harbor: any date element more specific than
    # year is identifying, so we mask every full date).
    (re.compile(r"\b(?:19|20)\d{2}[-/]\d{1,2}[-/]\d{1,2}\b"), "[REDACTED:date]"),
    (re.compile(r"\b\d{1,2}[-/]\d{1,2}[-/](?:19|20)\d{2}\b"), "[REDACTED:date]"),
    # MRN-like: MRN: 12345678
    (re.compile(r"\bMRN[\s:#-]*\d{4,}\b", re.IGNORECASE), "[REDACTED:mrn]"),
)


def _matches_phi_field_key(key: str) -> bool:
    lowered = key.lower()
    return any(p in lowered for p in PHI_FIELD_PATTERNS)


def _redact_string(s: str) -> Tuple[str, bool]:
    """Apply value-pattern redactions to a single string. Returns (new, changed)."""
    changed = False
    for pattern, replacement in PHI_VALUE_PATTERNS:
        new_s = pattern.sub(replacement, s)
        if new_s != s:
            changed = True
            s = new_s
    return s, changed


def _mask_value(value: Any) -> Any:
    """Replace a value flagged via field-key match with a typed marker."""
    if value is None:
        return None
    if isinstance(value, dict):
        return {k: "[REDACTED:phi]" for k in value}
    if isinstance(value, list):
        return ["[REDACTED:phi]" for _ in value]
    return "[REDACTED:phi]"


def _redact_walk(value: Any, redacted: list) -> Any:
    if isinstance(value, dict):
        result = {}
        for k, v in value.items():
            if _matches_phi_field_key(k):
                result[k] = _mask_value(v)
                redacted[0] = True
            else:
                result[k] = _redact_walk(v, redacted)
        return result
    if isinstance(value, list):
        return [_redact_walk(item, redacted) for item in value]
    if isinstance(value, str):
        new, changed = _redact_string(value)
        if changed:
            redacted[0] = True
        return new
    return value


def _truncate(s: str) -> Tuple[str, bool]:
    if len(s) <= TRUNCATION_LIMIT:
        return s, False
    cutoff = max(0, TRUNCATION_LIMIT - len(TRUNCATION_MARKER))
    return s[:cutoff] + TRUNCATION_MARKER, True


def redact(value: Any, *, kind: str = "args") -> Tuple[Optional[str], bool]:
    """Redact PHI from ``value`` and serialise to a truncated string.

    Args:
        value: Any JSON-serialisable input. ``None`` is passed through.
        kind: One of ``"args"`` / ``"result"`` / ``"error"``; used only for
            structured-log context.

    Returns:
        ``(redacted_truncated_string, was_truncated)`` — or ``(None, False)``
        when ``value`` is ``None``. Never raises; on any internal failure
        returns ``("[redaction failed]", False)``.
    """
    if value is None:
        return None, False
    try:
        flag = [False]
        scrubbed = _redact_walk(value, flag)
        if isinstance(scrubbed, str):
            serialised = scrubbed
        else:
            try:
                serialised = json.dumps(scrubbed, default=str, ensure_ascii=False)
            except (TypeError, ValueError):
                serialised = repr(scrubbed)
        truncated, was_truncated = _truncate(serialised)
        if flag[0]:
            logger.info(
                "phi_redactor.redaction_applied",
                extra={"kind": kind, "truncated": was_truncated},
            )
        return truncated, was_truncated
    except Exception as exc:  # pragma: no cover — defensive
        logger.error(
            "phi_redactor.redaction_failed",
            extra={"kind": kind, "error": str(exc)},
        )
        return "[redaction failed]", False
