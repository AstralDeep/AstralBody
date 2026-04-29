# Phase 1 Data Model — User-Configurable LLM Subscription

**Scope reminder**: this feature **adds no new tables**. Server-side state is limited to (a) three new audit `event_class` identifiers in the existing `audit_events` table, and (b) per-WebSocket in-memory credentials that vanish on disconnect. All other state lives in the user's browser.

---

## 1. Browser-resident state (the only source of truth for user credentials)

### 1.1 `LlmConfig` (localStorage key: `astralbody.llm.config.v1`)

| Field          | Type     | Required | Validation                                                                          |
|----------------|----------|----------|-------------------------------------------------------------------------------------|
| `apiKey`       | string   | yes      | non-empty after trim                                                                |
| `baseUrl`      | string   | yes      | parses as URL with `http(s)://` scheme; trailing `/` stripped on save               |
| `model`        | string   | yes      | non-empty after trim                                                                |
| `connectedAt`  | ISO 8601 | yes      | set by the client at the moment Test Connection last succeeded; cleared on save-without-probe |
| `schemaVersion`| number   | yes      | `1` (reserved for future migrations)                                                 |

**Lifecycle**:
- *Created* on the first save that passes Test Connection.
- *Updated* whenever the user clicks Save in the settings panel.
- *Cleared* when the user clicks "Clear configuration" in the settings panel (the entire localStorage key is removed).
- **Never** cleared on sign-out, token refresh, or session expiry (Clarifications Q1).
- **Never** sent server-side for storage (FR-002); only sent transiently with each LLM-dependent request.

**State transitions**:
```
[absent] ── save+probe-ok ──> [present, connectedAt=now]
[present] ── save+probe-fail ──> [present, connectedAt unchanged] (with surfaced error; no transition)
[present] ── clear ──> [absent]
[present] ── sign-out / session-expiry ──> [present] (no-op)
[present] ── browser cache wipe ──> [absent] (no in-app side-effect; user re-prompted on next LLM call only if env default also missing)
```

### 1.2 `TokenUsage` (same localStorage key, sub-object `usage`)

| Field         | Type                    | Required | Validation                                              |
|---------------|-------------------------|----------|---------------------------------------------------------|
| `session`     | integer ≥ 0             | yes      | resets on each tab open / sign-in cycle                 |
| `today`       | integer ≥ 0             | yes      | resets when the local-day boundary on the device passes |
| `todayDate`   | ISO `YYYY-MM-DD` (local)| yes      | written when `today` is incremented; rollover trigger   |
| `lifetime`    | integer ≥ 0             | yes      | resets only on explicit "Reset usage stats"             |
| `unknownCalls`| integer ≥ 0             | yes      | counts calls whose response omitted `usage.total_tokens`|
| `perModel`    | `Record<string,number>` | yes      | `model_name → cumulative_tokens` (lifetime scope)       |

**Lifecycle**:
- Only mutated by the browser, only in response to a server `llm_usage_report` WS message (which the server only emits for `credential_source = user` calls — FR-016 enforced by emission-side filter).
- "Reset usage stats" clears `session`, `today`, `lifetime`, `unknownCalls`, and `perModel` to zero / empty; leaves `apiKey/baseUrl/model/connectedAt` intact (FR-017 + acceptance US3:3).

---

## 2. Per-WebSocket in-memory state on the orchestrator (transient)

### 2.1 `SessionCreds`

```python
@dataclass(slots=True)
class SessionCreds:
    api_key: str          # never logged, never serialized
    base_url: str
    model: str
    set_at: float         # time.monotonic() — for diagnostics only
```

Stored in `Orchestrator._session_llm_creds: Dict[int, SessionCreds]`, keyed by `id(websocket)`. Populated when:
- the client sends `register_ui` with an `llm_config` field, OR
- the client sends an `llm_config_set` WS message mid-session.

Cleared when:
- the client sends `llm_config_clear`, OR
- `_cleanup_session(websocket)` runs on disconnect.

Never copied, sliced, partially logged, or returned by any API. The `__repr__` is overridden to render `<SessionCreds api_key=… base_url=https://… model=…>` with the key elided.

### 2.2 `OperatorDefaultCreds` (read once at startup)

```python
@dataclass(frozen=True, slots=True)
class OperatorDefaultCreds:
    api_key: Optional[str]      # from OPENAI_API_KEY
    base_url: Optional[str]     # from OPENAI_BASE_URL
    model: Optional[str]        # from LLM_MODEL
    @property
    def is_complete(self) -> bool: ...
```

Constructed once in `Orchestrator.__init__` from `os.getenv(...)`. Treated as immutable for the life of the process. Used as the fallback whenever `SessionCreds` is absent.

---

## 3. Database additions (PostgreSQL — extends existing `audit_events`)

**No new tables.** The existing `audit_events` table from feature 003 already has:
- per-user isolation
- HMAC-SHA256 hash-chain via `pg_advisory_xact_lock`
- append-only trigger gated by `audit.allow_purge` GUC
- partial index on failures
- index on `(user_id, recorded_at)` and `(user_id, event_class)`

The only schema delta is adding three identifiers to the `event_class` CHECK constraint. The change goes into `Database._init_db()` per the convention established by features 003 and 004.

### New `event_class` identifiers

| Identifier             | Emitted when                                                                                             | Notable payload fields                          |
|------------------------|----------------------------------------------------------------------------------------------------------|-------------------------------------------------|
| `llm.config_change`    | A user creates, updates, or clears their personal LLM configuration via WS or REST                        | `action: created\|updated\|cleared`, `base_url`, `model` (NEVER `api_key`) |
| `llm.unconfigured`     | An LLM-dependent feature is invoked but neither user creds nor operator defaults are usable               | `feature: <call-site identifier>`, `reason`     |
| `llm.call`             | An LLM-dependent call is served (either by user creds OR operator defaults)                              | `feature`, `credential_source: user\|operator_default`, `base_url`, `model`, `total_tokens` (or null), `outcome: success\|failure` |

Per-user isolation, hash-chain, retention, and the `verify-chain` / `purge-expired` CLIs from feature 003 apply unchanged.

---

## 4. Validation rules (cross-referenced against FRs and acceptance scenarios)

| Rule | Where enforced | Spec ref |
|------|----------------|----------|
| `apiKey` is never written to disk on the server | `log_scrub.py` redacts; no DB write path exists | FR-002, SC-002 |
| `apiKey` is never present in any audit-event payload | `audit_events.py` helpers strip the field before recording | FR-006, FR-007a |
| User creds always win over operator defaults when present | `client_factory.build_llm_client` prefers `session_creds` | FR-003, FR-010, US4:1 |
| Failure of user creds at runtime never falls back to operator defaults | The `try/except` in `_call_llm` re-raises without consulting `OperatorDefaultCreds` once `credential_source == USER` | FR-009, Edge case "saved key was valid at save time but later fails" |
| When a user has no creds AND env is unset: emit `llm.unconfigured` and return UI prompt | `client_factory` raises `LLMUnavailable`; caller catches → audit + `Alert` UI primitive | FR-004a, FR-007, US4:3 |
| Token-usage counters never include `operator_default` calls | Server only emits `llm_usage_report` for `credential_source == USER` | FR-016, US3:4 |
| Sign-out does NOT clear `LlmConfig` | `useLlmConfig` does not subscribe to auth-state changes | FR-013, US3:1 |
| Clearing creds takes effect on next call | `_session_llm_creds.pop(id(ws), None)` plus immediate localStorage delete | FR-012, US2:2 |
| Test Connection probe = real `chat.completions.create` with `max_tokens: 1` | `POST /api/llm/test` implementation | FR-005, Clarification Q4 |

---

## 5. What is **not** modeled here (deliberate omissions)

- **Cost in dollars**: out of scope (Out of Scope §3).
- **Provider catalogs / OAuth flows**: out of scope (Out of Scope §2).
- **Cross-device sync of credentials or usage**: out of scope; explicit in spec.
- **Predictive balance warnings**: out of scope (Clarifications Q5).
- **`KNOWLEDGE_LLM_*`-driven knowledge synthesis**: untouched; uses its own env vars; out of scope.
