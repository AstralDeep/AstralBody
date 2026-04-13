"""AttachmentRepository: insert, ownership-scoped get, listing, soft-delete."""

from __future__ import annotations

from orchestrator.attachments.repository import AttachmentRepository
from .conftest import insert_sample


def test_insert_and_get_by_id(stub_db):
    repo = AttachmentRepository(stub_db)
    aid = insert_sample(repo, user_id="alice")
    got = repo.get_by_id(aid, "alice")
    assert got is not None
    assert got.attachment_id == aid
    assert got.user_id == "alice"


def test_get_by_id_returns_none_for_foreign_user(stub_db):
    repo = AttachmentRepository(stub_db)
    aid = insert_sample(repo, user_id="alice")
    assert repo.get_by_id(aid, "bob") is None


def test_list_filters_by_user_and_category(stub_db):
    repo = AttachmentRepository(stub_db)
    insert_sample(repo, user_id="alice", category="document", extension="pdf")
    insert_sample(repo, user_id="alice", category="image", extension="png")
    insert_sample(repo, user_id="bob", category="document", extension="pdf")

    alice_all, _ = repo.list_for_user("alice")
    assert len(alice_all) == 2

    alice_docs, _ = repo.list_for_user("alice", category="document")
    assert len(alice_docs) == 1
    assert alice_docs[0].category == "document"

    # Bob's listing must never include alice's rows.
    bob_all, _ = repo.list_for_user("bob")
    assert len(bob_all) == 1
    assert bob_all[0].user_id == "bob"


def test_list_pagination_cursor(stub_db):
    repo = AttachmentRepository(stub_db)
    ids = [insert_sample(repo, user_id="alice") for _ in range(5)]
    page1, cursor = repo.list_for_user("alice", limit=2)
    assert len(page1) == 2
    assert cursor is not None
    page2, cursor2 = repo.list_for_user("alice", limit=2, cursor=cursor)
    assert len(page2) == 2
    page3, cursor3 = repo.list_for_user("alice", limit=2, cursor=cursor2)
    assert len(page3) == 1
    assert cursor3 is None
    seen = {a.attachment_id for a in (*page1, *page2, *page3)}
    assert seen == set(ids)


def test_soft_delete_hides_from_get_and_list(stub_db):
    repo = AttachmentRepository(stub_db)
    aid = insert_sample(repo, user_id="alice")
    assert repo.soft_delete(aid, "alice") is True
    assert repo.get_by_id(aid, "alice") is None
    items, _ = repo.list_for_user("alice")
    assert items == []


def test_soft_delete_rejects_foreign_user(stub_db):
    repo = AttachmentRepository(stub_db)
    aid = insert_sample(repo, user_id="alice")
    assert repo.soft_delete(aid, "bob") is False
    # Alice's row is still live.
    assert repo.get_by_id(aid, "alice") is not None


def test_soft_delete_all_for_user(stub_db):
    repo = AttachmentRepository(stub_db)
    insert_sample(repo, user_id="alice")
    insert_sample(repo, user_id="alice")
    insert_sample(repo, user_id="bob")
    purged = repo.soft_delete_all_for_user("alice")
    assert purged == 2
    assert repo.list_for_user("alice")[0] == []
    assert len(repo.list_for_user("bob")[0]) == 1
