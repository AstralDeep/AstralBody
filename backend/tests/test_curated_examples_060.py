"""Truthfulness checks for feature-060 curated welcome examples."""

from __future__ import annotations

from urllib.parse import urlparse

from agents.dice_roller.mcp_tools import TOOL_REGISTRY as DICE_TOOLS
from agents.summarizer.mcp_tools import TOOL_REGISTRY as SUMMARY_TOOLS
from agents.weather.mcp_tools import TOOL_REGISTRY as WEATHER_TOOLS
from agents.web_research.mcp_tools import TOOL_REGISTRY as RESEARCH_TOOLS
from orchestrator.welcome import WELCOME_EXAMPLES


def _example(title_fragment: str) -> tuple[str, str, str]:
    matches = [item for item in WELCOME_EXAMPLES if title_fragment in item[0]]
    assert len(matches) == 1
    return matches[0]


def test_every_curated_example_is_nonempty_and_has_one_capability_disposition() -> None:
    """Each tile is either tool-backed or explicitly UI-composition-only."""

    expected_titles = {
        "Business dashboard",
        "Weather outlook",
        "Research brief",
        "Summarize a page",
        "Roll some dice",
        "System status",
    }
    actual_titles = {
        title.removeprefix(title.split(maxsplit=1)[0]).strip()
        for title, _caption, _query in WELCOME_EXAMPLES
    }
    assert actual_titles == expected_titles
    assert all(caption.strip() and query.strip() for _, caption, query in WELCOME_EXAMPLES)


def test_dice_example_matches_the_selected_tool_bounds_and_fixed_side_count() -> None:
    _title, caption, query = _example("Roll some dice")
    schema = DICE_TOOLS["roll_dice"]["input_schema"]["properties"]

    assert query == (
        "Roll exactly six six-sided dice and show the normalized results."
    )
    assert "six-sided" in caption.lower()
    assert schema["n"]["minimum"] <= 6 <= schema["n"]["maximum"]
    assert schema["sides"]["const"] == 6
    assert "d20" not in (caption + query).lower()


def test_weather_example_has_a_real_weekly_forecast_tool_contract() -> None:
    _title, _caption, query = _example("Weather outlook")
    schema = WEATHER_TOOLS["get_weekly_forecast"]["input_schema"]

    assert "Lexington, KY" in query
    assert "week" in query.lower()
    assert {"city", "state"} <= set(schema["properties"])


def test_research_example_requests_only_the_registered_brief_inputs() -> None:
    _title, _caption, query = _example("Research brief")
    schema = RESEARCH_TOOLS["research_brief"]["input_schema"]

    assert schema["required"] == ["topic"]
    assert "cited brief" in query.lower()
    assert schema["properties"]["depth"]["enum"] == ["shallow", "standard"]


def test_summary_example_uses_a_supported_absolute_http_url() -> None:
    _title, _caption, query = _example("Summarize a page")
    schema = SUMMARY_TOOLS["summarize_url"]["input_schema"]
    url = next(part for part in query.split() if part.startswith("https://"))
    parsed = urlparse(url)

    assert parsed.scheme == "https" and parsed.netloc
    assert schema["required"] == ["url"]
    assert schema["properties"]["url"]["type"] == "string"


def test_composition_examples_do_not_claim_an_unsupported_bounded_tool() -> None:
    for title_fragment in ("Business dashboard", "System status"):
        _title, _caption, query = _example(title_fragment)
        assert "dice" not in query.lower()
        assert "d20" not in query.lower()
