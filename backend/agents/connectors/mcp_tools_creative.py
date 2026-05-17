"""
Creative/Design tools for the Claude Connectors Agent — US-22.

- Blender: deferred — no public cloud API; the stub points operators at the
  self-hosted Blender-server pattern.
- Adobe CC: IMS server-to-server token validation against the real Adobe IMS
  endpoint when ADOBE_CLIENT_ID/ADOBE_CLIENT_SECRET are configured.
- Canva: real Canva Connect API call when CANVA_API_KEY is configured.
- Artifacts / Graphs / Design: functional spec generators, no external calls.
"""
import logging
from typing import Dict, Any

import requests

from shared.primitives import (
    Alert, Collapsible, Text, Container, Divider, Card,
    create_ui_response,
)
from shared.external_http import request as http_request, ExternalHttpError, validate_egress_url

from agents.connectors._external import verdict_for_exception, user_facing_error

logger = logging.getLogger("Connectors.Creative")


# ---------------------------------------------------------------------------
# Blender — deferred (no public cloud API)
# ---------------------------------------------------------------------------

_BLENDER_METADATA = {
    "name": "blender_tool",
    "description": "Blender 3D tooling connector. Requires a self-hosted Blender headless server (no public cloud API).",
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
    return create_ui_response([
        Alert(
            variant="info",
            title="Blender Connector",
            message=(
                "Blender has no public cloud API. To enable this tool, run a "
                "Blender headless instance with a Python scripting endpoint and "
                "set BLENDER_SERVER_URL in this agent's credentials. Integration "
                "with that endpoint is not implemented yet."
            ),
        ),
        Text(content=f"Requested action: {action}", variant="body"),
        Collapsible(
            title="Planned actions",
            content=[Container(children=[
                Text(content="• debug — scene / DAG inspection"),
                Text(content="• batch_transform — apply transforms to named objects"),
                Text(content="• export — export selected objects to FBX/GLTF"),
                Text(content="• info — scene statistics and object listing"),
            ])],
        ),
    ])


# ---------------------------------------------------------------------------
# Adobe CC — IMS server-to-server token validation
# ---------------------------------------------------------------------------

_ADOBE_IMS_TOKEN_URL = "https://ims-na1.adobelogin.com/ims/token/v3"

_ADOBE_METADATA = {
    "name": "adobe_cc",
    "description": (
        "Adobe Creative Cloud connector. Validates ADOBE_CLIENT_ID/ADOBE_CLIENT_SECRET "
        "via the Adobe IMS token endpoint; full Firefly/CC API integration pending."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "app": {"type": "string", "enum": ["photoshop", "illustrator", "indesign", "firefly"]},
            "action": {"type": "string", "description": "Action to perform (informational only)"},
        },
        "required": ["app"],
    },
}


def _exchange_adobe_ims_token(client_id: str, client_secret: str) -> requests.Response:
    """Exchange Adobe IMS server-to-server credentials for a bearer token.

    Uses ``requests`` directly (not ``shared.external_http``) because that
    helper assumes a bearer-token request — IMS instead expects a form body
    with no Authorization header. SSRF policy is still enforced via
    ``validate_egress_url``.
    """
    validate_egress_url(_ADOBE_IMS_TOKEN_URL)
    return requests.post(
        _ADOBE_IMS_TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "openid,AdobeID,read_organizations,firefly_api,ff_apis",
        },
        timeout=30,
        allow_redirects=False,
    )


def handle_adobe(args: Dict[str, Any]) -> Dict[str, Any]:
    app = args.get("app", "photoshop")
    creds = args.get("_credentials") or {}
    client_id = creds.get("ADOBE_CLIENT_ID", "")
    client_secret = creds.get("ADOBE_CLIENT_SECRET", "")

    header = [Text(content=f"Adobe {app.capitalize()} Connector", variant="h2")]

    if not client_id or not client_secret:
        return create_ui_response(header + [
            Alert(
                variant="info",
                title="Credentials not configured",
                message=(
                    "Set both ADOBE_CLIENT_ID and ADOBE_CLIENT_SECRET in this agent's "
                    "settings (Adobe Developer Console → server-to-server credentials)."
                ),
            ),
            Collapsible(
                title="Supported apps (planned)",
                content=[Container(children=[
                    Text(content="• Photoshop: image editing, layer ops"),
                    Text(content="• Illustrator: vector creation, design automation"),
                    Text(content="• InDesign: layout, template fill"),
                    Text(content="• Firefly: text-to-image generation"),
                ])],
            ),
        ])

    try:
        resp = _exchange_adobe_ims_token(client_id, client_secret)
    except requests.RequestException as e:
        return create_ui_response(header + [
            Alert(
                variant="warning",
                title="Adobe IMS unreachable",
                message=f"Could not reach Adobe IMS: {e}",
            ),
        ])
    except ExternalHttpError as e:
        return create_ui_response(header + [
            Alert(variant="warning", title="Egress blocked", message=str(e)),
        ])

    if resp.status_code == 200 and "access_token" in (resp.text or ""):
        return create_ui_response(header + [
            Alert(
                variant="success",
                title="Credentials verified",
                message="Adobe IMS issued an access token. Full Firefly/CC actions pending implementation.",
            ),
            Collapsible(
                title="Token details",
                content=[Container(children=[
                    Text(content=f"Status: HTTP {resp.status_code}"),
                    Text(content="Scopes requested: openid, AdobeID, read_organizations, firefly_api, ff_apis"),
                ])],
            ),
        ])

    if resp.status_code in (400, 401, 403):
        snippet = (resp.text or "")[:300]
        return create_ui_response(header + [
            Alert(
                variant="warning",
                title="Credentials rejected",
                message=f"Adobe IMS returned HTTP {resp.status_code}: {snippet}",
            ),
        ])

    return create_ui_response(header + [
        Alert(
            variant="warning",
            title=f"Unexpected response (HTTP {resp.status_code})",
            message=(resp.text or "")[:300],
        ),
    ])


_ADOBE_CHECK_METADATA = {
    "name": "adobe_credentials_check",
    "description": "Probe ADOBE_CLIENT_ID/SECRET by exchanging them for an IMS access token.",
    "input_schema": {"type": "object", "properties": {}, "additionalProperties": True},
}


def handle_adobe_credentials_check(args: Dict[str, Any]) -> Dict[str, Any]:
    creds = args.get("_credentials") or {}
    client_id = creds.get("ADOBE_CLIENT_ID", "")
    client_secret = creds.get("ADOBE_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        return {
            "credential_test": "unconfigured",
            "detail": "ADOBE_CLIENT_ID and/or ADOBE_CLIENT_SECRET is not set.",
        }
    try:
        resp = _exchange_adobe_ims_token(client_id, client_secret)
    except requests.RequestException as e:
        return {"credential_test": "unreachable", "detail": str(e)}
    except ExternalHttpError as e:
        return verdict_for_exception(e)
    if resp.status_code == 200 and "access_token" in (resp.text or ""):
        return {"credential_test": "ok"}
    if resp.status_code in (400, 401, 403):
        return {"credential_test": "auth_failed", "detail": f"HTTP {resp.status_code}"}
    return {"credential_test": "unexpected", "detail": f"HTTP {resp.status_code}"}


# ---------------------------------------------------------------------------
# Canva — Connect API
# ---------------------------------------------------------------------------

_CANVA_BASE = "https://api.canva.com/rest/v1"

_CANVA_METADATA = {
    "name": "canva_design",
    "description": (
        "Canva design connector. When CANVA_API_KEY is configured, creates a "
        "design in your Canva workspace via the Canva Connect API; otherwise "
        "returns a stub describing the required credential."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "design_type": {"type": "string", "description": "Canva design type (e.g. 'presentation', 'doc', 'whiteboard')"},
            "title": {"type": "string", "description": "Optional title for the new design"},
        },
        "required": ["design_type"],
    },
}


def handle_canva(args: Dict[str, Any]) -> Dict[str, Any]:
    design_type = args.get("design_type", "presentation")
    title = args.get("title") or f"New {design_type}"

    creds = args.get("_credentials") or {}
    token = creds.get("CANVA_API_KEY", "")

    header = [Text(content=f"Canva — {design_type}", variant="h2")]

    if not token:
        return create_ui_response(header + [
            Alert(
                variant="info",
                title="Credentials not configured",
                message=(
                    "Set CANVA_API_KEY in this agent's settings (Canva Connect API "
                    "bearer token) to actually create designs."
                ),
            ),
        ])

    try:
        resp = http_request(
            "POST",
            f"{_CANVA_BASE}/designs",
            api_key=token,
            json_body={
                "design_type": {"type": "preset", "name": design_type},
                "title": title,
            },
        )
    except ExternalHttpError as e:
        return create_ui_response(header + [
            Alert(
                variant="warning",
                title="Canva call failed",
                message=user_facing_error(e, "Canva"),
            ),
        ])

    if resp.status_code in (200, 201):
        try:
            payload = resp.json()
        except ValueError:
            payload = {}
        design = (payload or {}).get("design") or {}
        urls = design.get("urls") or {}
        edit_url = urls.get("edit_url") or urls.get("view_url")
        design_id = design.get("id", "(unknown id)")
        components = header + [
            Alert(
                variant="success",
                title="Design created",
                message=f"Canva design {design_id} created in your workspace.",
            ),
        ]
        if edit_url:
            components.append(Text(content=f"Open in Canva: {edit_url}", variant="body"))
        return create_ui_response(components)

    return create_ui_response(header + [
        Alert(
            variant="warning",
            title=f"Unexpected response (HTTP {resp.status_code})",
            message=(resp.text or "")[:300],
        ),
    ])


_CANVA_CHECK_METADATA = {
    "name": "canva_credentials_check",
    "description": "Probe the saved Canva API key with a cheap GET /users/me.",
    "input_schema": {"type": "object", "properties": {}, "additionalProperties": True},
}


def handle_canva_credentials_check(args: Dict[str, Any]) -> Dict[str, Any]:
    creds = args.get("_credentials") or {}
    token = creds.get("CANVA_API_KEY", "")
    if not token:
        return {"credential_test": "unconfigured", "detail": "CANVA_API_KEY is not set."}
    try:
        resp = http_request("GET", f"{_CANVA_BASE}/users/me", api_key=token)
    except ExternalHttpError as e:
        return verdict_for_exception(e)
    if resp.status_code == 200:
        return {"credential_test": "ok"}
    return {"credential_test": "unexpected", "detail": f"HTTP {resp.status_code}"}


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
    edge_text = "\n".join(
        f"• {e['source']} → {e['target']}" + (f" ({e['label']})" if e.get("label") else "")
        for e in edges
    )
    components = [
        Text(content="Visual Graph Network", variant="h2"),
        Collapsible(title=f"Nodes ({len(nodes)})", content=[Text(content=node_text)]),
        Collapsible(title=f"Edges ({len(edges)})", content=[Text(content=edge_text)]),
        Text(
            content="To visualize: import into Obsidian, Cytoscape, or a graph visualization library.",
            variant="caption",
        ),
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
    "adobe_credentials_check": {"function": handle_adobe_credentials_check, **_ADOBE_CHECK_METADATA},
    "canva_design": {"function": handle_canva, **_CANVA_METADATA},
    "canva_credentials_check": {"function": handle_canva_credentials_check, **_CANVA_CHECK_METADATA},
    "interactive_artifacts": {"function": handle_artifacts, **_ARTIFACTS_METADATA},
    "visual_graphs": {"function": handle_graphs, **_GRAPHS_METADATA},
    "claude_design": {"function": handle_design, **_DESIGN_METADATA},
}
