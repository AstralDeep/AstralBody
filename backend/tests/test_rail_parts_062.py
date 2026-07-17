"""Feature 062 — the 060 snapshot transcript honors the 045 words-only rail.

`_rail_parts` post-processes a transcript message's parts: `components` parts
keep only text-like members (the `_transcript_html` predicate mirrored), other
part kinds pass through untouched, and a message whose parts all drop is
omitted by the caller. These are pure functions — no orchestrator needed.
"""

from orchestrator.history import _is_rail_text_only, _rail_parts


def _text(content: str) -> dict:
    return {"type": "text", "content": content}


def _metric() -> dict:
    return {"type": "metric", "label": "TOP MATCH", "value": "59.2%"}


class TestIsRailTextOnly:
    def test_text_primitive_is_text_only(self):
        assert _is_rail_text_only([_text("hello")])

    def test_rich_primitive_is_not(self):
        assert not _is_rail_text_only([_metric()])

    def test_table_and_chart_are_not(self):
        assert not _is_rail_text_only([{"type": "table", "headers": [], "rows": []}])
        assert not _is_rail_text_only([{"type": "bar_chart", "series": []}])

    def test_card_of_text_is_text_only(self):
        card = {"type": "card", "title": "Response", "content": [_text("words")]}
        assert _is_rail_text_only([card])

    def test_card_with_nested_rich_child_is_not(self):
        card = {"type": "card", "title": "Stats", "content": [_metric()]}
        assert not _is_rail_text_only([card])

    def test_container_children_key_is_checked(self):
        container = {"type": "container", "children": [_metric()]}
        assert not _is_rail_text_only([container])

    def test_non_mapping_entries_are_ignored(self):
        assert _is_rail_text_only(["stray string", _text("ok")])

    def test_alert_and_list_and_divider_are_text_only(self):
        assert _is_rail_text_only(
            [
                {"type": "alert", "message": "heads up", "variant": "info"},
                {"type": "list", "items": ["a", "b"]},
                {"type": "divider"},
            ]
        )


class TestRailParts:
    def test_text_part_passes_through(self):
        parts = [{"type": "text", "text": "hello"}]
        assert _rail_parts(parts) == parts

    def test_structured_and_recovery_parts_pass_through(self):
        parts = [
            {"type": "structured", "value": {"a": 1}, "plain_text": "a=1"},
            {"type": "recovery", "code": "bad_content", "message": "unreadable"},
        ]
        assert _rail_parts(parts) == parts

    def test_pure_tool_components_part_drops_entirely(self):
        parts = [{"type": "components", "components": [_metric(), _metric()]}]
        assert _rail_parts(parts) == []

    def test_mixed_components_keep_only_text_like(self):
        words = _text("the answer")
        parts = [{"type": "components", "components": [_metric(), words]}]
        assert _rail_parts(parts) == [
            {"type": "components", "components": [words]}
        ]

    def test_text_only_card_survives(self):
        doc = {"type": "card", "title": "Response", "content": [_text("summary")]}
        parts = [{"type": "components", "components": [doc]}]
        assert _rail_parts(parts) == parts

    def test_rich_dropped_but_other_parts_keep_order(self):
        words = {"type": "text", "text": "before"}
        rich = {"type": "components", "components": [_metric()]}
        after = {"type": "components", "components": [_text("after")]}
        assert _rail_parts([words, rich, after]) == [words, after]
