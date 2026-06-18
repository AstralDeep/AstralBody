"""Feature 033 (capability C-D9) — the deterministic WCAG audit wired as a
designer-side accessibility check.

When ``FF_UI_DESIGNER_A11Y`` is on, :func:`design_round`'s lint stage runs
``webrender.a11y.a11y_audit`` over the chosen arrangement and logs any findings
(image without alt, an action with no accessible label, an unlabelled
landmark/tab, an empty heading). The audit is advisory — it annotates/logs but
never drops a valid arrangement, so the fail-open posture is preserved. With the
flag OFF the audit never runs.

These tests drive the REAL ``design_round`` end-to-end (the LLM is a stub) and
assert against both the structured log and a spy on the real audit function.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from orchestrator import ui_designer  # noqa: E402
from orchestrator.ui_designer import design_round  # noqa: E402
from webrender import a11y  # noqa: E402

ALLOWED = {
    "container", "text", "card", "table", "list", "alert", "metric", "grid",
    "tabs", "image", "button", "hero", "badge", "ref",
}

_COMPS = [
    {"type": "table", "component_id": "A", "title": "Tbl", "_source_agent": "a", "_source_tool": "t"},
    {"type": "line_chart", "component_id": "B", "title": "Chart", "_source_agent": "a", "_source_tool": "t"},
]

# A draft whose garnish carries a KNOWN a11y problem: an UNTITLED card landmark
# (a11y_audit → "landmark has no label (title)") wrapping the two refs.
_DRAFT_BAD_A11Y = json.dumps({"layout": [
    {"type": "card", "content": [
        {"type": "ref", "component_id": "A"}, {"type": "ref", "component_id": "B"}]},
]})

# A clean draft: a titled card landmark.
_DRAFT_CLEAN = json.dumps({"layout": [
    {"type": "card", "title": "Results", "content": [
        {"type": "ref", "component_id": "A"}, {"type": "ref", "component_id": "B"}]},
]})


def _stub_llm(replies):
    it = iter(replies)

    async def _call(_messages):
        try:
            return next(it)
        except StopIteration:
            return "DONE"
    return _call


# ───────────────────────── flag ──────────────────────────────────────────────

def test_a11y_audit_flag_default_off(monkeypatch):
    monkeypatch.delenv("FF_UI_DESIGNER_A11Y", raising=False)
    assert ui_designer.a11y_audit_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "  TRUE  "])
def test_a11y_audit_flag_on(monkeypatch, value):
    monkeypatch.setenv("FF_UI_DESIGNER_A11Y", value)
    assert ui_designer.a11y_audit_enabled() is True


# ───────────────────────── audit flags a known problem ───────────────────────

async def test_designer_a11y_flags_unlabelled_landmark(monkeypatch, caplog):
    """ON: the designer flow runs a11y_audit on the final arrangement and logs
    the untitled-card landmark finding."""
    monkeypatch.setenv("FF_UI_DESIGNER_A11Y", "true")
    monkeypatch.setenv("FF_UI_DESIGNER_LINT", "false")  # isolate the a11y stage
    with caplog.at_level(logging.WARNING, logger="orchestrator.ui_designer"):
        out = await design_round(
            user_request="x", round_components=_COMPS, canvas_rows=[],
            chat_id="a1", layout_key="lk1", allowed_types=ALLOWED,
            llm_call=_stub_llm([_DRAFT_BAD_A11Y, "DONE"]), timeout_s=5, max_rounds=2,
        )
    assert out is not None
    # The arrangement is still delivered (advisory, never dropped) ...
    assert any(n.get("type") == "card" for n in out)
    # ... and the finding was logged.
    assert any("ui_designer.a11y_findings" in r.getMessage() for r in caplog.records)
    assert any("card" in r.getMessage() for r in caplog.records
               if "a11y_findings" in r.getMessage())


async def test_designer_a11y_runs_real_audit_on_final(monkeypatch):
    """Spy on the REAL a11y_audit to prove design_round actually calls it with
    the chosen arrangement (a card node present), and that it returns the known
    finding for the untitled card."""
    seen = {}
    real_audit = a11y.a11y_audit

    def _spy(components):
        result = real_audit(components)
        seen["components"] = components
        seen["result"] = result
        return result

    monkeypatch.setenv("FF_UI_DESIGNER_A11Y", "true")
    monkeypatch.setattr("webrender.a11y.a11y_audit", _spy)
    out = await design_round(
        user_request="x", round_components=_COMPS, canvas_rows=[],
        chat_id="a2", layout_key="lk2", allowed_types=ALLOWED,
        llm_call=_stub_llm([_DRAFT_BAD_A11Y, "DONE"]), timeout_s=5, max_rounds=2,
    )
    assert out is not None
    assert "components" in seen, "design_round never called a11y_audit"
    # It audited the real chosen arrangement (the untitled card is in it) ...
    assert any(isinstance(n, dict) and n.get("type") == "card" for n in seen["components"])
    # ... and the audit flagged the unlabelled landmark.
    assert any(f["type"] == "card" and "label" in f["issue"] for f in seen["result"])


async def test_designer_a11y_clean_arrangement_no_findings(monkeypatch, caplog):
    """A clean (titled) arrangement produces no a11y findings → no warning."""
    monkeypatch.setenv("FF_UI_DESIGNER_A11Y", "true")
    monkeypatch.setenv("FF_UI_DESIGNER_LINT", "false")
    with caplog.at_level(logging.WARNING, logger="orchestrator.ui_designer"):
        out = await design_round(
            user_request="x", round_components=_COMPS, canvas_rows=[],
            chat_id="a3", layout_key="lk3", allowed_types=ALLOWED,
            llm_call=_stub_llm([_DRAFT_CLEAN, "DONE"]), timeout_s=5, max_rounds=2,
        )
    assert out is not None
    assert not any("ui_designer.a11y_findings" in r.getMessage() for r in caplog.records)


# ───────────────────────── flag OFF + fail-open ──────────────────────────────

async def test_designer_a11y_off_does_not_run(monkeypatch):
    """OFF (default): a11y_audit is never invoked — a spy that would explode is
    never reached, and the arrangement is delivered unchanged."""
    monkeypatch.delenv("FF_UI_DESIGNER_A11Y", raising=False)

    def _boom(_components):
        raise AssertionError("a11y_audit must not run when the flag is off")

    monkeypatch.setattr("webrender.a11y.a11y_audit", _boom)
    out = await design_round(
        user_request="x", round_components=_COMPS, canvas_rows=[],
        chat_id="a4", layout_key="lk4", allowed_types=ALLOWED,
        llm_call=_stub_llm([_DRAFT_BAD_A11Y, "DONE"]), timeout_s=5, max_rounds=2,
    )
    assert out is not None
    assert any(n.get("type") == "card" for n in out)


async def test_designer_a11y_failure_is_fail_open(monkeypatch):
    """An a11y_audit that raises must never break the designer — the arrangement
    is still delivered (advisory check, fail-open)."""
    monkeypatch.setenv("FF_UI_DESIGNER_A11Y", "true")

    def _boom(_components):
        raise RuntimeError("audit exploded")

    monkeypatch.setattr("webrender.a11y.a11y_audit", _boom)
    out = await design_round(
        user_request="x", round_components=_COMPS, canvas_rows=[],
        chat_id="a5", layout_key="lk5", allowed_types=ALLOWED,
        llm_call=_stub_llm([_DRAFT_BAD_A11Y, "DONE"]), timeout_s=5, max_rounds=2,
    )
    assert out is not None  # never crashes
    assert any(n.get("type") == "card" for n in out)
