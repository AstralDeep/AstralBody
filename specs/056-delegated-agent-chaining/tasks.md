# Tasks: Delegated Agent Chaining

**Input**: Design documents from `/specs/056-delegated-agent-chaining/`

**Prerequisites**: plan.md, spec.md, research.md (17 decisions + fail-closed resolutions), data-model.md, contracts/delegation-chaining.md, contracts/audit-and-machine-turn.md, quickstart.md

**Tests**: REQUIRED — Constitution III (≥90% changed-code coverage) and X (production-posture verification). This feature wires security-critical authority machinery; test tasks accompany every code path. The 048 property suite + delegation + tool-permission suites MUST stay green with the flag off (SC-009). quickstart.md is the live-verification script.

**Organization**: grouped by user story. US3 (dispatch-path parity) is a prerequisite hardening slice that lands with/before US1 flag-on; US1 is the headline MVP. US1–US5 are independently shippable increments.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1–US5 for user-story tasks; no label for Setup/Foundational/Polish
- Every task names exact file paths. All paths are repo-relative from the worktree root.

---

## Phase 1: Setup (shared scaffolding)

**Purpose**: audit vocabulary + flag confirmation every story hangs off. No new product flag is required — the seam rides the existing `FF_RECURSIVE_DELEGATION` (interactive) and `FF_SCHEDULER_EXECUTION` (machine root).

- [X] T001 Add `"delegation"` to the `EVENT_CLASSES` tuple in `backend/audit/schemas.py` (≈:30-65, before the closing paren) so hop provenance records validate through `AuditEventCreate._check_event_class` (≈:115-119); unit test in `backend/tests/test_audit_schema_delegation_class.py` (an `AuditEventCreate(event_class="delegation", ...)` validates; an unknown class still raises)
- [X] T002 Confirm/annotate flag posture in `backend/shared/feature_flags.py`: `recursive_delegation` (≈:107, default off) gates the interactive chaining seam; `scheduler_execution` (≈:47, default off) gates the machine root pending T057. Document both roles in `.env.example`; no new flag added. Assert defaults in `backend/tests/test_feature_flags_056.py`
- [X] T003 [P] Document the two-flag posture and the T057 inheritance in `specs/056-delegated-agent-chaining/contracts/audit-and-machine-turn.md` cross-check (no code) — confirm the plan's flag table matches `feature_flags.py`

**Checkpoint**: audit accepts the `delegation` class; flag roles fixed; no runtime behavior changed yet.

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: the shared gate authorizer and the machine-authority module that later stories build on. These MUST land before the user stories that consume them.

- [X] T004 Extract the single-path gate stack from `Orchestrator.execute_single_tool` (`backend/orchestrator/orchestrator.py` ≈5779-6062) into a new `_authorize_and_prepare(websocket, agent_id, tool_name, args, chat_id, user_id, *, parent_token=None)` on the orchestrator returning `(prepared_args, cap_job_id, delegation_token)` on allow or a refusal `MCPResponse` on deny; `execute_single_tool` calls it (behavior byte-identical); unit test in `backend/tests/test_authorize_and_prepare.py` (each gate's allow/deny surfaces identically to today's single path)
- [X] T005 Create `backend/orchestrator/chain_authority.py` (NEW) with `ChainBudget` (per-turn cumulative depth ≤ `DEFAULT_MAX_DELEGATION_DEPTH`, total hop count, wall-clock ceiling; `charge()`/`exhausted()`) and `MachineTurnAuthority.derive(...)` (offline-grant validate → mint → intersect-scopes → root token or `AuthoritySkip`), reusing `offline_grant.py` + `scheduler/runner._intersect_scopes` (≈:29-31); unit tests in `backend/tests/test_chain_authority.py` (budget exhaustion, skip on revoked/expired/empty-∩, principal shape)
- [X] T006 [P] Add the machine-principal resolution to `backend/audit/hooks.py`: `actor_principal_from_claims` (≈:29-43) and the recording helpers resolve a `machine:<class>` principal + owning human from a per-turn machine-context marker BEFORE the `legacy` fallback (so machine-turn records are recorded, not dropped at ≈:59/105/150/250/273/317); unit test in `backend/tests/test_machine_principal.py` (machine turn produces `machine:<class>` + human attribution; interactive turn unchanged)

**Checkpoint**: shared authorizer + machine-authority + machine principal in place; no user-facing behavior changed until wired.

---

## Phase 3: User Story 3 — Every dispatch path enforces the same rules (P2) 🎯 hardening prerequisite

**Goal**: single, parallel, and chained paths apply the identical gate stack; no cheaper path exists. Lands with/before US1 flag-on.

**Independent test**: quickstart.md §US3 — same violating call down all three paths → identical refusals + equivalent audit.

- [X] T007 [US3] Route `execute_parallel_tools` (`backend/orchestrator/orchestrator.py` ≈6220-6304) through `_authorize_and_prepare` (T004), replacing its partial inline prepare loop so the parallel path gains the policy, taint, supervisor, HITL, RFC 8693 delegation-token mint, concurrency-cap, and PRE_TOOL_USE gates it currently skips (verified gap: parallel path applies only creds/security/permission/no-agent today)
- [X] T008 [US3] Meta-tool dispatch parity: the parallel path gains the `__scheduler__`/`__memory__`/`__desktop_codegen__` branches (`orchestrator.py` ≈5758-5777) it lacks today (≈6261 handles only `__orchestrator__`), keeping the exemption limited to reserved pseudo-agent ids (FR-018)
- [X] T009 [US3] Concurrency accounting for hops (FR-019): charge BOTH `(user_id, executing_agent)` and `(user_id, initiating_agent)` slots on a long-running hop in `_authorize_and_prepare`/the cap acquire site (`orchestrator.py` ≈6026-6062, `concurrency_cap.py:29`); reject-not-queue preserved; unit test in `backend/tests/test_hop_concurrency_accounting.py` (fan-out cannot exceed the per-agent cap on either side)
- [X] T010 [US3] Shared gate-contract parity test `backend/tests/test_dispatch_parity.py`: for each gate (security flag, permission, policy, taint, supervisor, HITL, delegation-required, concurrency cap) drive the SAME violating call down the single path, the parallel batch, and a chained hop; assert identical refusal outcomes + equivalent audit evidence (FR-017, SC-006)
- [X] T011 [US3] Confirm the two pre-existing supervisor-gate failures (`backend/tests/test_security_gates_wiring.py::test_supervisor_off_is_noop` / `::test_supervisor_allows_when_intent_present`) pass after the parity refactor; if they trace to a genuine supervisor-gate bug touched by T007, fix it minimally and note the bound in the PR (spec Assumption)
- [X] T012 [US3] Live verification per quickstart.md §US3 (production posture: parallel batch now mints a delegation token per call / refuses fail-closed when unavailable, matching the single path) — record evidence under `specs/056-delegated-agent-chaining/evidence/us3/`

**Checkpoint**: US3 shippable — SC-006 measurable; the weakest-path amplification risk closed before chaining turns on.

---

## Phase 4: User Story 1 — Agents chain on my behalf, safely (P1) 🎯 MVP

**Goal**: an agent requests a peer tool mid-task; the hop acts under a strictly-narrower child authority, passes the full gate stack, and is fully reconstructable from audit — all behind `FF_RECURSIVE_DELEGATION`, byte-identical when off.

**Independent test**: quickstart.md §US1 — two-agent chained request; child narrower than parent; full gate stack ran; paired audit with correlation; two-hop reconstruction; flag-off equivalence.

- [X] T013 [US1] Add `AgentRuntime.call_agent_tool(callee_agent_id, tool_name, arguments, *, timeout=30.0)` to `backend/shared/agent_runtime.py` (today only `start_long_running_job` ≈:45): builds an `agent_hop_request` frame, routes it back via the loopback (`shared/local_transport.py:38-45`), awaits a correlated response future, returns the peer `MCPResponse` or an honest error — never talks to a peer, never holds a token; unit test in `backend/tests/test_agent_runtime_call_agent_tool.py` (frame shape, future correlation, error-return-not-raise)
- [X] T014 [US1] Route the `agent_hop_request` frame in `Orchestrator.handle_agent_message` (`backend/orchestrator/orchestrator.py` ≈1067-1116) to a new hop-mediation handler that resolves `(callee_agent_id, tool_name, arguments, parent_token)` and calls `execute_single_tool` so the hop re-enters the FULL single-path gate stack with the meta-tool bypass structurally unavailable to real-agent ids (FR-001, FR-003, FR-029), threading the initiator's parent authority; delivers the result back to the initiator's awaiting future (mirrors `pending_requests` ≈1075-1078); integration test in `backend/tests/test_chain_hop.py` (in-process built-in initiates a mediated hop to a peer built-in; a hop can never reach a `__orchestrator__`/`__scheduler__` handler; a disabled/opt-out callee and a hard security-flag block both refuse)
- [X] T015 [US1] Child-authority mint at the dispatch token-inject site (`orchestrator.py` ≈5977-6007) and/or `_get_delegation_token` (≈:6798) satisfying the 048 invariants (FR-001, FR-002, FR-008 — credentials injected per-(user, callee), never carried on the token): when a parent token is present, mint the child with `delegation.mint_child_delegation(parent, callee_agent_id, requested_scopes)` (`delegation.py:515`) instead of the flat exchange, catch `DelegationDepthExceeded` (`delegation.py:435`) as a per-call depth refusal, inject the compact-encoded child as `args["_delegation_token"]`; add a compact encode/sign helper beside `_create_mock_delegation_token` (`delegation.py:312-329`) if needed; unit tests in `backend/tests/test_chain_hop.py` (child scopes ⊆ parent, exp ≤ parent, depth+1, actor chain to human; initiator credentials never appear in the callee's args)
- [X] T016 [US1] Empty-intersection refusal (FR-005, D3): when `attenuate_scopes(parent, requested)` is empty AND requested was non-empty, refuse the hop before dispatch with an audited `delegation.hop.mint outcome=failure detail=empty_intersection` recording requested-vs-granted scopes, and return an honest per-call error; unit test in `backend/tests/test_chain_hop.py::test_empty_intersection_refused`
- [X] T017 [US1] Per-hop verification at the mediation point (FR-004): call `delegation.authorize_chained_tool_call(child, tool_name, required_scope)` (`delegation.py:621`) before execution; a `(False, reason)` verdict refuses per-call, keeps the session open, and audits `delegation.hop.enforce outcome=failure detail=<reason>` (depth/tamper/scope/expiry); unit tests in `backend/tests/test_chain_hop.py` (out-of-scope, tampered chain, over-depth each refused without teardown — US1-AS3)
- [X] T018 [US1] Emit paired hop provenance records to the hash-chained audit via `delegation.delegation_chain_audit_record` (`delegation.py:642`) through the normal `Recorder`, under the new `delegation` class, sharing the turn's `correlation_id`, carrying actor/scope/depth metadata and NO token bytes (FR-028); integration test in `backend/tests/test_chain_audit.py` (mint+enforce pair present; secrets absent)
- [X] T019 [US1] Two-hop chain reconstruction regression `backend/tests/test_chain_audit_reconstruction.py` (FR-026, closes 048 T018 / SC-003): drive a two-hop chained turn, reconstruct human→A→B→tool from `audit_events` alone, and prove `verify_chain` (`audit/repository.py:365`) detects a tampered record
- [X] T020 [US1] Flag-off byte-equivalence for US1: with `FF_RECURSIVE_DELEGATION=0` the hop path is inert (agents get today's single-hop behavior); `backend/tests/test_recursive_delegation.py` (14), `test_delegation.py` (11), `test_tool_permissions.py` (26) pass unchanged; assert in `backend/tests/test_chain_flag_off_equivalence.py` (SC-009, FR-009)
- [X] T021 [US1] Live verification per quickstart.md §US1 on a real container turn (web): `web_research → summarizer` chain executes; disabled-callee and over-depth and empty-∩ refusals are honest + audited + non-terminating; credentials never cross agents — evidence under `evidence/us1/`

**Checkpoint**: US1 shippable — SC-001/SC-002/SC-003/SC-010(partial) measurable; flag-off byte-identical.

---

## Phase 5: User Story 2 — Background work acts with my real, revocable consent (P1)

**Goal**: machine turns derive per-run authority from durable consent, act in production (dark behind `FF_SCHEDULER_EXECUTION`), and are attributed to a defined machine principal — at one shared seam all machine-turn classes inherit.

**Independent test**: quickstart.md §US2 — capture consent; run under production posture; revoke → paused with one notification; all three classes share the seam.

- [X] T022 [US2] Wire consent capture (FR-011, D8): in the scheduling consent path (`backend/orchestrator/scheduling_chat.py` ≈:295 where `offline_grant_id` is hardcoded `None`, and the `schedule_decision` handler) add an explicit step recording granted scopes + durable nature + revocation path, call the currently-uncalled `OfflineGrantStore.capture(user_id, refresh_token, agent_id)` (`offline_grant.py:64`) with the session refresh token (`session_store.py:207`), and link `grant_id` via `scheduler/store.py:set_grant` (≈:71-74); integration test in `backend/tests/test_consent_capture.py` (grant created + linked; nothing captured without the explicit step)
- [X] T023 [US2] Thread the derived root into `Orchestrator.run_scheduled_turn` (`backend/orchestrator/orchestrator.py` ≈2923, which drops the minted token at ≈2946-2949/2980) via the one shared mechanism all machine-turn classes inherit (FR-012): accept the `MachineTurnAuthority` root (T005) and pass its token into `handle_chat_message` so real-agent dispatch runs delegated in production; `scheduler/runner.py:run_job` (≈:88) obtains the root via `MachineTurnAuthority.derive` (narrowed to consented ∩ current, re-checking revocation at derivation not only expiry — FR-006) before calling `run_scheduled_turn`; integration test in `backend/tests/test_machine_turn_authority.py` (production posture: real-agent tool dispatches under (consented ∩ current) scopes)
- [X] T024 [US2] Authority-skip + collapsed notification (FR-013): a machine turn without derivable authority (missing/revoked/expired/empty-∩) dispatches 0 real-agent tools, records `skipped_auth` (`scheduler/runner.py:105-124`), and notifies via `notify_user` (`orchestrator.py:3010`) — repeated skips for one paused job collapse into ONE actionable notification (spec Edge Case "Notification fatigue"); test in `backend/tests/test_machine_turn_authority.py::test_revocation_pauses_with_one_notification`
- [X] T025 [P] [US2] Extend the same seam to parser replay: `attachment_autoparse.auto_continue_after_go_live` (`backend/orchestrator/attachment_autoparse.py` ≈:87-146) derives machine authority via `MachineTurnAuthority` before its `handle_chat_message` replay; test in `backend/tests/test_machine_turn_classes.py::test_parser_replay_authority`
- [X] T026 [P] [US2] Extend the same seam to draft self-tests: `agentic_creation._self_test_draft` (`backend/orchestrator/agentic_creation.py` ≈:323-350) derives machine authority before its `handle_chat_message`; test in `backend/tests/test_machine_turn_classes.py::test_self_test_authority`
- [X] T027 [US2] Machine-principal attribution in audit (FR-014, SC-005): set the per-turn machine-context marker (turn_class + owning human + consent_ref) so the T006 principal resolution attributes machine-turn tool-call records to `machine:<class>` + human, never "legacy"/"unknown", while cost stays on the SYSTEM LLM credential (054, `_llm_audit_principals` ≈4624-4640); test in `backend/tests/test_machine_principal.py` (all three classes attributed; cost vs authority distinct — US2-AS5)
- [X] T028 [US2] Machine-root chains use the same child-mint rules (FR-015): a hop initiated inside a machine turn mints children off the consent-derived root exactly as an interactive hop (T015); test in `backend/tests/test_machine_turn_authority.py::test_machine_turn_chains_attenuate`
- [X] T029 [US2] Ship-dark verification (FR-016): with `FF_SCHEDULER_EXECUTION=0` all US2 machinery is present but inert (no run executes); the review gate is inherited, not bypassed; assert in `backend/tests/test_scheduler_execution_gate.py`
- [X] T030 [US2] Live verification per quickstart.md §US2 under production posture with `FF_SCHEDULER_EXECUTION=1` in a staging boot: scheduled run dispatches real-agent tools under consent; logout → next run pauses with one notification — evidence under `evidence/us2/`

**Checkpoint**: US2 shippable dark — SC-004/SC-005 measurable once the review flag is enabled.

---

## Phase 6: User Story 4 — Plans decompose without losing control (P2)

**Goal**: bounded, isolated sub-tasks with fresh context, child authority, and per-subtree budget; global chain budget; MAS scan on inter-agent payloads; the peer path retired.

**Independent test**: quickstart.md §US4 — ≥3 sub-tasks isolated + budgeted; orphan cancel; payload scan; peer path gone.

- [X] T031 [US4] Sub-task spawn (FR-020): a planner decomposition spawns bounded isolated sub-tasks on the existing `BackgroundTask`/`VirtualWebSocket` substrate (`backend/orchestrator/async_tasks.py:29-105`), each with a child authority derived from the turn root (T015) and a per-subtree slice of the `ChainBudget` (T005); results return as bounded provenance-tagged digests (never raw transcripts); integration test in `backend/tests/test_subtask_decomposition.py`
- [X] T032 [US4] Global chain budget enforcement (FR-021): the `ChainBudget` (T005) bounds cumulative depth + total hop count + wall clock across the whole nested tree (including machine turns), composing with the existing `MAX_TURNS=10` ReAct bound (`orchestrator.py:3796`); exhaustion yields honest partial results + an audited `budget_stop`; test in `backend/tests/test_chain_budget.py` (no runaway recursion; partial results on exhaustion)
- [X] T033 [US4] Orphan cancellation (FR-023): parent-ended / socket-gone / budget-exhausted sub-tasks are cancelled via `BackgroundTaskManager.cancel` (`async_tasks.py:191-198`) and audited; their partial `outputs` are discarded, never attached to a later turn; test in `backend/tests/test_subtask_orphan.py`
- [X] T034 [US4] MAS payload scan enforcement (FR-007, D11): every hop result and sub-task digest is scanned by `mas_defense.scan_message` (`backend/orchestrator/mas_defense.py:101-110`) before entering another context; a finding quarantines the payload (not delivered), records an audited reason, returns an honest error — promoting the scan from log-only (`orchestrator.py:3990-3996`) to enforcing on inter-agent hops; test in `backend/tests/test_hop_payload_scan.py`
- [X] T035 [US4] Hierarchical progress attribution (FR-022): hop/sub-task progress rides the EXISTING progress frames (`ToolProgress`/`chat_status`) with per-hop attribution (acting agent, sub-task, authorizing chain) — no new frame type; assert no `ui_protocol.json` change and drift guards green; test in `backend/tests/test_hop_progress_attribution.py`
- [X] T036 [US4] Retire the dormant peer-call path (FR-010, D12): remove (or hard-refuse with audit) `BaseA2AAgent.call_peer_tool` (`backend/shared/base_agent.py:682-719`), `_call_peer_via_ws`/`_call_peer_via_a2a` (≈:726-841), and the `connect_to_peer`/`_peer_listen_loop`/peer-registry surface (≈:653-679); regression test in `backend/tests/test_peer_path_retired.py` proving an agent cannot bypass mediation (SC-010: 100% failure, audited)
- [X] T037 [US4] Live verification per quickstart.md §US4 (decomposed request → ≥3 isolated budgeted sub-tasks; MAS quarantine; peer path gone; hierarchical progress on web AND one native client unchanged) — evidence under `evidence/us4/`

**Checkpoint**: US4 shippable — SC-007/SC-010 measurable; confused-deputy cleanup complete.

---

## Phase 7: User Story 5 — Chaining is measured, not assumed safe (P3, eval-only)

**Goal**: the 047 benchmark gains chained-attack scenarios through the real dispatch path; ASR(on) ≤ ASR(off), each block attributed to a named layer.

**Independent test**: quickstart.md §US5 — off-vs-on comparison report; every chained attack blocked by a named layer.

- [ ] T038 [US5] Add chained-attack scenarios to `backend/security_benchmark/adapters/` (eval-only): confused deputy, cross-hop scope escalation, depth-bound violation, actor-chain forgery, chained-consent replay — each mapped to its expected defense layer in `backend/security_benchmark/envelope.py` (`LAYER_FOR_OBJECTIVE`), reusing the 4-outcome adjudicator (`adjudicator.py`); tests in `backend/security_benchmark/tests/test_chained_scenarios.py`
- [ ] T039 [US5] Execute chained scenarios through the REAL dispatch path via `backend/security_benchmark/drivers/inprocess.py` (the 047 T021 seam), toggling `FF_RECURSIVE_DELEGATION`; verify each block is genuine gate enforcement (attempt-vs-effect, distinguishing "blocked" from "not attempted", FR-024)
- [ ] T040 [US5] Off-vs-on comparison report (FR-025, SC-008) in `backend/security_benchmark/report.py`: per-scenario outcomes + overall ASR with the acceptance bar `ASR(on) ≤ ASR(off)`; each blocked attack attributed to a named layer; reproducible via `python -m security_benchmark --benchmarks chained`; test asserts no ASR regression on the pinned config
- [ ] T041 [US5] Confirm the isolation guard stays green (`backend/security_benchmark/isolation_check.py`) — no product-runtime module imports the harness or a benchmark corpus (Constitution V/XI); `pytest security_benchmark/tests/test_isolation_check.py`
- [ ] T042 [US5] Produce the comparison artifact on demand and record it under `evidence/us5/` with the (model, benchmark-version, harness-version, seed) tuple (FR-025); confirm audit trail alone reconstructs each blocked attack (US5-AS2)

**Checkpoint**: US5 shippable — SC-008 measurable; the thesis enforcement evidence produced.

---

## Phase 8: Polish & cross-cutting

- [ ] T043 Flags-off byte-equivalence CI job: a variant in `.github/workflows/ci.yml` running the backend suite + the 048/delegation/permission suites with `FF_RECURSIVE_DELEGATION=0` and `FF_SCHEDULER_EXECUTION=0` — zero diffs (SC-009)
- [ ] T044 [P] Observability sweep (Constitution X): structured logs with agent/chat/correlation context for every child mint, hop refusal (with reason code), empty-∩ refusal, MAS quarantine, budget stop, orphan cancel, machine-turn derive/skip, and consent capture; verify no secret token material in any log (FR-028) — spot-check across `orchestrator.py`, `chain_authority.py`, `mas_defense` call sites
- [ ] T045 [P] Documentation (Constitution VI): docstrings for `call_agent_tool`, `_authorize_and_prepare`, `MachineTurnAuthority`, `ChainBudget`, and the hop audit helper; keep `contracts/` in sync with any implementation drift; note the retired peer path in the base_agent module docstring
- [ ] T046 Migration/rollback check (FR-027, Constitution IX): confirm NO new third-party runtime dependency and NO schema migration ships by default (audit trail rides `audit_events`; consent linkage reuses existing columns; `delegation` is a constant). IF the optional `audit_events.chain_root_correlation_id` column proves needed, ship it as the guarded idempotent `_init_db` delta in `backend/shared/database.py` with the `SCHEMA_REVISION` bump (054.001→056.001) and rollback per data-model.md, with representative-dataset evidence that `verify_chain` stays intact
- [ ] T047 Full gate run: container pytest (both invocations), host `ruff check .`, changed-code coverage ≥90% (diff-cover vs origin/main), production-posture boot smoke exits 78, benchmark isolation guard green; attach evidence to the PR

---

## Dependencies & execution order

- **Phase 1 → Phase 2 → user stories**. T001 (audit class) blocks T018/T027 (hop + machine records). T004 (`_authorize_and_prepare`) blocks T007 (parallel parity) and every hop dispatch (T015). T005 (`chain_authority`) blocks US2 (T023–T029) and US4 budget (T031/T032). T006 (machine principal) blocks T027.
- **US3 (Phase 3)**: pure hardening; independent of the flag. T004→T007→T008/T009/T010; T011/T012 after T007. Lands with/before US1 flag-on.
- **US1 (Phase 4)**: the MVP. T013→T014→T015→{T016,T017}→T018→T019; T020/T021 last. Depends on T004 (authorizer) and T001 (audit class).
- **US2 (Phase 5)**: depends on T005 + T006. T022 (consent) independent; T023→T024; T025/T026 parallel after T005; T027 after T006; T028 after T015; T029/T030 last. Ships dark behind `FF_SCHEDULER_EXECUTION`.
- **US4 (Phase 6)**: depends on US1 authority (T015) + T005 budget. T031→{T032,T033,T034,T035}; T036 (peer retirement) independent of the rest; T037 last.
- **US5 (Phase 7)**: depends on US1–US4 landed. T038→T039→T040; T041/T042 after.
- **Phase 8**: after the shipped stories (T043 runnable once any story lands; T047 gates the PR).

## Parallel opportunities

- Phase 1: T003 alongside T001/T002.
- Phase 2: T006 parallel with T004/T005 (different files).
- US2: T025 + T026 (parser replay + self-test, disjoint files).
- Polish: T044 + T045 concurrently.
- Cross-story: US3 and US1 backend work both touch `orchestrator.py` dispatch region — coordinate merges (US3 lands the authorizer refactor first, US1 consumes it). US2/US4/US5 phases proceed as separate PRs in priority order.

## Implementation strategy

MVP = Phase 1 + Phase 2 + Phase 3 (US3 hardening) + Phase 4 (US1) — ships attenuated agent-to-agent chaining with full gate parity and audit reconstruction behind `FF_RECURSIVE_DELEGATION`, byte-identical when off. Then US2 (machine-turn authority, dark), US4 (decomposition + peer retirement), US5 (measurement) in priority order, each independently PR-able. Every phase ends at its checkpoint with the 048/delegation/permission suites green and its quickstart section executed live.
