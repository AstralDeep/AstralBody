"""
SDUI Dashboard Home Page Builder.

Generates the home/welcome page as SDUI components, sent to authenticated
clients over WebSocket. Design matches the React ChatInterface empty state.

Colors:
  bg: #0F1221, surface: #1A1E2E, primary: #6366F1, secondary: #8B5CF6
  text: #F3F4F6, muted: #9CA3AF, accent: #06B6D4
"""
from typing import List, Dict, Any
from shared.primitives import (
    Container, Text, Button, Card, Grids, MetricCard, Divider,
)

SUGGESTIONS = [
    "Get me all patients over 30 and graph their ages",
    "What is my system's CPU and memory usage?",
    "Search Wikipedia for artificial intelligence",
    "Show me disk usage information",
]


def build_dashboard_page(
    agents: List[Dict[str, Any]],
    total_tools: int = 0,
    username: str = "",
) -> List[Dict[str, Any]]:
    """Generate SDUI dashboard home page matching the React design."""

    # --- Welcome Hero ---
    hero_children: List[Any] = [
        # Sparkles icon badge
        Container(
            children=[
                Text(
                    content="\u2728",
                    variant="h1",
                    id="hero-icon",
                    style={"fontSize": "28px", "textAlign": "center", "color": "#FFFFFF"},
                ),
            ],
            id="hero-badge",
            style={
                "width": "64px",
                "height": "64px",
                "borderRadius": "16px",
                "background": "linear-gradient(135deg, #6366F1, #8B5CF6)",
                "display": "flex",
                "alignItems": "center",
                "justifyContent": "center",
                "alignSelf": "center",
            },
        ),
        # Title
        Text(
            content="AstralDeep",
            variant="h1",
            id="hero-title",
            style={
                "textAlign": "center",
                "color": "#FFFFFF",
                "fontSize": "20px",
                "fontWeight": "600",
                "marginTop": "8px",
            },
        ),
        # Description
        Text(
            content=(
                "Ask anything \u2014 your connected agents will search, analyze, "
                "and visualize results as interactive UI components."
            ),
            variant="body",
            id="hero-desc",
            style={
                "textAlign": "center",
                "color": "#9CA3AF",
                "fontSize": "14px",
                "maxWidth": "420px",
                "alignSelf": "center",
                "marginBottom": "16px",
            },
        ),
    ]

    # --- Suggested Prompts (2-column grid) ---
    prompt_cards = []
    for i, suggestion in enumerate(SUGGESTIONS):
        prompt_cards.append(
            Button(
                label=suggestion,
                action="chat_message",
                payload={"text": suggestion, "chat_id": "default"},
                variant="secondary",
                id=f"suggestion-{i}",
                style={
                    "textAlign": "left",
                    "fontSize": "12px",
                    "color": "#9CA3AF",
                    "padding": "12px",
                    "background": "rgba(255, 255, 255, 0.05)",
                    "border": "1px solid rgba(255, 255, 255, 0.05)",
                    "borderRadius": "8px",
                },
            )
        )

    suggestions_grid = Grids(
        columns=2,
        children=prompt_cards,
        gap=8,
        id="suggestions-grid",
        style={"maxWidth": "480px", "alignSelf": "center", "width": "100%"},
    )

    # --- Status Metrics ---
    connected_count = sum(1 for a in agents if a.get("status") == "connected")
    metrics = Grids(
        columns=2,
        children=[
            MetricCard(
                title="Agents",
                value=str(connected_count),
                subtitle="connected",
                icon="bot",
                id="metric-agents",
                style={
                    "background": "rgba(26, 30, 46, 0.6)",
                    "border": "1px solid rgba(255, 255, 255, 0.05)",
                    "borderRadius": "8px",
                },
            ),
            MetricCard(
                title="Tools",
                value=str(total_tools),
                subtitle="available",
                icon="wrench",
                id="metric-tools",
                style={
                    "background": "rgba(26, 30, 46, 0.6)",
                    "border": "1px solid rgba(255, 255, 255, 0.05)",
                    "borderRadius": "8px",
                },
            ),
        ],
        gap=12,
        id="status-metrics",
        style={"maxWidth": "320px", "alignSelf": "center", "width": "100%"},
    )

    # --- Assemble page ---
    page = Container(
        children=[
            *hero_children,
            suggestions_grid,
            Divider(id="dash-divider", style={"margin": "16px 0", "opacity": "0.1"}),
            metrics,
        ],
        id="dashboard-container",
        style={
            "display": "flex",
            "flexDirection": "column",
            "alignItems": "center",
            "justifyContent": "center",
            "minHeight": "70vh",
            "padding": "24px 16px",
            "gap": "8px",
        },
    )

    return [page.to_json()]
