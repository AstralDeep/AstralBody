"""Append-only enforcement tests (FR-014 / AU-9).

Direct UPDATE/DELETE against ``audit_events`` MUST raise unless the
session has set ``audit.allow_purge = 'true'`` (held only by the
retention CLI). The application repository never sets that GUC.
"""
from __future__ import annotations

import pytest


def test_direct_update_is_blocked_by_trigger(repo, make_event, unique_user, database):
    e = repo.insert(make_event(actor_user_id=unique_user, auth_principal=unique_user))
    conn = database._get_connection()
    try:
        with conn.cursor() as cur:
            with pytest.raises(Exception):
                cur.execute(
                    "UPDATE audit_events SET description = %s WHERE event_id = %s",
                    ("tamper", e.event_id),
                )
        conn.rollback()
    finally:
        conn.close()


def test_direct_delete_is_blocked_by_trigger(repo, make_event, unique_user, database):
    e = repo.insert(make_event(actor_user_id=unique_user, auth_principal=unique_user))
    conn = database._get_connection()
    try:
        with conn.cursor() as cur:
            with pytest.raises(Exception):
                cur.execute("DELETE FROM audit_events WHERE event_id = %s", (e.event_id,))
        conn.rollback()
    finally:
        conn.close()


def test_purge_path_holds_guc_and_succeeds(repo, make_event, unique_user, database):
    e = repo.insert(make_event(actor_user_id=unique_user, auth_principal=unique_user))
    conn = database._get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL audit.allow_purge = 'true'")
            cur.execute("DELETE FROM audit_events WHERE event_id = %s", (e.event_id,))
        conn.commit()
    finally:
        conn.close()
    assert repo.get_for_user(unique_user, e.event_id) is None
