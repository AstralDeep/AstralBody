"""030 T023 — onboarding → personalization round-trip integration (US3).

Full slice: start onboarding → submit the personalization ParamPicker (via the
orchestrator submit interpreter) → profile persists → mark completed → returning
user is not re-onboarded and their preferences are in effect.
"""
import asyncio
import sys
import types
import uuid
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _can_connect():
    try:
        import psycopg2
        from shared.database import _build_database_url
        psycopg2.connect(_build_database_url()).close()
        return True
    except Exception:
        return False


needs_db = pytest.mark.skipif(not _can_connect(), reason="Postgres unavailable")


class _CleanGate:
    def contains_phi(self, value):
        return False


class _FakeTP:
    def get_tool_scope(self, agent_id, tool_name):
        return "tools:read"

    def is_scope_enabled(self, user_id, agent_id, scope):
        return True

    def set_skill_enabled(self, user_id, agent_id, tool_name, enabled):
        pass


@needs_db
def test_onboarding_personalization_roundtrip(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from onboarding import api as oapi
    from onboarding.repository import OnboardingRepository
    from orchestrator import onboarding_submit
    from orchestrator.auth import get_current_user_payload, require_user_id
    from personalization import api as papi
    from personalization.service import PersonalizationService
    from shared.database import Database

    # Clean PHI gate so the submit interpreter doesn't depend on Presidio.
    import personalization.phi_gate as pg
    monkeypatch.setattr(pg, "get_phi_gate", lambda: _CleanGate())

    db = Database()
    user = f"pytest-onbint-{uuid.uuid4().hex[:8]}"
    svc = PersonalizationService(db)

    async def _send_ui_render(ws, components, target="canvas"):
        return None

    orch = types.SimpleNamespace(
        onboarding_repo=OnboardingRepository(db),
        personalization_service=svc,
        tool_permissions=_FakeTP(),
        send_ui_render=_send_ui_render,
    )

    app = FastAPI()
    app.state.orchestrator = orch
    app.include_router(oapi.onboarding_user_router)
    app.include_router(papi.personalization_router)
    payload = {"sub": user, "preferred_username": user, "realm_access": {"roles": ["user"]}}
    app.dependency_overrides[require_user_id] = lambda: user
    app.dependency_overrides[get_current_user_payload] = lambda: payload
    tc = TestClient(app)

    try:
        # 1. New user — onboarding not yet completed.
        r = tc.get("/api/onboarding/state")
        assert r.status_code == 200
        assert r.json()["status"] != "completed"

        # 2. Start onboarding.
        assert tc.put("/api/onboarding/state", json={"status": "in_progress"}).status_code == 200

        # 3. Submit the personalization ParamPicker (orchestrator submit path).
        handled = asyncio.run(onboarding_submit.handle_submit(
            orch, object(), user,
            "Save my personalization profile — profession: Researcher; goals: grants, papers",
            "c1"))
        assert handled is True

        # 4. Complete onboarding.
        r = tc.put("/api/onboarding/state", json={"status": "completed"})
        assert r.status_code == 200
        assert r.json().get("completed_at") is not None

        # 5. Profile persisted and reflected via the personalization API.
        prof = tc.get("/api/personalization/profile").json()
        assert prof["profession"] == "Researcher"
        assert "grants" in prof["goals"]

        # 6. Returning user is not re-onboarded.
        assert tc.get("/api/onboarding/state").json()["status"] == "completed"
    finally:
        for table, col in (("onboarding_state", "user_id"),
                           ("user_personalization", "user_id"),
                           ("memory_item", "user_id")):
            try:
                db.execute(f"DELETE FROM {table} WHERE {col} = ?", (user,))
            except Exception:
                pass
