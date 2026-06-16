"""Captured evidence + secret-safe redaction (T004).

``CapturedEvidence`` holds the concrete observations a scenario produced so a
verdict can be justified and replayed. ``redact`` scrubs any credential-shaped
value before persistence; if a known secret value would have appeared, the run is
flagged (FR-022 / SC-011) — fail-safe, never silent.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

_MASK = "***REDACTED***"

# Generic secret-shaped patterns (defence in depth, on top of known env values).
_GENERIC_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]{8,}", re.IGNORECASE),
    re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{6,}"),  # JWT
    re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"),  # OpenAI-style key
)


def _redact_text(text: str, secret_values: List[str]) -> Tuple[str, bool]:
    """Return ``(masked_text, hit)`` masking known values and generic patterns."""
    hit = False
    for sv in secret_values:
        if sv and sv in text:
            text = text.replace(sv, _MASK)
            hit = True
    for pat in _GENERIC_PATTERNS:
        if pat.search(text):
            text = pat.sub(_MASK, text)
            hit = True
    return text, hit


def redact(obj: Any, secret_values: List[str]) -> Tuple[Any, bool]:
    """Recursively redact secret-shaped values from a JSON-like structure.

    Args:
        obj: Any JSON-serializable structure (dict/list/str/scalar).
        secret_values: Live credential values to mask (from RunConfig).

    Returns:
        ``(clean_obj, near_exposure)`` — ``near_exposure`` is True if any value
        was masked, which the caller surfaces as a run flag (FR-022).
    """
    near = False
    if isinstance(obj, str):
        cleaned, hit = _redact_text(obj, secret_values)
        return cleaned, hit
    if isinstance(obj, dict):
        out: Dict[Any, Any] = {}
        for k, v in obj.items():
            cv, h = redact(v, secret_values)
            out[k] = cv
            near = near or h
        return out, near
    if isinstance(obj, (list, tuple)):
        out_list = []
        for v in obj:
            cv, h = redact(v, secret_values)
            out_list.append(cv)
            near = near or h
        return out_list, near
    return obj, False


@dataclass
class CapturedEvidence:
    """Concrete observations from one scenario, retained for replay + audit.

    All fields are redacted before persistence; ``near_exposure`` records whether
    any value had to be masked.
    """

    evidence_id: str
    scenario_id: str
    run_mode: str  # real_keycloak | mock_inprocess
    messages: List[Dict[str, Any]] = field(default_factory=list)
    components: List[Dict[str, Any]] = field(default_factory=list)
    workspace_state: List[Dict[str, Any]] = field(default_factory=list)
    audit_rows: List[Dict[str, Any]] = field(default_factory=list)
    audit_chain_ok: Any = True  # True or first-broken event_id (str)
    client_inspection: Dict[str, Any] = field(default_factory=dict)
    device_diff: Dict[str, Any] = field(default_factory=dict)
    extra: Dict[str, Any] = field(default_factory=dict)
    near_exposure: bool = False

    def redacted(self, secret_values: List[str]) -> "CapturedEvidence":
        """Return a redaction-clean copy, flagging any near-exposure."""
        msgs, h1 = redact(self.messages, secret_values)
        comps, h2 = redact(self.components, secret_values)
        ws, h3 = redact(self.workspace_state, secret_values)
        audit, h4 = redact(self.audit_rows, secret_values)
        extra, h5 = redact(self.extra, secret_values)
        return CapturedEvidence(
            evidence_id=self.evidence_id,
            scenario_id=self.scenario_id,
            run_mode=self.run_mode,
            messages=msgs,
            components=comps,
            workspace_state=ws,
            audit_rows=audit,
            audit_chain_ok=self.audit_chain_ok,
            client_inspection=self.client_inspection,
            device_diff=self.device_diff,
            extra=extra,
            near_exposure=any((h1, h2, h3, h4, h5)),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for the JSON run record."""
        return {
            "evidence_id": self.evidence_id,
            "scenario_id": self.scenario_id,
            "run_mode": self.run_mode,
            "messages": self.messages,
            "components": self.components,
            "workspace_state": self.workspace_state,
            "audit_rows": self.audit_rows,
            "audit_chain_ok": self.audit_chain_ok,
            "client_inspection": self.client_inspection,
            "device_diff": self.device_diff,
            "extra": self.extra,
            "near_exposure": self.near_exposure,
        }


def flatten_components(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract delivered component dicts from captured server->client messages.

    Handles both ``ui_render`` (``components: [...]``) and ``ui_upsert``
    (``ops: [{component: {...}}]``) wire shapes.
    """
    out: List[Dict[str, Any]] = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        mtype = msg.get("type")
        if mtype == "ui_render":
            for c in msg.get("components", []) or []:
                if isinstance(c, dict):
                    out.append(c)
        elif mtype == "ui_upsert":
            for op in msg.get("ops", []) or []:
                if isinstance(op, dict) and isinstance(op.get("component"), dict):
                    out.append(op["component"])
    return out
