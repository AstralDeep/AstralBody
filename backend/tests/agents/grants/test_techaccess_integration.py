"""Integration tests for the nine TechAccess MCP tools — exercised
end-to-end via the existing ``MCPServer.process_request`` so the
tool-error routing path (``_ui_components`` → ``error.code=-32000``)
matches what the orchestrator sees in production.

Implements T013 / T019 / T026.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

_BACKEND = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


@pytest.fixture(scope="module")
def server(tools):
    """Build an MCPServer wired to the freshly loaded tools module."""
    grants_dir = Path(_BACKEND) / "agents" / "grants"

    # mcp_server imports `from agents.grants.mcp_tools import TOOL_REGISTRY`
    # — that import binds at module-load time. Make sure agents.grants.mcp_tools
    # is the *tools* module the test fixture loaded (not a fresh import that
    # would re-trigger the conftest path-mangling).
    sys.modules.setdefault("agents.grants.mcp_tools", tools)

    spec = importlib.util.spec_from_file_location(
        "agents.grants.mcp_server",
        grants_dir / "mcp_server.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["agents.grants.mcp_server"] = module
    spec.loader.exec_module(module)
    return module.MCPServer()


def _build_request(name: str, arguments: dict, request_id: str = "1"):
    from shared.protocol import MCPRequest
    return MCPRequest(
        request_id=request_id,
        method="tools/call",
        params={"name": name, "arguments": arguments},
    )


# ─────────────────────────────────────────────────────────────────────────
#  tools/list
# ─────────────────────────────────────────────────────────────────────────


def test_tools_list_returns_all_tools(server):
    from shared.protocol import MCPRequest
    req = MCPRequest(request_id="1", method="tools/list", params={})
    resp = server.process_request(req)
    assert resp.result is not None
    names = {t["name"] for t in resp.result["tools"]}
    # All nine new tools must be exposed.
    expected = {
        "techaccess_scope_check",
        "draft_loi",
        "draft_proposal_section",
        "refine_section",
        "gap_check_section",
        "draft_supplemental_artifact",
        "draft_program_officer_questions",
        "prioritize_page_budget",
        "cite_deadlines",
    }
    assert expected.issubset(names)


# ─────────────────────────────────────────────────────────────────────────
#  Happy-path round-trips
# ─────────────────────────────────────────────────────────────────────────


def test_round_trip_techaccess_scope_check(server):
    req = _build_request(
        "techaccess_scope_check",
        {"user_request": "Draft Section 1 for the Kentucky Coordination Hub."},
    )
    resp = server.process_request(req)
    assert resp.error is None
    assert resp.ui_components is not None
    assert any(
        isinstance(c, dict) and c.get("title") == "Scope Decision"
        for c in resp.ui_components
    )


def test_round_trip_draft_loi_default(server):
    req = _build_request("draft_loi", {})
    resp = server.process_request(req)
    assert resp.error is None
    titles = [
        c.get("title", "") for c in resp.ui_components
        if isinstance(c, dict)
    ]
    assert "LOI Title" in titles
    assert "LOI Synopsis" in titles


def test_round_trip_draft_proposal_section_section_4(server):
    req = _build_request(
        "draft_proposal_section",
        {"section_key": "section_4"},
    )
    resp = server.process_request(req)
    assert resp.error is None
    titles = [
        c.get("title", "") for c in resp.ui_components
        if isinstance(c, dict)
    ]
    assert any("Section 4" in t for t in titles)


def test_round_trip_refine_section(server):
    req = _build_request(
        "refine_section",
        {
            "section_key": "section_1",
            "draft_text": (
                "The Hub will deliver training to all KCTCS students "
                "across the state."
            ),
        },
    )
    resp = server.process_request(req)
    assert resp.error is None
    titles = [
        c.get("title", "") for c in resp.ui_components
        if isinstance(c, dict)
    ]
    assert "Refined Draft" in titles
    assert "What Changed and Why" in titles


def test_round_trip_gap_check_section_4_metric_coverage(server):
    req = _build_request(
        "gap_check_section",
        {
            "section_key": "section_4",
            "draft_text": (
                "Year 1 milestones include convenings and training "
                "across Kentucky. We will track activities and report."
            ),
        },
    )
    resp = server.process_request(req)
    assert resp.error is None
    titles = [
        c.get("title", "") for c in resp.ui_components
        if isinstance(c, dict)
    ]
    assert "Required Sub-Element Coverage" in titles
    assert "Metric Coverage" in titles


def test_round_trip_letter_of_collaboration_for_kctcs(server):
    req = _build_request(
        "draft_supplemental_artifact",
        {
            "artifact_key": "letter_of_collaboration",
            "partner_key": "kctcs",
        },
    )
    resp = server.process_request(req)
    assert resp.error is None
    titles = [
        c.get("title", "") for c in resp.ui_components
        if isinstance(c, dict)
    ]
    assert any("Letter of Collaboration" in t for t in titles)


def test_round_trip_data_management_plan(server):
    req = _build_request(
        "draft_supplemental_artifact",
        {"artifact_key": "data_management_plan"},
    )
    resp = server.process_request(req)
    assert resp.error is None
    titles = [
        c.get("title", "") for c in resp.ui_components
        if isinstance(c, dict)
    ]
    assert "Data Management Plan" in titles


def test_round_trip_mentoring_plan_with_budget_flag(server):
    req = _build_request(
        "draft_supplemental_artifact",
        {
            "artifact_key": "mentoring_plan",
            "budget_includes_postdocs_or_grad_students": True,
        },
    )
    resp = server.process_request(req)
    assert resp.error is None


def test_round_trip_program_officer_questions(server):
    req = _build_request(
        "draft_program_officer_questions",
        {"max_questions": 4},
    )
    resp = server.process_request(req)
    assert resp.error is None


def test_round_trip_prioritize_page_budget(server):
    req = _build_request(
        "prioritize_page_budget",
        {
            "current_pages": {
                "section_1": 5.0,
                "section_2": 3.0,
                "section_3": 2.0,
                "section_4": 5.0,
                "section_5": 2.0,
            },
        },
    )
    resp = server.process_request(req)
    assert resp.error is None


def test_round_trip_cite_deadlines(server):
    req = _build_request("cite_deadlines", {})
    resp = server.process_request(req)
    assert resp.error is None
    titles = [
        c.get("title", "") for c in resp.ui_components
        if isinstance(c, dict)
    ]
    assert "NSF 26-508 Critical Deadlines" in titles


# ─────────────────────────────────────────────────────────────────────────
#  Refusal paths route as tool errors
# ─────────────────────────────────────────────────────────────────────────


def test_refusal_letter_of_support_routes_as_tool_error(server):
    """The mcp_server.process_request scans Alert(variant='error') in
    the UI components and re-emits the response as ``error={code: -32000,
    retryable: True}`` (mcp_server.py:86-106). That is what the
    orchestrator sees as a tool-level error."""
    req = _build_request(
        "draft_supplemental_artifact",
        {"artifact_key": "letter_of_support"},
    )
    resp = server.process_request(req)
    assert resp.error is not None
    assert resp.error.get("code") == -32000
    assert resp.error.get("retryable") is True
    assert "Letters of Support" in resp.error.get("message", "")


def test_refusal_unknown_section_in_draft(server):
    req = _build_request(
        "draft_proposal_section",
        {"section_key": "section_99"},
    )
    resp = server.process_request(req)
    assert resp.error is not None
    assert resp.error.get("code") == -32000


def test_refusal_unknown_artifact(server):
    req = _build_request(
        "draft_supplemental_artifact",
        {"artifact_key": "made_up_artifact"},
    )
    resp = server.process_request(req)
    assert resp.error is not None


def test_refusal_mentoring_plan_without_budget_flag(server):
    req = _build_request(
        "draft_supplemental_artifact",
        {"artifact_key": "mentoring_plan"},
    )
    resp = server.process_request(req)
    assert resp.error is not None
    assert "postdocs or graduate students" in resp.error.get("message", "")


def test_refusal_program_officer_only_resolved_topics(server):
    req = _build_request(
        "draft_program_officer_questions",
        {
            "topics": [
                "hub_responsibility_count",
                "page_limit_value",
                "round_one_award_count",
            ],
        },
    )
    resp = server.process_request(req)
    assert resp.error is not None


def test_refusal_page_budget_negative_value(server):
    req = _build_request(
        "prioritize_page_budget",
        {"current_pages": {"section_1": -1.0}},
    )
    resp = server.process_request(req)
    assert resp.error is not None


def test_unknown_tool_name_routes_as_unknown_method_error(server):
    req = _build_request("not_a_real_tool", {})
    resp = server.process_request(req)
    assert resp.error is not None
    assert resp.error.get("code") == -32601


# ─────────────────────────────────────────────────────────────────────────
#  Existing grants-agent tools still routable (FR-001 regression check)
# ─────────────────────────────────────────────────────────────────────────


def test_existing_get_caai_profile_still_routable(server):
    """Constitution / FR-001: merging the TechAccess capability into the
    existing grants agent must not regress its prior tool surface."""
    req = _build_request(
        "get_caai_profile",
        {"section": "mission"},
    )
    resp = server.process_request(req)
    # Either succeeds or surfaces a tool-level error — but the routing
    # layer must recognize the tool name.
    assert resp.error is None or resp.error.get("code") != -32601
