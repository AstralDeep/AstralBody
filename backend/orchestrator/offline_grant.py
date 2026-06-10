"""Encrypted offline-grant store for unattended job authorization (feature 025).

⚠️ SECURITY-CRITICAL — gated by task T057 (lead-dev security review) before merge.

At job-creation consent time (user present, live session) we capture the user's
Keycloak ``offline_access`` refresh token, encrypt it at rest, and record a hard
365-day expiry. Per run, the scheduler:
  1. loads the grant; refuses if revoked / expired (FR-024),
  2. exchanges the refresh token at Keycloak for a fresh short-lived access token,
  3. (caller then) intersects the job's consented scopes with the user's CURRENT
     scopes and performs the existing RFC 8693 delegated exchange.

The refresh token is encrypted with Fernet (``cryptography``, already a
dependency) using ``OFFLINE_GRANT_ENC_KEY``. It is NEVER returned by any API and
NEVER logged. If the key is unset, capture fails closed (no plaintext storage).
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Optional

import aiohttp

from agentic_settings import OFFLINE_GRANT_ENC_KEY, OFFLINE_GRANT_MAX_DAYS

logger = logging.getLogger("orchestrator.offline_grant")

_DAY_MS = 86_400_000


class OfflineGrantError(RuntimeError):
    """Raised when a grant cannot be captured, is unavailable, or is expired/revoked."""


def _fernet():
    """Build a Fernet from the configured key, or raise (fail closed)."""
    if not OFFLINE_GRANT_ENC_KEY:
        raise OfflineGrantError(
            "OFFLINE_GRANT_ENC_KEY is not configured; refusing to store offline grants."
        )
    from cryptography.fernet import Fernet  # already present via python-jose[cryptography] chain
    return Fernet(OFFLINE_GRANT_ENC_KEY.encode() if isinstance(OFFLINE_GRANT_ENC_KEY, str) else OFFLINE_GRANT_ENC_KEY)


def _now_ms() -> int:
    return int(time.time() * 1000)


class OfflineGrantStore:
    """Persistence + crypto for offline grants. Token bytes never leave this class."""

    def __init__(self, db=None) -> None:
        if db is None:
            # Lazy default (mirrors session_store.WebSessionStore): callers
            # like web_auth.auth_logout construct the store bare at sign-out.
            from shared.database import Database
            db = Database()
        self.db = db

    def capture(self, user_id: str, refresh_token: str, agent_id: Optional[str] = None) -> str:
        """Encrypt + store a refresh token captured from the live session.

        Returns the new grant id. Raises OfflineGrantError if encryption is not
        configured (fail closed — never store plaintext).
        """
        if not refresh_token:
            raise OfflineGrantError("no refresh token available in the session (offline_access not granted)")
        token_enc = _fernet().encrypt(refresh_token.encode("utf-8"))
        grant_id = str(uuid.uuid4())
        now = _now_ms()
        expires = now + OFFLINE_GRANT_MAX_DAYS * _DAY_MS
        self.db.execute(
            """INSERT INTO user_offline_grant
                   (id, user_id, agent_id, refresh_token_enc, issued_at, expires_at,
                    revoked_at, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?)""",
            (grant_id, user_id, agent_id, token_enc, now, expires, now, now),
        )
        return grant_id

    def _row(self, grant_id: str) -> Optional[dict]:
        row = self.db.fetch_one("SELECT * FROM user_offline_grant WHERE id = ?", (grant_id,))
        return dict(row) if row else None

    def revoke_for_user(self, user_id: str) -> int:
        """Revoke all of a user's grants (e.g. on logout / sign-out-everywhere)."""
        cur = self.db.execute(
            "UPDATE user_offline_grant SET revoked_at = ?, updated_at = ? WHERE user_id = ? AND revoked_at IS NULL",
            (_now_ms(), _now_ms(), user_id),
        )
        return getattr(cur, "rowcount", 0)

    def is_valid(self, grant_id: str) -> bool:
        row = self._row(grant_id)
        if not row:
            return False
        if row.get("revoked_at"):
            return False
        if int(row["expires_at"]) <= _now_ms():
            return False
        return True

    async def mint_access_token(self, grant_id: str) -> str:
        """Exchange the stored refresh token for a fresh access token at Keycloak.

        Raises OfflineGrantError on revoked/expired grants or refresh failure
        (e.g. Keycloak-side revocation) — the caller fails the run safe.
        """
        row = self._row(grant_id)
        if not row:
            raise OfflineGrantError("offline grant not found")
        if row.get("revoked_at"):
            raise OfflineGrantError("offline grant revoked")
        if int(row["expires_at"]) <= _now_ms():
            raise OfflineGrantError("offline grant expired (365-day cap reached); re-consent required")

        refresh_token = _fernet().decrypt(bytes(row["refresh_token_enc"])).decode("utf-8")

        token_url = os.getenv("KEYCLOAK_TOKEN_URL") or (
            f"{os.getenv('KEYCLOAK_URL', '').rstrip('/')}/realms/"
            f"{os.getenv('KEYCLOAK_REALM', 'astral')}/protocol/openid-connect/token"
        )
        client_id = os.getenv("KEYCLOAK_CLIENT_ID") or os.getenv("VITE_KEYCLOAK_CLIENT_ID", "astral-frontend")
        data = {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": refresh_token,
        }
        client_secret = os.getenv("KEYCLOAK_CLIENT_SECRET")
        if client_secret:
            data["client_secret"] = client_secret

        async with aiohttp.ClientSession() as session:
            async with session.post(token_url, data=data) as resp:
                if resp.status != 200:
                    # Keycloak-side revocation / invalid refresh → fail safe.
                    body = await resp.text()
                    logger.warning("offline_grant.refresh_failed", extra={"status": resp.status})
                    raise OfflineGrantError(f"refresh exchange failed ({resp.status}): {body[:200]}")
                payload = await resp.json()
        access_token = payload.get("access_token")
        if not access_token:
            raise OfflineGrantError("refresh exchange returned no access_token")
        return access_token
