#!/usr/bin/env python3
"""Union MCP tool registry for the ML Services agent.

Merges the three per-service tool slices (classify / forecaster / llm_factory)
into one ``TOOL_REGISTRY`` and adds the single ``_credentials_check`` internal
tool that probes all three optional credential bundles and reports a per-bundle
verdict plus an aggregate one.

Tool-name layout (feature 029 consolidation contract):

- The five verbs CLASSify and Forecaster shared are exposed twice with
  service prefixes: ``classify_submit_dataset`` … ``classify_delete_dataset``
  and ``forecaster_submit_dataset`` … ``forecaster_delete_dataset``.
- Every other tool keeps its original name: ``set_column_types``,
  ``get_ml_options``, ``propose_training_config``, ``get_output_log``,
  ``set_column_roles``, ``list_models``, ``chat_with_model``,
  ``create_embedding``, ``transcribe_audio``.
"""
import logging
import os
import sys
from typing import Any, Dict, Set

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from astralprims import Card, Table

from agents.ml_services import _wrapper, classify_tools, forecaster_tools, llm_factory_tools
from agents.ml_services._wrapper import ui as _ui

logger = logging.getLogger("MlServicesAgentMCPTools")

AGENT_ID = "ml-services-1"

LONG_RUNNING_TOOLS: Set[str] = (
    classify_tools.LONG_RUNNING_TOOLS
    | forecaster_tools.LONG_RUNNING_TOOLS
    | llm_factory_tools.LONG_RUNNING_TOOLS
)

# (registry key, display label, bundle, per-service probe) for the union
# credential check. Order fixed: CLASSify, Forecaster, LLM-Factory.
_BUNDLE_PROBES = (
    ("classify", "CLASSify", _wrapper.CLASSIFY_BUNDLE, classify_tools._credentials_check),
    ("forecaster", "Forecaster", _wrapper.FORECASTER_BUNDLE, forecaster_tools._credentials_check),
    ("llm_factory", "LLM-Factory", _wrapper.LLM_FACTORY_BUNDLE, llm_factory_tools._credentials_check),
)

# Aggregate-verdict precedence over the configured bundles: any hard auth
# failure outranks reachability problems, which outrank shape surprises.
_VERDICT_PRECEDENCE = ("auth_failed", "unreachable", "unexpected")


def _credentials_check(**kwargs) -> Dict[str, Any]:
    """Probe all three optional credential bundles and report per-bundle verdicts.

    Each configured bundle (both of its keys saved and non-empty) is probed
    with the same per-service logic the predecessor agents used; bundles with
    no saved credentials are reported as ``not_configured`` and excluded from
    the aggregate verdict, because all three bundles are optional.

    Args:
        **kwargs: Tool kwargs carrying ``_credentials`` (the union credential
            map holding any of the six CLASSIFY_*/FORECASTER_*/LLM_FACTORY_*
            keys) and optionally ``_credentials_stale``.

    Returns:
        An MCP UI response dict whose single Card holds a three-row status
        Table, and whose ``_data`` carries the aggregate ``credential_test``
        verdict (``ok`` / ``auth_failed`` / ``unreachable`` / ``unexpected``),
        a human-readable ``detail`` summary, and the per-bundle verdict map
        under ``bundles``.
    """
    credentials = kwargs.get("_credentials", {}) or {}
    bundles: Dict[str, Dict[str, str]] = {}
    rows = []
    for key, label, bundle, probe in _BUNDLE_PROBES:
        if not _wrapper.bundle_configured(credentials, bundle):
            verdict = {
                "credential_test": "not_configured",
                "detail": f"{bundle.display_name} credentials are not saved.",
            }
        else:
            verdict = probe(**kwargs)
        bundles[key] = verdict
        rows.append([label, verdict.get("credential_test", "unexpected"),
                     verdict.get("detail") or "—"])

    configured = {
        key: v for key, v in bundles.items()
        if v.get("credential_test") != "not_configured"
    }
    summary = "; ".join(
        f"{label}: {bundles[key].get('credential_test')}"
        for key, label, _bundle, _probe in _BUNDLE_PROBES
    )
    if not configured:
        overall = "unexpected"
        detail = (
            "No ML Services credentials are configured. Save at least one "
            "service's URL and API key in the agent's settings."
        )
    else:
        overall = "ok"
        for level in _VERDICT_PRECEDENCE:
            if any(v.get("credential_test") == level for v in configured.values()):
                overall = level
                break
        detail = summary

    status_table = Table(headers=["Service", "Status", "Detail"], rows=rows)
    return _ui(
        [Card(title="ML Services credential status", content=[status_table])],
        data={"credential_test": overall, "detail": detail, "bundles": bundles},
    )


TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {
    "_credentials_check": {
        "function": _credentials_check,
        "description": (
            "Internal: probe the saved URL + API key of each configured service "
            "bundle (CLASSify, Forecaster, LLM-Factory) with a cheap authenticated "
            "GET and report per-bundle verdicts."
        ),
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": True},
        "scope": "tools:read",
    },
    **classify_tools.TOOL_REGISTRY,
    **forecaster_tools.TOOL_REGISTRY,
    **llm_factory_tools.TOOL_REGISTRY,
}
