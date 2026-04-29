"""T018 — verify the feature-006 LLM event-class identifiers are
accepted by the existing AuditEventCreate validator.

The audit DDL has no Postgres CHECK constraint on ``event_class``;
validation lives entirely in :data:`audit.schemas.EVENT_CLASSES`.
This test ensures the three new identifiers (``llm_config_change``,
``llm_unconfigured``, ``llm_call``) round-trip through ``AuditEventCreate``
without rejection, while a typo'd identifier still raises.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from audit.schemas import EVENT_CLASSES, AuditEventCreate


def _now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.mark.parametrize(
    "event_class",
    ["llm_config_change", "llm_unconfigured", "llm_call"],
)
def test_new_event_classes_accepted(event_class):
    assert event_class in EVENT_CLASSES
    ev = AuditEventCreate(
        actor_user_id="u1",
        auth_principal="u1",
        event_class=event_class,
        action_type=f"{event_class}.smoke",
        description="smoke test",
        correlation_id="00000000-0000-0000-0000-000000000001",
        outcome="success",
        started_at=_now(),
    )
    assert ev.event_class == event_class


def test_typo_event_class_still_rejected():
    with pytest.raises(ValueError, match="unknown event_class"):
        AuditEventCreate(
            actor_user_id="u1",
            auth_principal="u1",
            event_class="llm_call_typo",
            action_type="x",
            description="x",
            correlation_id="00000000-0000-0000-0000-000000000001",
            outcome="success",
            started_at=_now(),
        )
