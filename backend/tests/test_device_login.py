"""051 — RFC 8628 device-login broker (`orchestrator/device_login.py`).

DB-free: the IdP is a scripted fake injected through the module's HTTP seams;
audit + revocation are recorded through monkeypatched module hooks. Covers the
contract in specs/051-apple-native-clients/contracts/device-login.md.
"""
from __future__ import annotations

import base64
import hashlib
import json
import sys
import time
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from cryptography.fernet import Fernet  # noqa: E402

from orchestrator import device_login as dl  # noqa: E402

AUTHORITY = "https://idp.example/realms/astral"
DEVICE_EP = f"{AUTHORITY}/protocol/openid-connect/auth/device"
TOKEN_EP = f"{AUTHORITY}/protocol/openid-connect/token"


# ---------------------------------------------------------------------------
# Fakes.
# ---------------------------------------------------------------------------

def fake_get(*, with_device_ep: bool = True):
    async def _get(url):
        assert url == f"{AUTHORITY}/.well-known/openid-configuration"
        body = {"token_endpoint": TOKEN_EP}
        if with_device_ep:
            body["device_authorization_endpoint"] = DEVICE_EP
        return 200, body
    return _get


class FakePost:
    """Scripted (status, body) responses; records every call."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    async def __call__(self, url, data):
        self.calls.append((url, dict(data)))
        if not self.responses:
            raise AssertionError("unexpected IdP call")
        return self.responses.pop(0)


def start_body(**over):
    body = {
        "device_code": "dev-code-123",
        "user_code": "WDJB-MJHT",
        "verification_uri": f"{AUTHORITY}/device",
        "verification_uri_complete": f"{AUTHORITY}/device?user_code=WDJB-MJHT",
        "expires_in": 600,
        "interval": 5,
    }
    body.update(over)
    return body


def jwt_with(roles=("user",), sub="user-1"):
    payload = {"sub": sub, "realm_access": {"roles": list(roles)}}
    b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"eyJhbGciOiJub25lIn0.{b64}.sig"


def token_body(roles=("user",), sub="user-1"):
    return {
        "access_token": jwt_with(roles, sub),
        "refresh_token": "refresh-secret-xyz",
        "expires_in": 300,
        "refresh_expires_in": 1800,
        "token_type": "Bearer",
        "not_before_policy": 0,          # must NOT be relayed
        "session_state": "leak-me-not",  # must NOT be relayed
    }


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("FF_DEVICE_LOGIN", "1")
    monkeypatch.setenv("WEB_SESSION_ENC_KEY", Fernet.generate_key().decode())
    # BOTH spellings: shared/__init__ re-aliases KEYCLOAK_AUTHORITY over the
    # legacy alias at (possibly lazy) import time (unprefixed name wins), so a
    # container run with a real .env would otherwise clobber the fake realm.
    monkeypatch.setenv("KEYCLOAK_AUTHORITY", AUTHORITY)
    monkeypatch.setenv("KEYCLOAK_AUTHORITY", AUTHORITY)
    monkeypatch.setenv("KEYCLOAK_CLIENT_ID", "astral-frontend")
    monkeypatch.setenv(
        "KEYCLOAK_ALLOWED_AZP", "astral-desktop,astral-mobile,astral-ios,astral-macos,astral-watch"
    )
    monkeypatch.setenv("KEYCLOAK_DEVICE_CLIENTS", "astral-watch")
    dl.reset_state()

    audits = []

    async def _audit(action, sub, description, *, outcome="success"):
        audits.append({"action": action, "sub": sub,
                       "description": description, "outcome": outcome})

    revoked = []

    async def _revoke(refresh_token, client_id):
        revoked.append((refresh_token, client_id))

    monkeypatch.setattr(dl, "_audit", _audit)
    monkeypatch.setattr(dl, "_revoke_refresh", _revoke)
    yield {"audits": audits, "revoked": revoked}
    dl.reset_state()


async def do_start(post=None, get=None, client="astral-watch", ip="1.2.3.4"):
    return await dl.start(
        client, ip,
        http_post=post or FakePost((200, start_body())),
        http_get=get or fake_get(),
    )


# ---------------------------------------------------------------------------
# start
# ---------------------------------------------------------------------------

async def test_start_happy_path_shape(env):
    post = FakePost((200, start_body()))
    out = await do_start(post=post)
    assert post.calls[0][0] == DEVICE_EP
    assert post.calls[0][1]["client_id"] == "astral-watch"
    # PKCE rides on the device-auth request (realms enforcing a client PKCE
    # policy refuse without it; harmless elsewhere).
    assert post.calls[0][1]["code_challenge_method"] == "S256"
    assert len(post.calls[0][1]["code_challenge"]) == 43   # b64url(sha256), no pad
    assert out["user_code"] == "WDJB-MJHT"
    assert out["verification_uri_complete"].endswith("user_code=WDJB-MJHT")
    assert out["expires_in"] == 600 and out["interval"] == 5
    assert isinstance(out["handle"], str) and len(out["handle"]) > 40
    # handle is opaque: the device_code must not be recoverable without the key
    assert "dev-code-123" not in out["handle"]
    # backend-generated QR (FR-021): PNG + raw matrix
    assert base64.b64decode(out["qr_png_base64"]).startswith(b"\x89PNG")
    assert isinstance(out["qr_matrix"], list) and out["qr_matrix"]
    assert [a["action"] for a in env["audits"]] == ["device_login_started"]
    assert "dev-code-123" not in env["audits"][0]["description"]


async def test_start_flag_off_fails_closed(env, monkeypatch):
    monkeypatch.setenv("FF_DEVICE_LOGIN", "0")
    with pytest.raises(dl.DeviceLoginUnavailable):
        await do_start()


async def test_start_requires_encryption_key(env, monkeypatch):
    monkeypatch.delenv("WEB_SESSION_ENC_KEY", raising=False)
    monkeypatch.delenv("OFFLINE_GRANT_ENC_KEY", raising=False)
    with pytest.raises(dl.DeviceLoginUnavailable):
        await do_start()


async def test_start_unknown_client_rejected(env):
    for bad in ("", "astral-frontend", "astral-mobile", "evil"):
        with pytest.raises(dl.UnknownClient):
            await do_start(client=bad)


async def test_start_realm_without_device_grant_fails_closed(env):
    with pytest.raises(dl.DeviceLoginUnavailable) as exc:
        await do_start(get=fake_get(with_device_ep=False))
    assert "device_authorization_endpoint" in str(exc.value)


async def test_start_rate_limited_per_address(env):
    for _ in range(dl._START_MAX_PER_WINDOW):
        await do_start(post=FakePost((200, start_body())))
    with pytest.raises(dl.RateLimited):
        await do_start()
    # a different address is unaffected
    await do_start(post=FakePost((200, start_body())), ip="5.6.7.8")


async def test_start_idp_refusal_is_unavailable(env):
    with pytest.raises(dl.DeviceLoginUnavailable):
        await do_start(post=FakePost((400, {"error": "invalid_client"})))


# ---------------------------------------------------------------------------
# poll
# ---------------------------------------------------------------------------

async def test_poll_pending_then_local_slow_down(env):
    out = await do_start()
    handle = out["handle"]
    # jump past the initial interval so the first poll reaches the IdP
    dl._POLL_STATE[dl._handle_digest(handle)]["next_ok"] = 0.0
    post = FakePost((400, {"error": "authorization_pending"}))
    res = await dl.poll(handle, "1.2.3.4", http_post=post, http_get=fake_get())
    assert res == {"status": "pending", "interval": 5}
    # immediate re-poll is answered locally — the fake has no scripted response
    res2 = await dl.poll(handle, "1.2.3.4", http_post=post, http_get=fake_get())
    assert res2["status"] == "slow_down"
    assert len(post.calls) == 1


async def test_poll_slow_down_from_idp_bumps_interval(env):
    out = await do_start()
    handle = out["handle"]
    dl._POLL_STATE[dl._handle_digest(handle)]["next_ok"] = 0.0
    post = FakePost((400, {"error": "slow_down"}))
    res = await dl.poll(handle, "1.2.3.4", http_post=post, http_get=fake_get())
    assert res == {"status": "slow_down", "interval": 10}


async def test_poll_approved_releases_filtered_tokens_once(env):
    start_post = FakePost((200, start_body()))
    out = await do_start(post=start_post)
    handle = out["handle"]
    dl._POLL_STATE[dl._handle_digest(handle)]["next_ok"] = 0.0
    post = FakePost((200, token_body()))
    res = await dl.poll(handle, "1.2.3.4", http_post=post, http_get=fake_get())
    assert res["status"] == "approved"
    # PKCE round trip: the token poll carries the verifier whose S256 equals
    # the challenge sent at start — proving it survived the sealed handle.
    verifier = post.calls[0][1]["code_verifier"]
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    assert challenge == start_post.calls[0][1]["code_challenge"]
    tokens = res["tokens"]
    assert tokens["refresh_token"] == "refresh-secret-xyz"
    assert tokens["token_type"] == "Bearer"
    # relay is a strict allow-list
    assert "session_state" not in tokens and "not_before_policy" not in tokens
    assert [a["action"] for a in env["audits"]] == [
        "device_login_started", "device_login_approved"]
    assert env["audits"][1]["sub"] == "user-1"
    # no token material in audit descriptions
    assert "refresh-secret-xyz" not in json.dumps(env["audits"])
    # single-use: the handle is dead now
    with pytest.raises(dl.InvalidHandle):
        await dl.poll(handle, "1.2.3.4", http_post=FakePost(), http_get=fake_get())


async def test_poll_roleless_denied_and_revoked(env):
    out = await do_start()
    handle = out["handle"]
    dl._POLL_STATE[dl._handle_digest(handle)]["next_ok"] = 0.0
    post = FakePost((200, token_body(roles=("offline_access",), sub="nobody-9")))
    res = await dl.poll(handle, "1.2.3.4", http_post=post, http_get=fake_get())
    assert res == {"status": "denied", "reason": "denied_no_access"}
    assert env["revoked"] == [("refresh-secret-xyz", "astral-watch")]
    assert env["audits"][-1]["action"] == "device_login_denied"
    assert env["audits"][-1]["outcome"] == "failure"


async def test_poll_user_denied(env):
    out = await do_start()
    handle = out["handle"]
    dl._POLL_STATE[dl._handle_digest(handle)]["next_ok"] = 0.0
    post = FakePost((400, {"error": "access_denied"}))
    res = await dl.poll(handle, "1.2.3.4", http_post=post, http_get=fake_get())
    assert res == {"status": "denied", "reason": "access_denied"}
    with pytest.raises(dl.InvalidHandle):
        await dl.poll(handle, "1.2.3.4", http_post=FakePost(), http_get=fake_get())


async def test_poll_expired_at_idp_and_locally(env):
    out = await do_start()
    handle = out["handle"]
    dl._POLL_STATE[dl._handle_digest(handle)]["next_ok"] = 0.0
    res = await dl.poll(handle, "1.2.3.4",
                        http_post=FakePost((400, {"error": "expired_token"})),
                        http_get=fake_get())
    assert res == {"status": "expired"}

    # locally-expired handle never reaches the IdP
    out2 = await do_start(post=FakePost((200, start_body(expires_in=1))))
    handle2 = out2["handle"]
    digest = dl._handle_digest(handle2)
    dl._POLL_STATE[digest]["next_ok"] = 0.0
    time.sleep(1.1)
    res2 = await dl.poll(handle2, "1.2.3.4", http_post=FakePost(), http_get=fake_get())
    assert res2 == {"status": "expired"}
    assert env["audits"][-1]["action"] == "device_login_expired"


async def test_poll_garbage_handle(env):
    with pytest.raises(dl.InvalidHandle):
        await dl.poll("not-a-handle", "1.2.3.4",
                      http_post=FakePost(), http_get=fake_get())


async def test_poll_handle_from_other_key_is_invalid(env, monkeypatch):
    out = await do_start()
    handle = out["handle"]
    monkeypatch.setenv("WEB_SESSION_ENC_KEY", Fernet.generate_key().decode())
    with pytest.raises(dl.InvalidHandle):
        await dl.poll(handle, "1.2.3.4", http_post=FakePost(), http_get=fake_get())


# ---------------------------------------------------------------------------
# refresh
# ---------------------------------------------------------------------------

async def test_refresh_passthrough(env):
    post = FakePost((200, token_body()))
    out = await dl.refresh("astral-watch", "some-refresh",
                           http_post=post, http_get=fake_get())
    assert out["access_token"] and out["token_type"] == "Bearer"
    assert "session_state" not in out
    assert post.calls[0][0] == TOKEN_EP
    assert post.calls[0][1]["grant_type"] == "refresh_token"


async def test_refresh_rejected_and_validated(env):
    with pytest.raises(dl.RefreshRejected):
        await dl.refresh("astral-watch", "bad",
                         http_post=FakePost((400, {"error": "invalid_grant"})),
                         http_get=fake_get())
    with pytest.raises(dl.UnknownClient):
        await dl.refresh("astral-frontend", "x",
                         http_post=FakePost(), http_get=fake_get())
    with pytest.raises(dl.RefreshRejected):
        await dl.refresh("astral-watch", "   ",
                         http_post=FakePost(), http_get=fake_get())


async def test_refresh_flag_off_fails_closed(env, monkeypatch):
    monkeypatch.setenv("FF_DEVICE_LOGIN", "0")
    with pytest.raises(dl.DeviceLoginUnavailable):
        await dl.refresh("astral-watch", "rt",
                         http_post=FakePost(), http_get=fake_get())


async def test_refresh_idp_unreachable_is_unavailable(env):
    """A transport-level failure talking to the IdP surfaces as unavailable
    (transient), not a credential rejection."""
    async def _boom(_url, _data):
        raise RuntimeError("connection refused")

    with pytest.raises(dl.DeviceLoginUnavailable):
        await dl.refresh("astral-watch", "rt", http_post=_boom, http_get=fake_get())


async def test_refresh_200_without_access_token_is_rejected(env):
    """A 200 that carries no access_token is still a rejection, not success."""
    with pytest.raises(dl.RefreshRejected):
        await dl.refresh("astral-watch", "rt",
                         http_post=FakePost((200, {"token_type": "Bearer"})),
                         http_get=fake_get())


async def test_flag_default_is_on(env, monkeypatch):
    monkeypatch.delenv("FF_DEVICE_LOGIN", raising=False)
    assert dl.flag_on() is True
    monkeypatch.setenv("FF_DEVICE_LOGIN", "false")
    assert dl.flag_on() is False
