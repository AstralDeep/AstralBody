"""
A2UI Builders — High-level nested API for constructing A2UI components.

Agents write code using nested trees (intuitive) and this module auto-flattens
to the A2UI flat adjacency-list model for wire transport.

Usage::

    from shared.a2ui_builders import card, metric_card, alert, row, table, create_response

    ui = card("Weather", [
        row([metric_card("Temperature", "72°F"), metric_card("Humidity", "45%")]),
        alert("UV Index is high", variant="warning"),
        table(["Time", "Temp"], [["12pm", "72°F"], ["3pm", "75°F"]]),
    ])
    return create_response(ui, data=weather_data)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from shared.a2ui_primitives import (
    A2UIComponent,
    _gen_id,
    TEXT_STYLE_MAP,
)


# ---------------------------------------------------------------------------
# Node — tree wrapper that auto-flattens to A2UIComponent list
# ---------------------------------------------------------------------------

class Node:
    """Wraps an A2UIComponent with nested child Nodes for ergonomic tree construction."""

    __slots__ = ("component", "child_nodes")

    def __init__(self, component: A2UIComponent, children: Optional[List["Node"]] = None):
        self.component = component
        self.child_nodes: List[Node] = children or []

    @property
    def id(self) -> str:
        return self.component.id

    def flatten(self) -> tuple[List[A2UIComponent], str]:
        """Depth-first walk → flat list of A2UIComponents with wired children IDs."""
        flat: List[A2UIComponent] = []
        self._collect(flat)
        return flat, self.component.id

    def _collect(self, flat: List[A2UIComponent]) -> None:
        # Wire children IDs from child nodes
        self.component.children = [child.id for child in self.child_nodes]
        # Recurse depth-first (children before parent for consistent ordering)
        for child in self.child_nodes:
            child._collect(flat)
        flat.append(self.component)


# ---------------------------------------------------------------------------
# create_response — the single entry point agents call to return A2UI
# ---------------------------------------------------------------------------

def create_response(
    node: Node | List[Node],
    *,
    data: Any = None,
) -> Dict[str, Any]:
    """
    Build an MCP tool response with A2UI components.

    Accepts a single Node (used as root) or a list of Nodes (auto-wrapped in Column).
    """
    if isinstance(node, list):
        if len(node) == 0:
            return {"_a2ui_components": [], "_a2ui_root_id": "", "_data": data}
        if len(node) == 1:
            node = node[0]
        else:
            node = column(node)

    flat, root_id = node.flatten()
    return {
        "_a2ui_components": [c.to_dict() for c in flat],
        "_a2ui_root_id": root_id,
        "_data": data,
    }


# ---------------------------------------------------------------------------
# Standard component builders (A2UI spec v0.10)
# ---------------------------------------------------------------------------

def text(content: str, *, variant: str = "body", markdown: bool = False,
         id: Optional[str] = None, **extra: Any) -> Node:
    props: Dict[str, Any] = {"text": content}
    props["textStyle"] = TEXT_STYLE_MAP.get(variant, "body")
    if variant == "markdown" or markdown:
        props["markdown"] = True
    props.update(extra)
    return Node(A2UIComponent(id=id or _gen_id(), type="Text", properties=props))


def button(label: str, *, action_name: str = "", context: Optional[Dict[str, Any]] = None,
           variant: str = "default", id: Optional[str] = None, **extra: Any) -> Node:
    props: Dict[str, Any] = {"text": label, "variant": variant}
    if action_name:
        props["action"] = {"event": {"name": action_name, "context": context or {}}}
    props.update(extra)
    return Node(A2UIComponent(id=id or _gen_id(), type="Button", properties=props))


def text_field(*, placeholder: str = "", name: str = "", value: str = "",
               input_type: str = "shortText",
               id: Optional[str] = None, **extra: Any) -> Node:
    props: Dict[str, Any] = {
        "placeholder": placeholder, "name": name, "value": value, "type": input_type,
    }
    props.update(extra)
    return Node(A2UIComponent(id=id or _gen_id(), type="TextField", properties=props))


def image(url: str, *, alt: str = "", width: Optional[str] = None,
          height: Optional[str] = None, fit: str = "contain",
          id: Optional[str] = None, **extra: Any) -> Node:
    props: Dict[str, Any] = {"url": url, "alt": alt, "fit": fit}
    if width:
        props["width"] = width
    if height:
        props["height"] = height
    props.update(extra)
    return Node(A2UIComponent(id=id or _gen_id(), type="Image", properties=props))


def icon(name: str, *, id: Optional[str] = None, **extra: Any) -> Node:
    props: Dict[str, Any] = {"icon": name}
    props.update(extra)
    return Node(A2UIComponent(id=id or _gen_id(), type="Icon", properties=props))


def divider(*, variant: str = "horizontal", id: Optional[str] = None) -> Node:
    return Node(A2UIComponent(id=id or _gen_id(), type="Divider",
                               properties={"variant": variant}))


# --- Layout containers ---

def card(title: str, children: Optional[List[Node]] = None, *,
         collapsible: bool = False, default_open: bool = True,
         id: Optional[str] = None, **extra: Any) -> Node:
    props: Dict[str, Any] = {"title": title}
    if collapsible:
        props["isCollapsible"] = True
        props["defaultOpen"] = default_open
    props.update(extra)
    return Node(A2UIComponent(id=id or _gen_id(), type="Card", properties=props),
                children=children or [])


def column(children: Optional[List[Node]] = None, *,
           justify: str = "start", align: str = "stretch",
           id: Optional[str] = None, **extra: Any) -> Node:
    props: Dict[str, Any] = {"mainAxisAlignment": justify, "crossAxisAlignment": align}
    props.update(extra)
    return Node(A2UIComponent(id=id or _gen_id(), type="Column", properties=props),
                children=children or [])


def row(children: Optional[List[Node]] = None, *,
        justify: str = "start", align: str = "center",
        id: Optional[str] = None, **extra: Any) -> Node:
    props: Dict[str, Any] = {"mainAxisAlignment": justify, "crossAxisAlignment": align}
    props.update(extra)
    return Node(A2UIComponent(id=id or _gen_id(), type="Row", properties=props),
                children=children or [])


def tabs(tab_labels: List[str], tab_children: List[List[Node]], *,
         id: Optional[str] = None, **extra: Any) -> Node:
    """Create a Tabs node. Each tab has a label and a list of child Nodes."""
    all_child_nodes: List[Node] = []
    tab_items: List[Dict[str, Any]] = []
    for label, children in zip(tab_labels, tab_children):
        child_ids = [c.id for c in children]
        tab_items.append({"label": label, "children": child_ids})
        all_child_nodes.extend(children)
    props: Dict[str, Any] = {"tabs": tab_items}
    props.update(extra)
    return Node(A2UIComponent(id=id or _gen_id(), type="Tabs", properties=props),
                children=all_child_nodes)


def list_component(children: Optional[List[Node]] = None, *,
                   ordered: bool = False,
                   id: Optional[str] = None, **extra: Any) -> Node:
    props: Dict[str, Any] = {"ordered": ordered}
    props.update(extra)
    return Node(A2UIComponent(id=id or _gen_id(), type="List", properties=props),
                children=children or [])


def modal(title: str, trigger: Node, content: List[Node], *,
          id: Optional[str] = None, **extra: Any) -> Node:
    """Modal overlay. trigger is the Node that opens it; content is shown inside."""
    props: Dict[str, Any] = {"title": title, "triggerId": trigger.id}
    props.update(extra)
    return Node(A2UIComponent(id=id or _gen_id(), type="Modal", properties=props),
                children=[trigger] + content)


# --- New interactive components (A2UI-only, no legacy equivalent) ---

def slider(min_val: float = 0, max_val: float = 100, value: float = 50, *,
           step: float = 1, name: str = "", label: str = "",
           action_name: str = "",
           id: Optional[str] = None, **extra: Any) -> Node:
    props: Dict[str, Any] = {
        "min": min_val, "max": max_val, "value": value, "step": step,
    }
    if name:
        props["name"] = name
    if label:
        props["label"] = label
    if action_name:
        props["action"] = {"event": {"name": action_name}}
    props.update(extra)
    return Node(A2UIComponent(id=id or _gen_id(), type="Slider", properties=props))


def choice_picker(options: List[str | Dict[str, Any]], *,
                  max_selections: int = 1,
                  selected: Optional[List[str]] = None,
                  name: str = "", label: str = "",
                  action_name: str = "",
                  id: Optional[str] = None, **extra: Any) -> Node:
    # Normalize options to [{label, value}] format
    normalized = []
    for opt in options:
        if isinstance(opt, str):
            normalized.append({"label": opt, "value": opt})
        else:
            normalized.append(opt)
    props: Dict[str, Any] = {
        "options": normalized,
        "maxSelections": max_selections,
    }
    if selected:
        props["selected"] = selected
    if name:
        props["name"] = name
    if label:
        props["label"] = label
    if action_name:
        props["action"] = {"event": {"name": action_name}}
    props.update(extra)
    return Node(A2UIComponent(id=id or _gen_id(), type="ChoicePicker", properties=props))


def datetime_input(*, mode: str = "date", value: str = "", name: str = "",
                   label: str = "",
                   id: Optional[str] = None, **extra: Any) -> Node:
    props: Dict[str, Any] = {"mode": mode, "value": value}
    if name:
        props["name"] = name
    if label:
        props["label"] = label
    props.update(extra)
    return Node(A2UIComponent(id=id or _gen_id(), type="DateTimeInput", properties=props))


def checkbox(label: str, *, checked: bool = False, name: str = "",
             action_name: str = "",
             id: Optional[str] = None, **extra: Any) -> Node:
    props: Dict[str, Any] = {"label": label, "checked": checked}
    if name:
        props["name"] = name
    if action_name:
        props["action"] = {"event": {"name": action_name}}
    props.update(extra)
    return Node(A2UIComponent(id=id or _gen_id(), type="CheckBox", properties=props))


def video(url: str, *, autoplay: bool = False,
          id: Optional[str] = None, **extra: Any) -> Node:
    props: Dict[str, Any] = {"url": url, "autoplay": autoplay}
    props.update(extra)
    return Node(A2UIComponent(id=id or _gen_id(), type="Video", properties=props))


def audio_player(url: str, *, description: str = "",
                 id: Optional[str] = None, **extra: Any) -> Node:
    props: Dict[str, Any] = {"url": url}
    if description:
        props["description"] = description
    props.update(extra)
    return Node(A2UIComponent(id=id or _gen_id(), type="AudioPlayer", properties=props))


# --- Custom extension builders (x-astral-*) ---

def table(headers: List[str], rows: List[List[Any]], *,
          total_rows: Optional[int] = None, page_size: Optional[int] = None,
          page_offset: Optional[int] = None, page_sizes: Optional[List[int]] = None,
          source_tool: Optional[str] = None, source_agent: Optional[str] = None,
          source_params: Optional[Dict[str, Any]] = None,
          id: Optional[str] = None, **extra: Any) -> Node:
    props: Dict[str, Any] = {"headers": headers, "rows": rows}
    if total_rows is not None:
        props["totalRows"] = total_rows
    if page_size is not None:
        props["pageSize"] = page_size
    if page_offset is not None:
        props["pageOffset"] = page_offset
    if page_sizes:
        props["pageSizes"] = page_sizes
    if source_tool:
        props["sourceTool"] = source_tool
    if source_agent:
        props["sourceAgent"] = source_agent
    if source_params:
        props["sourceParams"] = source_params
    props.update(extra)
    return Node(A2UIComponent(id=id or _gen_id(), type="x-astral-table", properties=props))


def metric_card(title: str, value: str, *, subtitle: Optional[str] = None,
                icon_name: Optional[str] = None, progress: Optional[float] = None,
                id: Optional[str] = None, **extra: Any) -> Node:
    props: Dict[str, Any] = {"title": title, "value": value}
    if subtitle:
        props["subtitle"] = subtitle
    if icon_name:
        props["icon"] = icon_name
    if progress is not None:
        props["progress"] = progress
    props.update(extra)
    return Node(A2UIComponent(id=id or _gen_id(), type="x-astral-metric-card", properties=props))


def code_block(code: str, *, language: str = "text", show_line_numbers: bool = False,
               id: Optional[str] = None, **extra: Any) -> Node:
    props: Dict[str, Any] = {"code": code, "language": language,
                              "showLineNumbers": show_line_numbers}
    props.update(extra)
    return Node(A2UIComponent(id=id or _gen_id(), type="x-astral-code", properties=props))


def alert(message: str, *, variant: str = "info", title: Optional[str] = None,
          id: Optional[str] = None, **extra: Any) -> Node:
    props: Dict[str, Any] = {"message": message, "variant": variant}
    if title:
        props["title"] = title
    props.update(extra)
    return Node(A2UIComponent(id=id or _gen_id(), type="x-astral-alert", properties=props))


def progress_bar(value: float, *, label: Optional[str] = None,
                 show_percentage: bool = True,
                 id: Optional[str] = None, **extra: Any) -> Node:
    props: Dict[str, Any] = {"value": value, "showPercentage": show_percentage}
    if label:
        props["label"] = label
    props.update(extra)
    return Node(A2UIComponent(id=id or _gen_id(), type="x-astral-progress-bar", properties=props))


def bar_chart(title: str, labels: List[str], datasets: List[Dict[str, Any]], *,
              id: Optional[str] = None, **extra: Any) -> Node:
    props: Dict[str, Any] = {"title": title, "labels": labels, "datasets": datasets}
    props.update(extra)
    return Node(A2UIComponent(id=id or _gen_id(), type="x-astral-bar-chart", properties=props))


def line_chart(title: str, labels: List[str], datasets: List[Dict[str, Any]], *,
               id: Optional[str] = None, **extra: Any) -> Node:
    props: Dict[str, Any] = {"title": title, "labels": labels, "datasets": datasets}
    props.update(extra)
    return Node(A2UIComponent(id=id or _gen_id(), type="x-astral-line-chart", properties=props))


def pie_chart(title: str, labels: List[str], data: List[float], *,
              colors: Optional[List[str]] = None,
              id: Optional[str] = None, **extra: Any) -> Node:
    props: Dict[str, Any] = {"title": title, "labels": labels, "data": data}
    if colors:
        props["colors"] = colors
    props.update(extra)
    return Node(A2UIComponent(id=id or _gen_id(), type="x-astral-pie-chart", properties=props))


def plotly_chart(title: str, data: List[Dict[str, Any]], *,
                 layout: Optional[Dict[str, Any]] = None,
                 config: Optional[Dict[str, Any]] = None,
                 id: Optional[str] = None, **extra: Any) -> Node:
    props: Dict[str, Any] = {"title": title, "data": data}
    if layout:
        props["layout"] = layout
    if config:
        props["config"] = config
    props.update(extra)
    return Node(A2UIComponent(id=id or _gen_id(), type="x-astral-plotly-chart", properties=props))


def color_picker(label: str, color_key: str, *, value: str = "#000000",
                 id: Optional[str] = None, **extra: Any) -> Node:
    props: Dict[str, Any] = {"label": label, "colorKey": color_key, "value": value}
    props.update(extra)
    return Node(A2UIComponent(id=id or _gen_id(), type="x-astral-color-picker", properties=props))


def file_upload(*, label: str = "Upload File", accept: str = "*/*",
                action: str = "", id: Optional[str] = None, **extra: Any) -> Node:
    props: Dict[str, Any] = {"label": label, "accept": accept, "action": action}
    props.update(extra)
    return Node(A2UIComponent(id=id or _gen_id(), type="x-astral-file-upload", properties=props))


def file_download(url: str, *, label: str = "Download File",
                  filename: Optional[str] = None,
                  id: Optional[str] = None, **extra: Any) -> Node:
    props: Dict[str, Any] = {"label": label, "url": url}
    if filename:
        props["filename"] = filename
    props.update(extra)
    return Node(A2UIComponent(id=id or _gen_id(), type="x-astral-file-download", properties=props))
