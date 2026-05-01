"""Shared path setup for the NSF TechAccess grants-agent tests.

The agents.grants package transitively imports shared.base_agent which
in turn imports a2a — that import path is exercised in the production
container but the local venv has a version skew. To keep these tests
deterministic, we import the modules under test (nsf_techaccess_knowledge
and the relevant tool functions in mcp_tools) by file path rather than
through the agents.grants package, sidestepping the package's __init__.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest

# Make `from shared.X import Y` resolve.
_BACKEND = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

_GRANTS = Path(_BACKEND) / "agents" / "grants"


def _load_module_by_path(name: str, path: Path) -> ModuleType:
    """Load a Python module from an explicit file path, registering it
    under ``name`` so cross-module imports inside the loaded module
    resolve consistently across tests.
    """
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def knowledge():
    """The nsf_techaccess_knowledge module."""
    return _load_module_by_path(
        "agents.grants.nsf_techaccess_knowledge",
        _GRANTS / "nsf_techaccess_knowledge.py",
    )


@pytest.fixture(scope="session")
def tools(knowledge):
    """The mcp_tools module (only the TechAccess subset is exercised
    here; the existing CAAI grant-search tools remain covered by their
    own tests, if any).

    We pre-register the knowledge module so the tools module's
    ``from agents.grants.nsf_techaccess_knowledge import ...`` resolves.
    The same trick is applied to a stub for ``agents.grants.caai_knowledge``
    and ``shared.primitives`` — primitives is the real thing, but
    caai_knowledge needs to load standalone (without the package init).
    """
    # Real shared.primitives — imported via package path is fine since
    # shared.primitives has no a2a dependency.
    import shared.primitives  # noqa: F401

    # Load caai_knowledge by path so ``from agents.grants.caai_knowledge ...``
    # resolves without triggering agents.grants.__init__.
    caai_path = _GRANTS / "caai_knowledge.py"
    _load_module_by_path("agents.grants.caai_knowledge", caai_path)
    _load_module_by_path(
        "agents.grants.nsf_techaccess_knowledge",
        _GRANTS / "nsf_techaccess_knowledge.py",
    )

    return _load_module_by_path(
        "agents.grants.mcp_tools",
        _GRANTS / "mcp_tools.py",
    )
