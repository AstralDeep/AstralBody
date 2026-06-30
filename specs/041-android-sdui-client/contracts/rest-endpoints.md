# Contract: REST Endpoints (consumed, not defined)

Native chrome surfaces that read bulk/historical data use the **existing** orchestrator REST API over HTTPS, authenticated with the same bearer JWT the WebSocket registered with. Base origin = the WS origin with `ws→http`/`wss→https` (e.g. `https://<host>:8001`). All reads are scoped server-side to the authenticated user; the client sends no user-id parameter.

Header on every request: `Authorization: Bearer <access_token>`, `Accept: application/json`.

## GET /api/audit  (audit-log viewer — US4)
Query params (all optional): `limit` (1–200, default 50), `cursor`, `event_class` (repeatable), `outcome` (repeatable; one of `in_progress|success|failure|interrupted`), `from`/`to` (ISO-8601), `q` (keyword).

Response `200`:
```json
{ "items": [ {
    "event_id": "…", "recorded_at": "2026-06-30T12:34:56Z",
    "event_class": "auth", "action_type": "auth.ws_register",
    "outcome": "success", "description": "…",
    "agent_id": null, "conversation_id": null, "correlation_id": "…",
    "outcome_detail": null, "inputs_meta": {}, "outputs_meta": {},
    "artifact_pointers": [], "started_at": "…", "completed_at": "…"
  } ],
  "next_cursor": "…|null", "filters_echo": { } }
```
- Errors: `400` (unknown `event_class`/`outcome`, or a forbidden user-scoping param); `401` (token invalid/expired → trigger refresh + retry). The detail endpoint `GET /api/audit/{event_id}` returns one DTO or `404` (non-existence and cross-user are indistinguishable by design).

## Agents (US4)
- Primary path is **WS** data actions (`discover_agents`→`agent_list`, `set_agent_permissions`→`agent_permissions_updated`, `enable_recommended_agents`). The REST mirror `GET /api/agents` / `…/permissions` exists if a REST path is preferred for a screen.

## History (US1/US4)
- **WS** only: `get_history`→`history_list`, `load_chat`→`chat_loaded`. No REST needed.

## Auth token (US1)
- Obtained via OIDC PKCE (AppAuth) against Keycloak's token endpoint for the `astral-mobile` public client; refreshed silently. The orchestrator validates the JWT and enforces the `KEYCLOAK_ALLOWED_AZP` allow-list (must contain `astral-mobile`).

**No new endpoints are introduced by this feature.**
