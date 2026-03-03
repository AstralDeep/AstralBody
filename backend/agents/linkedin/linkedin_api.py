#!/usr/bin/env python3
"""
LinkedIn Marketing API Client.

Wraps LinkedIn REST API calls for the CAAI company page.
Supports 3-legged OAuth: stores Client ID + Secret, exchanges
authorization codes for access tokens, and auto-refreshes.

When credentials are missing, methods return None so tools can
render manual-input fallback UI instead.
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

# Scopes requested during OAuth.
# Organization scopes (r_organization_social, w_organization_social, rw_organization_admin)
# require Marketing API approval. If not approved, we use available member scopes.
OAUTH_SCOPES = [
    "openid",
    "profile",
    "email",
    "w_member_social",
    "r_basicprofile",
]


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
    """Exchange an authorization code for an access token.

    Returns dict with 'access_token', 'expires_in', and optionally
    'refresh_token', 'refresh_token_expires_in'.
    Returns None on failure.
    """
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
    """Refresh an expired access token using a refresh token.

    Returns dict with new 'access_token', 'expires_in', etc.
    Returns None on failure.
    """
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
    """LinkedIn Marketing API client with OAuth credential management.

    Accepts credentials dict containing:
    - LINKEDIN_CLIENT_ID, LINKEDIN_CLIENT_SECRET (for OAuth)
    - LINKEDIN_ACCESS_TOKEN (obtained after OAuth authorization)
    - LINKEDIN_REFRESH_TOKEN (optional, for auto-refresh)
    - LINKEDIN_TOKEN_EXPIRES_AT (optional, epoch timestamp)
    - LINKEDIN_ORG_ID (organization ID)

    When access token is missing or expired, methods return None so
    callers can render manual-input UI or prompt for OAuth authorization.
    """

    def __init__(self, credentials: Optional[Dict[str, str]] = None):
        creds = credentials or {}
        self.client_id = creds.get("LINKEDIN_CLIENT_ID") or os.getenv("LINKEDIN_CLIENT_ID")
        self.client_secret = creds.get("LINKEDIN_CLIENT_SECRET") or os.getenv("LINKEDIN_CLIENT_SECRET")
        self.access_token = creds.get("LINKEDIN_ACCESS_TOKEN") or os.getenv("LINKEDIN_ACCESS_TOKEN")
        self.refresh_token = creds.get("LINKEDIN_REFRESH_TOKEN") or os.getenv("LINKEDIN_REFRESH_TOKEN")
        self.org_id = creds.get("LINKEDIN_ORG_ID") or os.getenv("LINKEDIN_ORG_ID")
        self.api_version = creds.get("LINKEDIN_API_VERSION") or os.getenv("LINKEDIN_API_VERSION", "202502")
        self.base_url = "https://api.linkedin.com/rest"

        # Check token expiry
        token_expires = creds.get("LINKEDIN_TOKEN_EXPIRES_AT")
        if token_expires:
            try:
                self.token_expires_at = float(token_expires)
            except (ValueError, TypeError):
                self.token_expires_at = 0
        else:
            self.token_expires_at = 0

        self.api_available = bool(self.access_token and self.org_id)
        self.has_oauth_creds = bool(self.client_id and self.client_secret)

        # Store the credential manager ref for token refresh persistence
        self._credential_manager = creds.get("_credential_manager")
        self._user_id = creds.get("_user_id")
        self._agent_id = creds.get("_agent_id")

    def _is_token_expired(self) -> bool:
        """Check if the access token is expired or about to expire (5-min buffer)."""
        if not self.token_expires_at:
            return False  # No expiry info — assume valid
        return time.time() > (self.token_expires_at - 300)

    def _try_refresh_token(self) -> bool:
        """Attempt to refresh the access token. Returns True on success."""
        if not (self.has_oauth_creds and self.refresh_token):
            return False

        result = refresh_access_token(self.client_id, self.client_secret, self.refresh_token)
        if not result:
            return False

        self.access_token = result["access_token"]
        expires_in = result.get("expires_in", 3600)
        self.token_expires_at = time.time() + int(expires_in)
        self.api_available = bool(self.access_token and self.org_id)

        # If we have a new refresh token, update it
        if "refresh_token" in result:
            self.refresh_token = result["refresh_token"]

        logger.info("LinkedIn access token refreshed successfully")
        return True

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "LinkedIn-Version": self.api_version,
            "X-Restli-Protocol-Version": "2.0.0",
            "Content-Type": "application/json",
        }

    def _get(self, path: str, params: Optional[Dict] = None, timeout: int = 30) -> Optional[Dict]:
        """Make a GET request to the LinkedIn API. Returns None on failure."""
        if not self.api_available:
            return None

        # Auto-refresh if token is expired
        if self._is_token_expired() and not self._try_refresh_token():
            logger.warning("LinkedIn access token expired and refresh failed")
            return None

        ck = _cache_key("GET", path, params)
        cached = _get_cached(ck)
        if cached is not None:
            return cached

        try:
            url = f"{self.base_url}{path}"
            resp = requests.get(url, headers=self._headers(), params=params, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            _set_cached(ck, data)
            return data
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else "unknown"
            logger.error(f"LinkedIn API HTTP error {status} for {path}: {e}")
            if status in (401, 403):
                logger.error("LinkedIn token may be expired or missing required scopes")
                # Try refresh once on 401
                if status == 401 and self._try_refresh_token():
                    return self._get(path, params, timeout)
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"LinkedIn API request failed for {path}: {e}")
            return None

    def get_org_urn(self) -> str:
        return f"urn:li:organization:{self.org_id}"

    def get_org_posts(self, count: int = 20) -> Optional[List[Dict]]:
        """Retrieve recent posts from the organization page."""
        data = self._get(
            "/posts",
            params={
                "q": "author",
                "author": self.get_org_urn(),
                "count": count,
                "sortBy": "LAST_MODIFIED",
            }
        )
        if data is None:
            return None
        return data.get("elements", [])

    def get_follower_stats(self) -> Optional[Dict]:
        """Get follower statistics for the organization."""
        data = self._get(
            "/organizationalEntityFollowerStatistics",
            params={
                "q": "organizationalEntity",
                "organizationalEntity": self.get_org_urn(),
            }
        )
        if data is None:
            return None
        elements = data.get("elements", [])
        return elements[0] if elements else {}

    def get_page_stats(self) -> Optional[Dict]:
        """Get share/engagement statistics for the organization."""
        data = self._get(
            "/organizationalEntityShareStatistics",
            params={
                "q": "organizationalEntity",
                "organizationalEntity": self.get_org_urn(),
            }
        )
        if data is None:
            return None
        elements = data.get("elements", [])
        return elements[0] if elements else {}

    def get_follower_count(self) -> Optional[int]:
        """Get current follower count."""
        data = self._get(
            f"/networkSizes/{self.get_org_urn()}",
            params={"edgeType": "CompanyFollowedByMember"}
        )
        if data is None:
            return None
        return data.get("firstDegreeSize", 0)

    def get_org_info(self) -> Optional[Dict]:
        """Get basic organization information."""
        data = self._get(f"/organizations/{self.org_id}")
        return data
