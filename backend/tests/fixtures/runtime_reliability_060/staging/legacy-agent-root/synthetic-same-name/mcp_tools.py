"""Inert synthetic tool module for the feature-060 migration fixture."""

AGENT_ID = "fixture-server-agent"


def fixture_status() -> dict[str, str]:
    """Return deterministic non-sensitive fixture output."""
    return {"status": "synthetic"}
