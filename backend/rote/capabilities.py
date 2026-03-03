"""
ROTE Capabilities — Device capability and profile models.

DeviceCapabilities: raw data reported by the frontend on connection.
DeviceProfile: derived rendering constraints used by the adapter.
"""
from enum import Enum
from dataclasses import dataclass, asdict
from typing import Dict, Any


class DeviceType(str, Enum):
    BROWSER = "browser"  # Full desktop browser
    TABLET  = "tablet"   # iPad / Android tablet (~768-1024px)
    MOBILE  = "mobile"   # Phone (<=480px viewport)
    WATCH   = "watch"    # Smartwatch (<=200px viewport, or explicit)
    TV      = "tv"       # Smart TV (large screen, read-only)
    VOICE   = "voice"    # Audio-only, no screen


@dataclass
class DeviceCapabilities:
    """Raw capabilities as reported by the frontend in register_ui."""
    device_type: str = "browser"
    screen_width: int = 1920
    screen_height: int = 1080
    viewport_width: int = 1920
    viewport_height: int = 1080
    pixel_ratio: float = 1.0
    has_touch: bool = False
    has_geolocation: bool = False
    has_microphone: bool = False
    has_camera: bool = False
    has_file_system: bool = True
    connection_type: str = "unknown"  # wifi, 4g, 3g, 2g, slow-2g
    user_agent: str = ""


@dataclass
class DeviceProfile:
    """Derived rendering profile used to drive component adaptation."""
    device_type: DeviceType
    capabilities: DeviceCapabilities
    # Rendering constraints
    max_grid_columns: int   # Maximum columns in a grid layout
    supports_charts: bool   # Bar/line/pie/plotly charts
    supports_tables: bool   # Table component
    supports_code: bool     # Code blocks
    supports_file_io: bool  # file_upload / file_download
    supports_tabs: bool     # Tabs component
    max_text_chars: int     # Max text length before truncation; 0 = unlimited
    max_table_rows: int     # Max rows to keep in tables; 0 = unlimited
    max_table_cols: int     # Max columns to keep in tables; 0 = unlimited

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "DeviceProfile":
        """Build a DeviceProfile from a raw dict (from the frontend)."""
        valid_keys = DeviceCapabilities.__dataclass_fields__.keys()
        caps = DeviceCapabilities(**{k: v for k, v in data.items() if k in valid_keys})
        return DeviceProfile._derive(caps)

    @staticmethod
    def default() -> "DeviceProfile":
        """Default full-browser profile (no adaptation)."""
        return DeviceProfile._derive(DeviceCapabilities())

    @staticmethod
    def _derive(caps: DeviceCapabilities) -> "DeviceProfile":
        """Derive the profile from capabilities, including size-based overrides."""
        raw = caps.device_type
        dt = DeviceType(raw) if raw in DeviceType._value2member_map_ else DeviceType.BROWSER

        # Override based on viewport size when the frontend reports "browser"
        vw = caps.viewport_width or caps.screen_width
        if dt == DeviceType.BROWSER:
            if vw <= 200:
                dt = DeviceType.WATCH
            elif vw <= 480:
                dt = DeviceType.MOBILE
            elif vw <= 1024:
                dt = DeviceType.TABLET

        constraints: Dict[DeviceType, dict] = {
            DeviceType.BROWSER: dict(
                max_grid_columns=6,
                supports_charts=True,
                supports_tables=True,
                supports_code=True,
                supports_file_io=True,
                supports_tabs=True,
                max_text_chars=0,
                max_table_rows=0,
                max_table_cols=0,
            ),
            DeviceType.TABLET: dict(
                max_grid_columns=3,
                supports_charts=True,
                supports_tables=True,
                supports_code=True,
                supports_file_io=True,
                supports_tabs=True,
                max_text_chars=0,
                max_table_rows=0,
                max_table_cols=6,
            ),
            DeviceType.MOBILE: dict(
                max_grid_columns=1,
                supports_charts=True,
                supports_tables=True,
                supports_code=False,
                supports_file_io=True,
                supports_tabs=True,
                max_text_chars=0,
                max_table_rows=20,
                max_table_cols=4,
            ),
            DeviceType.WATCH: dict(
                max_grid_columns=1,
                supports_charts=False,
                supports_tables=False,
                supports_code=False,
                supports_file_io=False,
                supports_tabs=False,
                max_text_chars=120,
                max_table_rows=3,
                max_table_cols=2,
            ),
            DeviceType.TV: dict(
                max_grid_columns=4,
                supports_charts=True,
                supports_tables=True,
                supports_code=True,
                supports_file_io=False,
                supports_tabs=True,
                max_text_chars=0,
                max_table_rows=0,
                max_table_cols=0,
            ),
            DeviceType.VOICE: dict(
                max_grid_columns=1,
                supports_charts=False,
                supports_tables=False,
                supports_code=False,
                supports_file_io=False,
                supports_tabs=False,
                max_text_chars=300,
                max_table_rows=0,
                max_table_cols=0,
            ),
        }

        return DeviceProfile(device_type=dt, capabilities=caps, **constraints[dt])

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["device_type"] = self.device_type.value
        return d
