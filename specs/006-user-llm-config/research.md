# Phase 0 Research — User-Configurable LLM Subscription

**Status**: All Technical-Context unknowns resolved. Spec Clarifications section already settled four high-impact questions before planning, so research focuses on five remaining design choices that emerged when reading the existing code.

---

## R1. Where do incoming user credentials live on the server side?

**Decision**: A per-WebSocket in-memory dictionary on the orchestrator instance, `Orchestrator._session_llm_creds: Dict[int, SessionCreds]`, keyed by `id(websocket)` (the same identity scheme already used by `_chat_locks`, `cancelled_sessions`, and `ui_sessions`). Cleared in `_cleanup_session(websocket)` alongside the other per-socket maps. Never serialized, never logged, never written to disk.

**Rationale**:
- Spec FR-002 forbids any server-side persistence of the API key. In-memory + per-socket is the only data structure that meets that bar while still letting the same call site that today reads `self.llm_client` resolve credentials without round-tripping back to the browser.
- The orchestrator already uses `id(websocket)`-keyed dicts everywhere (see `orchestrator.py:88-95`), so the lifecycle (registered on `register_ui`, cleared on disconnect) is a 4-line addition with zero new abstractions.
- Per-call resolution preserves the existing retry/backoff logic in `_call_llm` (orchestrator.py:2274) — we only swap the *source* of the OpenAI client, not the call shape.

**Alternatives considered**:
- *Sending credentials in every WS frame* — wastes bandwidth (~250B per message) and would require thinking about replay across reconnects; rejected.
- *Sending credentials in REST headers* — works for REST endpoints but doesn't help WS-driven flows, which are the dominant LLM call path. Hybrid would mean two storage paths; rejected.
- *Client-side proxy (browser calls LLM directly)* — rejected in the spec's Transport assumption; it would require porting prompts to the frontend, which is out of scope.

---

## R2. How should the per-call client factory choose between user creds and the operator default?

**Decision**: A free function `build_llm_client(session_creds: Optional[SessionCreds], default_creds: OperatorDefaultCreds) -> Tuple[OpenAI, CredentialSource, ResolvedConfig]` returning the OpenAI client, an enum (`CredentialSource.USER` | `CredentialSource.OPERATOR_DEFAULT`), and the resolved `(base_url, model)` (no key) for use in the audit event. If `session_creds` is present and complete (api_key, base_url, model all non-empty) → return user client. Else if `default_creds` is complete → return operator-default client. Else raise `LLMUnavailable` (caller emits `llm.unconfigured` audit and surfaces the FR-004a prompt to the user).

**Rationale**:
- A pure function is trivial to unit-test (5 cases: user-only / default-only / both-present-prefer-user / neither-present-raise / partial-user-config-falls-through-to-default-only-if-partial-is-treated-as-absent). FR-009's no-runtime-fallback rule is enforced by the *caller* in error paths, not by the factory itself — the factory only chooses at the start of a call.
- Caching the OpenAI client is *not* worth it. Per-call construction is microseconds (no network in the constructor), and caching would couple lifetime to credential changes (tricky cache invalidation on config update). FR-012 ("clearing takes effect immediately") is satisfied for free.
- Returning the resolved `(base_url, model)` separately lets the audit-event recorder fill the `llm.call` payload without re-reading the creds object.

**Alternatives considered**:
- *Cache user clients in `session_creds`* — premature; reconsider only if profiling shows construction cost matters.
- *Pass the websocket to the factory* — leaks transport detail into a pure function; we pass already-resolved `SessionCreds` instead.
- *Always return a client and signal failure via a sentinel* — Pythonic exceptions are cleaner; the call site already has a `try/except` for upstream errors.

---

## R3. How are credentials transmitted from browser to server?

**Decision**: Two paths.
1. **WebSocket** (the primary path, since most LLM-dependent calls flow through `_call_llm` triggered by `ui_event` messages):
   - On `register_ui`, the existing payload gains an optional `llm_config: { api_key, base_url, model }` field. If present, it populates `_session_llm_creds[id(ws)]` immediately.
   - When the user saves or clears settings mid-session, a new `llm_config_set` / `llm_config_clear` WS message updates the same dict.
2. **REST**: `POST /api/llm/test` — the Test Connection endpoint — accepts the trio in the request body. The credentials are used to construct a one-shot `OpenAI` client, the probe is issued, and the response is returned. Nothing is stored. Standard `AuditHTTPMiddleware` per-user isolation applies (same as feature 003's REST routes).

**Rationale**:
- Reuses the existing `register_ui` extension pattern that ROTE already uses (`useWebSocket.ts` already attaches `device` capabilities — see project memory). A second optional field is consistent with that precedent.
- The Test Connection endpoint deliberately does *not* go through the WS path: tests need to run *before* save (the user might still be editing), and tying probes to the WS session would make probe-after-save pointless because the credentials are already there. A REST endpoint is the cleanest "stateless probe" surface.

**Alternatives considered**:
- *Send credentials in every WS frame* — see R1, rejected (bandwidth + ergonomics).
- *Use the existing `register_ui.device` field as a generic envelope* — overloads its semantics; rejected.

---

## R4. Where do the new audit event classes live?

**Decision**: Extend the existing `audit_events.event_class` check in `backend/audit/schemas.py` (already an enum-like Postgres `CHECK` per project memory) by adding `'llm.config_change'`, `'llm.unconfigured'`, `'llm.call'`. No new table, no migration script (the existing `Database._init_db()` convention from features 003 and 004 covers schema additions in-place).

**Rationale**:
- Project memory explicitly states the convention: "Schema additions go directly into `_init_db`. No SQLAlchemy/Alembic." Extending the check constraint and `_init_db` to include the new identifiers is the standard move.
- All three new events are per-user, so they inherit the existing per-user isolation, hash-chain (HMAC-SHA256 with `pg_advisory_xact_lock`), retention, and verify-chain CLI. We get the audit-side guarantees of the spec (FR-006, FR-007, FR-007a) for free.

**Alternatives considered**:
- *New table `llm_call_log`* — premature; the audit log is the right place for "the system did X on behalf of user Y." A separate table would duplicate hash-chain logic.
- *Event-class hierarchy (`llm.*` prefix as a wildcard)* — Postgres CHECK doesn't grok prefixes; the explicit-three-identifiers approach matches what features 003/004 did.

---

## R5. How does the frontend store the API key safely?

**Decision**: `localStorage` under the key `astralbody.llm.config.v1`, holding the full JSON object `{ apiKey, baseUrl, model, connectedAt, usage: { session, today, todayDate, lifetime, perModel } }`. A privacy notice in the settings panel calls out that the key resides on the user's device. No encryption-at-rest in this iteration (the threat model is "this device is the user's"; if XSS can read localStorage, it can also intercept the key in memory, so encryption-at-rest is theater).

**Rationale**:
- localStorage is the standard "I want this to survive a refresh and a sign-out" web storage. sessionStorage would clear on tab close (user's spec answer says sign-out persists, so sessionStorage is wrong). IndexedDB is overkill for ~200 bytes of config.
- The decision matches the spec Clarifications: never auto-clear, persist across sign-out and session expiry.
- Per Constitution V (no new dependencies), we cannot pull in a crypto library to encrypt-at-rest. The most we could add is `window.crypto.subtle` with a user-supplied passphrase — but spec is explicit that there's no passphrase UX, and asking for one every page load contradicts the "persist across sign-out" answer.
- Versioned key prefix (`v1`) lets us migrate the schema later without colliding.

**Alternatives considered**:
- *sessionStorage* — wrong lifecycle per the user's clarification.
- *IndexedDB* — overengineered for ~200 bytes.
- *HttpOnly server-side cookie* — would persist the key server-side, violates FR-002.
- *`window.crypto.subtle` with a user passphrase* — rejected, see Rationale above.

---

## R6. How does Test Connection verify a model is actually served?

**Decision**: Issue `client.chat.completions.create(model=<user_model>, messages=[{"role":"user","content":"ping"}], max_tokens=1)`. Success = HTTP 200 + a non-empty `choices[0].message`. Failure = surface the upstream exception's message verbatim (404 → "model not found at endpoint X"; 401 → "auth rejected"; etc.).

**Rationale**: This matches Clarification answer #4. A `/v1/models` GET would prove the API key works for the catalog endpoint but not that the chosen model is served by the chat-completions path — exactly the "wrong model name" failure mode this probe is meant to catch. ~1 token is negligible cost for definitive end-to-end fidelity.

**Alternatives considered**: see Clarifications question 4 for the full alternatives table.

---

## R7. Token-usage counters: where does the math actually happen?

**Decision**: Server reports raw `usage.total_tokens` per call via a new `llm_usage_report` WS message (sent only when `credential_source = user`); the *browser* does the accumulation into session/today/lifetime/per-model counters and persists them to localStorage. Server-side, no aggregate is kept.

**Rationale**:
- Keeping the math on the client preserves spec FR-016 ("counters MUST NOT include calls served from the operator's default credentials") trivially: the server simply doesn't emit the message in that branch. Server has no per-user usage state that could leak.
- "Today" boundary uses the user's local-day, computed on the browser — the server doesn't know the user's timezone and shouldn't.
- Per-model breakdown is `Map<modelName, totalTokens>` in JS, serialized as a plain object into localStorage.
- Counters fail closed when `usage` is absent (some endpoints omit it): the call is recorded as one "unknown" entry on a separate counter, the numeric totals are unaffected. Acceptance scenario US3:5 requires this.

**Alternatives considered**:
- *Server-side aggregate* — would require a new per-user table or in-memory state; for a feature whose spec excludes server-side usage tracking (FR-016 makes this device-local), this is gold-plating.
- *Polling endpoint instead of push* — push has zero latency and matches the existing `audit:append` window-event pattern from feature 003 (project memory).

---

## Summary

All seven design decisions land on "reuse an existing pattern in this codebase." Zero new dependencies, zero new tables, zero new abstractions beyond `SessionCreds` and `build_llm_client`. The work is intentionally narrow: audit gets three new identifiers, the orchestrator gets one credential-resolution function call swapped in front of three call sites, the frontend gets one settings panel and two hooks. Phase 1 contracts encode the WS message and REST endpoint shapes against this design.
