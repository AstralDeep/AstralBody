"""Feature 067 (C-2): a2a_card_to_custom must not invent phantom agent ids.

The A2A discovery fallback used to slugify an agent's display name into an id
(e.g. "Windows Tools (code & system)" -> "windows-tools-(code-&-system)") or use
a base URL's host:port as the id, diverging from the agent's real id and
creating phantom permission rows. These tests pin the cleaned behaviour.
"""
from shared.a2a_bridge import (
    a2a_card_to_custom,
    custom_card_to_a2a,
    _slugify_agent_id,
)
from shared.protocol import AgentCard as CustomAgentCard


def _custom(name: str, agent_id: str = "x") -> CustomAgentCard:
    return CustomAgentCard(
        name=name, description="d", agent_id=agent_id,
        version="1.0.0", skills=[], metadata={},
    )


def test_slugify_strips_punctuation_and_collapses():
    assert _slugify_agent_id("Windows Tools (code & system)") == "windows-tools-code-system"
    assert _slugify_agent_id("  A  B  ") == "a-b"
    assert _slugify_agent_id("") == "agent"
    assert _slugify_agent_id("Already-Clean-1") == "already-clean-1"


def test_no_interface_slugs_clean_id_not_raw_name():
    # url="" → the win_agent case (no interface in its card) → slug the name,
    # but cleanly: never "windows-tools-(code-&-system)".
    a2a = custom_card_to_a2a(_custom("Windows Tools (code & system)"), "")
    out = a2a_card_to_custom(a2a)
    assert out.agent_id == "windows-tools-code-system"
    assert "(" not in out.agent_id and "&" not in out.agent_id


def test_base_url_host_port_is_rejected():
    # http://host:8771 → last segment "host.docker.internal:8771" is NOT a slug.
    a2a = custom_card_to_a2a(
        _custom("Windows Tools (code & system)"), "http://host.docker.internal:8771"
    )
    out = a2a_card_to_custom(a2a)
    assert out.agent_id == "windows-tools-code-system"
    assert ":" not in out.agent_id and out.agent_id != "8771"


def test_clean_url_path_segment_is_used():
    a2a = custom_card_to_a2a(_custom("Some Agent"), "http://host:9003/some-agent-1")
    out = a2a_card_to_custom(a2a)
    assert out.agent_id == "some-agent-1"


def test_explicit_agent_id_override_wins():
    a2a = custom_card_to_a2a(_custom("Windows Tools (code & system)"), "http://host:8771")
    out = a2a_card_to_custom(a2a, agent_id="windows-tools-1")
    assert out.agent_id == "windows-tools-1"
