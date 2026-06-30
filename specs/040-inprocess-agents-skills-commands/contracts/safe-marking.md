# Contract: Owner-Safe Marking

## Storage

`agent_trust(agent_id PK, is_safe bool, marked_by, marked_at, prior_state, revised_reset_at)` — see data-model.md.

## Operations (orchestrator/agent_trust.py)

- `is_safe(agent_id) -> bool`: read the marker (cached per request). Returns False if absent or if `FF_SAFE_AGENTS` is off.
- `mark_safe(agent_id, actor_claims, safe: bool) -> result`:
  - MUST verify `actor_claims` carry the admin/owner role server-side (mirror `_h_draft_approve`'s admin check / `set_agent_visibility`). Reject otherwise.
  - Upsert `is_safe`, set `marked_by`/`marked_at`, store `prior_state`.
  - Emit an `agent_lifecycle` audit event: `marked_safe` or `unmarked_safe`, actor, `agent_id`, `prior_state`.
- `reset_on_revision(agent_id, actor_claims)`: called from `agentic_creation.apply_revision` when a previously-safe agent is revised; sets `is_safe=False`, `revised_reset_at=now()`, emits an audited `safe_reset` event. Re-approval (a fresh `mark_safe`) is required.
- Boot seed: mark the nine bundled agents safe idempotently (`marked_by='system'`), one audit event per newly-seeded agent, none on re-run.

## Permission baseline (orchestrator/tool_permissions.py::is_tool_allowed)

When `FF_SAFE_AGENTS` is on, resolution order:

1. Explicit per-(tool, kind) override present → honor it (allow or deny).
2. Explicit scope grant/deny present → honor it.
3. Agent is safe (`agent_trust.is_safe`) AND no explicit negative record for this scope/tool → **ALLOW**.
4. Otherwise → deny (legacy default).

Independent vetoes that always apply regardless of safe:

- Hard security-flag block (`tool_security` `blocked=True`) → deny (never cleared by safe; clearing requires a separate, audited owner action).
- An explicit user opt-out (override deny or scope-disabled record) → deny (opt-out wins; this is rule 1/2 taking precedence over rule 3).

No per-user rows are written by the safe baseline; the verdict is computed at check time.

## Gating & audit invariants (MUST hold)

- `mark_safe`/`unmark_safe`/`reset_on_revision` are admin/owner-only, server-side enforced.
- Every transition emits an `agent_lifecycle` audit event with actor + prior_state.
- With `FF_SAFE_AGENTS` off, `is_tool_allowed` behaves exactly as today (default-deny); `agent_trust` is inert.
- Safe never bypasses taint, policy, egress gating, PHI handling, or audit.
