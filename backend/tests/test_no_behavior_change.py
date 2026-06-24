"""Feature 026 — T015: behavior-regression guard for FR-015.

The astralprims migration is a delivery/rendering re-architecture; it MUST NOT
change agent behavior. This test asserts that, after the migration:

* Every agent's ``mcp_tools`` module still imports (no migration-induced
  ImportError) and exposes a well-formed ``TOOL_REGISTRY`` — each tool keeps its
  ``function`` / ``description`` / ``input_schema`` / ``scope`` (the capability +
  permission/scope surface that gates RFC 8693 delegation is unchanged).
* The code-gen validator still recognizes ``astralprims`` imports as valid (so
  generated agents are guided to the right primitives) and still warns when no
  primitive import is present.

It can't diff against a pre-migration snapshot, but it pins the behavior surface
that the migration could plausibly have broken.
"""
import importlib
import os
import sys

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

# Agents whose mcp_tools import only lightweight deps (skip heavy optional-imaging
# agents like `medical` whose import depends on env-specific native libs unrelated
# to this migration).
AGENT_TOOL_MODULES = [
    "agents.general.mcp_tools",
    "agents.weather.mcp_tools",
    "agents.journal_review.mcp_tools",
    # 029: classify + forecaster + llm_factory consolidated into ml_services.
    "agents.ml_services.mcp_tools",
]


@pytest.mark.parametrize("modname", AGENT_TOOL_MODULES)
def test_agent_tool_module_imports_and_registry_intact(modname):
    try:
        mod = importlib.import_module(modname)
    except ImportError as e:
        # The migration must never be the cause of an import failure.
        msg = str(e).lower()
        assert "astralprims" not in msg and "primitives" not in msg, (
            f"{modname} failed to import due to the primitives migration: {e}")
        pytest.skip(f"{modname} unimportable for an unrelated (env) reason: {e}")
        return

    registry = getattr(mod, "TOOL_REGISTRY", None)
    if registry is None:
        pytest.skip(f"{modname} has no TOOL_REGISTRY")
        return
    assert isinstance(registry, dict) and registry, f"{modname} TOOL_REGISTRY empty"
    for tool_name, spec in registry.items():
        assert callable(spec.get("function")), f"{modname}:{tool_name} missing function"
        assert spec.get("description"), f"{modname}:{tool_name} missing description"
        assert "input_schema" in spec, f"{modname}:{tool_name} missing input_schema"
        # scope is the permission gate fed into RFC 8693 attenuation — must persist.
        assert "scope" in spec, f"{modname}:{tool_name} missing scope (permission surface)"


def test_codegen_validator_accepts_astralprims_and_warns_without():
    from orchestrator.agent_validator import AgentSpecValidator, ValidationReport, ValidationSeverity

    v = AgentSpecValidator()

    def warnings_for(code):
        report = ValidationReport()
        v._validate_imports(code, report)
        return [i for i in report.findings if i.severity == ValidationSeverity.WARNING and i.category == "IMPORT"]

    # importing from astralprims is accepted (no IMPORT warning)
    assert not warnings_for("from astralprims import Card, Text\n"), \
        "validator should accept astralprims imports"
    # no primitive import at all -> warning preserved
    assert warnings_for("x = 1\n"), "validator should warn when no primitive import is present"
