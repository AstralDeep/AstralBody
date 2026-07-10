"""Accepted OIDC ``azp`` (authorized party) client ids.

The orchestrator does not enforce a strict ``aud`` (Keycloak confidential
clients set ``aud="account"``); it validates the *authorized party* (``azp``)
of the access token instead — the client the token was minted for. The web
client (``KEYCLOAK_CLIENT_ID``, default ``astral-frontend``) is always
accepted. Additional first-party clients are accepted when listed in
``KEYCLOAK_ALLOWED_AZP`` (comma-separated).

This is the configurable allow-list the native desktop client's production
posture requires (RFC 8252 / OAuth 2.0 for Native Apps): the Windows client
authenticates with its OWN dedicated *public* Keycloak client
(``astral-desktop``), so its tokens carry ``azp=astral-desktop`` rather than the
web client's id. Listing it here lets the desktop and web auth surfaces stay
isolated while both register over the same WebSocket / REST gates.

Empty/unset ``KEYCLOAK_ALLOWED_AZP`` ⇒ only the primary web client is accepted
(identical to the pre-allow-list single-``azp`` check — fully backwards
compatible).
"""
from __future__ import annotations

import os
from typing import Set


def _primary_client_id() -> str:
    # shared/__init__ normalizes the VITE_-prefixed aliases both directions, so
    # either name resolves here.
    return (
        os.getenv("KEYCLOAK_CLIENT_ID")
        or os.getenv("KEYCLOAK_CLIENT_ID")
        or ""
    ).strip()


def allowed_azps() -> Set[str]:
    """The set of accepted ``azp`` client ids (primary web client + allow-list)."""
    ids = {_primary_client_id()}
    for raw in os.getenv("KEYCLOAK_ALLOWED_AZP", "").split(","):
        cid = raw.strip()
        if cid:
            ids.add(cid)
    return {cid for cid in ids if cid}


def is_azp_allowed(azp: str) -> bool:
    """True when ``azp`` is acceptable for this deployment.

    A missing/empty ``azp`` is allowed (some token flows omit it) — matching the
    historical ``if azp and azp != client_id`` semantics. A present ``azp`` must
    be in :func:`allowed_azps`.
    """
    if not azp:
        return True
    return azp in allowed_azps()
