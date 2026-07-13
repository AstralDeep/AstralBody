"""Feature 055 (US5) — revocable snapshot share grants (research.md D11).

Store layer only: the REST routes (``POST/GET/DELETE /api/share``, public
``GET /share/{token}``) live in ``api.py`` behind ``FF_ARTIFACT_SHARING``
(default OFF, fail-closed). A grant is an immutable rendition captured at
mint — the public route serves ``snapshot_html`` verbatim and never reads
live workspace rows, so later edits or chat deletion cannot change what a
link shows.

Guarantees:

- **Raw tokens are never stored.** :meth:`ShareGrantStore.mint` returns the
  256-bit urlsafe token exactly once and persists only its SHA-256 hex digest
  (``share_grant.token_sha256``, unique-indexed — lookup is a single indexed
  probe on the digest, no timing oracle beyond it).
- **PHI gate fail-closed at mint** (data-model.md, contracts/rest-endpoints.md):
  the snapshot's component JSON is screened by the feature-025 Presidio gate
  (``personalization.phi_gate``). A hit — or an unavailable/erroring
  analyzer — refuses the mint with an audited ``share.refused_phi``; nothing
  is written on refusal.
- **Revocation is immediate.** :meth:`ShareGrantStore.resolve` filters on
  ``revoked_at IS NULL`` per request, so a revoked grant can never serve
  again. ``snapshot_*`` columns have no UPDATE path (immutable after mint).
- Audit: ``share.minted`` / ``share.opened`` / ``share.revoked`` /
  ``share.refused_phi`` (class ``conversation``), no token material in rows.

All public methods are async and keep every DB / analyzer call off the event
loop (feature-052 loop guard).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import secrets
from typing import Any, Dict, List, Optional

from psycopg2.extras import Json

from audit.hooks import record_share_event
from personalization.phi_gate import get_phi_gate
from shared.feature_flags import flags

logger = logging.getLogger("orchestrator.artifact_share")

VALID_SCOPES = ("component", "canvas")


class ShareError(Exception):
    """Base for share-grant refusals (routes map subclasses to HTTP codes)."""


class SharingDisabledError(ShareError):
    """FF_ARTIFACT_SHARING is off — mint refused (routes 404 when off)."""


class SharePHIRefusedError(ShareError):
    """Snapshot flagged as PHI, or the PHI engine is unavailable (fail-closed).

    Routes map this to 403 ``{error: "phi_blocked"}``.
    """


def hash_token(token: str) -> str:
    """SHA-256 hex digest of a share token — the only form ever persisted."""
    return hashlib.sha256(token.encode()).hexdigest()


class ShareGrantStore:
    """CRUD over ``share_grant`` (schema in shared/database.py, 055.001)."""

    def __init__(self, db=None):
        if db is None:
            from shared.database import Database
            db = Database()
        self.db = db

    # ── mint ─────────────────────────────────────────────────────────────
    async def mint(
        self, *, user_id: str, chat_id: str, scope: str,
        snapshot_html: str, snapshot_json: Any,
        component_id: Optional[str] = None, expires_at=None,
    ) -> Dict[str, Any]:
        """Create a grant; returns ``{id, token, share_url, created_at, expires_at}``.

        The returned ``token`` is shown exactly once — it cannot be recovered
        from storage. Raises :class:`SharingDisabledError`,
        :class:`SharePHIRefusedError`, or ``ValueError`` on bad arguments.
        """
        # Defense in depth behind the route-level 404: the store itself
        # refuses to mint while the fail-closed flag is off.
        if not flags.is_enabled("artifact_sharing"):
            logger.info("share.refused_disabled user=%s chat=%s scope=%s",
                        user_id, chat_id, scope)
            raise SharingDisabledError("artifact sharing is disabled (FF_ARTIFACT_SHARING)")
        if scope not in VALID_SCOPES:
            raise ValueError(f"invalid share scope: {scope!r}")
        if scope == "component" and not component_id:
            raise ValueError("component-scoped share requires component_id")
        if not user_id or not chat_id or not snapshot_html or snapshot_json is None:
            raise ValueError("mint requires user_id, chat_id and a non-empty snapshot")

        # The HTML is rendered from these dicts, so gating the JSON covers
        # every piece of user data the link would expose (research D11).
        gate_text = json.dumps(snapshot_json, default=str)
        phi_hit = await asyncio.to_thread(get_phi_gate().contains_phi, gate_text)
        if phi_hit:
            logger.warning("share.refused_phi user=%s chat=%s scope=%s component=%s",
                           user_id, chat_id, scope, component_id)
            detail: Dict[str, Any] = {"scope": scope}
            if component_id:
                detail["component_id"] = component_id
            await record_share_event(
                user_id=user_id, action="refused_phi", chat_id=chat_id,
                outcome="failure",
                description="Share mint refused: snapshot flagged as PHI (fail-closed)",
                detail=detail,
            )
            raise SharePHIRefusedError("snapshot content flagged as PHI")

        token = secrets.token_urlsafe(32)
        row = await asyncio.to_thread(
            self._insert_grant, hash_token(token), user_id, chat_id, scope,
            component_id, snapshot_html, snapshot_json, expires_at,
        )
        detail = {"scope": scope}
        if component_id:
            detail["component_id"] = component_id
        await record_share_event(
            user_id=user_id, action="minted", chat_id=chat_id,
            share_id=row["id"],
            description=f"Share link minted ({scope})", detail=detail,
        )
        logger.info("share.minted share_id=%s user=%s chat=%s scope=%s component=%s",
                    row["id"], user_id, chat_id, scope, component_id)
        return {
            "id": row["id"],
            "token": token,
            "share_url": f"/share/{token}",
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
        }

    def _insert_grant(self, digest: str, user_id: str, chat_id: str, scope: str,
                      component_id: Optional[str], snapshot_html: str,
                      snapshot_json: Any, expires_at) -> Dict[str, Any]:
        self.db.execute(
            "INSERT INTO share_grant (token_sha256, user_id, chat_id, scope, "
            "component_id, snapshot_html, snapshot_json, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (digest, user_id, chat_id, scope, component_id, snapshot_html,
             Json(snapshot_json), expires_at),
        )
        return self.db.fetch_one(
            "SELECT id, created_at, expires_at FROM share_grant WHERE token_sha256 = ?",
            (digest,),
        )

    # ── owner views ──────────────────────────────────────────────────────
    async def list_grants(self, user_id: str) -> List[Dict[str, Any]]:
        """Owner's grants, newest first — metadata only, never token/snapshot."""
        return await self.db.afetch_all(
            "SELECT id, chat_id, scope, component_id, created_at, expires_at, "
            "revoked_at, open_count FROM share_grant WHERE user_id = ? "
            "ORDER BY created_at DESC, id DESC",
            (user_id,),
        )

    async def revoke(self, user_id: str, share_id: int) -> bool:
        """Owner-scoped, idempotent revoke. False only when no such grant.

        Audits ``share.revoked`` on the live→revoked transition only, so a
        repeated DELETE stays idempotent in the log too.
        """
        state = await asyncio.to_thread(self._revoke_sync, user_id, share_id)
        if state == "revoked":
            await record_share_event(
                user_id=user_id, action="revoked", share_id=share_id,
                description="Share link revoked",
            )
        return state != "missing"

    def _revoke_sync(self, user_id: str, share_id: int) -> str:
        cur = self.db.execute(
            "UPDATE share_grant SET revoked_at = now() "
            "WHERE id = ? AND user_id = ? AND revoked_at IS NULL",
            (share_id, user_id),
        )
        if getattr(cur, "rowcount", 0):
            return "revoked"
        row = self.db.fetch_one(
            "SELECT 1 AS present FROM share_grant WHERE id = ? AND user_id = ?",
            (share_id, user_id),
        )
        return "already_revoked" if row else "missing"

    # ── public serving ───────────────────────────────────────────────────
    async def resolve(self, token: str) -> Optional[Dict[str, Any]]:
        """Grant row for a raw token, or None when unknown/revoked/expired.

        The three refusal causes are indistinguishable to the caller (uniform
        404 per contracts/rest-endpoints.md).
        """
        if not token:
            return None
        return await self.db.afetch_one(
            "SELECT id, user_id, chat_id, scope, component_id, snapshot_html, "
            "snapshot_json, created_at, expires_at, open_count "
            "FROM share_grant WHERE token_sha256 = ? AND revoked_at IS NULL "
            "AND (expires_at IS NULL OR expires_at > now())",
            (hash_token(token),),
        )

    async def record_open(self, grant: Dict[str, Any]) -> None:
        """Bump ``open_count`` and audit a public open of a resolved grant.

        ``share.opened``: actor = share owner, principal ``share:<id>`` (the
        anonymous visitor has no identity of their own).
        """
        await self.db.aexecute(
            "UPDATE share_grant SET open_count = open_count + 1 WHERE id = ?",
            (grant["id"],),
        )
        await record_share_event(
            user_id=grant["user_id"], action="opened", share_id=grant["id"],
            chat_id=grant.get("chat_id"), principal=f"share:{grant['id']}",
            description="Shared snapshot opened (public)",
        )


# ---------------------------------------------------------------------------
# Process-wide singleton (route layer entry point)
# ---------------------------------------------------------------------------

_STORE: Optional[ShareGrantStore] = None


def get_share_store() -> ShareGrantStore:
    """Return the process-wide store, building it on first use."""
    global _STORE
    if _STORE is None:
        _STORE = ShareGrantStore()
    return _STORE


def set_share_store(store: Optional[ShareGrantStore]) -> None:
    """Override the singleton (used by tests)."""
    global _STORE
    _STORE = store
