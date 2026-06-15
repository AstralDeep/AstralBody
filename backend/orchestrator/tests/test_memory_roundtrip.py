"""030 T016 — memory round-trip via the orchestrator meta-tool dispatch (US2).

Real DB-backed: remember → memory_get/memory_search through
memory_chat.handle_meta_tool, asserting persistence round-trips. (The pure-unit
shape is covered by test_memory_chat.py; this exercises the real repository.)
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


@needs_db
def test_remember_then_recall_roundtrip_real_db():
    from orchestrator import memory_chat
    from personalization.memory_tools import MemoryTools
    from personalization.service import PersonalizationService
    from shared.database import Database

    db = Database()
    user = f"pytest-memrt-{uuid.uuid4().hex[:8]}"
    svc = PersonalizationService(db)
    orch = types.SimpleNamespace(personalization_service=types.SimpleNamespace(repo=svc.repo))
    # Inject a clean gate so the test doesn't depend on Presidio.
    orch._memory_tools = MemoryTools(svc.repo, phi_gate=_CleanGate())

    try:
        stored = asyncio.run(memory_chat.handle_meta_tool(
            orch, "remember", {"value": "Works on NSF grants", "category": "context"},
            user_id=user, chat_id="c1", websocket=object()))
        assert stored.result["status"] == "stored"

        got = asyncio.run(memory_chat.handle_meta_tool(
            orch, "memory_get", {}, user_id=user, chat_id="c1", websocket=object()))
        assert got.result["count"] == 1
        assert got.result["items"][0]["value"] == "Works on NSF grants"

        found = asyncio.run(memory_chat.handle_meta_tool(
            orch, "memory_search", {"query": "NSF"}, user_id=user, chat_id="c1",
            websocket=object()))
        assert found.result["count"] == 1
    finally:
        try:
            db.execute("DELETE FROM memory_item WHERE user_id = ?", (user,))
        except Exception:
            pass
