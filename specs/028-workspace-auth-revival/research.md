# Phase 0 Research: 028-workspace-auth-revival

All decisions below were grounded in a verified four-track survey of the codebase (auth history, SDUI architecture, Spec Kit conventions, proposal gap analysis) performed 2026-06-10. File references are to the state of branch `028-workspace-auth-revival` at creation.

## Part A — Authentication

### D1 — Shell gate with `next` preservation

**Decision**: `serve_shell` (orchestrator.py ~5445) checks `web_auth` for a valid (refreshable) session. Absent one, it 302s to `/auth/login?next=<original path+query>`. `/auth/login` stores `next` alongside the PKCE state in `_PENDING`; `/auth/callback` redirects to `next` after establishing the session. `next` MUST be validated as a same-origin **relative** path beginning with `/` and not `//` (open-redirect guard); invalid values fall back to `/`.
**Rationale**: Straight-redirect UX per clarification; deep links (`/?chat=…`) are the FR-003 requirement; carrying `next` through the server-held pending-state map (not the OIDC `state` value itself) avoids tampering.
**Alternatives**: In-app branded login chrome (rejected by clarification); encoding `next` in the OIDC `state` string (rejected: state should stay an opaque CSRF nonce).

### D2 — Server-side silent refresh

**Decision**: `web_auth` gains `_ensure_fresh(session)` used by `session_token()`, `/auth/session`, and the shell gate: if the access token expires within 60 s (using the JWT `exp` with ±5 min skew tolerance per 016), POST `{authority}/protocol/openid-connect/token` with `grant_type=refresh_token`; store the rotated refresh token. Refresh failures mark the session dead → gate redirects to interactive login. Refresh NEVER moves the 365-day anchor (016 FR-001); at anchor+365 d the refresh is refused locally without calling Keycloak.
**Rationale**: Replaces the React client's `automaticSilentRenew` that died in 026; keeps tokens entirely server-side.
**Alternatives**: Client-side renewal via hidden iframe (rejected: resurrects client token handling, violates 026 FR-009 direction); refreshing on a background timer for all sessions (rejected: needless Keycloak load; refresh-on-use suffices since every surface passes through `session_token()`).

### D3 — Durable session store

**Decision**: New `backend/orchestrator/session_store.py` with a `web_session` Postgres table (see data-model.md). Tokens encrypted at rest with Fernet under `WEB_SESSION_ENC_KEY` (falls back to `OFFLINE_GRANT_ENC_KEY`; **fail-closed in production mode if neither set**, matching `offline_grant.py` posture). `_SESSIONS` becomes a read-through cache; cookie format (signed sid, HttpOnly, SameSite=Lax) unchanged. Expired/dead rows purged opportunistically.
**Rationale**: FR-008 (restart + multi-instance survival); reuses the exact crypto + env conventions feature 025 established.
**Alternatives**: Keeping in-memory store (rejected by clarification — breaks the 365-day promise); signed stateless cookie holding tokens (rejected: refresh-token-in-cookie enlarges attack surface; revocation list still needs a table).

### D4 — WS reconnect recovery

**Decision**: On `register_ui` validation failure the server sends additive `{type:'auth_required', reason}`. Client handler: fetch `/auth/session` (triggers D2 refresh) → if `authenticated`, retry `register_ui` with the fresh token; else `window.location = '/auth/login?next=' + encodeURIComponent(current)`. The dead-end "Authentication failed" alert path (orchestrator.py ~1007) is removed. Client also re-fetches `/auth/session` before any reconnect attempt instead of reusing the boot-time injected token. The literal `'dev-token'` client fallback is removed; mock-auth dev still works because `/auth/session` answers authenticated in mock mode.
**Rationale**: FR-009; the session (cookie) outlives the access token, so recovery is almost always silent.
**Alternatives**: Auto-redirect on any WS failure (rejected: transient network errors would bounce users to Keycloak needlessly).

### D5 — Logout revocation

**Decision**: `/auth/logout` does, in order: (1) delete the `web_session` row + cache entry (unconditional, FR-013); (2) best-effort POST to Keycloak `…/protocol/openid-connect/revoke` with the refresh token + client credentials; (3) `OfflineGrantStore.revoke_for_user(user_id)`; (4) audit `auth.logout`; (5) redirect to Keycloak end-session (existing behavior). If (2) fails (IdP unreachable), enqueue into `auth_revocation_queue` retried by a small async worker on the existing `BackgroundTaskManager`.
**Rationale**: FR-012/FR-013; restores 016 FR-009 semantics server-side; the queue is the server-side analog of 016's `revocationQueue`.
**Alternatives**: Synchronous retry loop at logout (rejected: blocks the user's redirect); skipping offline-grant revocation (rejected by clarification).

### D6 — User-switch revocation

**Decision**: In `/auth/callback`, if the request carries a valid `astral_session` cookie whose session belongs to a **different** `sub`, perform the D5 revocation flow for that prior session before establishing the new one. Audited as `auth.logout` with `detail.cause='user_switch'`.
**Rationale**: 016 FR-008 / spec FR-014.
**Alternatives**: None viable — silently orphaning the old session leaks a live refresh token.

### D7 — Fail-closed production posture

**Decision**: New env `ASTRAL_ENV` (`production` default when unset → fail closed; `development` enables dev affordances). Startup gate in orchestrator init: `USE_MOCK_AUTH=true` AND `ASTRAL_ENV!=development` → log a fatal operator-facing error and refuse to serve (raise SystemExit). `validate_agent_api_key`: unset `AGENT_API_KEY` returns True only in development mode; otherwise connections are refused and logged. `.env.example` updated to set `ASTRAL_ENV=development` next to `USE_MOCK_AUTH=true` so local dev is unchanged.
**Rationale**: FR-015/FR-016; "explicitly declared development mode" per spec — safety must not depend on remembering to set a var.
**Alternatives**: Defaulting `ASTRAL_ENV=development` (rejected: that is exactly the fail-open trap being fixed); deleting mock auth entirely (rejected: A13 keeps local dev viable).

### D8 — JWKS caching

**Decision**: Add a module-level JWKS cache (TTL ~10 min + kid-miss refetch) shared by `orchestrator.validate_token` and `auth.get_current_user_payload`, mirroring `a2a_security.py`'s existing cache.
**Rationale**: Today both fetch JWKS per call; with the gate enabled every REST request pays a Keycloak round-trip — an availability coupling, not just latency.
**Alternatives**: Leaving as-is (rejected: SC-002 "zero user-visible auth errors" is hostage to transient IdP blips).

### D9 — Operator documentation + secret scrub

**Decision**: Create `docs/keycloak-realm-settings.md` (realm session windows ≥365 d, access-token lifespan 5–15 min, required `user`/`admin` roles, client + token-exchange config, revocation endpoint requirements) and fix the CLAUDE.md dangling reference. Scrub the real client secret printed in `docs/keycloak_agent_delegation_setup.md` (lines ~184/250) → placeholder, and flag rotation in the PR description.
**Rationale**: FR-017; Constitution VII (no secrets in VCS).

### D10 — Legacy auth surfaces

**Decision**: Keep `POST /auth/token` (BFF proxy) mounted but mark deprecated in its docstring (no shipped client calls it; removal is out of scope). Fix `guide_content.py` text that references the removed "Unauthorized access" page. `web_auth.session_roles` keeps unverified-decode for shell UX gating (every handler re-validates), now reading tokens that are exclusively server-held.

## Part B — SDUI workspace

### D11 — Component identity

**Decision**: `component_id` resolution order: (1) author-supplied `Primitive.id` (astralprims base field, already rendered as DOM id) — namespaced per chat; (2) orchestrator fingerprint `wc_<sha1(source_agent|source_tool|canonical(sorted salient params))[:16]>`. Stamped into `component_data` alongside the existing `_source_*` provenance and persisted on the workspace row. The LLM canvas prompt block (orchestrator.py ~2499, "COMPONENTS CURRENTLY ON CANVAS") is extended to list each component's `component_id` with updated COMPONENT UPDATE RULES: same id ⇒ in-place update.
**Rationale**: FR-019 — fingerprint-with-params keeps two same-tool/different-params outputs distinct (fixing the `(tool, agent)` clobber in `_send_or_replace_components`), while explicit ids let the model and deterministic actions update a component even when parameters change (the "refresh with new filters" journey: the action targets the id, parameters are an input, identity is preserved).
**Alternatives**: Pure `(tool, agent)` key (rejected: spec edge case); random uuid per render (rejected: nothing would ever match ⇒ no upserts); server-remembered "last component per tool" (rejected: ambiguous with parallel tools).

### D12 — Wire protocol

**Decision**: Additive server→client `ui_upsert {chat_id, ops:[{op:'upsert'|'remove', component_id, component, html}]}` (structured dict AND web-rendered fragment per op, mirroring `ui_stream_data`'s dual shape). `webrender.render()` wraps each top-level component in `<div class="astral-component" data-component-id="…">`. Client applies ops via querySelector morph (replace node if present, else append) — the proven `mergeStream` pattern — then re-runs `processSideEffects`. Existing `ui_render` (full canvas) is retained for re-hydration, timeline views, and device-profile changes, and now always renders the **whole live workspace** from server state. Legacy `components_replaced`/`component_saved`/`components_combined`/`components_condensed` emissions are superseded by `ui_upsert`/`ui_render` (D18).
**Rationale**: FR-024 (structured layer first, additive only); keeps non-web targets viable; smallest possible client delta.
**Alternatives**: Repurposing `ui_append`'s dormant `target_id` (rejected: changing its semantics is non-additive for unknown consumers); fragment-only HTML messages (rejected: violates the structured-layer rule).

### D13 — Persistence & re-hydration

**Decision**: `saved_components` becomes the live workspace store: new columns `component_id` (unique per chat), `position` (ordering), `updated_at`; upserts UPDATE in place (stable row identity — `replace_components`' delete+reinsert-with-new-uuid behavior is retired). New `WorkspaceManager` (orchestrator/workspace.py) owns identity stamping, upsert, ordering, snapshot writes, and reads. `load_chat` → after `chat_loaded`, server renders the full workspace per-socket (ROTE-adapted) and pushes `ui_render {target:'canvas'}` (stream-resume precedent at orchestrator.py ~1287). `chat_loaded` messages gain a server-rendered `html` field for component-bearing content so transcripts render meaningfully (client uses it instead of the empty-bubble fallback). The LLM canvas context now reads from the same workspace state the user sees (FR-029).
**Rationale**: Reuses the table that already exists for exactly this purpose (proposal phase 2); one source of truth for user view + LLM context.
**Alternatives**: New `workspace_component` table (rejected: duplicates `saved_components`, orphans the existing REST/combine flows); rehydrating from `messages.content` replay (rejected for live state: replay diverges from action-driven mutations; it remains the conceptual basis only for pre-feature history).

### D14 — Snapshots & read-only timeline

**Decision**: New `workspace_snapshot` table — one row per assistant turn (written where the turn's components are persisted, orchestrator.py ~2989) and per component-action mutation, storing the full ordered component JSON + `turn_message_id` + `cause`. Timeline UI is a **chrome** surface (`webrender/chrome/surfaces/workspace_timeline.py`, topbar entry) listing snapshots for the active chat; selecting one pushes a full historical `ui_render` plus a chrome banner ("Viewing turn N — read only · Back to live"). Client sets `timelineMode`: canvas-targeted `ui_upsert`/`ui_render` are deferred (state still applied server-side; other sockets unaffected) and a "live has moved on" indicator shows; component actions inside the canvas are inert in this mode and the server also rejects mutating `component_action`s carrying `timeline:true` context (defense in depth). "Back to live" re-renders live state and replays nothing. Snapshot reads audited (`workspace.timeline_viewed`, event_class `conversation`).
**Rationale**: Read-only per clarification; full-state snapshots (not deltas) make turn reproduction trivial and bound the blast radius of bugs; chrome placement per spec A10.
**Alternatives**: Replaying `messages.content` per request (rejected: misses component-action mutations; rich-turn chat summaries aren't persisted in those rows); delta chains (rejected: complexity without need at this scale).

### D15 — Component interaction loop

**Decision**: New `ui_event` action `component_action {chat_id, component_id, kind:'refresh'|'invoke', params_patch?, target_component_id?}` handled in `handle_ui_message`. Server resolves the workspace row → `_source_agent`/`_source_tool`/`_source_params` → merges `params_patch` → **re-checks the current chat-path permission stack** (agent scopes, `tool_overrides`/`permission_kind`, security flags — same computation as `_get_delegation_token`'s effective-tool list) → `_execute_with_retry` → upserts result into `target_component_id or component_id` → snapshot (`cause='component_action'`) → broadcast (D16) → audit. Denials return a chat-target Alert + `workspace.action_denied` audit. **Intent** interactions remain the existing client idiom (param_picker → chat message); the contract documents both kinds (FR-035). `table_paginate` is reimplemented as `component_action kind:'refresh'` with `params_patch={page:…}` (legacy action name kept as an alias for one release; it no longer wipes the canvas).
**Rationale**: FR-034..FR-039; generalizes the one proven loop; closes the permission-bypass question the research flagged on `table_paginate`.
**Alternatives**: Routing all actions through the LLM (rejected: slow, nondeterministic for a pagination click); new REST endpoint (rejected: ui_event channel already exists with validated WS identity).

### D16 — Multi-device broadcast

**Decision**: `ui_upsert` (and workspace-affecting renders) fan out to every socket in `ui_clients` belonging to the same user whose `_ws_active_chat[id(ws)] == chat_id`, with ROTE adaptation + fragment rendering done **per socket**. Originating socket included (single code path).
**Rationale**: FR-040; `_ws_active_chat` already exists (orchestrator.py:272); per-socket adaptation keeps Constitution II's device promise.
**Alternatives**: Broadcast raw + client-side adapt (rejected: clients are thin by design); user-level broadcast regardless of active chat (rejected: pushes content into the wrong chat view).

### D17 — ROTE re-adapt source

**Decision**: On `update_device`, re-render the **full live workspace from server state** for that socket (replacing the `_last_components` single-slot replay, which would wipe all but the last fragment after upserts ship). `_last_components` stays only as a fallback for non-chat contexts.
**Rationale**: Research hazard item; correctness precondition for D12.

### D18 — Legacy verb reconciliation

**Decision**: `save_component` (ws + REST) becomes a no-op alias for workspace persistence (everything is auto-persisted) and is marked deprecated; `get_saved_components` now returns workspace rows (shape-compatible); `delete_saved_component` maps to workspace remove (emits `ui_upsert op:'remove'`); `combine_components`/`condense_components` keep working but write results **through** `WorkspaceManager` (snapshot + broadcast) so their effects are visible; `components_replaced`/`component_saved` messages are still emitted for legacy consumers but the web client now also receives the equivalent `ui_upsert`. `_send_or_replace_components`' `(tool, agent)` matcher is replaced by D11 identity.
**Rationale**: FR-026 — no invisible server mutations; additive wire contract preserved.

## Resolved spec-level unknowns

| Unknown | Resolution |
|---|---|
| "Production mode" definition | `ASTRAL_ENV` env var; unset ⇒ production (fail closed); `development` enables mock auth + keyless agents (D7). |
| Audit event classes | Auth events stay `event_class='auth'` (new `auth.logout`, `auth.token_refresh_failed`); workspace events use `event_class='conversation'` (matches existing save/delete hook classification): `workspace.component_added/updated/removed`, `workspace.action_denied`, `workspace.timeline_viewed`. |
| Snapshot size bounds | Full-state JSON per turn; timeline list paginates (50/page); snapshots share the chat's FK CASCADE lifecycle. |
| Pre-028 chats | No backfill: workspace starts empty; timeline shows turns from feature deployment onward; transcript html rendering applies to ALL history (works from `messages.content`). |
| Client state preservation through morphs | Morph replaces only the targeted component's subtree; other nodes untouched (FR-020). Within the replaced subtree, transient state resets are acceptable (documented in contract). |
