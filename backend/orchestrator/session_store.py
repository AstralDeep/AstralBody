"""Feature 028 — durable server-side web-session store (research D3/D5).

Backs ``web_auth``'s signed-cookie sessions with the ``web_session`` Postgres
table so sessions survive backend restarts and multi-instance deploys
(FR-008), honoring the feature-016 365-day hard cap anchored to the last
*interactive* login. Access/refresh tokens are Fernet-encrypted at rest under
``WEB_SESSION_ENC_KEY`` (falling back to ``OFFLINE_GRANT_ENC_KEY``, the
feature-025 convention). In production mode (``ASTRAL_ENV`` != development)
the absence of an encryption key is fail-closed: sessions cannot be persisted
and login is refused rather than storing tokens in the clear.

Also owns ``auth_revocation_queue`` — refresh tokens awaiting best-effort
revocation at Keycloak after an offline sign-out (FR-013; the server-side
analog of 016's client revocation queue).
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("orchestrator.session_store")

_DEV_VALUES = ("development", "dev")


def is_dev_mode() -> bool:
    """True only when the operator explicitly declared development mode.

    Unset/unknown ``ASTRAL_ENV`` means production: every 028 posture check
    fails closed by default (FR-015/FR-016).
    """
    return os.getenv("ASTRAL_ENV", "").strip().lower() in _DEV_VALUES


def assert_production_posture() -> None:
    """Fail-closed boot gate (028 FR-015): refuse to serve with mock auth on
    outside explicitly declared development mode. Raises ``SystemExit(78)``
    (EX_CONFIG) — called from ``Orchestrator.start``."""
    mock_on = os.getenv("VITE_USE_MOCK_AUTH", "").strip().lower() in ("1", "true", "yes")
    if mock_on and not is_dev_mode():
        logger.critical(
            "REFUSING TO START: USE_MOCK_AUTH is enabled but ASTRAL_ENV is not "
            "'development'. Mock authentication accepts any token as an admin "
            "user. Either set ASTRAL_ENV=development (local dev only) or set "
            "USE_MOCK_AUTH=false and configure KEYCLOAK_* for production."
        )
        raise SystemExit(78)  # EX_CONFIG


def _enc_key() -> Optional[bytes]:
    raw = os.getenv("WEB_SESSION_ENC_KEY") or os.getenv("OFFLINE_GRANT_ENC_KEY")
    return raw.encode() if raw else None


class SessionStoreError(Exception):
    """Raised when the store cannot operate safely (e.g. no key in prod)."""


class WebSessionStore:
    """Postgres-backed session CRUD with an in-process read-through cache."""

    def __init__(self, db=None):
        if db is None:
            from shared.database import Database
            db = Database()
        self.db = db
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._fernet = None
        key = _enc_key()
        if key:
            try:
                from cryptography.fernet import Fernet
                self._fernet = Fernet(key)
            except Exception:
                logger.exception("session_store: invalid WEB_SESSION_ENC_KEY (must be urlsafe-base64 Fernet)")
                self._fernet = None
        if self._fernet is None and not is_dev_mode():
            # Fail closed: production sessions must never hit disk unencrypted.
            raise SessionStoreError(
                "WEB_SESSION_ENC_KEY (or OFFLINE_GRANT_ENC_KEY) is required outside "
                "development mode — refusing to run with unencrypted session storage."
            )
        if self._fernet is None:
            logger.warning("session_store: DEV MODE — sessions stored without encryption at rest")

    # ── crypto ───────────────────────────────────────────────────────────
    def _enc(self, value: str) -> str:
        if self._fernet is None:
            return value or ""
        return self._fernet.encrypt((value or "").encode()).decode()

    def _dec(self, value: str) -> str:
        if self._fernet is None:
            return value or ""
        try:
            return self._fernet.decrypt((value or "").encode()).decode()
        except Exception:
            logger.warning("session_store: token decrypt failed (key rotated?) — treating session as dead")
            return ""

    # ── session CRUD ─────────────────────────────────────────────────────
    def create(self, sid: str, *, user_id: str, access_token: str,
               refresh_token: str, hard_max_seconds: int,
               resumed: bool = False) -> Dict[str, Any]:
        """Persist a new interactive session. Only this call sets the anchor."""
        now = int(time.time())
        row = {
            "sid": sid,
            "user_id": user_id,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "interactive_anchor": now,
            "hard_expires_at": now + int(hard_max_seconds),
            "last_refresh_at": now,
            "resumed": bool(resumed),
            "created_at": now,
        }
        self.db.execute(
            "INSERT INTO web_session (sid, user_id, access_token_enc, refresh_token_enc, "
            "interactive_anchor, hard_expires_at, last_refresh_at, resumed, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sid, user_id, self._enc(access_token), self._enc(refresh_token),
             row["interactive_anchor"], row["hard_expires_at"],
             row["last_refresh_at"], row["resumed"], row["created_at"]),
        )
        self._cache[sid] = row
        return row

    def get(self, sid: str) -> Optional[Dict[str, Any]]:
        """Return the live session (cap-checked); expired sessions are deleted."""
        row = self._cache.get(sid)
        if row is None:
            db_row = self.db.fetch_one("SELECT * FROM web_session WHERE sid = ?", (sid,))
            if not db_row:
                return None
            row = {
                "sid": db_row["sid"],
                "user_id": db_row["user_id"],
                "access_token": self._dec(db_row["access_token_enc"]),
                "refresh_token": self._dec(db_row["refresh_token_enc"]),
                "interactive_anchor": int(db_row["interactive_anchor"]),
                "hard_expires_at": int(db_row["hard_expires_at"]),
                "last_refresh_at": int(db_row["last_refresh_at"]),
                "resumed": bool(db_row.get("resumed")),
                "created_at": int(db_row["created_at"]),
            }
            if not row["access_token"] and not row["refresh_token"]:
                # Undecryptable (key rotation) — dead session.
                self.delete(sid)
                return None
            self._cache[sid] = row
        if int(time.time()) >= row["hard_expires_at"]:
            # 016 hard cap: only interactive login can start a new session.
            logger.info("session_store: session %s hit the 365-day cap — cleared", sid[:8])
            self.delete(sid)
            return None
        return row

    def update_tokens(self, sid: str, *, access_token: str, refresh_token: str) -> None:
        """Rotate tokens after a silent refresh. NEVER moves the anchor (016 FR-001)."""
        now = int(time.time())
        self.db.execute(
            "UPDATE web_session SET access_token_enc = ?, refresh_token_enc = ?, last_refresh_at = ? "
            "WHERE sid = ?",
            (self._enc(access_token), self._enc(refresh_token), now, sid),
        )
        row = self._cache.get(sid)
        if row:
            row.update(access_token=access_token, refresh_token=refresh_token, last_refresh_at=now)

    def mark_resumed(self, sid: str, resumed: bool = True) -> None:
        self.db.execute("UPDATE web_session SET resumed = ? WHERE sid = ?", (bool(resumed), sid))
        row = self._cache.get(sid)
        if row:
            row["resumed"] = bool(resumed)

    def delete(self, sid: str) -> Optional[Dict[str, Any]]:
        """Delete a session; returns the cached row (for revocation) if known."""
        row = self._cache.pop(sid, None)
        if row is None:
            db_row = self.db.fetch_one("SELECT * FROM web_session WHERE sid = ?", (sid,))
            if db_row:
                row = {
                    "sid": db_row["sid"],
                    "user_id": db_row["user_id"],
                    "access_token": self._dec(db_row["access_token_enc"]),
                    "refresh_token": self._dec(db_row["refresh_token_enc"]),
                }
        self.db.execute("DELETE FROM web_session WHERE sid = ?", (sid,))
        return row

    def delete_for_user(self, user_id: str) -> int:
        """Delete every session of a user (user-switch revocation, 016 FR-008)."""
        for sid in [s for s, r in self._cache.items() if r.get("user_id") == user_id]:
            self._cache.pop(sid, None)
        cur = self.db.execute("DELETE FROM web_session WHERE user_id = ?", (user_id,))
        return getattr(cur, "rowcount", 0)

    def purge_expired(self) -> int:
        """Opportunistic cleanup of hard-cap-expired rows."""
        now = int(time.time())
        for sid in [s for s, r in self._cache.items() if now >= r.get("hard_expires_at", 0)]:
            self._cache.pop(sid, None)
        cur = self.db.execute("DELETE FROM web_session WHERE hard_expires_at <= ?", (now,))
        return getattr(cur, "rowcount", 0)

    # ── revocation queue (FR-013) ────────────────────────────────────────
    def enqueue_revocation(self, user_id: str, refresh_token: str) -> None:
        if not refresh_token:
            return
        self.db.execute(
            "INSERT INTO auth_revocation_queue (user_id, refresh_token_enc, enqueued_at, attempts) "
            "VALUES (?, ?, ?, 0)",
            (user_id, self._enc(refresh_token), int(time.time())),
        )

    def pending_revocations(self, limit: int = 20) -> list:
        rows = self.db.fetch_all(
            "SELECT * FROM auth_revocation_queue ORDER BY enqueued_at ASC LIMIT ?", (limit,)
        )
        out = []
        for r in rows:
            out.append({
                "id": r["id"],
                "user_id": r["user_id"],
                "refresh_token": self._dec(r["refresh_token_enc"]),
                "attempts": int(r.get("attempts") or 0),
                "enqueued_at": int(r["enqueued_at"]),
            })
        return out

    def resolve_revocation(self, queue_id: int) -> None:
        self.db.execute("DELETE FROM auth_revocation_queue WHERE id = ?", (queue_id,))

    def bump_revocation_attempt(self, queue_id: int) -> None:
        self.db.execute(
            "UPDATE auth_revocation_queue SET attempts = attempts + 1 WHERE id = ?", (queue_id,)
        )
