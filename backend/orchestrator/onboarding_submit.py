"""030-finish-soul-integration — interpret onboarding ParamPicker submits (025 T021).

Feature 025's onboarding panels (``personalization/panels.py``) render
ParamPicker forms whose ``submit_message_template`` posts a deterministic chat
message when the user confirms (e.g. "Save my personalization profile —
profession: X; goals: Y"). Nothing interpreted those messages, so onboarding
selections were silently dropped.

Because the templates are fixed strings, this is handled deterministically
(pre-LLM) rather than via an LLM meta-tool: more reliable, no model dependency.
The orchestrator calls :func:`is_onboarding_submit` early in the chat path and,
when it matches, :func:`handle_submit` persists the values through the existing
personalization repository / tool-permission gates and returns a confirmation.
"""
import logging
from typing import List, Optional, Tuple

logger = logging.getLogger("Orchestrator.OnboardingSubmit")

_PROFILE_PREFIX = "Save my personalization profile —"
_SKILLS_PREFIX = "Enable these skills for me:"
_PERSONALITY_PREFIX = "Set my assistant personality —"


def is_onboarding_submit(message: str) -> bool:
    """True if ``message`` is one of the three onboarding submit templates."""
    m = (message or "").strip()
    return m.startswith(_PROFILE_PREFIX) or m.startswith(_SKILLS_PREFIX) or m.startswith(_PERSONALITY_PREFIX)


def _kv_tail(text: str, prefix: str) -> str:
    return text.strip()[len(prefix):].strip()


def _parse_fields(tail: str) -> dict:
    """Parse 'a: x; b: y; c: z' into {a: x, b: y, c: z} (order-independent)."""
    out: dict = {}
    for chunk in tail.split(";"):
        if ":" not in chunk:
            continue
        key, _, val = chunk.partition(":")
        out[key.strip().lower()] = val.strip()
    return out


def _split_list(val: str) -> List[str]:
    parts = [p.strip() for p in val.replace(";", ",").split(",")]
    return [p for p in parts if p]


def _parse_skill_token(token: str) -> Optional[Tuple[str, str]]:
    """Parse 'agent-id:tool_name (scope)' -> (agent_id, tool_name)."""
    t = token.strip()
    if " (" in t:  # drop a trailing " (read)"/"(write)" scope hint
        t = t[: t.index(" (")].strip()
    if ":" not in t:
        return None
    agent_id, _, tool_name = t.partition(":")
    agent_id, tool_name = agent_id.strip(), tool_name.strip()
    if not agent_id or not tool_name:
        return None
    return agent_id, tool_name


async def handle_submit(orch, websocket, user_id: str, message: str,
                        chat_id: Optional[str], result_sink=None) -> bool:
    """Persist an onboarding submit. Returns True if handled (caller then stops).

    Never raises — onboarding must not break the chat path; failures surface a
    warning Alert and return True (handled).
    """
    from astralprims import Alert

    m = (message or "").strip()

    async def _say(text: str, variant: str = "success"):
        if result_sink is not None:
            result_sink(text, variant)
        try:
            await orch.send_ui_render(
                websocket, [Alert(message=text, variant=variant).to_dict()], target="chat")
        except Exception:  # pragma: no cover - delivery best-effort
            logger.debug("onboarding_submit: confirmation send failed", exc_info=True)

    try:
        svc = getattr(orch, "personalization_service", None)
        if svc is None:
            return False

        if m.startswith(_PROFILE_PREFIX):
            fields = _parse_fields(_kv_tail(m, _PROFILE_PREFIX))
            profession = fields.get("profession") or None
            goals = _split_list(fields.get("goals", "")) or None
            # Reuse the personalization PHI gate (parity with PUT /api/profile).
            from personalization.phi_gate import get_phi_gate
            gate = get_phi_gate()
            for txt in [profession or ""] + (goals or []):
                if txt and gate.contains_phi(txt):
                    await _say("I didn't save that — it looked like protected health "
                               "information. Please re-enter without PHI.", "warning")
                    return True
            svc.repo.upsert_profile(user_id, profession=profession, goals=goals)
            logger.info("onboarding.profile_saved",
                        extra={"user_id": user_id, "has_profession": bool(profession),
                               "goals": len(goals or [])})
            await _say("Saved your profile. I'll tailor things to that.")
            return True

        if m.startswith(_PERSONALITY_PREFIX):
            fields = _parse_fields(_kv_tail(m, _PERSONALITY_PREFIX))
            personality = {k: v for k, v in {
                "tone": fields.get("tone"),
                "directness": fields.get("directness"),
                "verbosity": fields.get("verbosity"),
                "notes": fields.get("notes"),
            }.items() if v}
            svc.repo.upsert_profile(user_id, personality=personality)
            logger.info("onboarding.personality_saved",
                        extra={"user_id": user_id, "keys": sorted(personality)})
            await _say("Updated your assistant's personality.")
            return True

        if m.startswith(_SKILLS_PREFIX):
            tail = _kv_tail(m, _SKILLS_PREFIX)
            tp = getattr(orch, "tool_permissions", None)
            if tp is None:
                return False
            enabled, denied = [], []
            for token in _split_list(tail):
                parsed = _parse_skill_token(token)
                if not parsed:
                    continue
                agent_id, tool_name = parsed
                try:
                    required_scope = tp.get_tool_scope(agent_id, tool_name)
                    # FR-011: enabling a skill can never exceed the user's grant.
                    if not tp.is_scope_enabled(user_id, agent_id, required_scope):
                        denied.append(tool_name)
                        continue
                    tp.set_skill_enabled(user_id, agent_id, tool_name, True)
                    enabled.append(tool_name)
                except Exception:
                    logger.debug("onboarding_submit: skill enable failed for %s:%s",
                                 agent_id, tool_name, exc_info=True)
                    denied.append(tool_name)
            logger.info("onboarding.skills_enabled",
                        extra={"user_id": user_id, "enabled": len(enabled),
                               "denied": len(denied)})
            msg = (f"Enabled {len(enabled)} skill(s)." if enabled
                   else "No skills were enabled.")
            if denied:
                msg += (f" {len(denied)} need a permission you haven't been granted "
                        "and were skipped.")
            await _say(msg, "success" if enabled else "warning")
            return True

    except Exception:
        logger.warning("onboarding_submit: failed to handle submit", exc_info=True)
        await _say("Something went wrong saving that. Please try again.", "warning")
        return True

    return False
