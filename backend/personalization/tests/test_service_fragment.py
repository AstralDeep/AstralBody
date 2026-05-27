"""Tests for the personalization prompt-fragment assembly (feature 025, T010/T012).

These validate the *mechanism* that keeps personality subordinate to
compliance (FR-015): the personality block is rendered last and behind the
explicit "never overrides compliance" preamble, after memory/context/skills.
The full behavioral guarantee (the LLM actually obeying) is an integration
test that requires the live stack.
"""
from __future__ import annotations

from personalization.service import PERSONALITY_PREAMBLE, PersonalizationService


class _FakeRepo:
    def __init__(self, profile=None, memory=None):
        self._profile = profile
        self._memory = memory or []

    def list_memory(self, user_id):
        return list(self._memory)

    def get_profile(self, user_id):
        return self._profile


def _service_with(profile=None, memory=None) -> PersonalizationService:
    svc = PersonalizationService(db=None)  # repo replaced below; db unused
    svc.repo = _FakeRepo(profile=profile, memory=memory)
    return svc


def test_empty_user_returns_empty_fragment():
    svc = _service_with()
    assert svc.build_prompt_fragment(None) == ""
    assert svc.build_prompt_fragment("u1") == ""


def test_personality_is_last_and_subordinate():
    profile = {
        "profession": "Clinical researcher",
        "goals": ["Track grant deadlines"],
        "personality": {"tone": "concise", "directness": "high", "notes": "No filler."},
    }
    memory = [{"category": "preference", "value": "Prefers bullet points"}]
    svc = _service_with(profile=profile, memory=memory)

    fragment = svc.build_prompt_fragment("u1", skill_lines=["grants:search_grants — find funding"])

    # All sections present
    assert "WHAT YOU REMEMBER" in fragment
    assert "USER CONTEXT" in fragment
    assert "ENABLED SKILLS" in fragment
    assert PERSONALITY_PREAMBLE in fragment

    # Ordering: memory -> context -> skills -> personality (subordinate, last)
    i_mem = fragment.index("WHAT YOU REMEMBER")
    i_ctx = fragment.index("USER CONTEXT")
    i_skill = fragment.index("ENABLED SKILLS")
    i_persona = fragment.index(PERSONALITY_PREAMBLE)
    assert i_mem < i_ctx < i_skill < i_persona, fragment

    # The persona content is rendered behind the subordinate preamble.
    assert fragment.index("concise") > i_persona


def test_profile_without_personality_omits_style_block():
    profile = {"profession": "Nurse", "goals": [], "personality": {}}
    svc = _service_with(profile=profile)
    fragment = svc.build_prompt_fragment("u1")
    assert "USER CONTEXT" in fragment
    assert PERSONALITY_PREAMBLE not in fragment
