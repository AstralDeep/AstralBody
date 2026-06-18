"""The native Windows device type + supported_types capability negotiation.

Regression: a profile carrying `supported_types` (which the native Windows
client is the first client to send) must JSON-serialize — `to_dict` previously
emitted a frozenset and crashed the `rote_config` send on register.
"""
import json

from rote.capabilities import DeviceProfile, DeviceType


def test_windows_is_a_device_type():
    assert DeviceType("windows") is DeviceType.WINDOWS


def test_windows_profile_is_full_desktop():
    p = DeviceProfile.from_dict({"device_type": "windows",
                                 "viewport_width": 1280, "viewport_height": 860})
    assert p.device_type is DeviceType.WINDOWS
    assert p.max_grid_columns == 6
    assert p.supports_charts and p.supports_tables and p.supports_interactivity


def test_windows_not_downgraded_by_viewport():
    # _derive only viewport-downgrades a 'browser'; an explicit windows stays windows.
    p = DeviceProfile.from_dict({"device_type": "windows", "viewport_width": 300})
    assert p.device_type is DeviceType.WINDOWS


def test_supported_types_engages_and_serializes():
    p = DeviceProfile.from_dict({
        "device_type": "windows",
        "supported_types": ["text", "card", "hero", "table", "Bar_Chart"]})
    # carried onto the profile as a frozenset for membership checks…
    assert p.supported_types == frozenset({"text", "card", "hero", "table", "bar_chart"})
    # …but to_dict must be JSON-safe (the rote_config send path).
    d = p.to_dict()
    assert isinstance(d["supported_types"], list)
    assert json.loads(json.dumps(d))["device_type"] == "windows"


def test_no_supported_types_serializes_too():
    d = DeviceProfile.from_dict({"device_type": "windows"}).to_dict()
    assert d["supported_types"] is None
    json.dumps(d)  # must not raise
