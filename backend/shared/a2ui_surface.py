"""
A2UI Surface Manager — manages the lifecycle of A2UI surfaces.

Each surface represents a rendered UI context (typically one per chat response).
The manager tracks surfaces per WebSocket session and provides create/update/delete
operations that emit the corresponding A2UI protocol messages.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .a2ui_primitives import A2UIComponent
from .a2ui_protocol import (
    CreateSurfaceMessage,
    DeleteSurfaceMessage,
    UpdateComponentsMessage,
    UpdateDataModelMessage,
)
from .a2ui_data_model import DataModel


@dataclass
class Surface:
    """A single A2UI surface holding components and state."""

    surface_id: str
    catalog_id: str = "astral-default"
    components: Dict[str, A2UIComponent] = field(default_factory=dict)
    root_id: str = ""
    data_model: DataModel = field(default_factory=DataModel)
    theme: Optional[Dict[str, Any]] = None

    def get_component(self, component_id: str) -> Optional[A2UIComponent]:
        return self.components.get(component_id)

    def set_components(self, components: List[A2UIComponent], root_id: str) -> None:
        """Replace all components and set the root."""
        self.components = {c.id: c for c in components}
        self.root_id = root_id


class SurfaceManager:
    """
    Manages A2UI surfaces across WebSocket sessions.

    Each WebSocket connection can have multiple active surfaces.
    Surfaces are cleaned up when the connection is closed.
    """

    def __init__(self) -> None:
        self._surfaces: Dict[str, Surface] = {}
        # websocket id → list of surface_ids
        self._session_surfaces: Dict[int, List[str]] = {}

    def create_surface(
        self,
        ws_id: int,
        components: List[A2UIComponent],
        root_id: str,
        *,
        catalog_id: str = "astral-default",
        data_model: Optional[Dict[str, Any]] = None,
        theme: Optional[Dict[str, Any]] = None,
    ) -> CreateSurfaceMessage:
        """
        Create a new surface and return the protocol message to send.
        """
        surface_id = str(uuid.uuid4())
        surface = Surface(
            surface_id=surface_id,
            catalog_id=catalog_id,
            root_id=root_id,
            theme=theme,
        )
        surface.set_components(components, root_id)
        if data_model:
            surface.data_model.replace(data_model)

        self._surfaces[surface_id] = surface
        if ws_id not in self._session_surfaces:
            self._session_surfaces[ws_id] = []
        self._session_surfaces[ws_id].append(surface_id)

        return CreateSurfaceMessage(
            surface_id=surface_id,
            catalog_id=catalog_id,
            components=[c.to_dict() for c in components],
            root_component_id=root_id,
            data_model=data_model,
            theme=theme,
        )

    def update_components(
        self,
        surface_id: str,
        components: List[A2UIComponent],
        root_id: str,
    ) -> Optional[UpdateComponentsMessage]:
        """
        Update components on an existing surface.
        Returns None if the surface doesn't exist.
        """
        surface = self._surfaces.get(surface_id)
        if surface is None:
            return None

        surface.set_components(components, root_id)

        return UpdateComponentsMessage(
            surface_id=surface_id,
            components=[c.to_dict() for c in components],
            root_component_id=root_id,
        )

    def update_data_model(
        self,
        surface_id: str,
        path: str,
        value: Any,
    ) -> Optional[UpdateDataModelMessage]:
        """
        Update the data model at a JSON Pointer path.
        Returns None if the surface doesn't exist.
        """
        surface = self._surfaces.get(surface_id)
        if surface is None:
            return None

        surface.data_model.set(path, value)

        return UpdateDataModelMessage(
            surface_id=surface_id,
            path=path,
            value=value,
        )

    def delete_surface(self, surface_id: str) -> Optional[DeleteSurfaceMessage]:
        """
        Delete a surface and return the protocol message.
        Returns None if the surface doesn't exist.
        """
        if surface_id not in self._surfaces:
            return None

        del self._surfaces[surface_id]

        # Remove from session tracking
        for ws_id, sids in self._session_surfaces.items():
            if surface_id in sids:
                sids.remove(surface_id)
                break

        return DeleteSurfaceMessage(surface_id=surface_id)

    def get_surface(self, surface_id: str) -> Optional[Surface]:
        return self._surfaces.get(surface_id)

    def get_session_surfaces(self, ws_id: int) -> List[Surface]:
        """Get all surfaces for a WebSocket session."""
        sids = self._session_surfaces.get(ws_id, [])
        return [self._surfaces[sid] for sid in sids if sid in self._surfaces]

    def cleanup(self, ws_id: int) -> List[DeleteSurfaceMessage]:
        """
        Remove all surfaces for a disconnected session.
        Returns delete messages for each removed surface.
        """
        sids = self._session_surfaces.pop(ws_id, [])
        messages = []
        for sid in sids:
            if sid in self._surfaces:
                del self._surfaces[sid]
                messages.append(DeleteSurfaceMessage(surface_id=sid))
        return messages
