"""US-22: Claude Connectors agent tests."""

import pytest

from agents.connectors.mcp_tools_office import (
    handle_excel_generate,
    handle_ppt_outline,
    handle_word_document,
    handle_outlook_email,
    handle_pitch_template,
)
from agents.connectors.mcp_tools_dev import (
    handle_code_review,
    handle_constitution_critique,
)
from agents.connectors.mcp_tools_runtime import handle_adaptive_routing
from agents.connectors.mcp_tools_creative import (
    handle_blender,
    handle_adobe,
    handle_canva,
    handle_artifacts,
    handle_graphs,
    handle_design,
)


def _comps(result):
    """Extract serialized components from a create_ui_response dict."""
    return result["_ui_components"]


def _by_type(comps, typename):
    return [c for c in comps if c.get("type") == typename]


# ---------------------------------------------------------------------------
# Office Tools
# ---------------------------------------------------------------------------

class TestExcel:
    def test_generates_table_and_download(self):
        result = handle_excel_generate({
            "title": "Test Data",
            "columns": ["Name", "Value"],
            "rows": [["A", "1"], ["B", "2"]],
        })
        comps = _comps(result)
        assert len(_by_type(comps, "table")) == 1
        downloads = _by_type(comps, "file_download")
        assert len(downloads) == 1
        assert downloads[0]["filename"] == "Test Data.csv"

    def test_description_or_title_in_header(self):
        result = handle_excel_generate({
            "title": "No Desc",
            "columns": ["X"],
            "rows": [["1"]],
        })
        texts = _by_type(_comps(result), "text")
        assert any("No Desc" in t.get("content", "") for t in texts)


class TestPowerPoint:
    def test_generates_slide_collapsibles(self):
        result = handle_ppt_outline({
            "title": "My Deck",
            "slides": [
                {"title": "Intro", "bullets": ["Hello", "World"]},
                {"title": "Conclusion", "bullets": ["Thanks"]},
            ],
        })
        comps = _comps(result)
        collapsibles = _by_type(comps, "collapsible")
        assert len(collapsibles) == 2

    def test_description_rendered(self):
        result = handle_ppt_outline({
            "title": "Deck",
            "slides": [],
            "description": "Subtitle",
        })
        texts = _by_type(_comps(result), "text")
        assert any("Subtitle" in t.get("content", "") for t in texts)


class TestWord:
    def test_generates_collapsible_sections(self):
        result = handle_word_document({
            "title": "Report",
            "sections": [
                {"heading": "Section 1", "content": "Hello world"},
            ],
        })
        comps = _comps(result)
        collapsibles = _by_type(comps, "collapsible")
        assert len(collapsibles) == 1
        assert collapsibles[0]["title"] == "Section 1"

    def test_download_button_by_default(self):
        result = handle_word_document({
            "title": "Doc",
            "sections": [{"heading": "A", "content": "B"}],
        })
        assert len(_by_type(_comps(result), "file_download")) == 1

    def test_download_can_be_disabled(self):
        result = handle_word_document({
            "title": "Doc",
            "sections": [{"heading": "A", "content": "B"}],
            "include_download": False,
        })
        assert len(_by_type(_comps(result), "file_download")) == 0


class TestOutlook:
    def test_generates_email_preview(self):
        result = handle_outlook_email({
            "to": "alice@example.com",
            "subject": "Hello",
            "body": "This is the body.",
        })
        comps = _comps(result)
        containers = _by_type(comps, "container")
        assert len(containers) >= 1

    def test_cc_and_priority(self):
        result = handle_outlook_email({
            "to": "a@b.com",
            "subject": "Urgent",
            "body": "ASAP",
            "cc": "manager@b.com",
            "priority": "high",
        })
        comps = _comps(result)
        container = _by_type(comps, "container")[0]
        children = container.get("children", [])
        texts = [c for c in children if c.get("type") == "text"]
        assert any("high" in t.get("content", "") for t in texts)


class TestPitchTemplates:
    def test_all_template_types_exist(self):
        types = ["startup", "sales", "investor", "product", "project", "strategy"]
        for t in types:
            result = handle_pitch_template({"template_type": t})
            comps = _comps(result)
            assert len(comps) > 2

    def test_custom_title(self):
        result = handle_pitch_template({"template_type": "startup", "custom_title": "My Startup"})
        texts = _by_type(_comps(result), "text")
        assert any("My Startup" in t.get("content", "") for t in texts)


# ---------------------------------------------------------------------------
# Dev Tools
# ---------------------------------------------------------------------------

class TestCodeReview:
    def test_detects_eval(self):
        result = handle_code_review({
            "code": "x = eval(user_input)",
            "language": "python",
        })
        collapsibles = _by_type(_comps(result), "collapsible")
        assert any("Security Notes" in c.get("title", "") for c in collapsibles)

    def test_detects_innerhtml(self):
        result = handle_code_review({
            "code": "el.innerHTML = untrusted;",
            "language": "javascript",
        })
        collapsibles = _by_type(_comps(result), "collapsible")
        assert any("Security Notes" in c.get("title", "") for c in collapsibles)

    def test_no_issues_clean_code(self):
        result = handle_code_review({
            "code": "x = 1\ny = 2\nprint(x + y)",
            "language": "python",
        })
        alerts = _by_type(_comps(result), "alert")
        assert any("No issues" in (a.get("title") or "") for a in alerts)


class TestConstitutionCritique:
    def test_detects_missing_tests(self):
        result = handle_constitution_critique({
            "spec": "We will add database tables for user profiles.",
            "spec_title": "Profile Spec",
        })
        alerts = _by_type(_comps(result), "alert")
        messages = " ".join(a.get("message", "") for a in alerts)
        assert "test" in messages.lower()

    def test_detects_missing_privacy(self):
        result = handle_constitution_critique({
            "spec": "Create a new endpoint for user data.",
            "spec_title": "User Data Spec",
        })
        alerts = _by_type(_comps(result), "alert")
        messages = " ".join(a.get("message", "") for a in alerts)
        assert "privacy" in messages.lower()

    def test_clean_spec_passes(self):
        result = handle_constitution_critique({
            "spec": "This spec includes testing, privacy, PHI redaction, audit logging, and migration plans.",
            "spec_title": "Compliant Spec",
        })
        alerts = _by_type(_comps(result), "alert")
        assert any("No issues" in (a.get("title") or "") for a in alerts)


# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------

class TestAdaptiveRouting:
    def test_routes_weather_query(self):
        result = handle_adaptive_routing({"query": "what is the weather forecast"})
        comps = _comps(result)
        assert len(_by_type(comps, "text")) >= 1

    def test_routes_office_query(self):
        result = handle_adaptive_routing({"query": "create an excel spreadsheet"})
        comps = _comps(result)
        assert len(comps) >= 2

    def test_no_match_returns_info(self):
        result = handle_adaptive_routing({"query": "xyzzy nothing matches this"})
        alerts = _by_type(_comps(result), "alert")
        assert any("No strong matches" in (a.get("title") or "") for a in alerts)


# ---------------------------------------------------------------------------
# Creative / Stubs
# ---------------------------------------------------------------------------

class TestCreativeStubs:
    def test_blender_returns_stub(self):
        result = handle_blender({"action": "debug"})
        alerts = _by_type(_comps(result), "alert")
        assert any("external API" in a.get("message", "") for a in alerts)

    def test_adobe_returns_stub(self):
        result = handle_adobe({"app": "photoshop"})
        alerts = _by_type(_comps(result), "alert")
        assert any("external API" in a.get("message", "") for a in alerts)

    def test_canva_returns_stub(self):
        result = handle_canva({"design_type": "poster"})
        alerts = _by_type(_comps(result), "alert")
        assert any("external API" in a.get("message", "") for a in alerts)

    def test_artifacts_generates_cards(self):
        result = handle_artifacts({
            "title": "Sales Dashboard",
            "sections": [
                {"widget_type": "metric", "title": "Revenue", "data_source": "DB"},
                {"widget_type": "chart", "title": "Trend", "data_source": "API"},
            ],
        })
        cards = _by_type(_comps(result), "card")
        assert len(cards) == 2

    def test_graphs_returns_nodes_and_edges(self):
        result = handle_graphs({
            "nodes": ["A", "B", "C"],
            "edges": [{"source": "A", "target": "B", "label": "depends"}],
        })
        collapsibles = _by_type(_comps(result), "collapsible")
        assert len(collapsibles) == 2

    def test_design_returns_palette(self):
        result = handle_design({"context": "web", "style_preferences": "corporate"})
        cards = _by_type(_comps(result), "card")
        assert len(cards) > 0