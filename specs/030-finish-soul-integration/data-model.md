# Phase 1 Data Model: Finish Soul Integration

This feature reuses existing 025 tables. **No new tables are anticipated**; the default posture is zero schema change. Any column added during implementation MUST ship as an idempotent, guarded `_init_db()` delta with a documented rollback (Constitution IX).

## Reused entities (no shape change unless noted)

### scheduled_job
A user-consented recurring/one-shot task.
- Key fields used: `id`, `user_id`, `name`, `instruction`, `agent_id`, `schedule_kind` (`cron`|`interval`|`one_shot`), `schedule_expr`, `timezone`, `consented_scopes` (list), `offline_grant_id` (**now populated** by the consent handshake; previously always `None`), `status` (`active`|`paused`|`completed`), `last_run_at`, `next_run_at`, `target_chat_id`.
- New behavior: `offline_grant_id` is written from the captured grant (FR-003); dreaming registers a per-user job here (FR-013).

### job_run
One execution of a scheduled job (audit correlation).
- Key fields used: `id`, `job_id`, `user_id`, `correlation_id`, `outcome` (`success`|`failure`|`skipped_auth`), `summary`, `started_at`, `finished_at`, `auth_ref`.
- New behavior: structured logs/metrics emitted on run completion (FR-017); no shape change.

### user_offline_grant
Encrypted, revocable, lifetime-capped persistent-authority reference.
- Key fields used: grant id, encrypted refresh token (Fernet), expiry (≤365-day cap), revocation state.
- New behavior: written via the WS consent capture (FR-003); subject to recorded security review (FR-004). `is_valid()` and `mint_access_token()` already consumed by the runner. Mint success now logs structured metric (FR-017). No shape change.

### memory_item
Stored, non-PHI personalization fact.
- Key fields used: id, user_id, content/structured fields, created/updated timestamps, scope/category.
- New behavior: reachable via the `__memory__` meta-tool (FR-007); all writes pass the existing PHI gate + audit (FR-008); writes log structured metric (FR-017). No shape change.

### short_term_signal
Ephemeral signal captured via `capture_signal`.
- New behavior: reachable via meta-tool if exposed; otherwise unchanged.

### user_personalization
Per-user profile + flags.
- Key fields used: profession, goals, personality, enabled skills, `dreaming_enabled`.
- New behavior: onboarding submits now persist here (FR-009); enabled skills drive prompt guidance (FR-010); `dreaming_enabled` governs the recurring dreaming job (FR-014). No shape change.

### consolidation_sweep
Record of a dreaming consolidation sweep (`record_sweep`).
- New behavior: sweep runs now emit structured logs/metrics (FR-017); sweeps run automatically via the per-user recurring job (FR-013). No shape change.

## Non-entity state

### Feature flag: FF_SCHEDULER_EXECUTION (new)
Env-driven boolean in `shared/feature_flags.py`, default **False**. Gates the scheduler execution loop start (FR-005). Enabled only after the recorded offline-grant security sign-off (FR-004). Distinct from existing `FF_SCHEDULING_CHAT` (proposal/consent only).

### Security sign-off marker (new, documentation artifact)
A recorded lead-dev sign-off (committed review note referenced in the PR) that authorizes enabling `FF_SCHEDULER_EXECUTION`. Not a DB entity.

### Knowledge index entries (cleanup)
`backend/knowledge/_index.md` is regenerated at runtime from on-disk `.md` files. Post-cleanup it MUST contain **0** entries for `grants`, `nefarious`, `classify`, `forecaster`, `llm_factory` (FR-021). Not a DB entity.

## Validation rules

- A job MUST NOT execute without a valid `offline_grant_id` (runner already enforces → `skipped_auth`).
- Run authority = intersection(`consented_scopes`, current live scopes) (FR-006; runner `_intersect_scopes`).
- Memory writes MUST pass the PHI gate; disallowed content is refused and never persisted (FR-008).
- Onboarding submits with partial/invalid values MUST be rejected without persisting a corrupt profile (Edge Cases).
- The execution loop MUST be unreachable when `FF_SCHEDULER_EXECUTION` is false (fail-closed, FR-005).
