"""
A2UI Protocol Messages — v0.10 spec message types for surface lifecycle.

Server → Client: CreateSurface, UpdateComponents, UpdateDataModel, DeleteSurface
Client → Server: A2UIAction
"""

import json
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Base (reuse the existing Message base from protocol.py)
# ---------------------------------------------------------------------------

@dataclass
class A2UIMessage:
    """Base for all A2UI-specific messages."""
    type: str

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Server → Client messages
# ---------------------------------------------------------------------------

@dataclass
class CreateSurfaceMessage(A2UIMessage):
    """Sent when a new surface is created for a chat response."""
    type: str = "a2ui_create_surface"
    version: str = "v0.10"
    surface_id: str = ""
    catalog_id: str = "astral-default"
    components: List[Dict[str, Any]] = field(default_factory=list)
    root_component_id: str = ""
    data_model: Optional[Dict[str, Any]] = None
    theme: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "type": self.type,
            "version": self.version,
            "surfaceId": self.surface_id,
            "catalogId": self.catalog_id,
            "components": self.components,
            "rootComponentId": self.root_component_id,
        }
        if self.data_model is not None:
            d["dataModel"] = self.data_model
        if self.theme is not None:
            d["theme"] = self.theme
        return d


@dataclass
class UpdateComponentsMessage(A2UIMessage):
    """Sent to update components on an existing surface."""
    type: str = "a2ui_update_components"
    version: str = "v0.10"
    surface_id: str = ""
    components: List[Dict[str, Any]] = field(default_factory=list)
    root_component_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "version": self.version,
            "surfaceId": self.surface_id,
            "components": self.components,
            "rootComponentId": self.root_component_id,
        }


@dataclass
class UpdateDataModelMessage(A2UIMessage):
    """Sent to update the data model for an existing surface."""
    type: str = "a2ui_update_data_model"
    version: str = "v0.10"
    surface_id: str = ""
    path: str = ""        # JSON Pointer path
    value: Any = None     # New value (None = removal)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "type": self.type,
            "version": self.version,
            "surfaceId": self.surface_id,
            "path": self.path,
        }
        if self.value is not None:
            d["value"] = self.value
        return d


@dataclass
class DeleteSurfaceMessage(A2UIMessage):
    """Sent to delete a surface and free its resources."""
    type: str = "a2ui_delete_surface"
    version: str = "v0.10"
    surface_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "version": self.version,
            "surfaceId": self.surface_id,
        }


# ---------------------------------------------------------------------------
# Client → Server messages
# ---------------------------------------------------------------------------

@dataclass
class A2UIActionMessage(A2UIMessage):
    """User interaction dispatched from a component."""
    type: str = "a2ui_action"
    version: str = "v0.10"
    name: str = ""
    surface_id: str = ""
    source_component_id: str = ""
    timestamp: str = ""
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "version": self.version,
            "name": self.name,
            "surfaceId": self.surface_id,
            "sourceComponentId": self.source_component_id,
            "timestamp": self.timestamp,
            "context": self.context,
        }


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_A2UI_TYPE_MAP = {
    "a2ui_create_surface": CreateSurfaceMessage,
    "a2ui_update_components": UpdateComponentsMessage,
    "a2ui_update_data_model": UpdateDataModelMessage,
    "a2ui_delete_surface": DeleteSurfaceMessage,
    "a2ui_action": A2UIActionMessage,
}


def parse_a2ui_message(data: Dict[str, Any]) -> Optional[A2UIMessage]:
    """
    Parse a dict into the appropriate A2UIMessage subclass.
    Returns None if the type is not an A2UI message.
    """
    msg_type = data.get("type", "")
    cls = _A2UI_TYPE_MAP.get(msg_type)
    if cls is None:
        return None

    # Map camelCase wire keys → snake_case dataclass fields
    kwargs: Dict[str, Any] = {"type": msg_type}
    kwargs["version"] = data.get("version", "v0.10")

    if msg_type == "a2ui_create_surface":
        kwargs["surface_id"] = data.get("surfaceId", "")
        kwargs["catalog_id"] = data.get("catalogId", "astral-default")
        kwargs["components"] = data.get("components", [])
        kwargs["root_component_id"] = data.get("rootComponentId", "")
        kwargs["data_model"] = data.get("dataModel")
        kwargs["theme"] = data.get("theme")
    elif msg_type == "a2ui_update_components":
        kwargs["surface_id"] = data.get("surfaceId", "")
        kwargs["components"] = data.get("components", [])
        kwargs["root_component_id"] = data.get("rootComponentId", "")
    elif msg_type == "a2ui_update_data_model":
        kwargs["surface_id"] = data.get("surfaceId", "")
        kwargs["path"] = data.get("path", "")
        kwargs["value"] = data.get("value")
    elif msg_type == "a2ui_delete_surface":
        kwargs["surface_id"] = data.get("surfaceId", "")
    elif msg_type == "a2ui_action":
        kwargs["name"] = data.get("name", "")
        kwargs["surface_id"] = data.get("surfaceId", "")
        kwargs["source_component_id"] = data.get("sourceComponentId", "")
        kwargs["timestamp"] = data.get("timestamp", "")
        kwargs["context"] = data.get("context", {})

    return cls(**kwargs)


def is_a2ui_message(msg_type: str) -> bool:
    """Check if a message type string is an A2UI protocol message."""
    return msg_type in _A2UI_TYPE_MAP
