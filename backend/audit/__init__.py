"""
Audit log module — feature 003-agent-audit-log.

HIPAA + NIST SP 800-53 AU compliant per-user audit log covering every
user-attributable action in AstralBody (direct user actions and agent
actions taken on the user's behalf).

Core invariants enforced by this package:

- Append-only: rows are inserted; never updated; only the retention CLI
  may delete rows older than the retention window. A database trigger
  blocks UPDATE/DELETE outside the retention session.
- Per-user scoped: all reads filter by ``actor_user_id == authenticated
  caller``. There is no admin override and no cross-user read path.
- No raw payload bytes: ``inputs_meta`` / ``outputs_meta`` carry only
  non-PHI metadata. Filenames are stripped (FR-015). Payload digests
  use HMAC with a server-held key, never plain SHA-256 (FR-016).
- Hash-chain integrity (AU-9): each row links to the previous entry in
  the same user's stream via HMAC, providing tamper evidence.

Environment variables:

- ``AUDIT_HMAC_SECRET`` — server-held HMAC secret used for the chain
  and for payload digests. Loaded at process start. Required in
  production; in development a deterministic dev fallback is used.
- ``AUDIT_HMAC_KEY_ID`` — identifier of the active key (default ``"k1"``).
  Older entries continue to verify under their own ``key_id``.

See specs/003-agent-audit-log/ for the spec, plan, data model, and
contracts. See backend/audit/cli.py for the verify-chain and
purge-expired operator tools.
"""
from .schemas import (
    AuditEventCreate,
    AuditEventDTO,
    ArtifactPointer,
    EVENT_CLASSES,
    OUTCOMES,
)

__all__ = [
    "AuditEventCreate",
    "AuditEventDTO",
    "ArtifactPointer",
    "EVENT_CLASSES",
    "OUTCOMES",
]
