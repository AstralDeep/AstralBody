"""Feature 028 T014 — shared JWKS cache (``shared/jwks_cache.py``, research D8).

Pre-028, ``Orchestrator.validate_token`` and ``orchestrator.auth.
get_current_user_payload`` fetched the Keycloak JWKS document on every token
validation. The shared cache gives both validators a 10-minute TTL plus a
kid-miss escape hatch (key rotation refetches immediately instead of failing
tokens for the rest of the window).

Covers: cache hit within TTL (no refetch), TTL expiry refetch, kid-miss
refetch-and-return, ``clear()`` semantics, per-URL keying, and source-level
assertions that BOTH call sites actually route through ``shared.jwks_cache``.

The network layer is isolated by monkeypatching the module-internal
``_fetch`` with a counting fake that mirrors the real cache-population
behavior; the clock is faked by swapping the module's ``time`` binding.
"""
from __future__ import annotations

import asyncio
import base64
import inspect
import json
import os
import sys
import types
import uuid

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from shared import jwks_cache


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _url() -> str:
    """Unique JWKS URL per test so the module-global cache can never leak
    state across tests (belt-and-braces on top of the autouse clear)."""
    return f"https://idp.example/realms/{uuid.uuid4()}/protocol/openid-connect/certs"


def _make_token(kid: str) -> str:
    """Minimal JWT-shaped string whose header carries the given kid."""
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "RS256", "kid": kid}).encode()
    ).rstrip(b"=").decode()
    return f"{header}.e30.sig"


@pytest.fixture(autouse=True)
def _clean_cache():
    jwks_cache.clear()
    yield
    jwks_cache.clear()


@pytest.fixture
def fetch_counter(monkeypatch):
    """Replace the network ``_fetch`` with a counting fake that populates the
    module cache exactly like the real one (jwks + fetched_at via the
    module's — possibly faked — clock)."""
    state = {"calls": 0, "jwks": {"keys": [{"kid": "k1", "kty": "RSA"}]}}

    async def _fake_fetch(jwks_url):
        state["calls"] += 1
        jwks = state["jwks"]
        jwks_cache._cache[jwks_url] = {
            "jwks": jwks,
            "fetched_at": jwks_cache.time.time(),
        }
        return jwks

    monkeypatch.setattr(jwks_cache, "_fetch", _fake_fetch)
    return state


@pytest.fixture
def fake_clock(monkeypatch):
    """Swap the module's ``time`` binding for a controllable clock. Both
    ``get_jwks``'s TTL check and the (faked) ``_fetch``'s fetched_at stamp
    read it through the module attribute, so advancing ``state['now']``
    moves the cache's notion of time."""
    state = {"now": 1_000_000.0}
    monkeypatch.setattr(
        jwks_cache, "time", types.SimpleNamespace(time=lambda: state["now"])
    )
    return state


# ---------------------------------------------------------------------------
# (1) Within-TTL cache hit
# ---------------------------------------------------------------------------

def test_second_call_within_ttl_does_not_refetch(fetch_counter):
    """028 D8: the second get_jwks for the same URL inside the TTL window is
    served from cache — exactly one underlying fetch."""
    url = _url()

    async def run():
        first = await jwks_cache.get_jwks(url)
        second = await jwks_cache.get_jwks(url)
        return first, second

    first, second = asyncio.run(run())
    assert fetch_counter["calls"] == 1
    assert first == second == fetch_counter["jwks"]


def test_within_ttl_with_known_kid_does_not_refetch(fetch_counter):
    """028 D8: supplying a token whose kid IS in the cached set must not
    defeat the cache (the escape hatch is for rotation only)."""
    url = _url()

    async def run():
        await jwks_cache.get_jwks(url)
        return await jwks_cache.get_jwks(url, token=_make_token("k1"))

    jwks = asyncio.run(run())
    assert fetch_counter["calls"] == 1
    assert jwks == fetch_counter["jwks"]


def test_malformed_token_does_not_defeat_cache(fetch_counter):
    """028 D8: a token whose header cannot be parsed yields kid=None, which
    must fall through to the cached document rather than refetching."""
    url = _url()

    async def run():
        await jwks_cache.get_jwks(url)
        return await jwks_cache.get_jwks(url, token="not-a-jwt")

    jwks = asyncio.run(run())
    assert fetch_counter["calls"] == 1
    assert jwks == fetch_counter["jwks"]


def test_cache_is_keyed_per_url(fetch_counter):
    """028 D8: distinct JWKS URLs are cached independently — one fetch each,
    and a hit on one URL never satisfies the other."""
    url_a, url_b = _url(), _url()

    async def run():
        await jwks_cache.get_jwks(url_a)
        await jwks_cache.get_jwks(url_b)
        await jwks_cache.get_jwks(url_a)
        await jwks_cache.get_jwks(url_b)

    asyncio.run(run())
    assert fetch_counter["calls"] == 2


# ---------------------------------------------------------------------------
# (2) TTL expiry
# ---------------------------------------------------------------------------

def test_ttl_expiry_refetches(fetch_counter, fake_clock):
    """028 D8: once the entry is older than the TTL, get_jwks refetches."""
    url = _url()

    asyncio.run(jwks_cache.get_jwks(url))
    assert fetch_counter["calls"] == 1

    fake_clock["now"] += jwks_cache._TTL_SECONDS + 1
    asyncio.run(jwks_cache.get_jwks(url))
    assert fetch_counter["calls"] == 2


def test_just_under_ttl_still_cached(fetch_counter, fake_clock):
    """028 D8 boundary: an entry one second younger than the TTL is still a
    cache hit (strict '< _TTL_SECONDS' comparison)."""
    url = _url()

    asyncio.run(jwks_cache.get_jwks(url))
    fake_clock["now"] += jwks_cache._TTL_SECONDS - 1
    asyncio.run(jwks_cache.get_jwks(url))
    assert fetch_counter["calls"] == 1


def test_exactly_at_ttl_refetches(fetch_counter, fake_clock):
    """028 D8 boundary: age == _TTL_SECONDS is NOT '< _TTL_SECONDS', so the
    entry is stale and a refetch happens."""
    url = _url()

    asyncio.run(jwks_cache.get_jwks(url))
    fake_clock["now"] += jwks_cache._TTL_SECONDS
    asyncio.run(jwks_cache.get_jwks(url))
    assert fetch_counter["calls"] == 2


# ---------------------------------------------------------------------------
# (3) kid-miss escape hatch (key rotation)
# ---------------------------------------------------------------------------

def test_kid_miss_refetches_once_and_returns_rotated_key(fetch_counter):
    """028 D8: a token minted with a kid absent from the cached set forces an
    immediate refetch (rotation), and the refreshed document — now carrying
    the new kid — is returned."""
    url = _url()

    async def run():
        await jwks_cache.get_jwks(url)  # primes cache with k1 only
        # IdP rotated: the next fetch will see both keys.
        fetch_counter["jwks"] = {
            "keys": [{"kid": "k1", "kty": "RSA"}, {"kid": "k2", "kty": "RSA"}]
        }
        return await jwks_cache.get_jwks(url, token=_make_token("k2"))

    jwks = asyncio.run(run())
    assert fetch_counter["calls"] == 2
    assert "k2" in jwks_cache._kids(jwks)


@pytest.mark.asyncio
async def test_kid_miss_refetch_updates_cache_for_subsequent_calls():
    """028 D8: the rotation refetch repopulates the cache, so a follow-up
    call with the same (new) kid is a hit — no third fetch."""
    url = _url()
    calls = {"n": 0}
    docs = [
        {"keys": [{"kid": "k1", "kty": "RSA"}]},
        {"keys": [{"kid": "k2", "kty": "RSA"}]},
    ]

    async def _fake_fetch(jwks_url):
        jwks = docs[min(calls["n"], len(docs) - 1)]
        calls["n"] += 1
        jwks_cache._cache[jwks_url] = {
            "jwks": jwks,
            "fetched_at": jwks_cache.time.time(),
        }
        return jwks

    original = jwks_cache._fetch
    jwks_cache._fetch = _fake_fetch
    try:
        await jwks_cache.get_jwks(url)
        rotated = await jwks_cache.get_jwks(url, token=_make_token("k2"))
        again = await jwks_cache.get_jwks(url, token=_make_token("k2"))
    finally:
        jwks_cache._fetch = original

    assert calls["n"] == 2
    assert rotated == again == docs[1]


# ---------------------------------------------------------------------------
# (4) clear()
# ---------------------------------------------------------------------------

def test_clear_empties_cache_and_forces_refetch(fetch_counter):
    """028 D8: clear() drops every entry; the next get_jwks goes back to the
    network."""
    url = _url()

    asyncio.run(jwks_cache.get_jwks(url))
    assert url in jwks_cache._cache

    jwks_cache.clear()
    assert jwks_cache._cache == {}

    asyncio.run(jwks_cache.get_jwks(url))
    assert fetch_counter["calls"] == 2


# ---------------------------------------------------------------------------
# (5) Call-site wiring — both 028 validators route through the shared cache
# ---------------------------------------------------------------------------

def test_orchestrator_validate_token_uses_shared_jwks_cache():
    """028 D8 call site #1: Orchestrator.validate_token imports get_jwks from
    shared.jwks_cache (replacing the pre-028 per-call aiohttp fetch)."""
    from orchestrator.orchestrator import Orchestrator

    src = inspect.getsource(Orchestrator.validate_token)
    assert "shared.jwks_cache" in src
    assert "get_jwks" in src


def test_orchestrator_auth_module_uses_shared_jwks_cache():
    """028 D8 call site #2: orchestrator/auth.py (REST validator
    get_current_user_payload) references shared.jwks_cache."""
    import orchestrator.auth as auth_mod

    module_src = inspect.getsource(auth_mod)
    assert "shared.jwks_cache" in module_src

    fn_src = inspect.getsource(auth_mod.get_current_user_payload)
    assert "shared.jwks_cache" in fn_src
    assert "get_jwks" in fn_src
