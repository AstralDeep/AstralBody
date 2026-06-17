"""Deterministic pre-action policy engine — 033 Wave-4 (C-S3).

One ordered, fail-closed rule chain evaluated before a tool runs. Each rule is
DATA — a ``when`` predicate over the call context (tool, agent, roles, args) and
an ``effect`` (allow / deny / confirm / rewrite) — so an operator extends policy
without code (``POLICY_RULES`` env JSON). The first matching terminal rule
(deny/confirm/allow) wins; rewrite rules accumulate (e.g. redact a secret arg)
and evaluation continues; with no match the default is allow, so the engine is a
strictly ADDITIVE gate on top of the existing PHI/scope checks.

Pure + deterministic; a malformed rule never blocks (it just doesn't match), so
a bad config degrades to today's behavior. stdlib only — no new dependency.
"""
from __future__ import annotations

import fnmatch
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger("orchestrator.policy")

ALLOW, DENY, CONFIRM, REWRITE = "allow", "deny", "confirm", "rewrite"
#: 033 C-S8 — a terminal effect requiring the call to carry a valid single-use
#: transaction token (verified+consumed at dispatch by ``transaction_token``).
REQUIRE_TOKEN = "require_token"
_EFFECTS = (ALLOW, DENY, CONFIRM, REWRITE, REQUIRE_TOKEN)


@dataclass(frozen=True)
class PolicyDecision:
    effect: str = ALLOW
    reason: str = ""
    rule_id: str = ""
    args: Optional[Dict[str, Any]] = None  # rewritten args when changed, else None


def policy_enabled() -> bool:
    """FF_POLICY_ENGINE feature flag (default OFF; feature 033 C-S3). Off means
    the engine is not consulted (today's behavior); on evaluates ``POLICY_RULES``
    before each tool call. Additive — with no rules every call is allowed."""
    return os.getenv("FF_POLICY_ENGINE", "false").strip().lower() in ("1", "true", "yes", "on")


def _glob(pattern: Any, value: Any) -> bool:
    return fnmatch.fnmatchcase(str("" if value is None else value), str(pattern))


def _matches(when: Dict[str, Any], ctx: Dict[str, Any]) -> bool:
    """Declarative predicate (AND over the keys present). Unknown keys are
    ignored so forward-compatible configs don't crash."""
    if not isinstance(when, dict):
        return False
    roles = {str(r).lower() for r in (ctx.get("roles") or [])}
    if "tool" in when and not _glob(when["tool"], ctx.get("tool")):
        return False
    if "agent" in when and not _glob(when["agent"], ctx.get("agent")):
        return False
    if "role" in when and str(when["role"]).lower() not in roles:
        return False
    if "not_role" in when and str(when["not_role"]).lower() in roles:
        return False
    if "args_regex" in when:
        try:
            if not re.search(str(when["args_regex"]),
                             json.dumps(ctx.get("args") or {}, default=str), re.IGNORECASE):
                return False
        except re.error:
            return False
    return True


def _apply_rewrite(spec: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(args)
    if isinstance(spec, dict):
        for name in (spec.get("redact_args") or []):
            if name in out:
                out[name] = "[redacted by policy]"
    return out


def evaluate_policy(rules: List[Dict[str, Any]], context: Dict[str, Any]) -> PolicyDecision:
    """Evaluate the ordered rule chain. Returns the terminal decision (with any
    accumulated rewrites applied to ``args``)."""
    base_args = context.get("args") or {}
    args = dict(base_args)
    ctx = {**context, "args": args}
    for rule in (rules or []):
        if not isinstance(rule, dict):
            continue
        effect = str(rule.get("effect", "")).strip().lower()
        if effect not in _EFFECTS:
            continue
        try:
            if not _matches(rule.get("when") or {}, ctx):
                continue
        except Exception:  # a buggy rule must never block every call
            logger.debug("policy: rule %r failed to evaluate — skipping",
                         rule.get("id"), exc_info=True)
            continue
        if effect == REWRITE:
            args = _apply_rewrite(rule.get("rewrite"), args)
            ctx = {**ctx, "args": args}
            continue
        return PolicyDecision(effect=effect, reason=str(rule.get("reason", "")),
                              rule_id=str(rule.get("id", "")),
                              args=(args if args != base_args else None))
    return PolicyDecision(effect=ALLOW, args=(args if args != base_args else None))


#: Default rule set — empty so the engine is purely additive until an operator
#: configures rules. (The PHI gate and scope check remain enforced separately;
#: expressing them as seed rules here is a follow-on.)
_SEED_RULES: List[Dict[str, Any]] = []


def load_rules() -> List[Dict[str, Any]]:
    """The active rule chain: ``POLICY_RULES`` env JSON (a list of rule dicts),
    else the seed set. An unparseable/out-of-shape value falls back to seeds."""
    raw = os.getenv("POLICY_RULES")
    if not raw:
        return list(_SEED_RULES)
    try:
        rules = json.loads(raw)
    except (ValueError, TypeError) as exc:
        logger.warning("POLICY_RULES ignored (%s); using seed rules", exc)
        return list(_SEED_RULES)
    return rules if isinstance(rules, list) else list(_SEED_RULES)
