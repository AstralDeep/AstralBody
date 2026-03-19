"""
A2UI Primitives — A2UI-spec (v0.10) component library.

Components use a flat adjacency-list model: each component has a unique ID
and references children by ID rather than nesting objects. This module also
provides a migration bridge (flatten_tree) to convert legacy nested primitives
into the flat A2UI format.

Custom extensions use the ``x-astral-`` prefix to avoid collisions with
future A2UI standard types.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Type mapping: legacy AstralBody type → A2UI type
# ---------------------------------------------------------------------------

LEGACY_TYPE_MAP: Dict[str, str] = {
    "container":    "Column",
    "text":         "Text",
    "button":       "Button",
    "card":         "Card",
    "grid":         "Row",
    "list":         "List",
    "divider":      "Divider",
    "image":        "Image",
    "tabs":         "Tabs",
    "input":        "TextField",
    "collapsible":  "Card",
    # Custom extensions (no A2UI equivalent)
    "table":        "x-astral-table",
    "metric":       "x-astral-metric-card",
    "code":         "x-astral-code",
    "alert":        "x-astral-alert",
    "progress":     "x-astral-progress-bar",
    "bar_chart":    "x-astral-bar-chart",
    "line_chart":   "x-astral-line-chart",
    "pie_chart":    "x-astral-pie-chart",
    "plotly_chart": "x-astral-plotly-chart",
    "color_picker": "x-astral-color-picker",
    "file_upload":  "x-astral-file-upload",
    "file_download":"x-astral-file-download",
}

# Variant mapping: legacy text variants → A2UI textStyle
TEXT_STYLE_MAP: Dict[str, str] = {
    "h1":       "h1",
    "h2":       "h2",
    "h3":       "h3",
    "body":     "body",
    "caption":  "caption",
    "markdown": "body",  # markdown flag handled separately
}


# ---------------------------------------------------------------------------
# A2UI Component dataclass
# ---------------------------------------------------------------------------

def _gen_id() -> str:
    return str(uuid.uuid4())[:8]


@dataclass
class A2UIComponent:
    """A single A2UI component in the flat adjacency list."""

    id: str
    type: str
    properties: Dict[str, Any] = field(default_factory=dict)
    children: List[str] = field(default_factory=list)  # child component IDs
    accessibility: Optional[Dict[str, str]] = None
    data_binding: Optional[Dict[str, str]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to A2UI wire format."""
        d: Dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "properties": self.properties,
        }
        if self.children:
            d["children"] = self.children
        if self.accessibility:
            d["accessibility"] = self.accessibility
        if self.data_binding:
            d["dataBinding"] = self.data_binding
        return d


# ---------------------------------------------------------------------------
# Builder helpers — convenient constructors for agents
# ---------------------------------------------------------------------------

def text(content: str, *, variant: str = "body", id: Optional[str] = None,
         markdown: bool = False, **extra: Any) -> A2UIComponent:
    props: Dict[str, Any] = {"text": content}
    text_style = TEXT_STYLE_MAP.get(variant, "body")
    props["textStyle"] = text_style
    if variant == "markdown" or markdown:
        props["markdown"] = True
    props.update(extra)
    return A2UIComponent(id=id or _gen_id(), type="Text", properties=props)


def button(label: str, *, action_name: str = "", context: Optional[Dict[str, Any]] = None,
           variant: str = "default", id: Optional[str] = None, **extra: Any) -> A2UIComponent:
    props: Dict[str, Any] = {"text": label, "variant": variant}
    if action_name:
        props["action"] = {
            "event": {"name": action_name, "context": context or {}}
        }
    props.update(extra)
    return A2UIComponent(id=id or _gen_id(), type="Button", properties=props)


def text_field(*, placeholder: str = "", name: str = "", value: str = "",
               id: Optional[str] = None, **extra: Any) -> A2UIComponent:
    props: Dict[str, Any] = {"placeholder": placeholder, "name": name, "value": value}
    props.update(extra)
    return A2UIComponent(id=id or _gen_id(), type="TextField", properties=props)


def image(url: str, *, alt: str = "", width: Optional[str] = None,
          height: Optional[str] = None, id: Optional[str] = None, **extra: Any) -> A2UIComponent:
    props: Dict[str, Any] = {"url": url, "alt": alt}
    if width:
        props["width"] = width
    if height:
        props["height"] = height
    props.update(extra)
    return A2UIComponent(id=id or _gen_id(), type="Image", properties=props)


def divider(*, variant: str = "horizontal", id: Optional[str] = None) -> A2UIComponent:
    return A2UIComponent(id=id or _gen_id(), type="Divider",
                         properties={"variant": variant})


def icon(name: str, *, id: Optional[str] = None, **extra: Any) -> A2UIComponent:
    props: Dict[str, Any] = {"icon": name}
    props.update(extra)
    return A2UIComponent(id=id or _gen_id(), type="Icon", properties=props)


def card(title: str, child_ids: List[str], *, id: Optional[str] = None,
         collapsible: bool = False, default_open: bool = True, **extra: Any) -> A2UIComponent:
    props: Dict[str, Any] = {"title": title}
    if collapsible:
        props["isCollapsible"] = True
        props["defaultOpen"] = default_open
    props.update(extra)
    return A2UIComponent(id=id or _gen_id(), type="Card",
                         properties=props, children=child_ids)


def column(child_ids: List[str], *, id: Optional[str] = None,
           justify: str = "start", align: str = "stretch", **extra: Any) -> A2UIComponent:
    props: Dict[str, Any] = {"mainAxisAlignment": justify, "crossAxisAlignment": align}
    props.update(extra)
    return A2UIComponent(id=id or _gen_id(), type="Column",
                         properties=props, children=child_ids)


def row(child_ids: List[str], *, id: Optional[str] = None,
        justify: str = "start", align: str = "center", **extra: Any) -> A2UIComponent:
    props: Dict[str, Any] = {"mainAxisAlignment": justify, "crossAxisAlignment": align}
    props.update(extra)
    return A2UIComponent(id=id or _gen_id(), type="Row",
                         properties=props, children=child_ids)


def tabs(tab_labels: List[str], tab_child_ids: List[List[str]], *,
         id: Optional[str] = None, **extra: Any) -> A2UIComponent:
    tab_items = []
    for label, children in zip(tab_labels, tab_child_ids):
        tab_items.append({"label": label, "children": children})
    props: Dict[str, Any] = {"tabs": tab_items}
    props.update(extra)
    # Flatten all children from all tabs for the adjacency list
    all_children = [cid for group in tab_child_ids for cid in group]
    return A2UIComponent(id=id or _gen_id(), type="Tabs",
                         properties=props, children=all_children)


def list_component(child_ids: List[str], *, ordered: bool = False,
                   id: Optional[str] = None, **extra: Any) -> A2UIComponent:
    props: Dict[str, Any] = {"ordered": ordered}
    props.update(extra)
    return A2UIComponent(id=id or _gen_id(), type="List",
                         properties=props, children=child_ids)


def modal(trigger_id: str, content_ids: List[str], *, title: str = "",
          id: Optional[str] = None, **extra: Any) -> A2UIComponent:
    props: Dict[str, Any] = {"title": title, "triggerId": trigger_id}
    props.update(extra)
    return A2UIComponent(id=id or _gen_id(), type="Modal",
                         properties=props, children=content_ids)


# --- Custom extension builders (x-astral-*) ---

def table(headers: List[str], rows: List[List[Any]], *,
          total_rows: Optional[int] = None, page_size: Optional[int] = None,
          page_offset: Optional[int] = None, page_sizes: Optional[List[int]] = None,
          source_tool: Optional[str] = None, source_agent: Optional[str] = None,
          source_params: Optional[Dict[str, Any]] = None,
          id: Optional[str] = None, **extra: Any) -> A2UIComponent:
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
    return A2UIComponent(id=id or _gen_id(), type="x-astral-table", properties=props)


def metric_card(title: str, value: str, *, subtitle: Optional[str] = None,
                icon_name: Optional[str] = None, progress: Optional[float] = None,
                id: Optional[str] = None, **extra: Any) -> A2UIComponent:
    props: Dict[str, Any] = {"title": title, "value": value}
    if subtitle:
        props["subtitle"] = subtitle
    if icon_name:
        props["icon"] = icon_name
    if progress is not None:
        props["progress"] = progress
    props.update(extra)
    return A2UIComponent(id=id or _gen_id(), type="x-astral-metric-card", properties=props)


def code_block(code: str, *, language: str = "text", show_line_numbers: bool = False,
               id: Optional[str] = None, **extra: Any) -> A2UIComponent:
    props: Dict[str, Any] = {"code": code, "language": language,
                              "showLineNumbers": show_line_numbers}
    props.update(extra)
    return A2UIComponent(id=id or _gen_id(), type="x-astral-code", properties=props)


def alert(message: str, *, variant: str = "info", title: Optional[str] = None,
          id: Optional[str] = None, **extra: Any) -> A2UIComponent:
    props: Dict[str, Any] = {"message": message, "variant": variant}
    if title:
        props["title"] = title
    props.update(extra)
    return A2UIComponent(id=id or _gen_id(), type="x-astral-alert", properties=props)


def progress_bar(value: float, *, label: Optional[str] = None,
                 show_percentage: bool = True,
                 id: Optional[str] = None, **extra: Any) -> A2UIComponent:
    props: Dict[str, Any] = {"value": value, "showPercentage": show_percentage}
    if label:
        props["label"] = label
    props.update(extra)
    return A2UIComponent(id=id or _gen_id(), type="x-astral-progress-bar", properties=props)


def bar_chart(title: str, labels: List[str], datasets: List[Dict[str, Any]], *,
              id: Optional[str] = None, **extra: Any) -> A2UIComponent:
    props: Dict[str, Any] = {"title": title, "labels": labels, "datasets": datasets}
    props.update(extra)
    return A2UIComponent(id=id or _gen_id(), type="x-astral-bar-chart", properties=props)


def line_chart(title: str, labels: List[str], datasets: List[Dict[str, Any]], *,
               id: Optional[str] = None, **extra: Any) -> A2UIComponent:
    props: Dict[str, Any] = {"title": title, "labels": labels, "datasets": datasets}
    props.update(extra)
    return A2UIComponent(id=id or _gen_id(), type="x-astral-line-chart", properties=props)


def pie_chart(title: str, labels: List[str], data: List[float], *,
              colors: Optional[List[str]] = None,
              id: Optional[str] = None, **extra: Any) -> A2UIComponent:
    props: Dict[str, Any] = {"title": title, "labels": labels, "data": data}
    if colors:
        props["colors"] = colors
    props.update(extra)
    return A2UIComponent(id=id or _gen_id(), type="x-astral-pie-chart", properties=props)


def plotly_chart(title: str, data: List[Dict[str, Any]], *,
                 layout: Optional[Dict[str, Any]] = None,
                 config: Optional[Dict[str, Any]] = None,
                 id: Optional[str] = None, **extra: Any) -> A2UIComponent:
    props: Dict[str, Any] = {"title": title, "data": data}
    if layout:
        props["layout"] = layout
    if config:
        props["config"] = config
    props.update(extra)
    return A2UIComponent(id=id or _gen_id(), type="x-astral-plotly-chart", properties=props)


def color_picker(label: str, color_key: str, *, value: str = "#000000",
                 id: Optional[str] = None, **extra: Any) -> A2UIComponent:
    props: Dict[str, Any] = {"label": label, "colorKey": color_key, "value": value}
    props.update(extra)
    return A2UIComponent(id=id or _gen_id(), type="x-astral-color-picker", properties=props)


def file_upload(*, label: str = "Upload File", accept: str = "*/*",
                action: str = "", id: Optional[str] = None, **extra: Any) -> A2UIComponent:
    props: Dict[str, Any] = {"label": label, "accept": accept, "action": action}
    props.update(extra)
    return A2UIComponent(id=id or _gen_id(), type="x-astral-file-upload", properties=props)


def file_download(url: str, *, label: str = "Download File",
                  filename: Optional[str] = None,
                  id: Optional[str] = None, **extra: Any) -> A2UIComponent:
    props: Dict[str, Any] = {"label": label, "url": url}
    if filename:
        props["filename"] = filename
    props.update(extra)
    return A2UIComponent(id=id or _gen_id(), type="x-astral-file-download", properties=props)


# ---------------------------------------------------------------------------
# Migration bridge — flatten nested legacy trees to flat adjacency lists
# ---------------------------------------------------------------------------

# Fields that contain child components in legacy primitives
_CHILDREN_FIELDS = ("children", "content", "tabs")


def _map_legacy_properties(legacy_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract A2UI properties from a legacy component dict, excluding structural keys."""
    skip = {"type", "id", "style", "children", "content", "tabs", "variant"}
    props: Dict[str, Any] = {}

    if legacy_type == "text":
        props["text"] = data.get("content", "")
        variant = data.get("variant", "body")
        props["textStyle"] = TEXT_STYLE_MAP.get(variant, "body")
        if variant == "markdown":
            props["markdown"] = True
    elif legacy_type == "button":
        props["text"] = data.get("label", "")
        props["variant"] = data.get("variant", "default")
        action = data.get("action", "")
        if action:
            props["action"] = {
                "event": {
                    "name": action,
                    "context": data.get("payload", {}),
                }
            }
    elif legacy_type == "input":
        props["placeholder"] = data.get("placeholder", "")
        props["name"] = data.get("name", "")
        props["value"] = data.get("value", "")
    elif legacy_type == "card":
        props["title"] = data.get("title", "")
    elif legacy_type == "collapsible":
        props["title"] = data.get("title", "")
        props["isCollapsible"] = True
        props["defaultOpen"] = data.get("default_open", False)
    elif legacy_type == "grid":
        props["mainAxisAlignment"] = "start"
        props["crossAxisAlignment"] = "stretch"
        props["columns"] = data.get("columns", 2)
        props["gap"] = data.get("gap", 20)
    elif legacy_type == "image":
        props["url"] = data.get("url", "")
        props["alt"] = data.get("alt", "")
        if data.get("width"):
            props["width"] = data["width"]
        if data.get("height"):
            props["height"] = data["height"]
    elif legacy_type == "divider":
        props["variant"] = data.get("variant", "horizontal")
    elif legacy_type == "list":
        props["ordered"] = data.get("ordered", False)
        props["items"] = data.get("items", [])
    elif legacy_type == "tabs":
        pass  # handled specially in flatten
    else:
        # Custom extension types — pass all non-structural fields through
        for k, v in data.items():
            if k not in skip:
                props[k] = v
    return props


def flatten_tree(legacy_components: List[Dict[str, Any]]) -> Tuple[List[A2UIComponent], str]:
    """
    Convert a list of nested legacy component dicts into a flat A2UI adjacency
    list plus a root component ID.

    Returns (flat_components, root_id).
    """
    flat: List[A2UIComponent] = []

    def _flatten_one(data: Dict[str, Any]) -> str:
        """Recursively flatten a single legacy component dict, return its A2UI ID."""
        legacy_type = data.get("type", "container")
        a2ui_type = LEGACY_TYPE_MAP.get(legacy_type, legacy_type)
        comp_id = data.get("id") or _gen_id()

        # Recursively flatten children
        child_ids: List[str] = []

        if legacy_type == "tabs":
            # Tabs have a list of {label, content: [...]} items
            tab_items = []
            for tab_data in data.get("tabs", []):
                tab_child_ids = []
                for child in tab_data.get("content", []):
                    if isinstance(child, dict):
                        tab_child_ids.append(_flatten_one(child))
                label = tab_data.get("label", "")
                tab_items.append({"label": label, "children": tab_child_ids})
                child_ids.extend(tab_child_ids)
            props = _map_legacy_properties(legacy_type, data)
            props["tabs"] = tab_items
        else:
            # Handle children / content arrays
            for child_field in ("children", "content"):
                for child in data.get(child_field, []):
                    if isinstance(child, dict):
                        child_ids.append(_flatten_one(child))
            props = _map_legacy_properties(legacy_type, data)

        comp = A2UIComponent(
            id=comp_id,
            type=a2ui_type,
            properties=props,
            children=child_ids,
        )
        flat.append(comp)
        return comp_id

    # Flatten each top-level component
    root_ids: List[str] = []
    for comp_data in legacy_components:
        if isinstance(comp_data, dict):
            root_ids.append(_flatten_one(comp_data))

    # If multiple roots, wrap in a Column
    if len(root_ids) == 1:
        root_id = root_ids[0]
    else:
        root_id = _gen_id()
        root = A2UIComponent(
            id=root_id,
            type="Column",
            properties={"mainAxisAlignment": "start", "crossAxisAlignment": "stretch"},
            children=root_ids,
        )
        flat.append(root)

    return flat, root_id


# ---------------------------------------------------------------------------
# Response helper for agents
# ---------------------------------------------------------------------------

def create_a2ui_response(
    components: List[A2UIComponent],
    root_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build an MCP tool response containing A2UI components.

    If *root_id* is not provided, the first component is used as root.
    If there are multiple top-level components, they are wrapped in a Column.
    """
    if not components:
        return {"_a2ui_components": [], "_a2ui_root_id": "", "_data": None}

    serialized = [c.to_dict() for c in components]

    if root_id is None:
        root_id = components[0].id

    return {
        "_a2ui_components": serialized,
        "_a2ui_root_id": root_id,
        "_data": None,
    }
