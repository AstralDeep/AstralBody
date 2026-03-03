"""
ROTE — Response Output Translation Engine

Per-session device registry + component adaptation pipeline.
Instantiated once inside the Orchestrator and used as internal middleware.
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

from rote.capabilities import DeviceProfile, DeviceType
from rote.adapter import ComponentAdapter

logger = logging.getLogger("ROTE")


class ROTE:
    def __init__(self):
        # Maps WebSocket object → DeviceProfile
        self._profiles: Dict[Any, DeviceProfile] = {}
        # Maps WebSocket object → last raw (pre-adaptation) components
        self._last_components: Dict[Any, List[Dict]] = {}

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def register_device(self, websocket: Any, device_info: Dict[str, Any]) -> DeviceProfile:
        """
        Called during register_ui handling.
        Builds a DeviceProfile from the frontend-reported device_info dict
        and stores it keyed by the websocket object.
        Returns the profile so the orchestrator can send it back to the client.
        """
        profile = DeviceProfile.from_dict(device_info) if device_info else DeviceProfile.default()
        self._profiles[websocket] = profile
        logger.info(
            f"ROTE: registered device — type={profile.device_type.value} "
            f"viewport={profile.capabilities.viewport_width}x{profile.capabilities.viewport_height} "
            f"charts={profile.supports_charts} tables={profile.supports_tables} "
            f"grid_cols={profile.max_grid_columns}"
        )
        return profile

    def update_device(
        self, websocket: Any, device_info: Dict[str, Any]
    ) -> Tuple[DeviceProfile, Optional[List[Dict]]]:
        """
        Called when the frontend reports a viewport / capability change.
        Rebuilds the DeviceProfile and, if it differs from the current one,
        re-adapts the last-sent components so the orchestrator can push them.

        Returns (new_profile, re_adapted_components_or_None).
        re_adapted_components is None when:
          - the profile hasn't meaningfully changed, OR
          - there are no cached components to re-adapt.
        """
        old_profile = self._profiles.get(websocket)
        new_profile = DeviceProfile.from_dict(device_info) if device_info else DeviceProfile.default()
        self._profiles[websocket] = new_profile

        changed = (
            old_profile is None
            or old_profile.device_type != new_profile.device_type
            or old_profile.max_grid_columns != new_profile.max_grid_columns
            or old_profile.capabilities.viewport_width != new_profile.capabilities.viewport_width
            or old_profile.capabilities.viewport_height != new_profile.capabilities.viewport_height
        )

        logger.info(
            f"ROTE: device update — type={new_profile.device_type.value} "
            f"viewport={new_profile.capabilities.viewport_width}x{new_profile.capabilities.viewport_height} "
            f"changed={changed}"
        )

        if not changed:
            return new_profile, None

        # Re-adapt cached components if available
        raw = self._last_components.get(websocket)
        if not raw:
            return new_profile, None

        if new_profile.device_type == DeviceType.BROWSER:
            return new_profile, raw  # fast path

        adapted = ComponentAdapter.adapt(raw, new_profile)
        logger.debug(
            f"ROTE: re-adapted {len(raw)} → {len(adapted)} components "
            f"after viewport change for {new_profile.device_type.value}"
        )
        return new_profile, adapted

    def cleanup(self, websocket: Any) -> None:
        """Called on WebSocket disconnect to free the profile entry."""
        self._profiles.pop(websocket, None)
        self._last_components.pop(websocket, None)

    def get_profile(self, websocket: Any) -> DeviceProfile:
        """Return the stored profile, defaulting to full browser if not registered."""
        return self._profiles.get(websocket, DeviceProfile.default())

    # ------------------------------------------------------------------
    # Component adaptation
    # ------------------------------------------------------------------

    def adapt(self, websocket: Any, components: List[Dict]) -> List[Dict]:
        """
        Adapt a list of UI component dicts for the device attached to websocket.
        Called by Orchestrator.send_ui_render before transmitting to the client.
        Browser profile is a fast-path (no transformation applied).
        Caches the raw (pre-adaptation) components for re-adaptation on
        viewport change.
        """
        # Cache raw components for potential re-adaptation
        self._last_components[websocket] = components

        profile = self.get_profile(websocket)

        if profile.device_type == DeviceType.BROWSER:
            return components  # Fast path — no adaptation needed

        adapted = ComponentAdapter.adapt(components, profile)
        logger.debug(
            f"ROTE: adapted {len(components)} → {len(adapted)} components "
            f"for {profile.device_type.value}"
        )
        return adapted
