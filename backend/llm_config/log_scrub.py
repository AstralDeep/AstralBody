"""Log scrubber for the user's API key (feature 006-user-llm-config).

Defence-in-depth around FR-002 / SC-002. The application code already
takes pains to never log :class:`SessionCreds` (its ``__repr__`` elides
the key) and to never include ``api_key`` in audit-event payloads
(:func:`backend.llm_config.audit_events._assert_no_api_key`). This
scrubber catches the residual cases:

* A FastAPI/uvicorn access log that captures the request body of
  ``POST /api/llm/test`` (which carries ``api_key`` in plaintext —
  by design, since the probe needs it).
* A debug-level dump of a parsed WebSocket message via something
  like ``logger.debug("got msg: %s", payload)``.
* An exception's stringified arguments that happen to include a key.

The :func:`redact_llm_config` helper takes any dict / JSON-string /
loggable record and replaces ``api_key`` field values (and substrings
matching common API-key-shaped tokens) with the literal ``"<redacted>"``.
The :class:`LLMKeyRedactionFilter` is a :mod:`logging` ``Filter`` that
runs the scrubber over every log record's ``args`` and ``msg`` before
emission.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict


_REDACTED = "<redacted>"

# API-key-shaped tokens we redact wherever they appear in free-form text.
_KEY_TOKEN_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b"),
    re.compile(r"\bgsk_[A-Za-z0-9_\-]{20,}\b"),
    re.compile(r"\bxai-[A-Za-z0-9_\-]{20,}\b"),
    re.compile(r"\bor-[A-Za-z0-9_\-]{20,}\b"),
    re.compile(r"\bsk_live_[A-Za-z0-9_\-]{20,}\b"),
)


def _redact_text(text: str) -> str:
    for pat in _KEY_TOKEN_PATTERNS:
        text = pat.sub(_REDACTED, text)
    return text


def redact_llm_config(value: Any) -> Any:
    """Return ``value`` with any ``api_key`` field replaced by
    ``"<redacted>"`` and any API-key-shaped token in free text replaced
    similarly. Leaves the input shape otherwise unchanged.

    Handles ``dict``, ``list``, ``tuple``, ``str``, and JSON-serialized
    strings; all other types pass through unchanged. Recurses into
    nested structures.
    """
    if isinstance(value, dict):
        return {
            k: (_REDACTED if k == "api_key" else redact_llm_config(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact_llm_config(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_llm_config(item) for item in value)
    if isinstance(value, str):
        # Attempt JSON-aware redaction first; fall back to text scan.
        if value and value[0] in "{[":
            try:
                parsed = json.loads(value)
                return json.dumps(redact_llm_config(parsed))
            except (ValueError, TypeError):
                pass
        return _redact_text(value)
    return value


class LLMKeyRedactionFilter(logging.Filter):
    """:mod:`logging` filter that scrubs API keys from every record.

    Install on the root logger (or on uvicorn / FastAPI loggers) at
    application startup so every log emission, regardless of source,
    passes through the redactor before reaching a handler.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # Scrub the formatted message.
        if isinstance(record.msg, str):
            record.msg = _redact_text(record.msg)
        # Scrub each positional arg if it's a stringifiable structure.
        if record.args:
            if isinstance(record.args, dict):
                record.args = redact_llm_config(record.args)
            elif isinstance(record.args, tuple):
                record.args = tuple(redact_llm_config(a) for a in record.args)
        return True


def install_redaction_filter(logger_name: str = "") -> None:
    """Attach :class:`LLMKeyRedactionFilter` to ``logger_name`` (root by default).

    Idempotent: a second call has no effect if the filter is already attached.
    """
    target = logging.getLogger(logger_name)
    for f in target.filters:
        if isinstance(f, LLMKeyRedactionFilter):
            return
    target.addFilter(LLMKeyRedactionFilter())
