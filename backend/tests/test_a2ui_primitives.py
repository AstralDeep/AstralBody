"""
A2UI Primitives Tests — Component model, builder helpers, and flatten_tree migration bridge.
"""
import os
import sys
import json
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


class TestA2UIComponent:
    """Tests for A2UIComponent dataclass and serialization."""

    def test_component_to_dict(self):
        from shared.a2ui_primitives import A2UIComponent
        comp = A2UIComponent(
            id="test-1",
            type="Text",
            properties={"text": "Hello", "textStyle": "body"},
        )
        d = comp.to_dict()
        assert d["id"] == "test-1"
        assert d["type"] == "Text"
        assert d["properties"]["text"] == "Hello"
        assert "children" not in d  # empty children omitted

    def test_component_with_children(self):
        from shared.a2ui_primitives import A2UIComponent
        comp = A2UIComponent(
            id="col-1",
            type="Column",
            properties={},
            children=["text-1", "text-2"],
        )
        d = comp.to_dict()
        assert d["children"] == ["text-1", "text-2"]

    def test_component_with_accessibility(self):
        from shared.a2ui_primitives import A2UIComponent
        comp = A2UIComponent(
            id="btn-1",
            type="Button",
            properties={"text": "Click"},
            accessibility={"label": "Submit form"},
        )
        d = comp.to_dict()
        assert d["accessibility"]["label"] == "Submit form"

    def test_component_with_data_binding(self):
        from shared.a2ui_primitives import A2UIComponent
        comp = A2UIComponent(
            id="tf-1",
            type="TextField",
            properties={"placeholder": "Name"},
            data_binding={"value": "/user/name"},
        )
        d = comp.to_dict()
        assert d["dataBinding"]["value"] == "/user/name"


class TestBuilderHelpers:
    """Tests for convenience builder functions."""

    def test_text_builder(self):
        from shared.a2ui_primitives import text
        comp = text("Hello World", variant="h1", id="t1")
        assert comp.id == "t1"
        assert comp.type == "Text"
        assert comp.properties["text"] == "Hello World"
        assert comp.properties["textStyle"] == "h1"

    def test_text_markdown(self):
        from shared.a2ui_primitives import text
        comp = text("# Title", variant="markdown")
        assert comp.properties["markdown"] is True

    def test_button_builder(self):
        from shared.a2ui_primitives import button
        comp = button("Submit", action_name="chat_message", context={"msg": "hi"}, variant="primary")
        assert comp.type == "Button"
        assert comp.properties["text"] == "Submit"
        assert comp.properties["action"]["event"]["name"] == "chat_message"
        assert comp.properties["action"]["event"]["context"]["msg"] == "hi"

    def test_table_builder(self):
        from shared.a2ui_primitives import table
        comp = table(
            headers=["Name", "Age"],
            rows=[["Alice", 30], ["Bob", 25]],
            total_rows=100,
            page_size=25,
            source_tool="get_patients",
            source_agent="medical",
        )
        assert comp.type == "x-astral-table"
        assert comp.properties["headers"] == ["Name", "Age"]
        assert comp.properties["totalRows"] == 100
        assert comp.properties["sourceTool"] == "get_patients"

    def test_card_builder(self):
        from shared.a2ui_primitives import card, text
        t = text("Content")
        c = card("My Card", [t.id], collapsible=True, default_open=False)
        assert c.type == "Card"
        assert c.properties["title"] == "My Card"
        assert c.properties["isCollapsible"] is True
        assert c.children == [t.id]

    def test_column_builder(self):
        from shared.a2ui_primitives import column
        col = column(["a", "b", "c"])
        assert col.type == "Column"
        assert col.children == ["a", "b", "c"]

    def test_row_builder(self):
        from shared.a2ui_primitives import row
        r = row(["x", "y"], justify="center")
        assert r.type == "Row"
        assert r.properties["mainAxisAlignment"] == "center"

    def test_metric_card_builder(self):
        from shared.a2ui_primitives import metric_card
        m = metric_card("CPU", "45%", subtitle="Average", progress=0.45)
        assert m.type == "x-astral-metric-card"
        assert m.properties["value"] == "45%"
        assert m.properties["progress"] == 0.45

    def test_bar_chart_builder(self):
        from shared.a2ui_primitives import bar_chart
        bc = bar_chart("Sales", ["Q1", "Q2"], [{"label": "Revenue", "data": [100, 200]}])
        assert bc.type == "x-astral-bar-chart"
        assert bc.properties["title"] == "Sales"

    def test_alert_builder(self):
        from shared.a2ui_primitives import alert
        a = alert("Something failed", variant="error", title="Error")
        assert a.type == "x-astral-alert"
        assert a.properties["variant"] == "error"
        assert a.properties["title"] == "Error"

    def test_code_block_builder(self):
        from shared.a2ui_primitives import code_block
        cb = code_block("print('hi')", language="python", show_line_numbers=True)
        assert cb.type == "x-astral-code"
        assert cb.properties["showLineNumbers"] is True

    def test_file_upload_builder(self):
        from shared.a2ui_primitives import file_upload
        fu = file_upload(label="Upload CSV", accept=".csv", action="process_csv")
        assert fu.type == "x-astral-file-upload"
        assert fu.properties["accept"] == ".csv"

    def test_file_download_builder(self):
        from shared.a2ui_primitives import file_download
        fd = file_download("/api/export", label="Export", filename="report.csv")
        assert fd.type == "x-astral-file-download"
        assert fd.properties["filename"] == "report.csv"


class TestFlattenTree:
    """Tests for legacy-to-A2UI migration bridge."""

    def test_single_text(self):
        from shared.a2ui_primitives import flatten_tree
        legacy = [{"type": "text", "content": "Hello", "variant": "body"}]
        flat, root_id = flatten_tree(legacy)
        assert len(flat) == 1
        assert flat[0].type == "Text"
        assert flat[0].properties["text"] == "Hello"
        assert flat[0].id == root_id

    def test_card_with_children(self):
        from shared.a2ui_primitives import flatten_tree
        legacy = [{
            "type": "card",
            "title": "Results",
            "content": [
                {"type": "text", "content": "Line 1", "variant": "body"},
                {"type": "text", "content": "Line 2", "variant": "h2"},
            ],
        }]
        flat, root_id = flatten_tree(legacy)
        assert len(flat) == 3  # card + 2 text
        root = next(c for c in flat if c.id == root_id)
        assert root.type == "Card"
        assert len(root.children) == 2

    def test_nested_container(self):
        from shared.a2ui_primitives import flatten_tree
        legacy = [{
            "type": "container",
            "children": [
                {"type": "text", "content": "A"},
                {"type": "container", "children": [
                    {"type": "text", "content": "B"},
                ]},
            ],
        }]
        flat, root_id = flatten_tree(legacy)
        # root container + text A + inner container + text B = 4
        assert len(flat) == 4
        root = next(c for c in flat if c.id == root_id)
        assert root.type == "Column"
        assert len(root.children) == 2

    def test_multiple_roots_wrapped_in_column(self):
        from shared.a2ui_primitives import flatten_tree
        legacy = [
            {"type": "text", "content": "A"},
            {"type": "text", "content": "B"},
        ]
        flat, root_id = flatten_tree(legacy)
        # 2 text + 1 wrapper column = 3
        assert len(flat) == 3
        root = next(c for c in flat if c.id == root_id)
        assert root.type == "Column"
        assert len(root.children) == 2

    def test_button_action_mapping(self):
        from shared.a2ui_primitives import flatten_tree
        legacy = [{
            "type": "button",
            "label": "Click me",
            "action": "chat_message",
            "payload": {"message": "hello"},
            "variant": "primary",
        }]
        flat, root_id = flatten_tree(legacy)
        btn = flat[0]
        assert btn.type == "Button"
        assert btn.properties["text"] == "Click me"
        assert btn.properties["action"]["event"]["name"] == "chat_message"

    def test_collapsible_mapped_to_card(self):
        from shared.a2ui_primitives import flatten_tree
        legacy = [{
            "type": "collapsible",
            "title": "Details",
            "default_open": True,
            "content": [{"type": "text", "content": "Hidden"}],
        }]
        flat, root_id = flatten_tree(legacy)
        root = next(c for c in flat if c.id == root_id)
        assert root.type == "Card"
        assert root.properties["isCollapsible"] is True
        assert root.properties["defaultOpen"] is True

    def test_table_mapped_to_custom(self):
        from shared.a2ui_primitives import flatten_tree
        legacy = [{
            "type": "table",
            "headers": ["A", "B"],
            "rows": [[1, 2]],
            "total_rows": 100,
            "source_tool": "get_data",
        }]
        flat, root_id = flatten_tree(legacy)
        t = flat[0]
        assert t.type == "x-astral-table"
        assert t.properties["headers"] == ["A", "B"]
        assert t.properties["total_rows"] == 100

    def test_tabs_mapping(self):
        from shared.a2ui_primitives import flatten_tree
        legacy = [{
            "type": "tabs",
            "tabs": [
                {"label": "Tab 1", "content": [{"type": "text", "content": "A"}]},
                {"label": "Tab 2", "content": [{"type": "text", "content": "B"}]},
            ],
        }]
        flat, root_id = flatten_tree(legacy)
        root = next(c for c in flat if c.id == root_id)
        assert root.type == "Tabs"
        assert len(root.children) == 2
        # Tabs should have tab items in properties
        assert len(root.properties["tabs"]) == 2
        assert root.properties["tabs"][0]["label"] == "Tab 1"

    def test_preserves_existing_ids(self):
        from shared.a2ui_primitives import flatten_tree
        legacy = [{"type": "text", "id": "my-id", "content": "Hi"}]
        flat, root_id = flatten_tree(legacy)
        assert flat[0].id == "my-id"
        assert root_id == "my-id"


class TestCreateA2UIResponse:
    """Tests for the agent response helper."""

    def test_basic_response(self):
        from shared.a2ui_primitives import text, create_a2ui_response
        t = text("Hello")
        resp = create_a2ui_response([t])
        assert "_a2ui_components" in resp
        assert "_a2ui_root_id" in resp
        assert resp["_a2ui_root_id"] == t.id
        assert len(resp["_a2ui_components"]) == 1

    def test_empty_response(self):
        from shared.a2ui_primitives import create_a2ui_response
        resp = create_a2ui_response([])
        assert resp["_a2ui_components"] == []
        assert resp["_a2ui_root_id"] == ""

    def test_explicit_root_id(self):
        from shared.a2ui_primitives import text, column, create_a2ui_response
        t1 = text("A")
        t2 = text("B")
        col = column([t1.id, t2.id])
        resp = create_a2ui_response([t1, t2, col], root_id=col.id)
        assert resp["_a2ui_root_id"] == col.id
