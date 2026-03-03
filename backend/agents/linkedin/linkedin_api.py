#!/usr/bin/env python3
"""
LinkedIn API Client — Member-scoped endpoints.

Uses the authenticated member's OAuth token to:
- Read profile info (openid + profile + r_profile_basicinfo)
- Create / delete posts (w_member_social)
- React to posts (w_member_social)
- Comment on posts (w_member_social)

Organization-level analytics require Marketing API approval which
is a separate LinkedIn partnership program.  This client works with
the standard OAuth scopes available through a self-service app.
"""
import os
import json
import time
import hashlib
import logging
import urllib.parse
from typing import Dict, Any, List, Optional, Tuple

import requests

logger = logging.getLogger("LinkedInAPI")

# ── In-Memory Cache ────────────────────────────────────────────────────
_LINKEDIN_CACHE: Dict[str, Tuple[float, Any]] = {}
CACHE_TTL = 300  # 5 minutes

# LinkedIn OAuth endpoints
OAUTH_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
OAUTH_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"

# Scopes available through a standard LinkedIn app.
OAUTH_SCOPES = [
    "openid",
    "profile",
    "email",
    "w_member_social",
    "r_profile_basicinfo",
    "r_verify",
]

# Valid reaction types for LinkedIn posts
REACTION_TYPES = ["LIKE", "PRAISE", "EMPATHY", "INTEREST", "ENTERTAINMENT", "APPRECIATION"]


def _cache_key(*args: Any) -> str:
    raw = json.dumps(args, sort_keys=True, default=str)
    return hashlib.md5(raw.encode()).hexdigest()


def _get_cached(key: str) -> Optional[Any]:
    if key in _LINKEDIN_CACHE:
        ts, data = _LINKEDIN_CACHE[key]
        if time.time() - ts < CACHE_TTL:
            return data
        del _LINKEDIN_CACHE[key]
    return None


def _set_cached(key: str, data: Any) -> None:
    _LINKEDIN_CACHE[key] = (time.time(), data)


def build_authorization_url(client_id: str, redirect_uri: str, state: str = "") -> str:
    """Build the LinkedIn OAuth authorization URL for 3-legged flow."""
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(OAUTH_SCOPES),
    }
    if state:
        params["state"] = state
    return f"{OAUTH_AUTH_URL}?{urllib.parse.urlencode(params)}"


def exchange_code_for_token(
    client_id: str, client_secret: str, code: str, redirect_uri: str
) -> Optional[Dict[str, Any]]:
    """Exchange an authorization code for an access token."""
    try:
        resp = requests.post(
            OAUTH_TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"LinkedIn token exchange successful, expires_in={data.get('expires_in')}")
        return data
    except requests.exceptions.RequestException as e:
        logger.error(f"LinkedIn token exchange failed: {e}")
        return None


def refresh_access_token(
    client_id: str, client_secret: str, refresh_token: str
) -> Optional[Dict[str, Any]]:
    """Refresh an expired access token using a refresh token."""
    try:
        resp = requests.post(
            OAUTH_TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"LinkedIn token refresh successful, expires_in={data.get('expires_in')}")
        return data
    except requests.exceptions.RequestException as e:
        logger.error(f"LinkedIn token refresh failed: {e}")
        return None


class LinkedInClient:
    """LinkedIn API client using member-scoped OAuth tokens.

    Accepts credentials dict containing:
    - LINKEDIN_CLIENT_ID, LINKEDIN_CLIENT_SECRET (for OAuth)
    - LINKEDIN_ACCESS_TOKEN (obtained after OAuth authorization)
    - LINKEDIN_REFRESH_TOKEN (optional, for auto-refresh)
    - LINKEDIN_TOKEN_EXPIRES_AT (optional, epoch timestamp)
    - LINKEDIN_ORG_ID (organization ID, used for @mentions)
    """

    def __init__(self, credentials: Optional[Dict[str, str]] = None):
        creds = credentials or {}
        self.client_id = creds.get("LINKEDIN_CLIENT_ID") or os.getenv("LINKEDIN_CLIENT_ID")
        self.client_secret = creds.get("LINKEDIN_CLIENT_SECRET") or os.getenv("LINKEDIN_CLIENT_SECRET")
        self.access_token = creds.get("LINKEDIN_ACCESS_TOKEN") or os.getenv("LINKEDIN_ACCESS_TOKEN")
        self.refresh_token = creds.get("LINKEDIN_REFRESH_TOKEN") or os.getenv("LINKEDIN_REFRESH_TOKEN")
        self.org_id = creds.get("LINKEDIN_ORG_ID") or os.getenv("LINKEDIN_ORG_ID")
        self.api_version = creds.get("LINKEDIN_API_VERSION") or os.getenv("LINKEDIN_API_VERSION", "202502")
        self.base_url = "https://api.linkedin.com"

        # Token expiry
        token_expires = creds.get("LINKEDIN_TOKEN_EXPIRES_AT")
        if token_expires:
            try:
                self.token_expires_at = float(token_expires)
            except (ValueError, TypeError):
                self.token_expires_at = 0
        else:
            self.token_expires_at = 0

        self.api_available = bool(self.access_token)
        self.has_oauth_creds = bool(self.client_id and self.client_secret)

        # Person URN is fetched lazily from /userinfo
        self._person_id: Optional[str] = None

    def _is_token_expired(self) -> bool:
        if not self.token_expires_at:
            return False
        return time.time() > (self.token_expires_at - 300)

    def _try_refresh_token(self) -> bool:
        if not (self.has_oauth_creds and self.refresh_token):
            return False
        result = refresh_access_token(self.client_id, self.client_secret, self.refresh_token)
        if not result:
            return False
        self.access_token = result["access_token"]
        expires_in = result.get("expires_in", 3600)
        self.token_expires_at = time.time() + int(expires_in)
        self.api_available = bool(self.access_token)
        if "refresh_token" in result:
            self.refresh_token = result["refresh_token"]
        logger.info("LinkedIn access token refreshed successfully")
        return True

    def _ensure_token(self) -> bool:
        """Return True if we have a valid token, attempting refresh if needed."""
        if not self.api_available:
            return False
        if self._is_token_expired() and not self._try_refresh_token():
            logger.warning("LinkedIn access token expired and refresh failed")
            return False
        return True

    def _rest_headers(self) -> Dict[str, str]:
        """Headers for the versioned REST API (/rest/*)."""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "LinkedIn-Version": self.api_version,
            "X-Restli-Protocol-Version": "2.0.0",
            "Content-Type": "application/json",
        }

    def _v2_headers(self) -> Dict[str, str]:
        """Headers for the v2 API (/v2/*)."""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    # ── Profile ────────────────────────────────────────────────────────

    def get_my_profile(self) -> Optional[Dict[str, Any]]:
        """Get the authenticated user's profile via OpenID Connect userinfo.

        Returns dict with: sub (person ID), name, given_name, family_name,
        picture, email, email_verified, locale.
        """
        if not self._ensure_token():
            return None

        ck = _cache_key("userinfo")
        cached = _get_cached(ck)
        if cached is not None:
            return cached

        try:
            resp = requests.get(
                f"{self.base_url}/v2/userinfo",
                headers=self._v2_headers(),
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            self._person_id = data.get("sub")
            _set_cached(ck, data)
            return data
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else "unknown"
            logger.error(f"LinkedIn userinfo HTTP {status}: {e}")
            if status == 401 and self._try_refresh_token():
                return self.get_my_profile()
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"LinkedIn userinfo request failed: {e}")
            return None

    def get_person_urn(self) -> Optional[str]:
        """Return urn:li:person:{id} for the authenticated user."""
        if self._person_id:
            return f"urn:li:person:{self._person_id}"
        profile = self.get_my_profile()
        if profile and profile.get("sub"):
            return f"urn:li:person:{profile['sub']}"
        return None

    def get_org_urn(self) -> Optional[str]:
        """Return urn:li:organization:{id} if org ID is configured."""
        if self.org_id:
            return f"urn:li:organization:{self.org_id}"
        return None

    # ── Posts ──────────────────────────────────────────────────────────

    def create_post(
        self,
        text: str,
        visibility: str = "PUBLIC",
        article_url: Optional[str] = None,
        article_title: Optional[str] = None,
        article_description: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Create a LinkedIn post as the authenticated member.

        Args:
            text: Post commentary text.
            visibility: "PUBLIC", "CONNECTIONS", or "LOGGED_IN" (LinkedIn members only).
            article_url: Optional URL to share as an article attachment.
            article_title: Optional title for the article attachment.
            article_description: Optional description for the article attachment.

        Returns dict with post details on success, None on failure.
        """
        if not self._ensure_token():
            return None

        person_urn = self.get_person_urn()
        if not person_urn:
            logger.error("Cannot create post: unable to determine person URN")
            return None

        body: Dict[str, Any] = {
            "author": person_urn,
            "commentary": text,
            "visibility": visibility,
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
        }

        # Add article attachment if provided
        if article_url:
            article = {"source": article_url}
            if article_title:
                article["title"] = article_title
            if article_description:
                article["description"] = article_description
            body["content"] = {
                "article": article,
            }

        try:
            resp = requests.post(
                f"{self.base_url}/rest/posts",
                headers=self._rest_headers(),
                json=body,
                timeout=30,
            )
            resp.raise_for_status()

            # LinkedIn returns 201 Created with x-restli-id header containing the post URN
            post_urn = resp.headers.get("x-restli-id", "")
            logger.info(f"LinkedIn post created: {post_urn}")
            return {
                "success": True,
                "post_urn": post_urn,
                "visibility": visibility,
                "text_preview": text[:100],
            }
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else "unknown"
            detail = ""
            if e.response is not None:
                try:
                    detail = e.response.json().get("message", e.response.text[:200])
                except Exception:
                    detail = e.response.text[:200]
            logger.error(f"LinkedIn create post HTTP {status}: {detail}")
            if status == 401 and self._try_refresh_token():
                return self.create_post(text, visibility, article_url, article_title, article_description)
            return {"success": False, "error": f"HTTP {status}: {detail}"}
        except requests.exceptions.RequestException as e:
            logger.error(f"LinkedIn create post failed: {e}")
            return {"success": False, "error": str(e)}

    def delete_post(self, post_urn: str) -> Optional[Dict[str, Any]]:
        """Delete a post created by the authenticated member."""
        if not self._ensure_token():
            return None

        encoded = urllib.parse.quote(post_urn, safe="")
        try:
            resp = requests.delete(
                f"{self.base_url}/rest/posts/{encoded}",
                headers=self._rest_headers(),
                timeout=30,
            )
            resp.raise_for_status()
            logger.info(f"LinkedIn post deleted: {post_urn}")
            return {"success": True, "deleted_urn": post_urn}
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else "unknown"
            logger.error(f"LinkedIn delete post HTTP {status}: {e}")
            return {"success": False, "error": f"HTTP {status}"}
        except requests.exceptions.RequestException as e:
            logger.error(f"LinkedIn delete post failed: {e}")
            return {"success": False, "error": str(e)}

    # ── Reactions ─────────────────────────────────────────────────────

    def react_to_post(self, post_urn: str, reaction_type: str = "LIKE") -> Optional[Dict[str, Any]]:
        """Add a reaction to a LinkedIn post.

        Args:
            post_urn: The URN of the post (e.g. "urn:li:share:123" or "urn:li:ugcPost:123").
            reaction_type: One of LIKE, PRAISE, EMPATHY, INTEREST, ENTERTAINMENT, APPRECIATION.
        """
        if not self._ensure_token():
            return None

        reaction_type = reaction_type.upper()
        if reaction_type not in REACTION_TYPES:
            return {"success": False, "error": f"Invalid reaction type. Must be one of: {', '.join(REACTION_TYPES)}"}

        person_urn = self.get_person_urn()
        if not person_urn:
            return {"success": False, "error": "Unable to determine person URN"}

        # LinkedIn REST API for reactions
        encoded_post = urllib.parse.quote(post_urn, safe="")
        try:
            resp = requests.post(
                f"{self.base_url}/rest/socialActions/{encoded_post}/likes",
                headers=self._rest_headers(),
                json={
                    "actor": person_urn,
                    "object": post_urn,
                    "reactionType": reaction_type,
                },
                timeout=15,
            )
            resp.raise_for_status()
            logger.info(f"Reacted {reaction_type} to {post_urn}")
            return {"success": True, "post_urn": post_urn, "reaction": reaction_type}
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else "unknown"
            detail = ""
            if e.response is not None:
                try:
                    detail = e.response.json().get("message", e.response.text[:200])
                except Exception:
                    detail = e.response.text[:200]
            logger.error(f"LinkedIn react HTTP {status}: {detail}")
            return {"success": False, "error": f"HTTP {status}: {detail}"}
        except requests.exceptions.RequestException as e:
            logger.error(f"LinkedIn react failed: {e}")
            return {"success": False, "error": str(e)}

    # ── Comments ──────────────────────────────────────────────────────

    def comment_on_post(self, post_urn: str, text: str) -> Optional[Dict[str, Any]]:
        """Add a comment to a LinkedIn post.

        Args:
            post_urn: The URN of the post to comment on.
            text: Comment text.
        """
        if not self._ensure_token():
            return None

        person_urn = self.get_person_urn()
        if not person_urn:
            return {"success": False, "error": "Unable to determine person URN"}

        encoded_post = urllib.parse.quote(post_urn, safe="")
        try:
            resp = requests.post(
                f"{self.base_url}/rest/socialActions/{encoded_post}/comments",
                headers=self._rest_headers(),
                json={
                    "actor": person_urn,
                    "message": {"text": text},
                },
                timeout=15,
            )
            resp.raise_for_status()
            comment_urn = resp.headers.get("x-restli-id", "")
            logger.info(f"Commented on {post_urn}: {text[:50]}")
            return {"success": True, "post_urn": post_urn, "comment_urn": comment_urn, "text": text}
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else "unknown"
            detail = ""
            if e.response is not None:
                try:
                    detail = e.response.json().get("message", e.response.text[:200])
                except Exception:
                    detail = e.response.text[:200]
            logger.error(f"LinkedIn comment HTTP {status}: {detail}")
            return {"success": False, "error": f"HTTP {status}: {detail}"}
        except requests.exceptions.RequestException as e:
            logger.error(f"LinkedIn comment failed: {e}")
            return {"success": False, "error": str(e)}
