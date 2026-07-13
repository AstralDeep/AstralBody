# REST Contract: Export & Share (US5) — 055-uniform-artifacts

All `/api/*` routes require the standard web session (same auth dependency as
existing component verbs); `/share/{token}` is deliberately unauthenticated.
Flags: `FF_ARTIFACT_EXPORT` (default on) gates the two export routes;
`FF_ARTIFACT_SHARING` (default off, fail-closed) gates the three share routes +
public serve. Flag off ⇒ 404 (route absent), never 500.

## GET /api/export/component/{component_id}.csv

Query: `chat_id` (required).
- Ownership check: `(chat_id, user_id)` scoping identical to workspace reads.
- Source: the stored component dict. `type` must be `table` (else 422).
- When `total_rows > len(rows)` (stored page only), the handler re-invokes the
  component's recorded source tool through the existing deterministic
  `component_action` pipeline (same permission gates, retired/merged-agent
  handling, credential injection) with full-range parameters, and serves the
  complete rows.
- Response: `text/csv; charset=utf-8`, `Content-Disposition: attachment`,
  headers row from `headers`, cells stringified via stdlib `csv` (formula-
  injection guard: leading `=+-@` prefixed with `'`).
- Audit: `workspace.component_exported` (class `conversation`).

## GET /api/export/canvas/{chat_id}.html

- Ownership check as above; loads live components + layouts, materializes
  designed arrangements (same `_canvas_components` path), renders via
  `render_workspace`, and wraps in a **self-contained** document: inlined
  minimal CSS subset, no scripts, no WS, charts degraded to their table/text
  fallback ladder, provenance badges + "Generated <date> by AstralDeep" footer.
- Response: `text/html`, `Content-Disposition: attachment`.
- Audit: `workspace.canvas_exported`.

## POST /api/share

Body: `{chat_id, scope: "component"|"canvas", component_id?}`.
- Ownership check; renders the snapshot rendition (fragment or full canvas as
  above) at mint time.
- **PHI gate (fail-closed)** over the snapshot text; on hit → 403
  `{error:"phi_blocked"}` + audit `share.refused_phi`.
- Token: `secrets.token_urlsafe(32)`; stores `sha256(token)` only; returns
  `{share_url: "/share/<token>", id, created_at, expires_at}` exactly once.
- Audit: `share.minted`.

## GET /api/share

Lists the owner's grants: `{id, scope, component_id, created_at, expires_at,
revoked_at, open_count}` — never token material.

## DELETE /api/share/{id}

Owner-scoped revoke; sets `revoked_at`; idempotent; audit `share.revoked`.
Subsequent public opens refuse immediately.

## GET /share/{token}  (public, unauthenticated)

- Lookup by `sha256(token)`; refuse (404, uniform body, no timing oracle beyond
  the indexed lookup) when unknown, revoked, or expired.
- Serves `snapshot_html` verbatim (already escape-by-default rendered at mint;
  no live workspace read, no user data beyond the snapshot).
- Headers: `X-Robots-Tag: noindex, nofollow`, `Cache-Control: no-store`,
  `Referrer-Policy: no-referrer`, CSP `default-src 'none'; style-src 'unsafe-inline'; img-src data:`.
- Increments `open_count`; audit `share.opened` (actor = share owner, principal
  `share:<id>`).

## Error shapes

Standard existing envelope `{error: <code>, detail?}`: 401 unauthenticated
(API routes), 403 `phi_blocked` / not-owner, 404 unknown/revoked/flag-off,
422 wrong component type, 503 source re-execution failed (CSV full-export path
only — carries `detail:"partial data available"` and offers stored-page CSV via
`?stored_only=1`).
