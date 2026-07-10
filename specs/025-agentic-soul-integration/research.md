# Phase 0 Research: Agentic Soul Integration

This document resolves the open technical decisions implied by the spec, grounded in the actual AstralDeep codebase. Each item follows Decision / Rationale / Alternatives.

---

## R1 — Scheduling & cron evaluation without a new dependency

**Decision**: Implement a **single in-process asyncio scheduler loop** (`scheduler/loop.py`) started as an orchestrator startup task, plus a **pure-Python next-run evaluator** (`scheduler/cron.py`) that supports the three timezone-aware forms from the spec: one-shot (`at` an absolute time), fixed interval (`every N {minutes,hours,days}`), and standard 5-field cron (`m h dom mon dow`). The loop ticks every ≤30 s, queries the durable store for jobs whose `next_run_at <= now`, and dispatches each via `scheduler/runner.py`.

**Rationale**:
- Constitution V forbids new third-party libraries, so croniter / APScheduler / Celery are out. A 5-field cron "next time after T" evaluator is a small, well-understood, testable algorithm (minute-resolution stepping with field matching). Interval and one-shot are trivial arithmetic.
- The existing `BackgroundTaskManager` (`backend/orchestrator/async_tasks.py`, `MAX_CONCURRENT_TASKS = 5`) already provides safe concurrent execution + output capture; the scheduler only needs to decide *when* and hand off to it.
- A 30 s tick comfortably meets SC-007's 1-minute tolerance and the FR-038 sub-minute floor (no job may recur faster than the tick/floor).

**Alternatives considered**:
- *croniter/APScheduler* — rejected: new dependency (Constitution V).
- *Postgres `pg_cron`* — rejected: infra dependency, can't carry per-run delegated auth, and can't reuse the chat/UI substrate.
- *External cron + webhook* — rejected: adds an external trigger surface and complicates the in-app-only/audit boundary.

---

## R2 — Unattended authorization (the critical finding)

**Decision**: Add a **server-side, encrypted offline-grant store** (`user_offline_grant` table + `orchestrator/offline_grant.py`). At job-creation consent time (user present, live tokens in the WebSocket session), capture the user's Keycloak **`offline_access` refresh token**, encrypt it at rest (using the already-present `cryptography` package + a configured key), and record `issued_at` + a hard `expires_at = issued_at + 365 days`. Per job run, the runner:
1. Loads the grant; if revoked / past `expires_at` → fail safe (pause job, audit, notify in-app) per FR-024.
2. Exchanges the refresh token at Keycloak (`grant_type=refresh_token`) for a **fresh short-lived access token** (Keycloak enforces server-side revocation here).
3. Re-checks the user's **current** `agent_scopes` live and intersects them with the job's consented scopes.
4. Calls the existing `delegation.exchange_token_for_agent(fresh_access_token, agent_id, allowed_tools, user_id, enabled_scopes)` (RFC 8693 + DPoP) to get the attenuated agent token used for the run.

**Rationale**:
- **Grounding finding**: `delegation.exchange_token_for_agent` (`backend/orchestrator/delegation.py:158`) takes `user_token` as the RFC 8693 `subject_token` and **requires a live access token**; there is no refresh-from-stored-token path today. Feature 016 persistent login is **purely client-side** (oidc-client-ts `localStorage`); it stores **no server-side token** and the 365-day cap is enforced in the browser (`specs/016-persistent-login/research.md`). Therefore the spec's clarification "reuse the existing persistent-login mechanism" cannot be taken literally — there is nothing server-side to reuse.
- The faithful interpretation is to reuse the **same underlying Keycloak grant** (`offline_access`) and the **same 365-day ceiling** the login feature depends on at the realm level (Offline Session Max ≥ 365 days), but add the missing server-side piece: an encrypted refresh-token store + a refresh→access→delegation exchange chain. This keeps the IdP and delegation paths unchanged; it adds storage + a refresh call.
- Every invariant the spec demands is preserved: authority can never exceed the user's current scopes (step 3 intersection), revocation/logout disables future runs (step 1 + Keycloak refresh failure), hard 365-day cap (step 1), and every mint is audited.

**Security controls (Constitution VII, flagged for lead-dev review)**:
- Refresh tokens encrypted at rest; encryption key from environment/secret store (never committed).
- Store is per-(user, agent) and strictly user-scoped; never returned over any API.
- Re-derivation is audited (`event_class="auth"`, `action_type="auth.offline_grant_minted"` / `auth.offline_grant_revoked`).
- A user "sign out everywhere" / scope revocation path invalidates grants.

**Alternatives considered**:
- *Restrict unattended jobs to non-PHI / require a live session* — rejected: contradicts the user's clarified choice (Q2 = scoped+PHI, re-validated) and openclaw parity.
- *Long-lived service account acting for all users* — rejected: breaks per-user attribution and least privilege; un-auditable as the user.
- *Encrypt-and-store the access token instead of refresh* — rejected: access tokens are short-lived; refresh/offline is the only grant that survives to run time.

---

## R3 — PHI exclusion gate for memory (second finding)

> **Update 2026-05-27**: The lead developer / product owner **explicitly approved adding third-party package(s) required for PHI detection**, recording the Constitution V approval. This supersedes the earlier "pure-Python only" constraint for *this specific purpose* and lets us use a purpose-built detector instead of regex heuristics.

**Decision**: Use **Microsoft Presidio** (`presidio-analyzer`, plus `presidio-anonymizer` for redaction of review/notification artifacts) as the authoritative PHI/PII detection gate, running **locally in-process** so PHI never leaves the application boundary (preserves FR-034/SC-006). The memory/personalization write path (`personalization/phi_gate.py`) passes every candidate value through Presidio; if any HIPAA-relevant entity is detected (`PERSON`, `US_SSN`, `MEDICAL_LICENSE`, date-of-birth `DATE_TIME`, `PHONE_NUMBER`, `EMAIL_ADDRESS`, `LOCATION`, `US_DRIVER_LICENSE`, plus a **custom MRN / encounter-ID recognizer**), the content is **blocked** from durable `memory_item` and `short_term_signal` while remaining usable in the live turn. Structured typed categories (R-data-model) are **kept as defense-in-depth** and to keep memory high-signal; Presidio is the enforcement gate over each value. The existing audit PII sanitization (`backend/audit/pii.py`) is unchanged for audit-metadata; Presidio governs the memory write path and PHI-redaction of dream-review / notification text.

**Rationale**:
- Presidio is the de-facto open-source PII/PHI framework, **Apache-2.0** (matches the project license), healthcare-oriented, and **extensible with custom recognizers** (MRN, accession numbers) — far more reliable than regex for names and contextual identifiers, making SC-005 robust even against free-text inputs (personality notes, explicit "remember" text).
- It runs **locally** (no external PHI egress), unlike cloud medical-NLP services, so it does not weaken the in-app-only / no-external posture.
- With lead-dev approval recorded, the dependency is constitution-compliant (V). Transitive deps (spaCy + a language model, e.g. `en_core_web_lg`) are covered by the approval; the model is fetched at **build time** and bundled into the image — no runtime network fetch in production (document in deploy / Dockerfile).
- The previous pure-Python identifier guard is retained as a **cheap pre-filter** ahead of Presidio (fast-path obvious rejects, and a fallback if the analyzer is unavailable at startup — fail-closed: if the detector can't run, block the write).

**Alternatives considered**:
- *Pure-Python identifier regex only* (previous plan) — demoted to a pre-filter; insufficient alone for names/contextual PHI.
- *AWS Comprehend Medical / cloud medical NLP* — rejected: sends PHI to an external service (BAA burden; violates in-app/no-egress posture and FR-034).
- *scrubadub / philter (clinical)* — viable but smaller ecosystems and weaker custom-recognizer/anonymizer story than Presidio; can be added as supplementary recognizers later if needed.

**Memory policy unchanged**: durable memory is still **non-PHI personalization only** (clarification Q3); Presidio makes that guarantee enforceable rather than probabilistic. PHI may still flow *through* a live turn / job run and be delivered + audited, but never persists.

---

## R4 — System-prompt injection of personality, memory, and skills

**Decision**: Inject per-user context into the orchestrator's LLM system prompt at the existing extension point in `backend/orchestrator/orchestrator.py` — immediately after the knowledge-synthesis routing-hints block (~line 2516) and before `_call_llm` (~line 2598). Order: existing safety/compliance preamble → tool/process rules → **memory recall block** (durable items + recent recalled signals) → **skill guidance block** (one-line how-to per enabled skill/tool) → **personality block** ("soul"), explicitly framed as *style only, never overriding safety/security/compliance* (FR-015). Personality + profile come from the per-user `user_personalization` row; memory from `memory_item` (+ recent `short_term_signal`).

**Rationale**:
- The injection point is already used for additive per-turn context (file context, canvas context, knowledge synthesis), so this is a low-risk extension of an established pattern.
- Putting personality **last and clearly subordinate** ensures the compliance preamble dominates (FR-015, edge case "personality vs compliance").
- Skills as one-line guidance keeps the enabled-tool set authoritative (the actual tool list is still computed by the existing scope/permission gate in Phase A/B/C of tool assembly), so disabled skills cannot leak (FR-012).

**Alternatives considered**:
- *Per-agent system-prompt override files (openclaw SOUL.md)* — rejected: openclaw uses per-agent workspace files; AstralDeep's clarified model is **one personality per user** (Q3), and a DB-backed per-user fragment is simpler, auditable, and editable through primitives.

---

## R5 — Memory capture, recall, and the "remember" path

**Decision**: Provide three orchestrator-level memory capabilities (`personalization/memory_tools.py`): `remember(category, value)` (explicit user request), `memory_search(query)` and `memory_get()` (recall). Auto-capture: after a turn, a lightweight extraction proposes candidate **short-term signals** (structured, PHI-gated) — these are *not* durable; the dreaming sweep (R6) is the promotion gate (FR-016, FR-027). Recall is injected into the prompt (R4). All memory mutations are audited (FR-019) and strictly user-scoped.

**Rationale**: Matches the clarified "both explicit and auto-capture, dreaming is the gate" (Q4). Keeping auto-capture as non-durable signals avoids polluting durable memory and gives the user a single review/delete surface.

**Alternatives considered**:
- *Auto-capture writes durable memory immediately* — rejected: contradicts the consolidation-gate clarification and risks low-signal bloat (the problem dreaming exists to solve).

---

## R6 — Dreaming (consolidation) execution model

**Decision**: Implement dreaming as a **system-owned scheduled job** (rides on R1's scheduler) that runs per user on a default cadence (configurable; default daily), **enabled by default / opt-out** (FR-029, Q5). `dreaming/consolidation.py` scores short-term signals (recurrence, recency, diversity) and promotes those above threshold into durable `memory_item` rows, excluding any PHI-flagged content via the R3 gate, and writes a human-readable `consolidation_sweep` record for review. The user can disable or trigger it on demand.

**Rationale**: Reuses the scheduler instead of a second background mechanism. Opt-out matches the clarification; structured signals make scoring simple and PHI-safe.

**Alternatives considered**:
- *Separate dreaming daemon* — rejected: duplicates scheduling infrastructure.
- *Opt-in default* — rejected: clarification chose opt-out (Q5).

---

## R7 — Server-generated UI for all new surfaces

**Decision**: Build onboarding personalization, the skills catalog, personality editor, memory viewer, schedule manager, and dream review entirely from the existing 27 primitives — chiefly **ParamPicker** (forms: boolean/number/text/checklist/select with `submit_message_template`), **Card/Table/List/Alert/Button/Collapsible/MetricCard/Text**. Interactive submits round-trip via the existing ParamPicker → `submit_message_template` → `onSendMessage` → `ui_event:chat_message` path; the orchestrator interprets the message and calls the relevant new tool/endpoint. No new primitive types; no new `DynamicRenderer` cases (SC-009, Constitution VIII).

**Rationale**: **Grounding finding** confirmed all 27 primitive `type` strings are dispatched in `DynamicRenderer.tsx`, `create_ui_response` wraps components into `_ui_components`, and ParamPicker already round-trips to the backend as an LLM-interpreted chat message (e.g., `agents/classify/mcp_tools.py::propose_training_config`). This is exactly the openclaw "server decides the UI" property, satisfied with zero frontend additions.

**Alternatives considered**:
- *Hardcoded React panels (as SettingsMenu/UserGuidePanel are today)* — rejected for the data-bound management surfaces because it would violate the spec's server-generated-UI imperative (FR-031) and add frontend templates (SC-009). Thin React entry points (a button that asks the backend to render the panel) are acceptable and minimal.

---

## R8 — Job execution reuses the async-query substrate

**Decision**: `scheduler/runner.py` executes a due job by calling the same chat-turn machinery used for async queries, driven by a `VirtualWebSocket` (`backend/orchestrator/async_tasks.py`) so all UI/chat outputs are captured and persisted to the target chat's history, and an in-app notification is emitted on completion (FR-022). Delivery is **in-app only**; there is no external-channel code path (SC-006).

**Rationale**: Reuses proven capture/persist behavior; guarantees scheduled output looks identical to interactive output and never leaves the app.

**Alternatives considered**:
- *Bespoke headless runner* — rejected: would re-implement output capture and risk divergence from interactive behavior.

---

## R9 — Restart recovery & durability

**Decision**: `scheduled_job` and `job_run` are durable Postgres rows. On startup the scheduler reconciles: any `job_run` left `running` (interrupted by restart) is marked `interrupted` and audited; `next_run_at` is recomputed for active jobs. In-flight async execution is not resumed (at-most-once for the interrupted tick); the next scheduled tick proceeds normally (FR-025, edge case "restart").

**Rationale**: Matches the single-orchestrator assumption and gives a defined, auditable post-restart state without a distributed queue.

**Alternatives considered**:
- *Exactly-once / distributed execution* — rejected: out of scope (spec Out of Scope; single-orchestrator assumption).

---

## Summary of new vs reused

| Capability | Reused as-is | New (security-equivalent) |
|---|---|---|
| Skills | `agent_scopes`, `tool_overrides`, tool registry | read-view "catalog" + enable/disable audit |
| Personality / profile / memory | `user_preferences` pattern, prompt injection point | `user_personalization`, `memory_item`, `short_term_signal` tables + `personalization/` |
| Onboarding | `onboarding_state`, `tutorial_step`, ParamPicker | personalization steps + seeds |
| Scheduling | `BackgroundTaskManager`, `VirtualWebSocket` | `scheduled_job`/`job_run` store, asyncio loop, pure-Python cron |
| Unattended auth | Keycloak `offline_access`, RFC 8693 `delegation`, DPoP | **`user_offline_grant` encrypted store + refresh→access exchange** |
| Dreaming | scheduler (R1), memory (R5) | `consolidation_sweep` + scoring |
| PHI gate | `audit/pii.py` invariants | **Presidio** detector (lead-dev approved) + structured fields + pre-filter, fail-closed |
| UI | all 27 primitives, `DynamicRenderer` | none (server-generated) |
| Audit | hash-chained `audit_events`, `audit/hooks.py` | new `event_class` values |
