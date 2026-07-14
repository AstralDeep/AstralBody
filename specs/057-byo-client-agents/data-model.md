# Data Model: Bring-Your-Own Client-Side Agents (Feature 057)

All schema ships as idempotent, guarded `_init_db()` deltas (Constitution IX), mirroring the feature-027/029 pattern: `CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS` via `_column_exists`, guarded `_migrate_*` helpers, inline `Rollback:` comments, and a `SCHEMA_REVISION` bump (`055.002 → 057.001`) with the `schema_meta` fast-path.

## Entities

### 1. User Agent (`user_agent` — NEW table)

The durable registry row for one user-authored, client-hosted agent. **Distinct from `draft_agents`** (a transient authoring/codegen artifact) and from in-memory liveness (`self.agents` socket presence).

| Column | Type | Notes |
|--------|------|-------|
| `agent_id` | TEXT PRIMARY KEY | Owner-namespaced, collision-refused at registration (Constitution H). |
| `owner_user_id` | TEXT NOT NULL | **Canonical owner key** (the OIDC `sub`). The single source the boundary binds to. |
| `owner_email` | TEXT | Denormalized for display + reconciliation with `agent_ownership.owner_email`. |
| `display_name` | TEXT NOT NULL | User-facing name. |
| `status` | TEXT NOT NULL DEFAULT `'authoring'` | Durable lifecycle: `authoring \| validated \| live \| disabled`. NOT running/offline. |
| `declared_tools` | JSONB NOT NULL DEFAULT `'[]'` | Tools the agent declared (Constitution B). |
| `declared_scopes` | JSONB NOT NULL DEFAULT `'[]'` | Requested scope-level claims (Constitution B/C). |
| `declared_egress` | JSONB | Declared external egress targets/categories (Constitution J), or NULL. |
| `constitution_version` | TEXT | Agent-constitution semver this agent was Analyze-validated against (Constitution L). |
| `validated_at` | TIMESTAMPTZ | When Analyze last passed. |
| `revalidation_required` | BOOLEAN NOT NULL DEFAULT FALSE | Set TRUE by a constitution MAJOR bump or a revision (FR-028). |
| `draft_id` | TEXT | FK-ish link to `draft_agents.id` (authoring/codegen home, FR-007). |
| `host_client_id` | TEXT | Which desktop host this agent belongs to (author-on-mobile → desktop binding, FR-024). |
| `host_session_id` | TEXT | Disambiguates duplicate/reconnect instances (edge case). |
| `host_last_seen_at` | TIMESTAMPTZ | Heartbeat freshness; feeds the derived running/offline state (never authoritative alone). |
| `is_public` | BOOLEAN NOT NULL DEFAULT FALSE **CHECK (`is_public` = FALSE)** | Privacy-by-construction structural (FR-019/020, Constitution K). |
| `created_at` / `updated_at` | TIMESTAMPTZ | Standard. |

**Derived (not stored)**: `running` ⇔ `agent_id ∈ orchestrator.self.agents` **AND** `host_last_seen_at` is fresh. Persisting liveness would drift on crash (FR-010 is offline-on-close, no server-side persistence).

**Companion row**: on go-live, insert one `agent_ownership` row (`owner_email`, `is_public=FALSE`) per user agent so the existing routing/permission/visibility code treats it uniformly — no parallel path (FR-007).

### 2. Agent Constitution (baked asset + loader — not a DB entity)

- **Authoritative runtime copy**: `backend/agent_constitution/agent_constitution.md` (baked into the image; `.specify/` and `specs/` are not — `Dockerfile:49` copies only `backend/`). Byte-identical to `specs/057-byo-client-agents/agent-constitution.md` (CI test asserts identity).
- **Loader** `backend/orchestrator/agent_constitution.py`: `AGENT_CONSTITUTION_VERSION` (semver from the header), `load_checklist()` → the A–L principle list. Path resolved `__file__`-relative (mirroring `knowledge_synthesis.AUTHORED_KNOWLEDGE_DIR`). Never hand-copied into a Python literal (`mcp_tools_dev.py:231` proves that drifts).

### 3. Authoring Session (additive `draft_agents` columns)

The 5-phase journey rides `draft_agents` (reuse), with additive nullable columns:

| Column | Type | Notes |
|--------|------|-------|
| `origin` | (existing) gains value `'byo_client'` | Keeps deliberate flow distinct from `auto_chat` (no gap-dedup / `should_inject` conflation). |
| `phase` | TEXT | `specify \| clarify \| plan \| tasks \| analyze \| generated`. |
| `clarify_answers` | TEXT (json) | Captured clarifications. |
| `plan_json` | TEXT | The tool/scope/data mapping approved in Plan. |
| `analyze_result` | TEXT (json) | Pass/fail + per-principle cited violations. |
| `constitution_version` | TEXT | Version Analyze ran against (stamped onto `user_agent` on go-live). |
| `host_binding` | TEXT | Target desktop host (FR-024). |

### 4. Boundary Verification Record (no new table)

Reuses the existing hash-chained `audit_events` (`delegation` / `agent_tool_call` classes). Every user-agent action's allow/deny, owner, derived scopes, and reason are already recorded by the gate stack + `_record_hop_audit`. No new storage.

### 5. Owning User (no new table)

The human `owner_user_id`; the sole principal the boundary derives grants from. Already the validated OIDC `sub` in `ui_sessions[ws]`.

## Owner-identity reconciliation (resolved, not deferred)

`agent_ownership` keys on **`owner_email`**; permissions/dispatch key on **`user_id`**. **Decision: `owner_user_id` (OIDC `sub`) is canonical** on `user_agent` and in every boundary check; `owner_email` is denormalized for display and for writing the companion `agent_ownership` row. The owner-binding check at registration compares the authenticated socket's `sub` against `user_agent.owner_user_id` — never against a card field or email alone. This removes the lock-out / mis-bind risk flagged in research.

## Lifecycle state machine (`user_agent.status`)

```text
authoring ──(Clarify+Analyze pass, code generated)──▶ validated
validated ──(delivered to host + registered inward)──▶ live
live ──(revision authored)──▶ authoring         (prior live version keeps running until the revision validates — FR-026)
live ──(owner disable / delete)──▶ disabled
any ──(constitution MAJOR bump)──▶ revalidation_required=TRUE  (boundary fail-closed refuses routing until re-Analyze passes — FR-028, Constitution L)
```

`running`/`offline` is orthogonal and derived (socket presence), independent of `status`.

## Validation rules (from requirements)

- Analyze MUST pass (all A–L) before `status` leaves `authoring` (FR-003/SC-004).
- `is_public` is immutable FALSE (DB CHECK) — no code path may flip it (FR-020, Constitution K).
- Registration MUST refuse an `agent_id` whose `owner_user_id` ≠ the authenticated principal, and any id colliding with a built-in/public/reserved/other-user id (Constitution H).
- A grant on a private user agent is permitted only when `can_user_use_agent(caller, agent_id)` is true (owner or public) — enforced at the grant endpoint, dispatch gate, and tool-list build (FR-016/019).
- `revalidation_required=TRUE` ⇒ boundary refuses to route the agent until re-Analyze clears it (FR-028).

## Migration & rollback

- **Forward**: `_apply_full_schema` adds `user_agent` + the `draft_agents` columns; `SCHEMA_REVISION 055.002 → 057.001`; guarded `_migrate_revalidate_on_constitution_change` sets `revalidation_required=TRUE` where a stored `constitution_version` MAJOR is below `AGENT_CONSTITUTION_VERSION`.
- **Rollback**: drop `user_agent` and the additive `draft_agents` columns; revert `SCHEMA_REVISION`. No destructive change to existing tables (all additive), so a rollback loses only 057 registry rows; user agents simply stop being routable (fail-closed) — consistent with `FF_BYO_AGENTS` off.
- **Data safety**: additive-only; the `SCHEMA_REVISION` bump forces one idempotent re-run at next boot (expected/safe per convention).
