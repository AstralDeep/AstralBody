# Phase 0 Research: Finish Soul Integration

All "unknowns" here are really "confirm the existing shape" — this is a remediation feature. Findings are grounded in the current code.

## R1 — Orchestrator scheduler seams (FR-001/FR-002)

**Decision**: Implement two async methods on `Orchestrator` with the exact signatures `backend/scheduler/runner.py` already calls:
- `async def run_scheduled_turn(self, *, user_id, chat_id, instruction, agent_id, access_token, allowed_scopes, correlation_id) -> str` — executes `instruction` as a background chat turn via the existing `BackgroundTaskManager` + `VirtualWebSocket`, under the minted delegated `access_token` bounded to `allowed_scopes`, persisting output to chat history; returns a short summary string.
- `async def notify_user(self, user_id, payload: dict) -> None` — fans an in-app `notification` to all of the user's connected sockets (reusing `_safe_send`/`ui_clients`) and persists it so it is delivered on next connect.

**Rationale**: `runner.py:99` and `runner.py:44` already call these; the runner, store, scope-intersection, mint, and reschedule logic are complete and unit-tested. Only the orchestrator side is missing. Signatures are fixed by the caller.

**Alternatives rejected**: Changing the runner to inline orchestrator internals — rejected; the runner is the tested unit and the seam boundary is intentional.

## R2 — Fail-closed scheduler-execution gate (FR-004/FR-005, Constitution VII)

**Decision**: Add a new env flag `FF_SCHEDULER_EXECUTION` (default **False**) to `shared/feature_flags.py`. The scheduler **execution loop** (`scheduler/loop.py`) starts only when the flag is enabled AND a recorded security sign-off marker is present. Until then the loop does not start and the scheduling surface reports unattended execution as unavailable. Note this is distinct from the existing `FF_SCHEDULING_CHAT` (default True), which only injects the chat consent meta-tool — proposing/creating jobs stays available; *executing* them is what gates.

**Rationale**: Constitution VII forbids running security-critical offline-grant execution without lead-dev sign-off; the loop is currently started unconditionally (027 wiring). Fail-closed default + explicit flag is the minimal safe mechanism and matches the project's `FF_*` convention.

**Alternatives rejected**: Default-ON flag (ships ungoverned); no flag / always-off hard-code (loses the ability to enable post-review without a code change).

## R3 — Offline-grant security review sign-off (FR-004, Constitution VII)

**Decision**: Conduct the lead-dev security review of `backend/orchestrator/offline_grant.py` (encryption at rest via Fernet, revocation, lifetime cap, scope intersection, no token egress) and record the sign-off in-repo (review note committed under `specs/030-finish-soul-integration/` and referenced in the PR). The `FF_SCHEDULER_EXECUTION` gate may be enabled only after this is recorded.

**Rationale**: The store is implemented and unit-tested but never formally reviewed; the review is a governance gate, not new code.

**Alternatives rejected**: Treating unit tests as the review — rejected; Constitution VII requires explicit lead-dev sign-off.

## R4 — Memory tool registration (FR-007/FR-008)

**Decision**: New module `backend/orchestrator/memory_chat.py` mirroring `scheduling_chat.py`: `META_AGENT_ID = "__memory__"`, `meta_tool_definitions()` exposing `remember` / `memory_search` / `memory_get` (and `capture_signal` if appropriate), `should_inject(user_id)` (respect enablement/scope), and `handle_meta_tool(...)` dispatching to the existing `personalization/memory_tools.py` through the PHI gate + audit. Inject into the chat tool list at the same orchestrator site that injects scheduling/agentic-creation meta-tools.

**Rationale**: `scheduling_chat.py` is the proven, tested pattern for orchestrator meta-tools; memory tools already exist and are unit-tested but unreachable. Reuse minimizes risk.

**Alternatives rejected**: Treating each memory function as a standalone pseudo-agent — rejected; the meta-tool module is the established convention.

## R5 — Onboarding submit interpretation (FR-009/FR-010)

**Decision**: Interpret onboarding ParamPicker `submit_message_template` submissions in the orchestrator chat path and persist via the existing `personalization` endpoints/repository (profile + enabled skills). Then populate the dead `personalization_skill_lines` call site (`orchestrator.py:~2925`) from the user's enabled skills so guidance reaches the prompt (FR-010). Approach mirrors how scheduling submits are handled.

**Rationale**: Panels already emit submit templates; only interpretation/persistence is missing. The skill-guidance call site already exists but is never populated.

**Alternatives rejected**: A bespoke onboarding RPC channel — rejected; reuse the existing chat-submit + meta-tool path.

## R6 — Offline-grant consent capture over WS (FR-003)

**Decision**: Add WS handlers for `offline_grant_request` (server→client, asking the client to affirm capture of its `offline_access` refresh token at job-creation consent) and `offline_grant_ack` (client→server affirmation), dispatched through the existing `chrome_events.py`/`handle_ui_message` routing. On ack, call the existing `OfflineGrantStore.capture(...)` and write the resulting `grant_id` to the `scheduled_job.offline_grant_id` (currently always `None`).

**Rationale**: The store's `capture()` exists; only the WS handshake that feeds it is missing. The contract is documented in `contracts/websocket-events.md`.

**Alternatives rejected**: REST-only capture — rejected; consent happens in the live WS chat session at creation time.

## R7 — Dreaming as a per-user recurring job (FR-013/FR-014)

**Decision**: On personalization init (and on dreaming-enable), ensure a per-user recurring `scheduled_job` exists with the dreaming instruction and `DREAMING_DEFAULT_CRON` (currently dead code in `agentic_settings.py:44`); pause/remove it on disable. Route dreaming jobs to the consolidation sweep (either via `run_scheduled_turn` dispatch on a dreaming marker, or a dedicated runner branch invoking `dreaming/consolidation.run_sweep`).

**Rationale**: All prerequisites exist (sweep logic, enable flag, `record_sweep`, scheduler loop wiring); only the job registration is missing.

**Alternatives rejected**: Manual-only trigger (the current broken state) — rejected; spec requires default-on automatic.

## R8 — Deferred tests & coverage (FR-015/FR-016)

**Decision**: Add FastAPI `TestClient` contract tests (`test_profile_api.py`, `test_personalize_steps.py`, `test_skills_api.py`, `test_memory_api.py`), an onboarding round-trip integration test (`tests/integration/test_onboarding_personalization.py`), and a scheduler end-to-end test (`test_scheduler_e2e.py`) covering run timing, scope intersection, `skipped_auth`, restart recovery, and notification. Bring changed-code coverage ≥90% (`diff-cover` vs `origin/main`). Run both CI invocations locally via root `.venv` + docker postgres.

**Rationale**: These were explicitly deferred in 025 ("validated live"), leaving REST/loop code at ~0% automated coverage — below the merge gate.

## R9 — Structured observability (FR-017)

**Decision**: Add `logger.info`/metrics with structured `extra={...}` for: scheduled run success (runner step 5), consolidation sweeps (`consolidation.run_sweep`), memory writes (`memory_tools.remember`/`capture_signal`), and grant mints (`offline_grant.mint_access_token` success). Failures already log; this backfills the success/operation paths per Constitution X.

## R10 — Durable knowledge cleanup (FR-021)

**Decision**: Remove the retired/merged agents' knowledge files (`grants`, `nefarious`, `classify`, `forecaster`, `llm_factory` — capabilities + techniques) so they do not exist in the image build context, and ensure the runtime `KnowledgeSynthesizer` index regenerates without them. Because `backend/knowledge/` is git-ignored and re-indexed from disk, "durable" means: not present in the COPYed image content and not re-creatable by the indexer. Treated as intentional destructive cleanup (lead-dev approval, Principle IX).

**Rationale**: The 029 `git rm` left on-disk copies that the indexer re-discovers, re-adding retired-agent index entries.

## R11 — Bookkeeping reconciliation (FR-020)

**Decision**: Update 025's `tasks.md`: mark T022 done (reimplemented as `webrender/chrome/surfaces/personalization.py`, not the deleted React frontend), mark T050 done (implemented in `scheduling_chat.py`), and annotate T018 as "archived by 030 rewrite — final state documented." No code change; documentation accuracy only (Constitution X, no contradictory claims).

## R12 — Schema impact

**Decision**: No new tables. `scheduled_job.offline_grant_id` already exists (currently written as `None`). Notification persistence reuses chat history / `job_run`. If a dedicated notification column/table proves necessary during implementation, it ships as an idempotent guarded `_init_db` delta with a documented rollback (Principle IX). Default assumption: **no schema change required**.
