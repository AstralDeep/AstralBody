"""Tests for the A2UI high-level nested builder API."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.a2ui_builders import (
    Node, create_response,
    text, button, text_field, image, icon, divider,
    card, column, row, tabs, list_component, modal,
    slider, choice_picker, datetime_input, checkbox, video, audio_player,
    table, metric_card, code_block, alert, progress_bar,
    bar_chart, line_chart, pie_chart, plotly_chart,
    color_picker, file_upload, file_download,
)
from shared.a2ui_primitives import A2UIComponent


# ---------------------------------------------------------------------------
# Node basics
# ---------------------------------------------------------------------------

def test_node_has_id():
    n = text("hello")
    assert isinstance(n, Node)
    assert isinstance(n.id, str)
    assert len(n.id) == 8


def test_node_flatten_single():
    n = text("hello")
    flat, root_id = n.flatten()
    assert root_id == n.id
    assert len(flat) == 1
    assert isinstance(flat[0], A2UIComponent)
    assert flat[0].type == "Text"
    assert flat[0].properties["text"] == "hello"


def test_node_flatten_nested():
    child1 = text("a")
    child2 = text("b")
    parent = column([child1, child2])
    flat, root_id = parent.flatten()
    assert root_id == parent.id
    assert len(flat) == 3  # child1, child2, parent
    # Parent should reference children by ID
    parent_comp = [c for c in flat if c.id == parent.id][0]
    assert child1.id in parent_comp.children
    assert child2.id in parent_comp.children


def test_node_flatten_deep():
    leaf = text("leaf")
    mid = card("mid", [leaf])
    root = column([mid])
    flat, root_id = root.flatten()
    assert len(flat) == 3
    assert root_id == root.id


# ---------------------------------------------------------------------------
# create_response
# ---------------------------------------------------------------------------

def test_create_response_single_node():
    n = alert("test", variant="warning")
    resp = create_response(n)
    assert "_a2ui_components" in resp
    assert "_a2ui_root_id" in resp
    assert resp["_a2ui_root_id"] != ""
    assert len(resp["_a2ui_components"]) == 1
    assert resp["_a2ui_components"][0]["type"] == "x-astral-alert"


def test_create_response_with_data():
    n = text("hi")
    resp = create_response(n, data={"key": "value"})
    assert resp["_data"] == {"key": "value"}


def test_create_response_list_of_nodes():
    nodes = [text("a"), text("b")]
    resp = create_response(nodes)
    # Should auto-wrap in Column
    assert resp["_a2ui_root_id"] != ""
    comps = resp["_a2ui_components"]
    types = {c["type"] for c in comps}
    assert "Column" in types
    assert "Text" in types
    assert len(comps) == 3  # 2 texts + 1 column


def test_create_response_single_list():
    resp = create_response([text("only")])
    assert len(resp["_a2ui_components"]) == 1


def test_create_response_empty_list():
    resp = create_response([])
    assert resp["_a2ui_components"] == []
    assert resp["_a2ui_root_id"] == ""


# ---------------------------------------------------------------------------
# Standard component builders
# ---------------------------------------------------------------------------

def test_text_builder():
    n = text("hello", variant="h1")
    assert n.component.type == "Text"
    assert n.component.properties["text"] == "hello"
    assert n.component.properties["textStyle"] == "h1"


def test_text_markdown():
    n = text("# Title", markdown=True)
    assert n.component.properties["markdown"] is True


def test_button_builder():
    n = button("Click", action_name="do_thing", context={"id": 1}, variant="primary")
    assert n.component.type == "Button"
    assert n.component.properties["text"] == "Click"
    assert n.component.properties["action"]["event"]["name"] == "do_thing"
    assert n.component.properties["action"]["event"]["context"] == {"id": 1}


def test_text_field_builder():
    n = text_field(placeholder="Enter...", name="field1", value="hello")
    assert n.component.type == "TextField"
    assert n.component.properties["placeholder"] == "Enter..."


def test_image_builder():
    n = image("http://example.com/img.png", alt="test", width="100px")
    assert n.component.type == "Image"
    assert n.component.properties["url"] == "http://example.com/img.png"
    assert n.component.properties["width"] == "100px"


def test_divider_builder():
    n = divider()
    assert n.component.type == "Divider"


def test_icon_builder():
    n = icon("star")
    assert n.component.type == "Icon"
    assert n.component.properties["icon"] == "star"


# ---------------------------------------------------------------------------
# Layout containers
# ---------------------------------------------------------------------------

def test_card_builder():
    child = text("content")
    n = card("Title", [child])
    assert n.component.type == "Card"
    assert n.component.properties["title"] == "Title"
    assert len(n.child_nodes) == 1


def test_card_collapsible():
    n = card("Collapse Me", [], collapsible=True, default_open=False)
    assert n.component.properties["isCollapsible"] is True
    assert n.component.properties["defaultOpen"] is False


def test_column_builder():
    n = column([text("a"), text("b")])
    assert n.component.type == "Column"
    assert len(n.child_nodes) == 2


def test_row_builder():
    n = row([text("a"), text("b")])
    assert n.component.type == "Row"
    assert len(n.child_nodes) == 2


def test_tabs_builder():
    t = tabs(["Tab1", "Tab2"], [[text("c1")], [text("c2"), text("c3")]])
    assert t.component.type == "Tabs"
    assert len(t.child_nodes) == 3  # c1, c2, c3
    tab_items = t.component.properties["tabs"]
    assert len(tab_items) == 2
    assert tab_items[0]["label"] == "Tab1"


def test_list_component_builder():
    n = list_component([text("item1")], ordered=True)
    assert n.component.type == "List"
    assert n.component.properties["ordered"] is True


def test_modal_builder():
    trigger = button("Open")
    content = [text("Modal content")]
    n = modal("Dialog", trigger, content)
    assert n.component.type == "Modal"
    assert n.component.properties["triggerId"] == trigger.id
    assert len(n.child_nodes) == 2  # trigger + 1 content


# ---------------------------------------------------------------------------
# New interactive components (A2UI-only)
# ---------------------------------------------------------------------------

def test_slider_builder():
    n = slider(0, 100, 50, step=5, name="vol", label="Volume")
    assert n.component.type == "Slider"
    assert n.component.properties["min"] == 0
    assert n.component.properties["max"] == 100
    assert n.component.properties["step"] == 5


def test_choice_picker_string_options():
    n = choice_picker(["A", "B", "C"], label="Pick one")
    assert n.component.type == "ChoicePicker"
    opts = n.component.properties["options"]
    assert len(opts) == 3
    assert opts[0] == {"label": "A", "value": "A"}


def test_choice_picker_dict_options():
    n = choice_picker([{"label": "Opt1", "value": "1"}])
    opts = n.component.properties["options"]
    assert opts[0] == {"label": "Opt1", "value": "1"}


def test_datetime_input_builder():
    n = datetime_input(mode="dateTime", value="2026-01-01T12:00", label="Start")
    assert n.component.type == "DateTimeInput"
    assert n.component.properties["mode"] == "dateTime"


def test_checkbox_builder():
    n = checkbox("Accept terms", checked=True, name="tos")
    assert n.component.type == "CheckBox"
    assert n.component.properties["checked"] is True
    assert n.component.properties["label"] == "Accept terms"


def test_video_builder():
    n = video("http://example.com/vid.mp4", autoplay=True)
    assert n.component.type == "Video"
    assert n.component.properties["autoplay"] is True


def test_audio_player_builder():
    n = audio_player("http://example.com/audio.mp3", description="Podcast")
    assert n.component.type == "AudioPlayer"
    assert n.component.properties["description"] == "Podcast"


# ---------------------------------------------------------------------------
# Custom extension builders (x-astral-*)
# ---------------------------------------------------------------------------

def test_table_builder():
    n = table(["Name", "Age"], [["Alice", "30"]], page_size=25, total_rows=100)
    assert n.component.type == "x-astral-table"
    assert n.component.properties["headers"] == ["Name", "Age"]
    assert n.component.properties["pageSize"] == 25
    assert n.component.properties["totalRows"] == 100


def test_metric_card_builder():
    n = metric_card("CPU", "85%", subtitle="High load", progress=0.85)
    assert n.component.type == "x-astral-metric-card"
    assert n.component.properties["value"] == "85%"
    assert n.component.properties["progress"] == 0.85


def test_code_block_builder():
    n = code_block("print('hi')", language="python", show_line_numbers=True)
    assert n.component.type == "x-astral-code"
    assert n.component.properties["showLineNumbers"] is True


def test_alert_builder():
    n = alert("Error occurred", variant="error", title="Oops")
    assert n.component.type == "x-astral-alert"
    assert n.component.properties["variant"] == "error"
    assert n.component.properties["title"] == "Oops"


def test_progress_bar_builder():
    n = progress_bar(0.75, label="Upload")
    assert n.component.type == "x-astral-progress-bar"
    assert n.component.properties["value"] == 0.75


def test_bar_chart_builder():
    ds = [{"label": "Sales", "data": [10, 20, 30]}]
    n = bar_chart("Revenue", ["Q1", "Q2", "Q3"], ds)
    assert n.component.type == "x-astral-bar-chart"


def test_pie_chart_builder():
    n = pie_chart("Distribution", ["A", "B"], [60.0, 40.0], colors=["#f00", "#0f0"])
    assert n.component.type == "x-astral-pie-chart"
    assert n.component.properties["colors"] == ["#f00", "#0f0"]


def test_plotly_chart_builder():
    n = plotly_chart("Custom", [{"x": [1], "y": [2], "type": "scatter"}])
    assert n.component.type == "x-astral-plotly-chart"


def test_color_picker_builder():
    n = color_picker("Background", "bg_color", value="#ffffff")
    assert n.component.type == "x-astral-color-picker"


def test_file_upload_builder():
    n = file_upload(label="Upload CSV", accept=".csv")
    assert n.component.type == "x-astral-file-upload"


def test_file_download_builder():
    n = file_download("http://example.com/file.csv", label="Get CSV", filename="data.csv")
    assert n.component.type == "x-astral-file-download"
    assert n.component.properties["filename"] == "data.csv"


# ---------------------------------------------------------------------------
# Integration: full nested tree → create_response
# ---------------------------------------------------------------------------

def test_full_nested_tree():
    """End-to-end: build a realistic nested UI and verify serialization."""
    ui = card("Dashboard", [
        row([
            metric_card("Users", "1,234"),
            metric_card("Revenue", "$56K", progress=0.72),
        ]),
        table(["Name", "Status"], [["API", "OK"], ["DB", "Slow"]]),
        alert("System healthy", variant="success"),
    ])

    resp = create_response(ui, data={"summary": "all good"})

    assert resp["_data"] == {"summary": "all good"}
    comps = resp["_a2ui_components"]
    types = [c["type"] for c in comps]

    assert "Card" in types
    assert "Row" in types
    assert "x-astral-metric-card" in types
    assert "x-astral-table" in types
    assert "x-astral-alert" in types

    # Root should be the Card
    root = [c for c in comps if c["id"] == resp["_a2ui_root_id"]][0]
    assert root["type"] == "Card"
    assert len(root["children"]) == 3  # row, table, alert


def test_extra_kwargs_passed_through():
    """Verify **extra kwargs are preserved in component properties."""
    n = text("hi", custom_prop="custom_value")
    assert n.component.properties["custom_prop"] == "custom_value"
