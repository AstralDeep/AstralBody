"""Initial-load welcome canvas — example queries as ordinary SDUI.

Server-driven per Constitution II: astralprims defines → orchestrator renders
→ ROTE adapts. Every client target receives the same component tree over the
normal ``ui_render`` path (no shell HTML, no client-specific code). The
example buttons dispatch the standard ``chat_message`` ui_event action, so
they work on any client that can press a button and degrade to readable text
on voice profiles.
"""
from typing import Any, Dict, List

from astralprims import Button, Card, Grids, Hero, Text

#: (title, caption, query) — one tile per example. Queries are aimed at the
#: post-029 agent catalog: connectors dashboards, weather, web_research,
#: summarizer, dice_roller, general system metrics.
WELCOME_EXAMPLES = [
    ("📊 Business dashboard",
     "Hero, metrics, charts and a schedule — arranged by the adaptive designer.",
     "Build a rich dashboard for a dog grooming business — booking requests, "
     "monthly revenue line chart, most popular services pie chart, and today's "
     "schedule as a table"),
    ("⛅ Weather outlook",
     "A week of forecasts charted, not just described.",
     "What's the weather forecast for Lexington, KY this week? Show it with charts"),
    ("🔎 Research brief",
     "Web research distilled into a multi-part brief with citations.",
     "Research the latest developments in small modular reactors and give me a cited brief"),
    ("📄 Summarize a page",
     "TL;DR, key points and quotable lines from any URL.",
     "Summarize https://en.wikipedia.org/wiki/Dog_grooming — give me a TL;DR and key points"),
    ("🎲 Roll some dice",
     "Random rolls with a live distribution chart.",
     "Roll 6d20 and chart the distribution of results"),
    ("🖥️ System status",
     "Live host metrics as KPI tiles and gauges.",
     "Show current system status with CPU and memory metrics"),
]


def welcome_components() -> List[Dict[str, Any]]:
    """The welcome canvas as plain component dicts (pre-ROTE).

    Not workspace components — no identities, never persisted; the canvas
    they occupy is replaced by the first real render/upsert of the session.
    """
    cards = [
        Card(title=title, content=[
            Text(content=caption, variant="caption"),
            Button(label="Run example", action="chat_message",
                   payload={"message": query}, variant="secondary"),
        ])
        for title, caption, query in WELCOME_EXAMPLES
    ]
    tree = [
        Hero(
            title="What would you like to build?",
            eyebrow="Welcome",
            subtitle=("Ask in plain language — agents answer with live, interactive "
                      "components: dashboards, charts, tables, timelines and cited briefs."),
            variant="gradient",
        ),
        Grids(columns=2, children=cards),
        Text(content="Run an example, or type your own request.", variant="caption"),
    ]
    return [c.to_dict() for c in tree]
