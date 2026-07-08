"""Feature 029 — workspace_layout persistence + schema + catalog migrations (T004/T012).

Real-Postgres coverage of: the new ``workspace_layout`` table and
``workspace_snapshot.layouts`` column (idempotent creation, CASCADE), the
WorkspaceManager layout API (upsert/claim-stealing/live ordering/remove
pruning/shared position space), snapshot round-trips including layouts, and
the feature-029 agent-catalog migrations (ml_services remap with verb
prefixing + retired-agent row cleanup) — including double-run idempotency.
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from orchestrator.workspace import (  # noqa: E402
    WorkspaceManager,
    iter_layout_refs,
    layout_key_for,
    prune_layout_refs,
)


def _can_connect_to_db() -> bool:
    try:
        import psycopg2
        from shared.database import _build_database_url

        conn = psycopg2.connect(_build_database_url())
        conn.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _can_connect_to_db(),
    reason="Postgres unavailable in this environment",
)


@pytest.fixture(scope="module")
def history(tmp_path_factory):
    from orchestrator.history import HistoryManager

    return HistoryManager(data_dir=str(tmp_path_factory.mktemp("layout-data")))


@pytest.fixture(scope="module")
def ws(history):
    return WorkspaceManager(history)


@pytest.fixture
def chat(history):
    user_id = f"pytest-layout-{uuid.uuid4().hex[:12]}"
    chat_id = history.create_chat(user_id=user_id)
    yield chat_id, user_id
    history.delete_chat(chat_id, user_id)


def _comp(agent, tool, params, **extra):
    c = {"type": "table", "headers": ["A"], "rows": [["1"]],
         "_source_agent": agent, "_source_tool": tool, "_source_params": params}
    c.update(extra)
    return c


def _ref(cid):
    return {"type": "ref", "component_id": cid}


# ---------------------------------------------------------------------------
# Schema (T004)
# ---------------------------------------------------------------------------


def test_schema_table_column_and_indexes_exist(history):
    db = history.db
    row = db.fetch_one(
        "SELECT 1 AS ok FROM information_schema.tables WHERE table_name = 'workspace_layout'")
    assert row and row["ok"] == 1
    col = db.fetch_one(
        "SELECT 1 AS ok FROM information_schema.columns "
        "WHERE table_name = 'workspace_snapshot' AND column_name = 'layouts'")
    assert col and col["ok"] == 1
    idx = db.fetch_one(
        "SELECT 1 AS ok FROM pg_indexes WHERE indexname = 'ux_workspace_layout_chat_key'")
    assert idx and idx["ok"] == 1


def test_init_db_reruns_idempotently(history):
    """Constitution IX: repeated boots are safe — _init_db twice, no error."""
    history.db._init_db()
    history.db._init_db()


def test_chat_delete_cascades_layouts(history, ws):
    user_id = f"pytest-cascade-{uuid.uuid4().hex[:12]}"
    chat_id = history.create_chat(user_id=user_id)
    ops = ws.upsert(chat_id, user_id, [_comp("a", "t", {"p": 1})])
    ws.upsert_layout(chat_id, user_id, layout_key_for(chat_id, "m1"),
                     [_ref(ops[0]["component_id"])])
    assert ws.live_layouts(chat_id, user_id)
    history.delete_chat(chat_id, user_id)
    rows = history.db.fetch_all(
        "SELECT 1 FROM workspace_layout WHERE chat_id = ?", (chat_id,))
    assert rows == []


# ---------------------------------------------------------------------------
# Layout API (T012)
# ---------------------------------------------------------------------------


def test_layout_key_deterministic():
    assert layout_key_for("c1", "42") == layout_key_for("c1", "42")
    assert layout_key_for("c1", "42") != layout_key_for("c1", "43")
    assert layout_key_for("c1", "42").startswith("ly_")


def test_upsert_layout_roundtrip_and_update_in_place(ws, chat):
    chat_id, user_id = chat
    ops = ws.upsert(chat_id, user_id, [_comp("a", "t1", {}), _comp("a", "t2", {})])
    ids = [op["component_id"] for op in ops]
    key = layout_key_for(chat_id, "m1")
    layout_v1 = [{"type": "grid", "columns": 2, "children": [_ref(ids[0]), _ref(ids[1])]}]
    assert ws.upsert_layout(chat_id, user_id, key, layout_v1)
    live = ws.live_layouts(chat_id, user_id)
    assert len(live) == 1 and live[0]["layout_key"] == key
    assert set(iter_layout_refs(live[0]["layout"])) == set(ids)
    # Re-design the same round: same key updates in place, position kept.
    pos_before = live[0]["position"]
    layout_v2 = [_ref(ids[0]), _ref(ids[1]), {"type": "divider"}]
    ws.upsert_layout(chat_id, user_id, key, layout_v2)
    live2 = ws.live_layouts(chat_id, user_id)
    assert len(live2) == 1 and live2[0]["position"] == pos_before
    assert live2[0]["layout"][-1]["type"] == "divider"


def test_later_layout_steals_claimed_refs(ws, chat):
    chat_id, user_id = chat
    ops = ws.upsert(chat_id, user_id, [_comp("a", "t1", {}), _comp("a", "t2", {})])
    ids = [op["component_id"] for op in ops]
    k1 = layout_key_for(chat_id, "m1")
    k2 = layout_key_for(chat_id, "m2")
    ws.upsert_layout(chat_id, user_id, k1, [_ref(ids[0]), _ref(ids[1])])
    ws.upsert_layout(chat_id, user_id, k2, [_ref(ids[1])])
    by_key = {item["layout_key"]: item for item in ws.live_layouts(chat_id, user_id)}
    assert set(iter_layout_refs(by_key[k1]["layout"])) == {ids[0]}, "k1 lost the stolen ref"
    assert set(iter_layout_refs(by_key[k2]["layout"])) == {ids[1]}


def test_remove_component_prunes_layout_refs(ws, chat):
    chat_id, user_id = chat
    ops = ws.upsert(chat_id, user_id, [_comp("a", "t1", {}), _comp("a", "t2", {})])
    ids = [op["component_id"] for op in ops]
    key = layout_key_for(chat_id, "m1")
    ws.upsert_layout(chat_id, user_id, key,
                     [{"type": "card", "title": "g", "content": [_ref(ids[0]), _ref(ids[1])]}])
    assert ws.remove(chat_id, user_id, ids[0])
    live = ws.live_layouts(chat_id, user_id)
    assert set(iter_layout_refs(live[0]["layout"])) == {ids[1]}


def test_positions_share_one_ordering_space(ws, chat):
    chat_id, user_id = chat
    ops = ws.upsert(chat_id, user_id, [_comp("a", "t1", {})])
    before = ws.next_canvas_position(chat_id, user_id)
    ws.upsert_layout(chat_id, user_id, layout_key_for(chat_id, "m1"),
                     [_ref(ops[0]["component_id"])])
    after = ws.next_canvas_position(chat_id, user_id)
    assert after == before + 1, "layout rows consume the shared position counter"


def test_prune_layout_refs_keeps_empty_containers():
    tree = [{"type": "card", "title": "g", "content": [_ref("x")]}]
    pruned = prune_layout_refs(tree, {"x"})
    assert pruned[0]["type"] == "card" and pruned[0]["content"] == []


# ---------------------------------------------------------------------------
# Snapshots carry layouts (T012 / FR-025)
# ---------------------------------------------------------------------------


def test_snapshot_roundtrips_layouts(ws, chat):
    chat_id, user_id = chat
    ops = ws.upsert(chat_id, user_id, [_comp("a", "t1", {}), _comp("a", "t2", {})])
    ids = [op["component_id"] for op in ops]
    ws.upsert_layout(chat_id, user_id, layout_key_for(chat_id, "m1"),
                     [_ref(ids[0]), _ref(ids[1])])
    sid = ws.snapshot(chat_id, user_id, cause="turn")
    snap = ws.get_snapshot(sid, user_id)
    assert snap["layouts"], "designed state captured"
    assert set(iter_layout_refs(snap["layouts"][0]["layout"])) == set(ids)


def test_pre_029_snapshot_reads_as_no_layouts(ws, chat, history):
    chat_id, user_id = chat
    history.db.execute(
        "INSERT INTO workspace_snapshot (chat_id, user_id, cause, components, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (chat_id, user_id, "turn", json.dumps([]), 1),
    )
    row = history.db.fetch_one(
        "SELECT id FROM workspace_snapshot WHERE chat_id = ? ORDER BY id DESC LIMIT 1",
        (chat_id,))
    snap = ws.get_snapshot(row["id"], user_id)
    assert snap["layouts"] == [], "NULL layouts column degrades to flat render"


def test_snapshot_without_layouts_stores_null(ws, chat, history):
    chat_id, user_id = chat
    ws.upsert(chat_id, user_id, [_comp("a", "t1", {})])
    ws.snapshot(chat_id, user_id, cause="turn")
    row = history.db.fetch_one(
        "SELECT layouts FROM workspace_snapshot WHERE chat_id = ? ORDER BY id DESC LIMIT 1",
        (chat_id,))
    assert row["layouts"] is None


# ---------------------------------------------------------------------------
# Feature-029 catalog migrations (T020/T022) — guarded, idempotent
# ---------------------------------------------------------------------------


def _seed_rows(db, user_id):
    now = 1
    db.execute(
        "INSERT INTO agent_scopes (user_id, agent_id, scope, enabled, updated_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, "classify-1", "tools:read", True, now))
    db.execute(
        "INSERT INTO agent_scopes (user_id, agent_id, scope, enabled, updated_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, "forecaster-1", "tools:read", False, now))
    db.execute(
        "INSERT INTO tool_overrides (user_id, agent_id, tool_name, enabled, updated_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, "classify-1", "submit_dataset", False, now))
    db.execute(
        "INSERT INTO tool_overrides (user_id, agent_id, tool_name, enabled, updated_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, "forecaster-1", "get_results", True, now))
    db.execute(
        "INSERT INTO tool_overrides (user_id, agent_id, tool_name, enabled, updated_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, "llm-factory-1", "chat_with_model", False, now))
    db.execute(
        "INSERT INTO user_credentials (user_id, agent_id, credential_key, encrypted_value, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, "classify-1", "CLASSIFY_URL", "enc:x", now, now))
    db.execute(
        "INSERT INTO agent_scopes (user_id, agent_id, scope, enabled, updated_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, "grants-1", "tools:read", True, now))
    db.execute(
        "INSERT INTO user_credentials (user_id, agent_id, credential_key, encrypted_value, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, "nocodb-1", "NOCODB_API_TOKEN", "enc:y", now, now))


def _cleanup_rows(db, user_id):
    for table in ("agent_scopes", "tool_overrides", "user_credentials"):
        db.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))


def _force_full_init(db):
    """Run ``_init_db`` with the schema_meta revision marker cleared.

    Feature 052's fast path skips the full migration set (including
    ``_migrate_agent_catalog_029``) when the marker is current; deleting the
    marker forces the full run, and ``_init_db`` re-upserts it afterward so
    other tests see a current marker again.
    """
    db.execute("DELETE FROM schema_meta WHERE key = 'revision'")
    db._init_db()


def test_catalog_migration_remaps_merges_and_cleans(history):
    db = history.db
    user_id = f"pytest-mig-{uuid.uuid4().hex[:12]}"
    _seed_rows(db, user_id)
    try:
        _force_full_init(db)  # runs _migrate_agent_catalog_029

        scopes = db.fetch_all(
            "SELECT agent_id, scope, enabled FROM agent_scopes WHERE user_id = ?", (user_id,))
        assert [dict(s) for s in scopes] == [
            {"agent_id": "ml-services-1", "scope": "tools:read", "enabled": True}
        ], "OR-merge: granted on any predecessor stays granted; grants-1 row deleted"

        overrides = {(r["agent_id"], r["tool_name"]): r["enabled"] for r in db.fetch_all(
            "SELECT agent_id, tool_name, enabled FROM tool_overrides WHERE user_id = ?", (user_id,))}
        assert overrides == {
            ("ml-services-1", "classify_submit_dataset"): False,
            ("ml-services-1", "forecaster_get_results"): True,
            ("ml-services-1", "chat_with_model"): False,
        }, "colliding verbs prefixed per source service; unique names unchanged"

        creds = db.fetch_all(
            "SELECT agent_id, credential_key FROM user_credentials WHERE user_id = ?", (user_id,))
        assert [dict(c) for c in creds] == [
            {"agent_id": "ml-services-1", "credential_key": "CLASSIFY_URL"}
        ], "credentials carry over; retired-agent credentials destroyed"

        # Idempotency: a second boot changes nothing.
        before = sorted(map(dict, db.fetch_all(
            "SELECT agent_id, tool_name, enabled FROM tool_overrides WHERE user_id = ?", (user_id,))),
            key=lambda r: r["tool_name"])
        _force_full_init(db)
        after = sorted(map(dict, db.fetch_all(
            "SELECT agent_id, tool_name, enabled FROM tool_overrides WHERE user_id = ?", (user_id,))),
            key=lambda r: r["tool_name"])
        assert before == after
    finally:
        _cleanup_rows(db, user_id)
