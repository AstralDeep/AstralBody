"""041 — the `android` ROTE device profile.

The native Android client registers ``device_type: "android"`` and renders the
structured components natively (Compose), so it receives a FULL-capability
profile (like ``windows``) plus ``supported_types`` capability-negotiation —
NOT the web-oriented ``mobile``/``tablet`` density constraints (which, e.g.,
strip code on a phone). The client owns its own responsive layout, so ROTE
applies primitive substitution, not layout density. Pure Python.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from rote.capabilities import DeviceProfile, DeviceType, load_host_config  # noqa: E402


def test_android_is_a_device_type():
    assert DeviceType("android") is DeviceType.ANDROID
    assert DeviceType.ANDROID.value == "android"


def test_android_host_config_is_full_capability():
    cfg = load_host_config()
    assert "android" in cfg
    a = cfg["android"]
    # Full native capability, mirroring `windows` (NOT the web `mobile` limits).
    assert a["supports_code"] is True          # web-mobile strips code; native keeps it
    assert a["supports_charts"] is True
    assert a["supports_tables"] is True
    assert a["supports_tabs"] is True
    assert a["supports_file_io"] is True
    assert a["max_grid_columns"] == 6          # not the mobile 1 / tablet 3
    assert a["max_table_rows"] == 0            # unbounded (mobile caps at 20)
    assert a["max_table_cols"] == 0            # unbounded (mobile caps at 4)
    assert a["supports_interactivity"] is True


def test_android_profile_derives_full_capability():
    prof = DeviceProfile.from_dict({"device_type": "android"})
    assert prof.device_type is DeviceType.ANDROID
    assert prof.supports_code is True
    assert prof.max_grid_columns == 6
    assert prof.supports_interactivity is True


def test_android_carries_supported_types_negotiation():
    prof = DeviceProfile.from_dict({
        "device_type": "android",
        "supported_types": ["text", "card", "table", "alert"],
    })
    assert prof.supported_types == frozenset({"text", "card", "table", "alert"})
    # round-trips into rote_config as a sorted list
    assert prof.to_dict()["supported_types"] == ["alert", "card", "table", "text"]


def test_android_distinct_from_web_mobile():
    cfg = load_host_config()
    # The native profile must NOT inherit the web-mobile content constraints.
    assert cfg["android"]["supports_code"] is True
    assert cfg["mobile"]["supports_code"] is False
    assert cfg["android"]["max_grid_columns"] != cfg["mobile"]["max_grid_columns"]


def test_android_respects_env_override(monkeypatch):
    # Operators can still tune the native profile via ROTE_HOST_CONFIG.
    monkeypatch.setenv("ROTE_HOST_CONFIG", '{"android": {"max_grid_columns": 4}}')
    prof = DeviceProfile.from_dict({"device_type": "android"})
    assert prof.max_grid_columns == 4
