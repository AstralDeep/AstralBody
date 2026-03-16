"""Category 3: ROTE Device Adaptation Tests.

Validates that ComponentAdapter correctly transforms UI components
for each of the 6 device profiles. 8 test cases.
"""

from rote.adapter import ComponentAdapter


# ---------------------------------------------------------------------------
# Reference components used across multiple tests
# ---------------------------------------------------------------------------

TABLE_10COL = {
    "type": "table",
    "headers": [f"Col{i}" for i in range(10)],
    "rows": [[f"r{r}c{c}" for c in range(10)] for r in range(25)],
}

BAR_CHART = {
    "type": "bar_chart",
    "title": "Test Results",
    "labels": ["A", "B", "C"],
    "datasets": [{"label": "Series 1", "data": [10, 20, 30], "color": "#f00"}],
}

FOUR_COL_GRID = {
    "type": "grid",
    "columns": 4,
    "children": [
        {"type": "text", "content": f"Item {i}", "variant": "body"}
        for i in range(4)
    ],
}

CODE_BLOCK = {
    "type": "code",
    "code": "print('hello world')",
    "language": "python",
}

BUTTON_PRIMARY = {
    "type": "button",
    "label": "Submit",
    "action": "submit",
    "variant": "primary",
    "payload": {},
}

BUTTON_SECONDARY = {
    "type": "button",
    "label": "Cancel",
    "action": "cancel",
    "variant": "secondary",
    "payload": {},
}

COMPLEX_LAYOUT = {
    "type": "card",
    "title": "Dashboard",
    "content": [
        {"type": "text", "content": "This is a long description " * 20, "variant": "body"},
        TABLE_10COL,
        BAR_CHART,
    ],
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestROTEAdaptation:
    """Verify component transformation across device profiles."""

    def test_table_mobile_truncation(self, mobile_profile):
        """ROTE-001: 10-column table on mobile → max 4 cols, max 20 rows."""
        result = ComponentAdapter.adapt([TABLE_10COL], mobile_profile)
        assert len(result) == 1
        table = result[0]
        assert table["type"] == "table"
        assert len(table["headers"]) <= 4
        assert len(table["rows"]) <= 20

    def test_chart_watch_degradation(self, watch_profile):
        """ROTE-002: Bar chart on watch → degraded to metric card."""
        result = ComponentAdapter.adapt([BAR_CHART], watch_profile)
        assert len(result) == 1
        comp = result[0]
        assert comp["type"] == "metric", f"Expected metric, got {comp['type']}"
        assert "title" in comp
        assert "value" in comp

    def test_voice_text_extraction(self, voice_profile):
        """ROTE-003: Complex layout on voice → text only, max 300 chars."""
        result = ComponentAdapter.adapt([COMPLEX_LAYOUT], voice_profile)
        assert len(result) >= 1
        for comp in result:
            assert comp["type"] == "text", f"Expected text, got {comp['type']}"
            assert len(comp.get("content", "")) <= 300

    def test_grid_collapse_mobile(self, mobile_profile):
        """ROTE-004: 4-column grid on mobile → collapsed to 1-column container."""
        result = ComponentAdapter.adapt([FOUR_COL_GRID], mobile_profile)
        assert len(result) == 1
        comp = result[0]
        # Mobile max_grid_columns=1, so grid collapses to container
        assert comp["type"] == "container"
        assert "children" in comp

    def test_code_block_mobile_removed(self, mobile_profile):
        """ROTE-005: Code block on mobile → removed (supports_code=False)."""
        result = ComponentAdapter.adapt([CODE_BLOCK], mobile_profile)
        assert len(result) == 0, "Code block should be removed on mobile"

    def test_browser_passthrough(self, browser_profile):
        """ROTE-006: All components on browser → no changes (passthrough)."""
        components = [TABLE_10COL, BAR_CHART, FOUR_COL_GRID, CODE_BLOCK]
        result = ComponentAdapter.adapt(components, browser_profile)
        assert len(result) == len(components)
        # Table should keep all columns
        assert len(result[0]["headers"]) == 10
        # Chart should pass through
        assert result[1]["type"] == "bar_chart"
        # Grid keeps 4 columns
        assert result[2]["columns"] == 4
        # Code block preserved
        assert result[3]["type"] == "code"

    def test_button_tv_removed(self, tv_profile):
        """ROTE-007: Buttons on TV → removed (read-only)."""
        result = ComponentAdapter.adapt([BUTTON_PRIMARY, BUTTON_SECONDARY], tv_profile)
        assert len(result) == 0, "Buttons should be removed on TV (read-only)"

    def test_table_tablet_column_limit(self, tablet_profile):
        """ROTE-008: 10-column table on tablet → max 6 columns."""
        result = ComponentAdapter.adapt([TABLE_10COL], tablet_profile)
        assert len(result) == 1
        table = result[0]
        assert table["type"] == "table"
        assert len(table["headers"]) <= 6
        # Rows not limited on tablet
        for row in table["rows"]:
            assert len(row) <= 6
