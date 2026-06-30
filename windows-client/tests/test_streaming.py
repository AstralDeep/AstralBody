"""Tests for the push-streaming consumer (``astral_client.streaming``).

Pure logic — no Qt/PySide6 required, so these run in the lean test env. They
verify the structured (non-HTML) rendering, the ``session_id`` filter, monotonic
``seq`` dedupe, terminal final/forget, error rendering, and the legacy poll
fallback — i.e. the behaviour that makes live tool output appear in the native
canvas in place.
"""
from astral_client.streaming import (
    stream_error_ops,
    stream_frame_to_ops,
    stream_node_id,
    subscribe_ack_ops,
)


def _frame(**kw):
    base = {"type": "ui_stream_data", "stream_id": "s1", "seq": 1}
    base.update(kw)
    return base


def test_renders_components_in_place_keyed_by_stream():
    seq: dict = {}
    ops = stream_frame_to_ops(
        _frame(components=[{"type": "text", "content": "hi"}]),
        active_chat=None, seq_state=seq,
    )
    assert ops == [{
        "op": "upsert",
        "component_id": stream_node_id("s1"),
        "component": {"type": "text", "content": "hi"},
    }]
    assert seq == {"s1": 1}


def test_multiple_components_wrapped_in_container():
    ops = stream_frame_to_ops(
        _frame(components=[{"type": "text", "content": "a"}, {"type": "text", "content": "b"}]),
        active_chat=None, seq_state={},
    )
    comp = ops[0]["component"]
    assert comp["type"] == "container"
    assert [c["content"] for c in comp["content"]] == ["a", "b"]


def test_renders_structured_components_not_html():
    ops = stream_frame_to_ops(
        _frame(html="<b>web only</b>", components=[{"type": "text", "content": "native"}]),
        active_chat=None, seq_state={},
    )
    # The native client must use `components`, never the web `html`.
    assert ops[0]["component"] == {"type": "text", "content": "native"}


def test_seq_dedupe_drops_stale_and_equal_keeps_newer():
    seq = {"s1": 5}
    assert stream_frame_to_ops(_frame(seq=5, components=[{"type": "text", "content": "x"}]),
                               active_chat=None, seq_state=seq) == []
    assert stream_frame_to_ops(_frame(seq=4, components=[{"type": "text", "content": "x"}]),
                               active_chat=None, seq_state=seq) == []
    assert stream_frame_to_ops(_frame(seq=6, components=[{"type": "text", "content": "x"}]),
                               active_chat=None, seq_state=seq) != []
    assert seq["s1"] == 6


def test_session_filter_drops_foreign_chat_keeps_match():
    foreign = stream_frame_to_ops(
        _frame(session_id="chatB", components=[{"type": "text", "content": "x"}]),
        active_chat="chatA", seq_state={},
    )
    assert foreign == []
    match = stream_frame_to_ops(
        _frame(session_id="chatA", components=[{"type": "text", "content": "x"}]),
        active_chat="chatA", seq_state={},
    )
    assert match != []


def test_error_frame_renders_alert_warning_when_retryable():
    ops = stream_frame_to_ops(
        _frame(error={"code": "tool_error", "message": "boom", "retryable": True}),
        active_chat=None, seq_state={},
    )
    comp = ops[0]["component"]
    assert comp["type"] == "alert" and comp["variant"] == "warning"
    assert "boom" in comp["message"]


def test_nonretryable_error_is_error_variant():
    ops = stream_frame_to_ops(
        _frame(error={"code": "cancelled", "message": "stop", "retryable": False}),
        active_chat=None, seq_state={},
    )
    assert ops[0]["component"]["variant"] == "error"


def test_terminal_with_payload_renders_then_forgets_stream():
    seq = {"s1": 1}
    ops = stream_frame_to_ops(
        _frame(seq=2, terminal=True, components=[{"type": "text", "content": "final"}]),
        active_chat=None, seq_state=seq,
    )
    assert ops[0]["component"]["content"] == "final"
    assert "s1" not in seq  # forgotten


def test_bare_terminal_frame_yields_no_ops_but_forgets():
    seq = {"s1": 1}
    assert stream_frame_to_ops(_frame(seq=2, terminal=True), active_chat=None, seq_state=seq) == []
    assert "s1" not in seq


def test_unaddressable_frame_dropped():
    assert stream_frame_to_ops({"components": [{"type": "text", "content": "x"}]},
                               active_chat=None, seq_state={}) == []


def test_legacy_poll_frame_keyed_by_tool_name():
    ops = stream_frame_to_ops(
        {"type": "stream_data", "tool_name": "ticker",
         "components": [{"type": "text", "content": "tick"}]},
        active_chat=None, seq_state={},
    )
    assert ops[0]["component_id"] == "stream-tool-ticker"


def test_subscribe_ack_placeholder_for_node():
    ops = subscribe_ack_ops({"stream_id": "s1", "tool_name": "ticker"})
    assert ops[0]["component_id"] == stream_node_id("s1")
    assert "ticker" in ops[0]["component"]["content"]


def test_stream_error_control_push_shape_targets_node():
    ops = stream_error_ops(
        {"type": "stream_error", "payload": {"stream_id": "s1", "code": "blocked", "message": "no"}}
    )
    assert ops[0]["component_id"] == stream_node_id("s1")
    assert ops[0]["component"]["type"] == "alert" and "no" in ops[0]["component"]["message"]


def test_stream_error_control_without_node_is_empty():
    # No stream_id/tool_name -> caller surfaces this as a status line instead.
    assert stream_error_ops({"type": "stream_error", "payload": {"code": "params_invalid", "message": "bad"}}) == []
