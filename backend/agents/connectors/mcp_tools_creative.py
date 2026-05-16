"""
Creative/Design tools for the Claude Connectors Agent — US-22.

Blender, Adobe CC, Canva, Interactive Artifacts, Visual Graphs, Design.
Stubs return structured outputs noting they require external API access.
"""
import logging
from typing import Dict, Any

from shared.primitives import (
    Alert, Collapsible, Text, Container, Divider, Card,
    create_ui_response,
)

logger = logging.getLogger("Connectors.Creative")

_STUB_NOTE = "This connector requires external API access. Full integration pending."

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _stub_response(title: str, stubs: list) -> Dict[str, Any]:
    return create_ui_response([
        Alert(variant="info", title=title, message=_STUB_NOTE),
    ] + stubs)


# ---------------------------------------------------------------------------
# Blender
# ---------------------------------------------------------------------------

_BLENDER_METADATA = {
    "name": "blender_tool",
    "description": "Blender 3D tooling connector. (Stub — requires Blender Python API server.)",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["debug", "batch_transform", "export", "info"]},
            "target_objects": {"type": "array", "items": {"type": "string"}},
            "transform": {"type": "object"},
        },
        "required": ["action"],
    },
}


def handle_blender(args: Dict[str, Any]) -> Dict[str, Any]:
    action = args.get("action", "info")
    return _stub_response("Blender Connector", [
        Text(content=f"Requested action: {action}", variant="body"),
        Text(content="To enable: run a Blender instance with the Python API server on the network."),
        Collapsible(
            title="API Documentation",
            content=[Container(children=[
                Text(content="• debug: Scene/DAG inspection"),
                Text(content="• batch_transform: Apply transforms to objects"),
                Text(content="• export: Export selected objects to FBX/GLTF"),
                Text(content="• info: Scene statistics and object listing"),
            ])],
        ),
    ])


# ---------------------------------------------------------------------------
# Adobe CC
# ---------------------------------------------------------------------------

_ADOBE_METADATA = {
    "name": "adobe_cc",
    "description": "Adobe Creative Cloud connector. (Stub — requires Adobe API credentials.)",
    "input_schema": {
        "type": "object",
        "properties": {
            "app": {"type": "string", "enum": ["photoshop", "illustrator", "indesign"]},
            "action": {"type": "string", "description": "Action to perform"},
        },
        "required": ["app"],
    },
}


def handle_adobe(args: Dict[str, Any]) -> Dict[str, Any]:
    app = args.get("app", "photoshop")
    return _stub_response(f"Adobe {app.capitalize()} Connector", [
        Text(content="To enable: provide Adobe API credentials in the agent configuration."),
        Collapsible(
            title="Supported Apps",
            content=[Container(children=[
                Text(content="• Photoshop: Image editing, layer management, batch processing"),
                Text(content="• Illustrator: Vector creation, design automation, export"),
                Text(content="• InDesign: Document layout, template filling, publishing"),
            ])],
        ),
    ])


# ---------------------------------------------------------------------------
# Canva
# ---------------------------------------------------------------------------

_CANVA_METADATA = {
    "name": "canva_design",
    "description": "Canva/Affinity design connector. (Stub — requires Canva API key.)",
    "input_schema": {
        "type": "object",
        "properties": {
            "design_type": {"type": "string", "description": "Type of design"},
            "template": {"type": "string", "description": "Template ID or name"},
        },
        "required": ["design_type"],
    },
}


def handle_canva(args: Dict[str, Any]) -> Dict[str, Any]:
    design_type = args.get("design_type", "social_post")
    return _stub_response(f"Canva {design_type} Connector", [
        Text(content="To enable: provide Canva API key in the agent configuration."),
    ])


# ---------------------------------------------------------------------------
# Interactive Artifacts / Dashboards
# ---------------------------------------------------------------------------

_ARTIFACTS_METADATA = {
    "name": "interactive_artifacts",
    "description": "Generate interactive dashboard specifications.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Dashboard title"},
            "sections": {"type": "array", "items": {"type": "object", "properties": {
                "widget_type": {"type": "string", "enum": ["chart", "metric", "table", "map", "text"]},
                "title": {"type": "string"},
                "data_source": {"type": "string"},
            }}},
        },
        "required": ["title", "sections"],
    },
}


def handle_artifacts(args: Dict[str, Any]) -> Dict[str, Any]:
    title = args.get("title", "Dashboard")
    sections = args.get("sections", [])

    components = [
        Text(content=title, variant="h2"),
        Text(content="Dashboard layout specification — ready for implementation:", variant="caption"),
        Divider(),
    ]

    for i, section in enumerate(sections):
        desc = f"Type: {section.get('widget_type', 'unknown')} | Source: {section.get('data_source', 'N/A')}"
        components.append(Card(
            title=section.get("title", f"Widget {i + 1}"),
            content=[Text(content=desc, variant="body")],
        ))

    return create_ui_response(components)


# ---------------------------------------------------------------------------
# Visual Graph Networks
# ---------------------------------------------------------------------------

_GRAPHS_METADATA = {
    "name": "visual_graphs",
    "description": "Generate Obsidian-style visual graph network data from entities and relationships.",
    "input_schema": {
        "type": "object",
        "properties": {
            "nodes": {"type": "array", "items": {"type": "string"}},
            "edges": {"type": "array", "items": {"type": "object", "properties": {
                "source": {"type": "string"},
                "target": {"type": "string"},
                "label": {"type": "string"},
            }}},
        },
        "required": ["nodes", "edges"],
    },
}


def handle_graphs(args: Dict[str, Any]) -> Dict[str, Any]:
    nodes = args.get("nodes", [])
    edges = args.get("edges", [])

    node_text = "\n".join(f"• {n}" for n in nodes)
    edge_text = "\n".join(f"• {e['source']} → {e['target']}" + (f" ({e['label']})" if e.get('label') else "") for e in edges)

    components = [
        Text(content="Visual Graph Network", variant="h2"),
        Collapsible(title=f"Nodes ({len(nodes)})", content=[Text(content=node_text)]),
        Collapsible(title=f"Edges ({len(edges)})", content=[Text(content=edge_text)]),
        Text(content="To visualize: import into Obsidian, Cytoscape, or a graph visualization library.", variant="caption"),
    ]

    return create_ui_response(components)


# ---------------------------------------------------------------------------
# Design
# ---------------------------------------------------------------------------

_DESIGN_METADATA = {
    "name": "claude_design",
    "description": "UI/UX design suggestions. Get design recommendations for layout, color, typography.",
    "input_schema": {
        "type": "object",
        "properties": {
            "context": {"type": "string", "description": "Design context: web, mobile, dashboard, landing page, etc."},
            "style_preferences": {"type": "string", "description": "Style preferences"},
        },
        "required": ["context"],
    },
}


_COLOR_PALETTES = {
    "minimal": ["#FFFFFF", "#F5F5F5", "#333333", "#666666", "#999999"],
    "bold": ["#FF6B6B", "#4ECDC4", "#45B7D1", "#F9ED69", "#FF8E72"],
    "corporate": ["#1A365D", "#2B6CB0", "#EDF2F7", "#4A5568", "#63B3ED"],
    "playful": ["#FF6B6B", "#FFE66D", "#4ECDC4", "#FF8E72", "#A8E6CF"],
}


def handle_design(args: Dict[str, Any]) -> Dict[str, Any]:
    context = args.get("context", "web")
    style = args.get("style_preferences", "minimal")

    palette = _COLOR_PALETTES.get(style, _COLOR_PALETTES["minimal"])
    swatches = "  ".join(f"[{c}]" for c in palette)

    components = [
        Text(content=f"Design Recommendations: {context} ({style})", variant="h2"),
        Card(title="Color Palette", content=[Text(content=swatches)]),
        Card(title="Typography", content=[Text(content="Headings: Inter, system-ui, sans-serif  |  Body: 16px, 1.6 line-height")]),
        Card(title="Spacing", content=[Text(content="Use 8px grid: 8, 16, 24, 32, 48, 64")]),
        Card(title="Accessibility", content=[Text(content="Ensure WCAG 2.1 AA contrast ratios. Test with keyboard and screen reader.")]),
    ]

    return create_ui_response(components)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

CREATIVE_TOOL_REGISTRY = {
    "blender_tool": {"function": handle_blender, **_BLENDER_METADATA},
    "adobe_cc": {"function": handle_adobe, **_ADOBE_METADATA},
    "canva_design": {"function": handle_canva, **_CANVA_METADATA},
    "interactive_artifacts": {"function": handle_artifacts, **_ARTIFACTS_METADATA},
    "visual_graphs": {"function": handle_graphs, **_GRAPHS_METADATA},
    "claude_design": {"function": handle_design, **_DESIGN_METADATA},
}