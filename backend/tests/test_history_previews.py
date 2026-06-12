"""Feature 030 — chat history listing fixes (orchestrator/history.py).

Covers the two halves of the verified UX bug:

* Previews: component-list message content is flattened into human text
  (``type == "text"`` components contribute their ``content``, other
  components fall back to ``title``, everything else is skipped) instead
  of leaking the Python repr of the serialized list. Plain-string content
  keeps its passthrough preview; everything is capped at
  ``PREVIEW_MAX_CHARS``.
* Listing: zero-message "New Chat" husks are excluded from
  ``get_recent_chats()``; a chat appears as soon as its first message
  lands. The per-chat return shape is unchanged (the no-build web client
  consumes it as-is).

Runs against the live Postgres inside the astralbody container, like the
other HistoryManager suites (see tests/test_database.py).
"""
import os
import sys
import uuid

import pytest

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from orchestrator.history import HistoryManager, PREVIEW_MAX_CHARS


@pytest.fixture(scope="module")
def hm(tmp_path_factory):
    """A HistoryManager backed by the live test Postgres."""
    return HistoryManager(data_dir=str(tmp_path_factory.mktemp("hist-prev-data")))


@pytest.fixture
def user_id(hm):
    """A unique per-test user id; rows are cleaned up on teardown."""
    uid = f"hist-prev-{uuid.uuid4().hex[:12]}"
    yield uid
    hm.db.execute("DELETE FROM messages WHERE user_id = ?", (uid,))
    hm.db.execute("DELETE FROM chats WHERE user_id = ?", (uid,))


def _listing_entry(hm, user_id, chat_id):
    """Return the get_recent_chats() entry for chat_id, or None."""
    chats = hm.get_recent_chats(user_id=user_id)
    return next((c for c in chats if c["id"] == chat_id), None)


# =========================================================================
# Preview extraction
# =========================================================================

def test_component_list_preview_extracts_text_content(hm, user_id):
    """A text component's content becomes the preview — never its repr."""
    chat_id = hm.create_chat(user_id=user_id)
    hm.add_message(
        chat_id,
        "assistant",
        [{"type": "text", "content": "This system can help you orchestrate agents.", "variant": "markdown"}],
        user_id=user_id,
    )

    entry = _listing_entry(hm, user_id, chat_id)
    assert entry is not None
    assert entry["preview"] == "This system can help you orchestrate agents."
    assert "{" not in entry["preview"]
    assert "[" not in entry["preview"]


def test_component_list_preview_title_fallback(hm, user_id):
    """Non-text components contribute their title instead of raw data."""
    chat_id = hm.create_chat(user_id=user_id)
    hm.add_message(
        chat_id,
        "assistant",
        [{"type": "chart", "title": "Revenue by Quarter", "data": {"x": [1, 2], "y": [3, 4]}}],
        user_id=user_id,
    )

    entry = _listing_entry(hm, user_id, chat_id)
    assert entry["preview"] == "Revenue by Quarter"
    assert "{" not in entry["preview"]


def test_component_list_preview_mixed_components(hm, user_id):
    """Mixed lists join text content and titles in order, skipping the rest."""
    chat_id = hm.create_chat(user_id=user_id)
    hm.add_message(
        chat_id,
        "assistant",
        [
            {"type": "text", "content": "Here are your results.", "variant": "markdown"},
            {"type": "table", "title": "ETF Holdings", "rows": [["VTI", "60%"]]},
            {"type": "chart", "data": {"x": [1], "y": [2]}},  # no title, no text -> skipped
            "as requested.",  # bare strings pass through
            42,  # non-dict, non-str items are skipped
        ],
        user_id=user_id,
    )

    entry = _listing_entry(hm, user_id, chat_id)
    assert entry["preview"] == "Here are your results. ETF Holdings as requested."
    assert "{" not in entry["preview"]


def test_component_preview_collapses_whitespace_and_truncates(hm, user_id):
    """Extracted text is whitespace-collapsed and capped at PREVIEW_MAX_CHARS."""
    chat_id = hm.create_chat(user_id=user_id)
    long_text = "Lorem  ipsum\n\ndolor sit amet. " * 20
    hm.add_message(
        chat_id,
        "assistant",
        [{"type": "text", "content": long_text, "variant": "markdown"}],
        user_id=user_id,
    )

    entry = _listing_entry(hm, user_id, chat_id)
    preview = entry["preview"]
    assert "\n" not in preview
    assert "  " not in preview
    assert preview.endswith("...")
    assert len(preview) == PREVIEW_MAX_CHARS + 3
    assert preview.startswith("Lorem ipsum dolor sit amet.")


def test_plain_string_preview_passthrough(hm, user_id):
    """Plain-string message content previews as-is."""
    chat_id = hm.create_chat(user_id=user_id)
    hm.add_message(chat_id, "user", "What is the weather in Lexington?", user_id=user_id)

    entry = _listing_entry(hm, user_id, chat_id)
    assert entry["preview"] == "What is the weather in Lexington?"


def test_plain_string_preview_truncates(hm, user_id):
    """Long plain strings are truncated to PREVIEW_MAX_CHARS."""
    chat_id = hm.create_chat(user_id=user_id)
    long_text = "z" * (PREVIEW_MAX_CHARS * 2)
    hm.add_message(chat_id, "user", long_text, user_id=user_id)

    entry = _listing_entry(hm, user_id, chat_id)
    assert entry["preview"] == "z" * PREVIEW_MAX_CHARS + "..."


def test_scalar_json_content_stringified(hm, user_id):
    """Non-str/list/dict JSON content (e.g. a bare number) stringifies."""
    chat_id = hm.create_chat(user_id=user_id)
    hm.add_message(chat_id, "assistant", 123, user_id=user_id)

    entry = _listing_entry(hm, user_id, chat_id)
    assert entry["preview"] == "123"


def test_dict_content_never_leaks_repr(hm, user_id):
    """Bare-dict content (no text/title) yields an empty preview, not repr."""
    chat_id = hm.create_chat(user_id=user_id)
    hm.add_message(chat_id, "assistant", {"response": "Hi there"}, user_id=user_id)

    entry = _listing_entry(hm, user_id, chat_id)
    assert entry is not None
    assert entry["preview"] == ""
    assert "{" not in entry["preview"]


# =========================================================================
# Zero-message chat exclusion
# =========================================================================

def test_empty_chat_excluded_from_listing(hm, user_id):
    """A freshly created chat with no messages is not listed."""
    chat_id = hm.create_chat(user_id=user_id)
    assert _listing_entry(hm, user_id, chat_id) is None
    # The chat itself still exists (creation is unchanged) and is loadable.
    assert hm.get_chat(chat_id, user_id=user_id) is not None


def test_chat_listed_as_soon_as_first_message_lands(hm, user_id):
    """A chat with one message IS listed, with the unchanged return shape."""
    chat_id = hm.create_chat(user_id=user_id)
    assert _listing_entry(hm, user_id, chat_id) is None

    hm.add_message(chat_id, "user", "hello", user_id=user_id)

    entry = _listing_entry(hm, user_id, chat_id)
    assert entry is not None
    assert entry["preview"] == "hello"
    # Return shape consumed by the no-build client must stay identical.
    assert set(entry.keys()) == {
        "id", "title", "agent_id", "updated_at", "preview", "has_saved_components",
    }
