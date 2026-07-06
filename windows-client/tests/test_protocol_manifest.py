"""Feature 044 — desktop protocol-coverage drift guard.

The committed manifest ``backend/shared/ui_protocol.json`` is the single source
of the server->client frame vocabulary. The desktop classification table must
cover it exactly: no unclassified frame, no stale entry. A new server frame
type therefore fails this suite until the desktop deliberately classifies it.
"""

import json
from pathlib import Path

from astral_client.protocol_manifest import (
    CLASSIFICATION,
    CLIENT_LOCAL_ACTIONS,
    HANDLED,
    IGNORED,
    is_handled,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / "backend" / "shared" / "ui_protocol.json"


def _manifest_push_types() -> set[str]:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {entry["name"] for entry in data["push_types"]}


def test_classification_covers_manifest_exactly():
    push = _manifest_push_types()
    classified = set(CLASSIFICATION)
    missing = sorted(push - classified)
    stale = sorted(classified - push)
    assert not missing, f"server frame types the desktop has not classified: {missing}"
    assert not stale, f"desktop classifies frame types the server no longer sends: {stale}"


def test_client_local_actions_matches_manifest():
    """The committed CLIENT_LOCAL_ACTIONS constant (a packaged build has no repo
    tree to probe at import time) must mirror the manifest's
    ``client_local_actions`` exactly."""
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert CLIENT_LOCAL_ACTIONS == frozenset(data["client_local_actions"])


def test_classification_values_are_valid():
    assert set(CLASSIFICATION.values()) <= {HANDLED, IGNORED}


def test_core_loop_frames_are_handled():
    for frame in (
        "ui_render", "ui_upsert", "chat_status", "error", "auth_required",
        "chrome_menu", "chrome_surface", "user_message_acked", "chat_step",
        "tool_progress", "task_started", "task_completed", "notification",
        "user_preferences", "workspace_timeline_mode",
    ):
        assert is_handled(frame), f"{frame} must be handled per the parity matrix"
