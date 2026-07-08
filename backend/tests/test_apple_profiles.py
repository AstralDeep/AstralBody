"""051 — the `ios` and `macos` ROTE device profiles.

The native Apple clients register ``device_type: "ios"`` / ``"macos"`` and
render structured components natively (SwiftUI), so they receive FULL-capability
profiles (the 041 ``android`` / ``windows`` pattern) plus ``supported_types``
capability-negotiation — NOT the web-oriented ``mobile``/``tablet`` density
constraints. The watch target reuses the existing ``watch`` profile unchanged:
it is the degradation authority for feature 051. Pure Python.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from rote.capabilities import DeviceProfile, DeviceType, load_host_config  # noqa: E402


def test_ios_and_macos_are_device_types():
    assert DeviceType("ios") is DeviceType.IOS
    assert DeviceType.IOS.value == "ios"
    assert DeviceType("macos") is DeviceType.MACOS
    assert DeviceType.MACOS.value == "macos"


def test_apple_host_configs_are_full_capability():
    cfg = load_host_config()
    for key in ("ios", "macos"):
        assert key in cfg
        a = cfg[key]
        # Full native capability, mirroring `windows`/`android` (NOT web limits).
        assert a["supports_code"] is True
        assert a["supports_charts"] is True
        assert a["supports_tables"] is True
        assert a["supports_tabs"] is True
        assert a["supports_file_io"] is True
        assert a["max_grid_columns"] == 6
        assert a["max_table_rows"] == 0
        assert a["max_table_cols"] == 0
        assert a["supports_interactivity"] is True


def test_apple_profiles_derive_full_capability():
    for key, member in (("ios", DeviceType.IOS), ("macos", DeviceType.MACOS)):
        prof = DeviceProfile.from_dict({"device_type": key})
        assert prof.device_type is member
        assert prof.supports_code is True
        assert prof.max_grid_columns == 6
        assert prof.supports_interactivity is True


def test_named_apple_types_bypass_viewport_downgrade():
    # A named native type must NOT be re-derived to mobile/tablet/watch from a
    # small viewport (an iPhone reports ios + a ~390pt viewport; the client owns
    # its own responsive layout).
    prof = DeviceProfile.from_dict({"device_type": "ios", "viewport_width": 390})
    assert prof.device_type is DeviceType.IOS
    assert prof.max_grid_columns == 6
    prof = DeviceProfile.from_dict({"device_type": "macos", "viewport_width": 1024})
    assert prof.device_type is DeviceType.MACOS


def test_apple_carries_supported_types_negotiation():
    prof = DeviceProfile.from_dict({
        "device_type": "ios",
        "supported_types": ["text", "card", "table", "plotly_chart"],
    })
    assert prof.supported_types == frozenset({"text", "card", "table", "plotly_chart"})
    assert prof.to_dict()["supported_types"] == sorted(prof.supported_types)


def test_watch_profile_unchanged_as_degradation_authority():
    # 051 relies on the existing watch bounds; pin them so a drive-by tune is a
    # deliberate act (ROTE_HOST_CONFIG) rather than an accident.
    cfg = load_host_config()
    w = cfg["watch"]
    assert w["max_grid_columns"] == 1
    assert w["supports_charts"] is False
    assert w["supports_tables"] is False
    assert w["supports_code"] is False
    assert w["supports_tabs"] is False
    assert w["supports_file_io"] is False
    assert w["max_text_chars"] == 120
    assert w["max_table_rows"] == 3
    assert w["max_table_cols"] == 2


def test_watch_explicit_registration_derives_watch():
    prof = DeviceProfile.from_dict(
        {"device_type": "watch", "viewport_width": 205, "has_microphone": True}
    )
    assert prof.device_type is DeviceType.WATCH
    assert prof.capabilities.has_microphone is True
    assert prof.max_text_chars == 120


def test_apple_profiles_respect_env_override(monkeypatch):
    monkeypatch.setenv(
        "ROTE_HOST_CONFIG", '{"ios": {"max_grid_columns": 2}, "macos": {"supports_code": false}}'
    )
    cfg = load_host_config()
    assert cfg["ios"]["max_grid_columns"] == 2
    assert cfg["macos"]["supports_code"] is False
    # untouched fields keep their defaults
    assert cfg["ios"]["supports_code"] is True
