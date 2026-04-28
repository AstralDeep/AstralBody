"""
HTTP request audit middleware.

Records every authenticated REST request as a metadata-only audit event
in the caller's own log. Skips the audit endpoints themselves (they
self-record via dedicated ``audit_view`` events) and skips OPTIONS and
unauthenticated requests.

The middleware does NOT inspect request or response bodies — only the
HTTP method, route template, and response status — so it never records
PHI, even for endpoints that handle PHI in their payloads.
"""
from __future__ import annotations

import logging
import time
from typing import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from .hooks import record_generic
from .recorder import get_recorder

logger = logging.getLogger("Audit.Middleware")

_SKIP_PATH_PREFIXES = (
    "/api/audit",      # self-recorded
    "/auth/",          # auth lifecycle handled at the WS register handler
    "/docs",
    "/openapi.json",
    "/.well-known",
    "/metrics",
)


class AuditHTTPMiddleware(BaseHTTPMiddleware):
    """Records every authenticated request to the audit log."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        path = request.url.path or ""
        method = request.method
        if method == "OPTIONS" or any(path.startswith(p) for p in _SKIP_PATH_PREFIXES):
            return await call_next(request)

        if get_recorder() is None:
            return await call_next(request)

        # We need the authenticated user to record the row. Rather than
        # re-validate the token (the route handlers will do that), we
        # record the row only if validation has populated request.state
        # (set by a thin auth resolver below). If the request fails auth
        # (401), there's no user to attribute it to, so we drop it.
        start = time.monotonic()
        response: Response | None = None
        error_detail: str | None = None
        try:
            response = await call_next(request)
        except Exception as exc:
            error_detail = f"{exc.__class__.__name__}: {exc}"[:500]
            raise
        finally:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            claims = getattr(request.state, "audit_claims", None)
            status_code = response.status_code if response is not None else 500
            if claims and 200 <= status_code < 600 and status_code != 401:
                try:
                    await record_generic(
                        claims=claims,
                        event_class="settings",  # default; route-specific recorders override
                        action_type=f"http.{method.lower()}",
                        description=f"{method} {path} → {status_code}",
                        inputs_meta={
                            "path": path,
                            "method": method,
                            "status": status_code,
                            "elapsed_ms": elapsed_ms,
                        },
                        outcome="success" if 200 <= status_code < 400 else "failure",
                        outcome_detail=error_detail,
                    )
                except Exception as exc:  # pragma: no cover
                    logger.debug("HTTP audit middleware record failed: %s", exc)
        return response  # type: ignore[return-value]
