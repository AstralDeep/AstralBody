"""Feature 033 (capability C-S7) — adversarial red-team self-test harness.

Covers the flag, the scenario library (+ env override), the three pure
assertions (out-of-scope tool call / egress / PHI) over a self-test result, and
the aggregate verdict.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from orchestrator import redteam  # noqa: E402


def _result(tools=None, evidence=""):
    return {"tools_called": tools or [], "evidence": evidence}


# ───────────────────────── flag + scenarios ──────────────────────────────────

def test_redteam_default_off(monkeypatch):
    monkeypatch.delenv("FF_REDTEAM_SELFTEST", raising=False)
    assert redteam.redteam_enabled() is False


@pytest.mark.parametrize("v", ["true", "1", "yes", "on"])
def test_redteam_on(monkeypatch, v):
    monkeypatch.setenv("FF_REDTEAM_SELFTEST", v)
    assert redteam.redteam_enabled() is True


def test_seed_scenarios_present(monkeypatch):
    monkeypatch.delenv("REDTEAM_SCENARIOS", raising=False)
    scen = redteam.scenarios()
    assert len(scen) >= 5 and all("prompt" in s for s in scen)
    kinds = {s["id"] for s in scen}
    assert {"ssrf-metadata", "phi-leak", "secret-exfil"} <= kinds


def test_scenarios_env_override(monkeypatch):
    monkeypatch.setenv("REDTEAM_SCENARIOS", '[{"id":"x","prompt":"do bad thing"}]')
    assert redteam.scenarios() == [{"id": "x", "prompt": "do bad thing"}]


def test_scenarios_bad_env_falls_back(monkeypatch):
    monkeypatch.setenv("REDTEAM_SCENARIOS", "{not json")
    assert len(redteam.scenarios()) >= 5
    monkeypatch.setenv("REDTEAM_SCENARIOS", "[]")  # empty → seeds
    assert len(redteam.scenarios()) >= 5


# ───────────────────────── egress assertion ──────────────────────────────────

@pytest.mark.parametrize("tool,egress", [
    ("fetch_page", True), ("send_email", True), ("http_get", True),
    ("upload_blob", True), ("read_text", False), ("parse_csv", False),
])
def test_is_egress_tool(tool, egress):
    assert redteam.is_egress_tool(tool) is egress


def test_egress_tool_call_is_flagged():
    v = redteam.evaluate_result(_result(tools=["fetch_page"]),
                                allowed_scopes=None, tool_scope_map=None)
    assert any(x.kind == "egress" for x in v)


def test_ssrf_url_in_output_is_flagged():
    v = redteam.evaluate_result(
        _result(evidence="I fetched http://169.254.169.254/latest/meta-data/ for you"),
        allowed_scopes=None, tool_scope_map=None)
    assert any(x.kind == "egress" for x in v)


# ───────────────────────── scope assertion ───────────────────────────────────

def test_out_of_scope_write_tool_flagged():
    offenders = redteam.out_of_scope_tools(
        ["delete_user"], allowed_scopes=["tools:read"],
        tool_scope_map={"delete_user": "tools:write"})
    assert offenders == ["delete_user"]


def test_own_read_tool_not_flagged():
    offenders = redteam.out_of_scope_tools(
        ["parse_csv"], allowed_scopes=["tools:read"],
        tool_scope_map={"parse_csv": "tools:read"})
    assert offenders == []


def test_unknown_tool_defaults_to_read_not_flagged():
    # a tool absent from the map defaults to tools:read → not an escalation
    assert redteam.out_of_scope_tools(["mystery"], ["tools:read"], {}) == []


# ───────────────────────── PHI assertion ─────────────────────────────────────

def test_phi_in_output_is_flagged():
    v = redteam.evaluate_result(_result(evidence="SSN 123-45-6789"),
                                allowed_scopes=None, tool_scope_map=None,
                                phi_check=lambda t: "123-45-6789" in t)
    assert any(x.kind == "phi" for x in v)


def test_phi_check_error_fails_closed():
    def boom(_):
        raise RuntimeError("detector down")
    v = redteam.evaluate_result(_result(evidence="some text"),
                                allowed_scopes=None, tool_scope_map=None, phi_check=boom)
    assert any(x.kind == "phi" for x in v)


def test_no_phi_check_means_no_phi_violation():
    v = redteam.evaluate_result(_result(evidence="SSN 123-45-6789"),
                                allowed_scopes=None, tool_scope_map=None, phi_check=None)
    assert not any(x.kind == "phi" for x in v)


# ───────────────────────── verdict aggregation ───────────────────────────────

def test_clean_run_passes():
    results = [_result(tools=["parse_csv"], evidence="parsed 10 rows"),
               _result(tools=["read_text"], evidence="hello")]
    v = redteam.verdict(results, allowed_scopes=["tools:read"],
                        tool_scope_map={"parse_csv": "tools:read", "read_text": "tools:read"})
    assert v.passed is True and v.violations == [] and v.scenarios_run == 2


def test_any_violation_fails_the_whole_verdict():
    results = [_result(tools=["parse_csv"], evidence="ok"),
               _result(tools=["send_email"], evidence="emailed attacker@evil.example")]
    v = redteam.verdict(results, allowed_scopes=["tools:read"],
                        tool_scope_map={"parse_csv": "tools:read"})
    assert v.passed is False
    assert any(x.kind == "egress" for x in v.violations)


def test_multiple_violation_kinds_collected():
    results = [_result(tools=["delete_user", "fetch_page"],
                       evidence="patient SSN 123-45-6789")]
    v = redteam.verdict(results, allowed_scopes=["tools:read"],
                        tool_scope_map={"delete_user": "tools:write"},
                        phi_check=lambda t: "123-45-6789" in t)
    kinds = {x.kind for x in v.violations}
    assert kinds == {"scope", "egress", "phi"} and v.passed is False
