"""055-uniform-artifacts US2 (T021) — boundary-buffered narrative markdown.

``markdown_safe_prefix_len`` holds an incremental narrative frame back to
the last whitespace boundary outside every unclosed ``**``/``*``/backtick
(incl. ``` fence)/``[link(`` span so no frame ever ships a dangling markup
token (research D5, spec FR-013). Property-tested over seeded random split
points of a markdown-heavy document: every frame is a safe prefix, prefixes
are monotonic, and the terminal flush is byte-identical to the input. The
``_call_llm`` streaming path is exercised end-to-end through the same
fake-client seam as test_llm_streaming.py.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from orchestrator.stream_manager import markdown_safe_prefix_len  # noqa: E402
from tests.test_llm_streaming import (  # noqa: E402
    _bare_orch, _content_chunk, _FakeCompletions, _stream_frames,
)


# ---------------------------------------------------------------------------
# Unit — hand-picked boundary cases
# ---------------------------------------------------------------------------

def test_dangling_bold_held():
    # The observed live defect: narrative rendered raw "You rolled **".
    assert markdown_safe_prefix_len("You rolled **") == len("You rolled ")


def test_closed_bold_ships_through_following_whitespace():
    text = "You rolled **6** and won"
    assert markdown_safe_prefix_len(text) == len("You rolled **6** and ")


def test_dangling_italic_held():
    assert markdown_safe_prefix_len("a *word") == len("a ")


def test_dangling_inline_code_held():
    assert markdown_safe_prefix_len("run `pip install") == len("run ")


def test_dangling_link_held():
    assert markdown_safe_prefix_len("see [the docs](https://x") == len("see ")
    text = "see [the docs](https://x) for more"
    assert markdown_safe_prefix_len(text) == len("see [the docs](https://x) for ")


def test_open_fence_holds_until_closed():
    text = "intro\n```python\ncode = 1\n"
    assert markdown_safe_prefix_len(text) == len("intro\n")
    closed = text + "```\nafter "
    assert markdown_safe_prefix_len(closed) == len(closed)


def test_partial_fence_marker_line_held():
    assert markdown_safe_prefix_len("intro\n```py") == len("intro\n")


def test_completed_line_resets_inline_state():
    # Inline spans never cross a newline (webrender applies them per line),
    # so a finished line with a dangling ** is final and safe to ship.
    text = "oops **\nnext words "
    assert markdown_safe_prefix_len(text) == len(text)


def test_bullet_marker_is_not_emphasis():
    assert markdown_safe_prefix_len("* item one") == len("* item ")


def test_bare_list_marker_held():
    # "* " / "- " / "1. " alone would flash as literal text, not a list item.
    assert markdown_safe_prefix_len("* ") == 0
    assert markdown_safe_prefix_len("- ") == 0
    assert markdown_safe_prefix_len("1. ") == 0


def test_escaped_asterisk_does_not_open():
    text = r"a \*lit and more"
    assert markdown_safe_prefix_len(text) == len(r"a \*lit and ")


def test_no_boundary_yet():
    assert markdown_safe_prefix_len("") == 0
    assert markdown_safe_prefix_len("Hello") == 0


# ---------------------------------------------------------------------------
# Property — random split points over a markdown-heavy document
# ---------------------------------------------------------------------------

_SPAN = "span"    # a markup span no frame may end inside
_PLAIN = "plain"

_DOC_PARTS = [
    (_PLAIN, "The dice results are in. "),
    (_SPAN, "**a bold verdict**"),
    (_PLAIN, " arrived with "),
    (_SPAN, "*subtle emphasis*"),
    (_PLAIN, " and inline "),
    (_SPAN, "`code_token()`"),
    (_PLAIN, " plus a "),
    (_SPAN, "[link label](https://example.com/path)"),
    (_PLAIN, ".\n\nA list follows:\n"),
    (_PLAIN, "* first item with "),
    (_SPAN, "**bold in item**"),
    (_PLAIN, "\n* second item\n- third item\n\n"),
    (_SPAN, "```python\ndef f():\n    return 42  # ** ` [ not markup\n```"),
    (_PLAIN, "\nAfter the fence, "),
    (_SPAN, "*receipts*"),
    (_PLAIN, " and totals "),
    (_SPAN, "**42 dollars**"),
    (_PLAIN, " even. Escaped \\*literal\\* stars too.\n"),
]

_DOC = "".join(part for _, part in _DOC_PARTS)


def _span_intervals():
    intervals, pos = [], 0
    for kind, part in _DOC_PARTS:
        if kind == _SPAN:
            intervals.append((pos, pos + len(part)))
        pos += len(part)
    return intervals


def test_property_random_split_points_never_ship_dangling_tokens():
    rng = random.Random(20260713)
    intervals = _span_intervals()
    for _trial in range(200):
        cut_count = rng.randint(1, 40)
        cuts = sorted(rng.sample(range(1, len(_DOC)), cut_count))
        pieces = [_DOC[a:b] for a, b in zip([0] + cuts, cuts + [len(_DOC)])]
        text = ""
        prev_safe = 0
        for piece in pieces:
            text += piece
            safe = markdown_safe_prefix_len(text)
            assert 0 <= safe <= len(text)
            # Frames are cumulative — a boundary once safe must stay safe.
            assert safe >= prev_safe
            if safe > prev_safe:
                frame = text[:safe]
                assert _DOC.startswith(frame)
                assert frame[-1].isspace()
                for a, b in intervals:
                    assert not (a < safe < b), (
                        f"frame ends inside span {_DOC[a:b]!r} at offset {safe}"
                    )
            prev_safe = safe
        # Terminal flush ships the full text — hold-back never loses bytes.
        assert text == _DOC


# ---------------------------------------------------------------------------
# Integration — the narrative streaming path holds back and flushes
# ---------------------------------------------------------------------------

async def test_stream_path_never_ships_dangling_bold():
    full = "You rolled **6** and won."
    comp = _FakeCompletions(chunks=[
        _content_chunk("You rolled "), _content_chunk("**"),
        _content_chunk("6"), _content_chunk("**"),
        _content_chunk(" and won.")])
    orch = _bare_orch(comp)
    msg, _usage = await orch._call_llm(
        object(), [{"role": "user", "content": "roll"}],
        allow_stream=True, stream_chat_id="chat-1")
    assert msg.content == full
    frames = _stream_frames(orch)
    assert frames and frames[-1]["terminal"] is True
    bold_span = (full.index("**"), full.index(" and won."))
    for frame in frames[:-1]:
        content = frame["components"][0]["content"]
        assert full.startswith(content)
        assert content == full or content[-1].isspace()
        assert not bold_span[0] < len(content) < bold_span[1], (
            f"frame ends inside the bold span: {content!r}")
    assert frames[0]["components"][0]["content"] == "You rolled "
    # The terminal flush delivered the held tail before the clearing frame.
    assert frames[-2]["components"][0]["content"] == full


async def test_stream_path_terminal_flush_delivers_held_tail():
    comp = _FakeCompletions(chunks=[
        _content_chunk("Total: "), _content_chunk("**42")])
    orch = _bare_orch(comp)
    msg, _usage = await orch._call_llm(
        object(), [{"role": "user", "content": "sum"}],
        allow_stream=True, stream_chat_id="chat-1")
    assert msg.content == "Total: **42"
    frames = _stream_frames(orch)
    contents = [f["components"][0]["content"] for f in frames if not f["terminal"]]
    assert contents[0] == "Total: "
    assert contents[-1] == "Total: **42"
    assert frames[-1]["terminal"] is True


async def test_stream_path_no_redundant_flush_when_fully_shipped():
    comp = _FakeCompletions(chunks=[_content_chunk("done. ")])
    orch = _bare_orch(comp)
    msg, _usage = await orch._call_llm(
        object(), [{"role": "user", "content": "hi"}],
        allow_stream=True, stream_chat_id="chat-1")
    assert msg.content == "done. "
    frames = _stream_frames(orch)
    assert [f["components"][0]["content"] for f in frames if not f["terminal"]] == ["done. "]
    assert frames[-1]["terminal"] is True
