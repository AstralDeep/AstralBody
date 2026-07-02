"""Enforcement property tests for recursive delegation (spec 048 US1, FR-001).

**Written before the implementation** (test-first per the instruction and the
Constitution). They encode the four enforcement invariants against the intended
API in ``orchestrator.delegation`` and MUST fail (red) until that API exists,
then pass (green) once it does — demonstrable from version history.

Property-based: each invariant is checked over many *generated* scope sets and
chain shapes (seeded RNG), not a single example (FR-001). No third-party
generator dependency is introduced (Constitution V) — generation is stdlib
``random``.
"""
from __future__ import annotations

import random
import time

import pytest

from orchestrator import delegation as D

# ---- generators -----------------------------------------------------------

SCOPE_POOL = [
    "tools:read", "tools:write", "tools:search", "tools:system",
    "tool:search_web", "tool:read_file", "tool:send_email",
    "tool:modify_data", "tool:admin_delete", "tool:summarize",
]


def _rng(seed: int) -> random.Random:
    return random.Random(seed)


def _rand_scopes(rng: random.Random, k_min=1, k_max=6) -> list:
    k = rng.randint(k_min, min(k_max, len(SCOPE_POOL)))
    return sorted(rng.sample(SCOPE_POOL, k))


def base_token(sub="human:U1", agent="A", scopes=None, exp_in=300, now=None) -> dict:
    now = now or int(time.time())
    scopes = scopes if scopes is not None else ["tools:read", "tool:search_web"]
    return {
        "sub": sub,
        "act": {"sub": f"agent:{agent}"},
        "scope": " ".join(scopes),
        "iss": "mock-astral-delegation",
        "aud": "astral-agent-service",
        "iat": now,
        "exp": now + exp_in,
        "delegation": True,
    }


# ---- Invariant 1: monotonic scope attenuation (US1-AS2) -------------------

def test_attenuation_is_monotonic_over_generated_scopes():
    rng = _rng(1)
    now = int(time.time())
    for _ in range(300):
        parent_scopes = _rand_scopes(rng)
        requested = _rand_scopes(rng)
        parent = base_token(scopes=parent_scopes, now=now)
        child = D.mint_child_delegation(parent, "B", requested, now=now)
        child_scopes = set(child["scope"].split())
        # child ⊆ parent, always
        assert child_scopes <= set(parent_scopes)
        # child expiry never exceeds parent expiry
        assert int(child["exp"]) <= int(parent["exp"])


# ---- Invariant 2: no privilege escalation (US1-AS3) -----------------------

def test_no_escalation_even_with_hostile_request():
    rng = _rng(2)
    now = int(time.time())
    for _ in range(300):
        parent_scopes = _rand_scopes(rng, 1, 3)
        # hostile: request scopes the parent does NOT hold
        outside = [s for s in SCOPE_POOL if s not in parent_scopes]
        hostile = parent_scopes + rng.sample(outside, rng.randint(1, len(outside)))
        parent = base_token(scopes=parent_scopes, now=now)
        child = D.mint_child_delegation(parent, "B", hostile, now=now)
        child_scopes = set(child["scope"].split())
        # nothing outside the parent's authority can appear in the child
        assert child_scopes <= set(parent_scopes)
        # a brand-new tool the parent never had must never leak in
        assert "tool:admin_delete" not in child_scopes or "tool:admin_delete" in parent_scopes


def test_child_cannot_relax_expiry_or_audience():
    now = int(time.time())
    parent = base_token(scopes=["tools:read"], exp_in=60, now=now)
    # request a much later expiry via a crafted parent-like call: mint must cap it
    child = D.mint_child_delegation(parent, "B", ["tools:read"], now=now)
    assert int(child["exp"]) <= int(parent["exp"])
    # audience is inherited, never widened
    assert child.get("aud") == parent.get("aud")


# ---- Invariant 3: actor-chain completeness (US1-AS4) ----------------------

def test_actor_chain_is_complete_and_terminates_at_human():
    rng = _rng(3)
    now = int(time.time())
    for _ in range(100):
        depth = rng.randint(1, D.DEFAULT_MAX_DELEGATION_DEPTH)
        token = base_token(sub="human:U7", scopes=list(SCOPE_POOL), now=now)
        actors_expected = ["agent:A"]
        for i in range(depth):
            child_id = f"S{i}"
            token = D.mint_child_delegation(token, child_id, list(SCOPE_POOL), now=now)
            actors_expected.insert(0, f"agent:{child_id}")  # current-first
        chain = D.actor_chain(token)
        # every actor present, current-first, no missing link
        assert chain == actors_expected
        assert None not in chain
        # top-level sub is the human principal, terminating the chain
        assert token["sub"] == "human:U7"
        ok, reason = D.verify_delegation_chain(token, now=now, expected_human_sub="human:U7")
        assert ok, reason


def test_forged_or_broken_actor_chain_fails_verify():
    now = int(time.time())
    token = base_token(sub="human:U7", scopes=["tools:read"], now=now)
    token = D.mint_child_delegation(token, "B", ["tools:read"], now=now)
    # tamper: sever the nested prior-actor link
    token["act"]["act"] = None
    ok, _ = D.verify_delegation_chain(token, now=now)
    assert not ok


# ---- Invariant 4: depth bounding (US1-AS5) --------------------------------

def test_mint_refuses_beyond_max_depth():
    now = int(time.time())
    token = base_token(scopes=["tools:read"], now=now)
    # mint exactly up to the bound
    for i in range(D.DEFAULT_MAX_DELEGATION_DEPTH):
        token = D.mint_child_delegation(token, f"S{i}", ["tools:read"], now=now)
    # the next mint must fail closed
    with pytest.raises(D.DelegationDepthExceeded):
        D.mint_child_delegation(token, "TOODEEP", ["tools:read"], now=now)


def test_verify_rejects_received_over_depth_chain():
    now = int(time.time())
    token = base_token(scopes=["tools:read"], now=now)
    token = D.mint_child_delegation(token, "B", ["tools:read"], now=now)
    # forge an over-depth claim
    token[D.DELEGATION_DEPTH_CLAIM] = D.DEFAULT_MAX_DELEGATION_DEPTH + 5
    ok, reason = D.verify_delegation_chain(token, now=now)
    assert not ok
    assert "depth" in reason.lower()


# ---- Chain-of-custody + flag + provenance --------------------------------

def test_child_never_outlives_parent():
    rng = _rng(4)
    now = int(time.time())
    for _ in range(100):
        parent_exp_in = rng.randint(10, 600)
        parent = base_token(scopes=["tools:read"], exp_in=parent_exp_in, now=now)
        child = D.mint_child_delegation(parent, "B", ["tools:read"], now=now)
        assert int(child["exp"]) <= int(parent["exp"])


def test_flag_defaults_off():
    # FR-009: fail-closed default. With the flag unset, the capability is off.
    assert D.recursive_delegation_enabled() is False


def test_provenance_record_carries_hipaa_fields():
    now = int(time.time())
    parent = base_token(sub="human:U9", scopes=["tools:read", "tool:read_file"], now=now)
    child = D.mint_child_delegation(parent, "B", ["tool:read_file"], now=now)
    rec = D.delegation_chain_audit_record(parent, child, operation="read_file", tool="read_file")
    # §2.5 HIPAA audit-field checklist
    assert rec["acting_agent"] == "agent:B"
    assert rec["human_authorizer"] == "human:U9"
    assert rec["operation"] == "read_file"
    assert "scope" in rec and rec["scope"]
    assert rec["delegation_depth"] == 1
    assert isinstance(rec["timestamp"], int)
    assert rec["parent_actor"] == "agent:A"


# ---- Dispatch enforcement over the persistent transport (US3) -------------

def test_authorize_permits_in_scope_chained_call():
    now = int(time.time())
    parent = base_token(sub="human:U1", scopes=["tools:read", "tool:read_file"], now=now)
    child = D.mint_child_delegation(parent, "B", ["tools:read", "tool:read_file"], now=now)
    ok, reason = D.authorize_chained_tool_call(child, "read_file", "tools:read", now=now)
    assert ok, reason


def test_authorize_refuses_out_of_scope_tool():
    now = int(time.time())
    parent = base_token(sub="human:U1", scopes=["tools:read", "tool:read_file"], now=now)
    # child attenuates to read only; a write tool is outside its scope
    child = D.mint_child_delegation(parent, "B", ["tools:read", "tool:read_file"], now=now)
    ok, reason = D.authorize_chained_tool_call(child, "send_email", "tools:write", now=now)
    assert not ok


def test_authorize_refuses_over_depth_and_tampered_per_call():
    now = int(time.time())
    parent = base_token(sub="human:U1", scopes=["tools:read"], now=now)
    child = D.mint_child_delegation(parent, "B", ["tools:read"], now=now)
    # over-depth token
    over = dict(child)
    over[D.DELEGATION_DEPTH_CLAIM] = D.DEFAULT_MAX_DELEGATION_DEPTH + 3
    ok, _ = D.authorize_chained_tool_call(over, "read_file", "tools:read", now=now)
    assert not ok
    # tampered actor chain
    tampered = dict(child)
    tampered["act"] = {"sub": "agent:B", "act": None}  # severed prior link
    ok2, _ = D.authorize_chained_tool_call(tampered, "read_file", "tools:read", now=now)
    assert not ok2


def test_mid_session_rederivation_two_calls_same_token():
    # US3-AS4: the same sub-agent needs different tools later in the turn; each
    # call is re-derived/checked against the same attenuated token — no new
    # user-token round trip. Both in-scope tools pass; an out-of-scope one fails.
    now = int(time.time())
    parent = base_token(sub="human:U1",
                        scopes=["tools:read", "tool:read_file", "tool:search_web"], now=now)
    child = D.mint_child_delegation(
        parent, "B", ["tools:read", "tool:read_file", "tool:search_web"], now=now)
    assert D.authorize_chained_tool_call(child, "read_file", "tools:read", now=now)[0]
    assert D.authorize_chained_tool_call(child, "search_web", "tools:read", now=now)[0]
    assert not D.authorize_chained_tool_call(child, "modify_data", "tools:write", now=now)[0]
