"""Evidence capture, hashing, and tamper detection for the audit trail."""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from qual_audit.models import AuditEntry, TestEvidence


def hash_data(data: Dict[str, Any]) -> str:
    """Compute SHA-256 of canonically serialized JSON data."""
    canonical = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def create_evidence(
    case_id: str,
    evidence_type: str,
    data: Dict[str, Any],
) -> TestEvidence:
    """Create a TestEvidence instance with computed hash."""
    return TestEvidence(
        case_id=case_id,
        evidence_type=evidence_type,
        data=data,
        sha256=hash_data(data),
        captured_at=datetime.now(timezone.utc),
    )


def compute_evidence_hash(evidence_list: List[TestEvidence]) -> str:
    """Compute a combined hash over all evidence for a test case."""
    combined = "|".join(sorted(ev.sha256 for ev in evidence_list))
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Audit hash chain
# ---------------------------------------------------------------------------

_GENESIS_HASH = hashlib.sha256(b"genesis").hexdigest()


def compute_chain_hash(entry_id: str, action: str, timestamp: str) -> str:
    """Compute the hash that the *next* entry stores as previous_hash."""
    payload = f"{entry_id}{action}{timestamp}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_previous_hash(last_entry: Optional[AuditEntry]) -> str:
    """Determine the previous_hash for a new audit entry."""
    if last_entry is None:
        return _GENESIS_HASH
    return compute_chain_hash(
        last_entry.id,
        last_entry.action.value,
        last_entry.timestamp.isoformat(),
    )


def verify_chain(entries: List[AuditEntry], require_genesis: bool = True) -> bool:
    """Verify the tamper-evidence hash chain for a list of audit entries.

    If *require_genesis* is False the first entry's previous_hash is not
    checked against the genesis constant — useful when verifying a sub-chain
    that continues from an earlier run's entries.

    Returns True if the chain is intact, False otherwise.
    """
    if not entries:
        return True

    if require_genesis and entries[0].previous_hash != _GENESIS_HASH:
        return False

    for i in range(1, len(entries)):
        prev = entries[i - 1]
        expected = compute_chain_hash(
            prev.id, prev.action.value, prev.timestamp.isoformat()
        )
        if entries[i].previous_hash != expected:
            return False

    return True
