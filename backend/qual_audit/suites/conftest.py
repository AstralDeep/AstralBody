"""Shared fixtures for the Academic Testing Suite."""

import os
import sys
import tempfile

import pytest

# Ensure backend is importable
_backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

# Force mock auth for all tests
os.environ["VITE_USE_MOCK_AUTH"] = "true"


@pytest.fixture
def tmp_data_dir():
    """Temporary directory for test data files (e.g. credential keys)."""
    d = tempfile.mkdtemp(prefix="astral_test_")
    yield d
    # Cleanup
    import shutil
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def tool_security_analyzer():
    """Pre-constructed ToolSecurityAnalyzer."""
    from orchestrator.tool_security import ToolSecurityAnalyzer
    return ToolSecurityAnalyzer()


@pytest.fixture
def code_security_analyzer():
    """Pre-constructed CodeSecurityAnalyzer."""
    from orchestrator.code_security import CodeSecurityAnalyzer
    return CodeSecurityAnalyzer()


@pytest.fixture
def perm_manager(tmp_data_dir):
    """ToolPermissionManager backed by a temp database."""
    from orchestrator.tool_permissions import ToolPermissionManager
    return ToolPermissionManager(data_dir=tmp_data_dir)


@pytest.fixture
def delegation_service():
    """DelegationService in mock mode."""
    from orchestrator.delegation import DelegationService
    return DelegationService()


@pytest.fixture
def nefarious_tool_registry():
    """The nefarious agent's TOOL_REGISTRY."""
    from agents.nefarious.mcp_tools import TOOL_REGISTRY
    return TOOL_REGISTRY


@pytest.fixture
def browser_profile():
    """Default browser DeviceProfile (no adaptation)."""
    from rote.capabilities import DeviceProfile
    return DeviceProfile.default()


@pytest.fixture
def mobile_profile():
    """Mobile DeviceProfile (phone, ≤480px)."""
    from rote.capabilities import DeviceCapabilities, DeviceProfile
    caps = DeviceCapabilities(device_type="mobile", viewport_width=375, viewport_height=667)
    return DeviceProfile._derive(caps)


@pytest.fixture
def watch_profile():
    """Watch DeviceProfile (smartwatch, ≤200px)."""
    from rote.capabilities import DeviceCapabilities, DeviceProfile
    caps = DeviceCapabilities(device_type="watch", viewport_width=180, viewport_height=180)
    return DeviceProfile._derive(caps)


@pytest.fixture
def tablet_profile():
    """Tablet DeviceProfile (~768-1024px)."""
    from rote.capabilities import DeviceCapabilities, DeviceProfile
    caps = DeviceCapabilities(device_type="tablet", viewport_width=768, viewport_height=1024)
    return DeviceProfile._derive(caps)


@pytest.fixture
def tv_profile():
    """TV DeviceProfile (large screen, read-only)."""
    from rote.capabilities import DeviceCapabilities, DeviceProfile
    caps = DeviceCapabilities(device_type="tv", viewport_width=1920, viewport_height=1080)
    return DeviceProfile._derive(caps)


@pytest.fixture
def voice_profile():
    """Voice DeviceProfile (audio-only, no screen)."""
    from rote.capabilities import DeviceCapabilities, DeviceProfile
    caps = DeviceCapabilities(device_type="voice", viewport_width=0, viewport_height=0)
    return DeviceProfile._derive(caps)
