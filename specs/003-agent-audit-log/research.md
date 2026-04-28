# Phase 0 Research: Agent & User Action Audit Log

**Branch**: `003-agent-audit-log`
**Date**: 2026-04-28
**Inputs**: [spec.md](./spec.md), [plan.md](./plan.md)

## R1 — NIST SP 800-53 control mapping

- **Decision**: Treat the following AU controls as in-scope and design directly to them: AU-2 (event selection), AU-3 (record content), AU-8 (timestamps), AU-9 (protection of audit information), AU-11 (record retention), AU-12 (audit generation).
- **Rationale**: These are the AU controls most directly applicable to a HIPAA-touching system at FedRAMP-Moderate-equivalent posture; they map cleanly onto FR-001 / FR-003 / FR-008 / FR-012 / FR-014 / FR-019 / FR-020. Other AU controls (AU-4 storage capacity, AU-5 alerting on failure, AU-6 review/analysis) are reasonable follow-ons but are *operational* rather than load-bearing for the user-visible feature; they are recorded as deferred concerns in quickstart.md, not in MVP scope.
- **Alternatives considered**:
  - Tracking the full AU family (AU-1 through AU-16): rejected as excessive for MVP and largely policy/operations-level rather than implementation-level.
  - Dropping NIST mapping entirely and relying solely on HIPAA recordkeeping: rejected — the user input explicitly named NIST as a constraint, and AU-9/AU-12 give us concrete tamper-evidence + always-on guarantees that HIPAA alone underspecifies.

## R2 — Append-only enforcement at the database layer

- **Decision**: Enforce append-only at *both* the application code layer (no UPDATE/DELETE statements in `backend/audit/repository.py`, enforced by code review + lint rule) AND the PostgreSQL role-grant layer. The application connects with a role that has only `INSERT` and `SELECT` privileges on `audit_events`; UPDATE/DELETE are not granted. A separate, manually-invoked `audit_retention_role` holds DELETE only on partitions older than 6 years and is never used by the application.
- **Rationale**: Belt-and-suspenders satisfies AU-9. Application-only conventions can be circumvented by a buggy migration or a careless contributor; role grants make the database itself reject the unsafe call, even from an authenticated session. Retention purges are a deliberate, separately-credentialed operation, which is also a NIST-friendly posture.
- **Alternatives considered**:
  - Application-only convention: rejected — single point of failure, fails AU-9 spirit.
  - PostgreSQL `REVOKE`-only without a separate retention role: rejected — leaves no documented path for the legal 6-year purge, forcing someone to grant UPDATE/DELETE on the application role under pressure.
  - Storing in an immutable ledger DB (QLDB, Datomic): rejected — introduces a new dependency under Principle V with no clear benefit over hash-chained append-only Postgres for this scale.

## R3 — Hash-chain construction (AU-9 tamper evidence)

- **Decision**: Per-user hash chain. Each `audit_events` row carries `prev_hash` (the `entry_hash` of the previous entry in the same user's stream) and `entry_hash = HMAC-SHA256(server_secret, prev_hash || canonical_json_of_row_minus_hash_fields)`. Insertion is wrapped in a serializable transaction that selects the user's most recent entry's hash for `FOR UPDATE` to prevent concurrent forks.
- **Rationale**: Per-user chains let us verify a single user's log without walking the entire dataset, and they constrain the blast radius of any chain corruption to one user. HMAC (not plain SHA-256) defends against an attacker who can write rows but not read the secret — they cannot forge a chain. The serializable insert + `FOR UPDATE` prevents two concurrent writes from creating sibling chain heads.
- **Alternatives considered**:
  - Single global chain: rejected — verification must walk every user's data, and one user's chain corruption breaks everyone's verification.
  - Daily/hourly chained Merkle roots published externally: rejected as overkill for MVP; can be layered on later.
  - No hash chain (rely only on grants): rejected — provides no tamper *evidence*, only tamper *prevention*; AU-9 wants both.

## R4 — HMAC key custody and rotation

- **Decision**: A server-held HMAC key (the same secret used in R3 and in the FR-016 payload digests) lives in the project's existing secret store (Keycloak-adjacent secrets / env via the deployment's standard mechanism — the constitution forbids new auth providers but not new secret storage). The key is loaded once at process start and held in process memory. Rotation: introduce a `key_id` column on `audit_events`; new entries are written under the current `key_id`; old entries continue to verify under the old key (kept available read-only in the secret store). Rotation does NOT rewrite historical entries.
- **Rationale**: Key rotation must not invalidate historical chains — that would itself be a tampering signal. The `key_id` column lets verification pick the right key per row. Storing the key in the deployment's secret store (rather than a custom KMS integration) avoids a new dependency under Principle V.
- **Alternatives considered**:
  - Re-HMAC historical rows on rotation: rejected — destroys the audit property; we can no longer prove historical rows were not retroactively altered.
  - Per-user keys: rejected — multiplies key-custody surface 1× per user with no commensurate gain; the per-user *chain* already isolates blast radius.
  - HSM-backed key: deferred — desirable, but introduces a new dependency under Principle V and is not required for MVP correctness.

## R5 — Filename handling per FR-015

- **Decision**: Adopt option (a) uniformly: persist `artifact_id` (the existing source-store ID) plus a normalized lowercase file extension (e.g., `dcm`, `pdf`, `txt`). The original filename is NOT stored in the audit row at all. The audit detail view shows `"<extension> file (<size>) — <artifact_id short hash>"` rather than the user-supplied filename.
- **Rationale**: Eliminates the filename PHI vector entirely instead of trying to encrypt/access-control it. The user can still navigate from an audit entry back to the artifact (subject to FR-018 ACL re-check at dereference), where the artifact's own UI may surface the filename under that artifact's ACL. Simpler, fewer cryptographic moving parts, no decryption-on-render risk.
- **Alternatives considered**:
  - Option (b) encrypted filename in a separate access-controlled column: rejected for MVP — adds key-management surface, encryption-at-rest semantics inside Postgres, and a separate ACL evaluator, all to display a name we already have a path to via the artifact reference.
  - Hashed filename (HMAC): rejected — provides search but is unreadable to humans; we don't need filename search in the audit log MVP.

## R6 — Active retention vs. cold archive

- **Decision**: MVP keeps the full 6-year window online in PostgreSQL with monthly range-partitioned `audit_events` (`PARTITION BY RANGE (recorded_at)`). No cold archive in MVP. Operator quickstart documents a future migration path to a WORM-locked object store for partitions older than ~13 months, gated on (a) actual data volume justifying it and (b) lead-developer approval for the new dependency under Principle V.
- **Rationale**: Range-partitioning gives us cheap retention deletion (`DROP PARTITION` with the retention role), keeps queries fast on the hot tail, and doesn't introduce a new external system in MVP. Hash-chain integrity is preserved because we never modify partitions, only drop the oldest one once it's past the 6-year horizon.
- **Alternatives considered**:
  - Single non-partitioned table: rejected — the SC-006 first-page-load target gets harder over time, and bulk delete at retention boundary becomes painful.
  - Cold archive in MVP: rejected — adds a dependency and new failure surface (archive-write reliability now affects AU-12) without MVP justification.

## R7 — RFC 8693 actor mapping for agent actions

- **Decision**: When an agent calls a tool, the orchestrator already holds the agent's delegated token (RFC 8693 token-exchange). The audit recorder reads `actor_user_id` from the token's `act` claim's `sub` (or, in the project's mock-auth dev path, from the hardcoded `dev-user-id`). The audit row records `actor_user_id` (the on-behalf-of user — owns the audit), `agent_id` (which agent acted), and `auth_principal` (the token's `sub`, i.e., the agent's machine identity) as three distinct columns. The user-visible audit log filters on `actor_user_id`; `auth_principal` exists for forensic completeness only.
- **Rationale**: Aligns with constitution Principle VII (RFC 8693 attenuated-scope tokens). Recording all three lets us answer "what did agent X do on behalf of user Y" without conflating the agent's identity with the user's. The user-visible log keys off `actor_user_id` so that user Y sees agent X's actions in their log, never user Z's.
- **Alternatives considered**:
  - Recording only `actor_user_id`: rejected — loses the ability to answer "is this agent misbehaving across many users" for operators (who, importantly, *cannot* answer that by reading audit logs of multiple users; they answer it from non-PHI agent telemetry, which is out of scope for this feature).
  - Recording only the token `sub`: rejected — would make the user-visible filter misalign with the on-behalf-of subject.

## R8 — Server-side WebSocket filtering for `audit_append`

- **Decision**: The orchestrator's WS dispatcher already maintains a per-connection `user_id`. The new `audit_append` publisher sends each event only to the connection(s) whose `user_id` equals the event's `actor_user_id`. There is no client-side filtering and no broadcast channel. A per-connection assertion in the test suite confirms a second user's connection never receives another user's events even when both are connected to the same process.
- **Rationale**: FR-007 and FR-019 are absolute. Server-side filtering is the only safe answer; client-side filtering is one bug away from a confidentiality breach.
- **Alternatives considered**:
  - Pub/sub topic per user: equivalent semantically, more infra; deferred unless we adopt a message bus for other reasons.
  - Broadcast + client filtering: rejected — violates FR-019 by design.

## R9 — Recording semantics: fire-and-forget vs. transactional outbox

- **Decision**: Use a *transactional outbox* pattern for any action that already participates in a database transaction (e.g., conversation creation, file upload metadata write): the audit insert happens in the same transaction as the action, satisfying SC-003 atomically. For actions that do not (e.g., a tool call that hits an external API), use synchronous-best-effort recording with a durable retry queue: the audit row is written immediately after the action returns; if that write fails, it goes to a small disk-backed retry queue that is drained on a background timer. Recording must never block the action's return path on success.
- **Rationale**: SC-003 requires 100% recording. Pure fire-and-forget cannot guarantee that under crash. Pure synchronous would gate the action on audit-store availability, which is unacceptable. The hybrid above is the minimum that hits 100% in steady state without coupling action latency to the audit store's availability.
- **Alternatives considered**:
  - Pure fire-and-forget: rejected — fails SC-003 under any process crash between action commit and audit emit.
  - Pure synchronous in-line: rejected — couples action latency / availability to the audit store; the action becomes unavailable when the audit store hiccups, which is exactly backwards.

## R10 — Inventory of recording sites (FR-021)

- **Decision**: The MVP records audit events at the following authority boundaries:
  - **HTTP API**: a FastAPI middleware on `backend/orchestrator/api.py` records every authenticated request (method, route template, status code, request id, latency).
  - **WebSocket message handlers**: each handler in the orchestrator's WS dispatcher records the action it just performed (`register_ui`, `ui_event`, etc.). The dispatcher itself does NOT log raw payloads.
  - **Orchestrator tool dispatch**: `Orchestrator.dispatch_tool` (or its current equivalent in `backend/orchestrator/orchestrator.py`) records before-call (`in_progress`) and after-call (`success`/`failure`) entries linked by `correlation_id`.
  - **Server-driven UI render**: `Orchestrator.send_ui_render` records each render that *changes user-visible state* (filtered by component-class allowlist to avoid recording every keystroke-driven re-render).
  - **External integrations**: any agent that calls an external system records the integration name + correlation id (no request/response bodies).
  - **Auth lifecycle**: login, logout, token refresh — recorded by the existing Keycloak callback handlers.
- **Rationale**: This inventory is the smallest set that covers FR-001 ("every user-attributable action") without recording every internal state mutation. Each site is testable with a dedicated integration test under `backend/tests/integration/audit/test_recording_coverage.py`.
- **Alternatives considered**:
  - One global request middleware only: rejected — misses WS messages, tool dispatch, and UI renders.
  - One global decorator on every internal function: rejected — explodes record volume with low-signal events and makes the log unreadable for users.

## Open follow-ups (deferred, not blocking)

- **AU-5 (failure alerting)**: alerting on audit-emit failures is operational; design a Prometheus/structured-log emit path post-MVP.
- **AU-6 (review/analysis)**: per-user log review is the user themselves; cross-user/operator review is explicitly out of scope (FR-019). If a forensic flow is added later, it must live behind its own approval/auth flow and be audited into the affected user's log.
- **AU-4 (storage capacity)**: capacity-based purge is irrelevant given a fixed 6-year time-based retention, but capacity *monitoring* is good ops hygiene.
- **WORM/object-lock cold tier**: revisit after MVP based on actual volume.

All Phase 0 unknowns from plan.md are now resolved. Proceeding to Phase 1.
