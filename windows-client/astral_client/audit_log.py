"""Append-only, hash-chained audit log for the Windows coding agent.

The orchestrator records its own ``tool`` audit event for every dispatch, but
the client is where files are actually touched and commands actually run. This
module records **what the tool did on disk** — once per action — in an
append-only JSONL file at ``%APPDATA%/AstralBody/audit.log`` (rotated), hash-
chained with an HMAC key derived from the machine + user identity, mirroring
the backend's per-user hash-chain posture.

Each entry: ``ts, seq, actor, tool, args(redacted), outcome, correlation_id,
prev_hash, hash``. The dangerous-bypass path emits ``event_class =
"dangerous_bypass"`` with the full command text (kept, never redacted, so the
audit trail shows exactly what ran).

Fail-open for the *product* (an audit-write failure must not block a user
action that the permission gate already allowed), but every write failure is
logged to stderr so it is visible.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any, Optional

logger = logging.getLogger("astral.audit")

_MAX_ROTATE_BYTES = 5 * 1024 * 1024  # 5 MB then rotate
_KEEP_ROTATED = 3


def _appdata_dir() -> str:
    base = os.getenv("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "AstralBody")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:  # noqa: BLE001
        d = os.path.expanduser("~")
    return d


def _audit_path() -> str:
    return os.path.join(_appdata_dir(), "audit.log")


def _chain_key(actor: str) -> bytes:
    """Derive a per-machine+user HMAC key for the hash chain.

    Not a secret intended to resist a determined local attacker (anyone with
    the machine can forge it) — it ties the chain to this user on this machine
    so casual tampering is detectable, matching the backend's per-user posture.
    """
    ident = f"{os.getenv('COMPUTERNAME', '')}|{os.getenv('USERNAME', '')}|{actor}"
    return hashlib.sha256(("astral-audit|" + ident).encode("utf-8")).digest()


def _hmac(key: bytes, msg: str) -> str:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).hexdigest()


def _read_last_hash(path: str) -> str:
    """Return the hash field of the last non-empty line, or '' if none."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            if size == 0:
                return ""
            # read the tail
            chunk = min(size, 8192)
            f.seek(size - chunk)
            tail = f.read().decode("utf-8", errors="replace")
        lines = [ln for ln in tail.splitlines() if ln.strip()]
        if not lines:
            return ""
        return json.loads(lines[-1]).get("hash", "")
    except Exception:  # noqa: BLE001
        return ""


def _rotate_if_needed(path: str) -> None:
    try:
        if not os.path.exists(path) or os.path.getsize(path) < _MAX_ROTATE_BYTES:
            return
        for i in range(_KEEP_ROTATED, 0, -1):
            old = f"{path}.{i}"
            new = f"{path}.{i + 1}" if i < _KEEP_ROTATED else None
            if os.path.exists(old):
                if new:
                    os.replace(old, new)
                else:
                    os.remove(old)
        os.replace(path, f"{path}.1")
    except Exception:  # noqa: BLE001
        logger.warning("audit log rotate failed", exc_info=True)


class AuditLogger:
    """Append-only hash-chained JSONL audit log."""

    def __init__(self, actor: str = "unknown"):
        self.actor = actor or "unknown"
        self._key = _chain_key(self.actor)
        self._path = _audit_path()

    def record(
        self,
        *,
        tool: str,
        args: Any,
        outcome: str,  # success | refused | phi_blocked | error
        correlation_id: Optional[str] = None,
        event_class: str = "tool",
        detail: str = "",
    ) -> None:
        """Append one audit entry. Never raises (fail-open for the product)."""
        try:
            _rotate_if_needed(self._path)
            prev = _read_last_hash(self._path)
            entry = {
                "ts": int(time.time()),
                "seq": 0,  # filled below
                "actor": self.actor,
                "event_class": event_class,
                "tool": tool,
                "args": _redact_args(tool, args),
                "outcome": outcome,
                "correlation_id": correlation_id or "",
                "detail": detail,
                "prev_hash": prev,
            }
            # seq = number of existing lines + 1 (best-effort)
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    entry["seq"] = sum(1 for _ in f) + 1
            except Exception:  # noqa: BLE001
                entry["seq"] = 1
            canon = json.dumps(entry, sort_keys=True, separators=(",", ":"))
            entry["hash"] = _hmac(self._key, canon)
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:  # noqa: BLE001 — fail-open
            logger.warning("audit log write failed (tool=%s outcome=%s)", tool, outcome, exc_info=True)

    def tail(self, n: int = 50) -> list:
        """Return the last ``n`` entries (for the native 'View audit log' dialog)."""
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            return [json.loads(ln) for ln in lines[-n:] if ln.strip()]
        except Exception:  # noqa: BLE001
            return []


def _redact_args(tool: str, args: Any) -> Any:
    """Redact file paths to workspace-relative; keep command text for exec tools.

    The dangerous-bypass command is deliberately kept verbatim (the whole point
    of auditing it is to know exactly what ran).
    """
    if not isinstance(args, dict):
        return args
    ws = _workspace_root()
    out = {}
    for k, v in args.items():
        if k == "path" and isinstance(v, str):
            out[k] = _rel(ws, v)
        elif k in ("command", "cmd") and isinstance(v, str):
            out[k] = v  # keep command text (audit trail)
        else:
            out[k] = v
    return out


def _workspace_root() -> str:
    return os.path.realpath(os.path.expanduser(os.path.expandvars(
        os.getenv("ASTRAL_WORKSPACE_DIR", os.path.join("~", "AstralWorkspace")))))


def _rel(root: str, path: str) -> str:
    try:
        rp = os.path.realpath(os.path.join(root, os.path.expandvars(os.path.expanduser(path))))
        rel = os.path.relpath(rp, root)
        if rel.startswith(".."):
            return "<outside-workspace>"
        return rel
    except Exception:  # noqa: BLE001
        return "<path>"
