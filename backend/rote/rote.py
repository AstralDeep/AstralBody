"""
ROTE — Response Output Translation Engine

Per-session device registry + component adaptation pipeline.
Instantiated once inside the Orchestrator and used as internal middleware.
"""
import logging
from typing import Any, Dict, List

from rote.capabilities import DeviceProfile, DeviceType
from rote.adapter import ComponentAdapter

logger = logging.getLogger("ROTE")


class ROTE:
    def __init__(self):
        # Maps WebSocket object → DeviceProfile
        self._profiles: Dict[Any, DeviceProfile] = {}

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

    def cleanup(self, websocket: Any) -> None:
        """Called on WebSocket disconnect to free the profile entry."""
        self._profiles.pop(websocket, None)

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
        """
        profile = self.get_profile(websocket)

        if profile.device_type == DeviceType.BROWSER:
            return components  # Fast path — no adaptation needed

        adapted = ComponentAdapter.adapt(components, profile)
        logger.debug(
            f"ROTE: adapted {len(components)} → {len(adapted)} components "
            f"for {profile.device_type.value}"
        )
        return adapted
