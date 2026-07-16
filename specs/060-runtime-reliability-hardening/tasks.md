# Tasks: Runtime Reliability and Release Readiness

**Input**: Design documents from `/specs/060-runtime-reliability-hardening/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`

**Tests**: Required by the specification. Within every phase, add the listed tests first and confirm
that they fail for the intended missing behavior before implementing the corresponding production
change.

**Organization**: Shared blockers precede nine independently testable user-story phases. Requirement
and outcome identifiers across the task set provide direct traceability to FR-001–FR-059 and
SC-001–SC-022.

## Phase 1: Setup and Contract Guardrails

**Purpose**: Establish feature-owned fixtures, validators, and release directories without adding a
new runtime dependency.

- [X] T001 Create the feature-060 fixture layout with neutral `process-supervision-vectors.json`, a runtime-lock contract digest fixture, sanitized synthetic `staging/representative-057.sql`, non-secret PKCE-only `staging/keycloak-realm.json`, and fingerprint/provenance/representativeness `staging/fixture-manifest.json`, then register any new pytest markers in `backend/tests/fixtures/runtime_reliability_060/` and `backend/pytest.ini` (FR-018, FR-049, FR-058; SC-012, SC-020, SC-021)
- [X] T002 [P] Add Draft 2020-12 syntax/behavior for deployment-profile, release-evidence, and release-trust schemas; strict-SemVer edge-corpus including every whitespace/line-terminator case; every-used-keyword; production-nonlocal plus no-userinfo/query/fragment deployment URI cases; canonical bundle/GitHub-run-member/GitHub-release-asset/OCI URI grammar; required background+scheduler paths; credential-free reachable/digest-qualified staging; quantitative-measurement/provenance; platform-to-artifact/runner binding; and representative valid/invalid schema plus sanitized deterministic fixture tests in `backend/tests/test_release_contract_schemas.py` and `backend/tests/test_staging_fixtures_060.py` (FR-033, FR-038, FR-048–FR-051; SC-012)
- [X] T003 [P] Add protocol-manifest drift expectations for `conversation_snapshot`, `operation_status`, `agent_lifecycle`, structured host registration, and `agent_host_registered` in `backend/tests/test_ui_protocol_manifest.py`, `windows-client/tests/test_protocol_manifest.py`, `android-client/core/src/test/kotlin/com/personalailabs/astraldeep/core/protocol/ProtocolManifestTest.kt`, and `apple-clients/AstralCore/Tests/AstralCoreTests/ManifestDriftTests.swift` (FR-029, FR-032, FR-043, FR-050)
- [X] T004 [P] Add protected-ledger fixture histories with create-only `debts/` and `resolutions/`, immutable pre-review request artifacts, approval/registration receipts, historical-debt then later-pass resolution then distinct-new-debt cases, legal temporary shipping-client-unavailability examples, and illegal failed-product/backend/docs/staging/trust/policy/Apple-first-login exception cases in `backend/tests/fixtures/runtime_reliability_060/release_evidence/` (FR-051; SC-012)
- [X] T005 Add the 060 focused-suite/non-empty-selection surface; lock-pinned CI-only ESLint/Playwright/V8-to-Istanbul/direct-parser manifest plus digest-pinned matching Playwright image and product-isolation guards; tested fail-closed event-aware cross-language collector with PR/main/manual base selection, candidate-attribute-resistant text hunks, maintained-path empty-hunk refusal, raw/unfiltered-V8 refusal, real pinned-image comment-padding regression, native counter/line-completeness validation, unexpected-empty, tooling-Python, union/dedupe, and report-mapping rules; tracked Apple swift-format configuration; real shared iOS/macOS UI-test and Watch unit-test targets plus both app/Watch scheme TestActions before their sources; and CI contract tests in `Makefile`, `tooling/web-ci/package.json`, `tooling/web-ci/package-lock.json`, `tooling/web-ci/playwright-image.txt`, `tooling/web-ci/eslint.config.mjs`, `tooling/web-ci/coverage-conversion.mjs`, `scripts/check_changed_coverage.py`, `backend/tests/test_changed_coverage_060.py`, `backend/tests/test_release_tooling_coverage_060.py`, `backend/tests/test_quickstart_commands.py`, `backend/tests/test_ci_javascript_lint.py`, `apple-clients/.swift-format`, `apple-clients/AstralApp/AstralApp.xcodeproj/project.pbxproj`, `apple-clients/AstralApp/AstralApp.xcodeproj/xcshareddata/xcschemes/AstralApp.xcscheme`, `apple-clients/AstralApp/AstralApp.xcodeproj/xcshareddata/xcschemes/AstralWatch.xcscheme`, and `.github/workflows/ci.yml` (FR-047, FR-049, FR-052, FR-053, FR-057; SC-012, SC-014, SC-015)

---

## Phase 2: Foundational Coordination, Schema, and Protocol

**Purpose**: Build the durable identities, execution fence, shared protocol vocabulary, immutable
registry, and bounded child supervisor that block every story.

**⚠️ CRITICAL**: No user-story implementation starts until this phase passes.

### Tests

- [X] T006 [P] Consume `backend/tests/fixtures/runtime_reliability_060/staging/representative-057.sql` in the 057.001→060.004 migration, conversation-commit legacy revision-zero/backfill, validated host platform/client/supported-contract fields, nullable pre-launch process/bind-once behavior, repeat-run, rollback, retention-FK, strict operation/slot lifecycle constraints, two-starter exact `(1095980114,60001)` schema and `(1095980114,60002)` policy advisory identities, explicit Analyze-policy ownership plus fail-closed canonical `constitution=0.1.0;analyze=1`, and policy-only revision tests in `backend/tests/test_migrations_060.py` and `backend/tests/test_schema_revision_guard.py` (FR-002, FR-022, FR-028, FR-059; SC-017)
- [X] T007 [P] Add operation-record/admission-slot/submission-reconciliation state-machine, owner-scoped non-disclosing query, 24h queryability/25h purge, and stale execution-fence tests in `backend/tests/test_work_admission.py` (FR-001–FR-005)
- [X] T008 [P] Consume the neutral supervisor-vector corpus while adding bounded stdout/stderr, oversized-line, ring-buffer, one-pipe-EOF, process-tree termination, and server-child call-site integration tests in `backend/tests/fixtures/runtime_reliability_060/process-supervision-vectors.json`, `backend/tests/test_process_supervision.py`, and `backend/tests/test_process_supervision_integration_060.py` (FR-058; SC-020)
- [X] T009 [P] Add immutable snapshot and concurrent register/remove/list registry tests in `backend/tests/test_runtime_registry.py` (FR-025; SC-018)
- [X] T010 [P] Add Python frame model/serialization tests for all canonical fields including `snapshot_purpose`, hydration-only equal-revision behavior, one committed-snapshot revision rule, transient overlay sequence, structured v2 host registration/server acknowledgement, and nullable-prelaunch/bind-once process fences in `backend/tests/test_runtime_reliability_protocol.py` (FR-029, FR-032, FR-043)

### Implementation

- [X] T011 Implement the additive 060.004 schema, strict operation/slot lifecycle integrity, conversation-commit/chat-message-component revision fields and legacy backfill, host-session validated `platform`, strict `client_version`, advertised/selected runtime-contract versions and lock digest, nullable pre-launch `process_id` with host-only bind-once CAS, exact fixed `(1095980114,60001)` schema and `(1095980114,60002)` policy advisory transaction identities (never process-language hashes), post-lock rechecks, independent fail-closed `constitution=<semver>;analyze=<positive-integer>` user-agent policy marker owned by `agent_constitution.py`/`agent_analyze.py`, and `ON DELETE SET NULL` retention behavior in `backend/shared/database.py` (FR-002, FR-006, FR-009, FR-019, FR-022, FR-023, FR-028, FR-059; SC-017)
- [X] T012 Implement durable operation/submission records, owner-scoped safe lookup, admission classes/slots, finite FIFO queues, BIGINT execution generations, UUID execution leases, terminal retention/purge, and commit-fence APIs in `backend/orchestrator/work_admission.py` (FR-001–FR-005, FR-008, FR-024)
- [X] T013 Bind `backend/orchestrator/async_tasks.py`, `backend/orchestrator/task_state.py`, and the production orchestrator to one shared PostgreSQL operation coordinator with read-only effective-config loading; preserve legacy dataclass compatibility while reusing exact operation/fence identities off-loop, enforcing exact-operation handoff and retryable replay, and running bounded maintenance-admitted, fenced, cache-independent terminal retention with full UUID identities (FR-001, FR-002, FR-043)
- [X] T014 Implement documented continuous bounded pipe readers, process-group/job-tree termination, and five-second cleanup in `backend/shared/process_supervision.py` and migrate server-owned child launches in `backend/orchestrator/agent_lifecycle.py` and `backend/start.py` (FR-058; SC-020)
- [X] T015 Implement copy-on-write immutable runtime snapshots and atomic writer publication in `backend/orchestrator/runtime_registry.py` (FR-025; SC-018)
- [X] T016 Add canonical snapshot/status/lifecycle/fence dataclasses including `snapshot_purpose` plus structured v2 `register_ui.agent_host`, `agent_host_registered`, and immutable candidate-capability map models with documented public APIs and validation helpers in `backend/shared/protocol.py` (FR-029, FR-032, FR-043)
- [X] T017 Register the new server→client frames/scoped fields and candidate capability-map shape in `backend/shared/ui_protocol.json` (FR-029, FR-032, FR-043)
- [X] T018 [P] Add matching Windows protocol models, structured v2 host registration/ack handling, and dispositions in `windows-client/astral_client/protocol.py` and `windows-client/astral_client/protocol_manifest.py` (FR-029, FR-032, FR-043, FR-050)
- [X] T019 [P] Add matching documented Android wire models, inbound variants, author-only host-ack disposition, and manifest entries in `android-client/core/src/main/kotlin/com/personalailabs/astraldeep/core/protocol/Messages.kt`, `android-client/core/src/main/kotlin/com/personalailabs/astraldeep/core/protocol/Wire.kt`, and `android-client/core/src/main/kotlin/com/personalailabs/astraldeep/core/protocol/ProtocolManifest.kt` (FR-029, FR-032, FR-043, FR-050)
- [X] T020 [P] Add matching Apple frame models and explicit author-only structured-host-registration/ack dispositions in `apple-clients/AstralCore/Sources/AstralCore/Protocol/Frames.swift` and `apple-clients/AstralCore/Sources/AstralCore/Protocol/Dispositions.swift` (FR-029, FR-032, FR-043, FR-050)

**Checkpoint**: The 060 schema is repeat-safe; accepted operations and side effects are durably
fenced; all clients recognize the shared vocabulary.

---

## Phase 3: User Story 1 — Work Completes Once Under Load (Priority: P1) 🎯 MVP

**Goal**: Enforce finite capacity, five-second connection cleanup, per-connection mutation ordering,
and one visible effect per durable scheduled occurrence.

**Independent Test**: Run the 1,000-frame connection test and 10,000-interleaving two-instance
scheduler test; active work never exceeds limits, every accepted attempt has one terminal state,
no connection work remains after five seconds, and each occurrence has at most one effect.

### Tests

- [X] T021 [P] [US1] Add 1,000-frame saturation, bounded preregistration flood, five-second registration timeout/disconnect drain, FIFO mutation order plus non-overlapping live read/mutation barrier, duplicate retry, and terminal-count tests in `backend/tests/perf/test_runtime_reliability_060.py` (FR-001–FR-005, including FR-004 disconnect ownership; SC-001)
- [X] T022 [P] [US1] Add background ceiling=5, finite queue/wait, cancellation, full-UUID, and 24h+1h purge tests in `backend/tests/test_async_tasks.py` (FR-001, FR-002, FR-008; SC-001)
- [X] T023 [P] [US1] Add real-PostgreSQL repeated-poll, lease-expiry, two-instance, crash-boundary, attempt-operation, saturated scheduled-pool delay beyond two 15-second leases, queued renewal/lost-renewal refusal, 10,000-effect-deduplication, owner-scoped idempotent Run-now without cadence mutation, and pause/delete-versus-claim/start cancellation tests in `backend/scheduler/tests/test_occurrence_claims_060.py`, `backend/scheduler/tests/test_schedule_actions_060.py`, `backend/scheduler/tests/test_schedule_api_060.py`, and `backend/tests/chrome/test_surface_personalization.py` (FR-006, FR-007; SC-002)
- [X] T024 [P] [US1] Add ineligible legacy-handler refusal and non-sensitive capacity/queue/oldest-age/duplicate/cancellation/claim-recovery/terminal-outcome observability tests in `backend/scheduler/tests/test_handler_eligibility_060.py` and `backend/tests/test_operation_observability.py` (FR-007, FR-008)

### Implementation

- [X] T025 [US1] Replace substring registration detection and untracked per-frame tasks with parsed control frames, bounded preregistration FIFO, five-second deadline, tracked connection scopes, and FIFO mutation lanes in `backend/orchestrator/orchestrator.py` (FR-003–FR-005; SC-001)
- [X] T026 [US1] Enforce background active/queue limits and operation-backed cancellation/retention in `backend/orchestrator/async_tasks.py` (FR-001, FR-002; SC-001)
- [X] T027 [US1] Bump the guarded schema revision after adding the nullable owner-scoped Run-now submission boundary, then materialize and claim canonical scheduled occurrences with `FOR UPDATE SKIP LOCKED`, attempt-scoped operations, atomic recurring `next_run_at` advancement, idempotent Run-now that leaves cadence unchanged, linearizable pause/delete cancellation of every not-yet-running occurrence/attempt, and renewal of each committed claim from enqueue through start/run at least once per lease/3 in `backend/shared/database.py` and `backend/scheduler/store.py` (FR-006, FR-007; SC-002)
- [X] T028 [US1] Dispatch only current fenced active-job claims, keep both the occurrence claim and accepted-operation execution lease renewed across queue/start/run, refuse dequeue/start/effect immediately after either renewal/CAS loss, preserve occurrence identity across retries, and route authenticated REST plus Chrome Run-now/pause/delete through the same idempotent/fenced store seams with fail-closed flag/eligibility checks in `backend/scheduler/loop.py`, `backend/scheduler/runner.py`, `backend/scheduler/api.py`, and `backend/webrender/chrome/surfaces/personalization.py` (FR-006, FR-007; SC-002)
- [X] T029 [US1] Add the fenced `effect_ledger` reservation/publication/reconciliation boundary and refuse non-idempotent unattended handlers in `backend/scheduler/runner.py` (FR-007; SC-002)
- [X] T030 [US1] Expose documented/OpenAPI-described authenticated user/schedule-owner-scoped `GET /api/operations/{operation_id}` and `GET /api/operation-submissions/{submission_id}` with identical non-disclosing handling for connection-owned/unknown/expired identities, plus authenticated `GET /api/runtime-reliability/metrics` for effective limits, queue wait, retention, counts, refusal codes, oldest age, duplicate suppression, cancellation, claim recovery, terminal outcome, and schedule effect metrics without payload labels in `backend/orchestrator/api.py` and `backend/orchestrator/orchestrator.py` (FR-001, FR-002, FR-008)
- [X] T031 [US1] Run the focused US1 real-PostgreSQL suite and record exact 1,000/10,000 trial results in `specs/060-runtime-reliability-hardening/verification/us1-runtime.md` (SC-001, SC-002)

---

## Phase 4: User Story 2 — BYO Agents Remain Honest Through Failure and Revision (Priority: P1)

**Goal**: Maintain one selected host/runtime generation, settle known failures promptly, preserve
last-known-good revisions, reconcile offline state, and bound every child process.

**Independent Test**: Inject exit, hang, host replacement, stale frames, delete/reconnect, and every
promotion failure boundary for 100 trials; no stale result is accepted and the prior working
revision remains callable unless the candidate is durably active.

### Tests

- [X] T032 [P] [US2] Add full host/delivery/revision/runtime/process/request fence, nullable pre-launch process ID, host allocation/bind-once plus stale/rebind refusal, sticky-host selection, stale-frame, and two-second exit/host-loss plus seven-second hang tests in `backend/tests/test_byo_runtime_fencing_060.py` (FR-009–FR-012, including FR-010 selected-host uniqueness; SC-003)
- [X] T033 [P] [US2] Add 100-boundary candidate promotion/last-known-good, durable delete, delayed registration, and inventory-before-autostart tests in `backend/tests/test_byo_revision_recovery_060.py` (FR-013–FR-016; SC-004, SC-005)
- [X] T034 [P] [US2] Add host/bundle contract-version and fixture lock-digest pairing, validated platform/client version, immutable false/true/malformed macOS capability-map, structured registration, and two-second acknowledgement/refusal tests in `backend/tests/test_byo_runtime_compatibility_060.py` and `windows-client/tests/test_byo_runtime_compatibility.py` (FR-017, FR-018; SC-021)
- [X] T035 [P] [US2] Consume the neutral supervisor-vector corpus in Windows-local parity plus 100 high-output, oversized-line, descendant, cancellation, quit, crash, and one-pipe-close trials through the packaged host in `backend/tests/fixtures/runtime_reliability_060/process-supervision-vectors.json` and `windows-client/tests/test_byo_supervision_060.py` (FR-058; SC-020)

### Implementation

- [X] T036 [US2] Implement immutable revision, host-session, nullable pre-launch process fence/bind-once runtime-instance, request, pointer, tombstone, and generation repositories in `backend/orchestrator/user_agents.py` (FR-009–FR-017)
- [X] T037 [US2] Replace broadcast/last-socket routing with validated platform/version structured host registration and server acknowledgement, sticky healthy incumbent selection, same-host session rollover, deterministic standby failover, complete frame fences, prompt pending-call settlement, and one shared immutable capability getter exposed identically by dashboard/system-config in `backend/orchestrator/orchestrator.py`, `backend/orchestrator/api.py`, and `backend/orchestrator/models.py` (FR-009–FR-012; SC-003)
- [X] T038 [US2] Implement two-phase candidate prepare/start/ready/transactional promote and last-known-good recovery in `backend/orchestrator/agent_lifecycle.py` (FR-013, FR-014; SC-004)
- [X] T039 [US2] Commit deletion/tombstone generations before routing cleanup and reconcile retained host inventory before any child start in `backend/orchestrator/user_agents.py` and `backend/orchestrator/orchestrator.py` (FR-015, FR-016; SC-005)
- [X] T040 [US2] Emit versioned runtime manifests, immutable revision identities, required packaged-lock metadata, and a deterministic digest over the complete three-file bundle in `backend/orchestrator/agent_generator.py`, then finalize that manifest/digest only after `backend/orchestrator/agent_lifecycle.py` has assembled `agent_main.py`, `astralprims_ui.py`, and `mcp_tools.py` (FR-017, FR-018; SC-021)
- [X] T041 [US2] Implement stable host identity persistence, server-session acknowledgement binding, acknowledgement-before-host-start coordination, inventory reconciliation, one-second heartbeat, exact v2 full-fence frames, staged immutable bundle installation, and fresh `process_id` allocation immediately before spawn with one-time binding to the current unbound server instance in `windows-client/astral_client/protocol.py`, `windows-client/astral_client/app.py`, and `windows-client/win_agent/byo_host.py` (FR-009–FR-017)
- [X] T042 [US2] Implement the frozen-safe Windows-local bounded-supervision contract in `windows-client/win_agent/process_supervision.py` and make `windows-client/win_agent/byo_host.py` the sole supervisor of each BYO worker process/tree, settling and killing the full tree within bounds without importing backend code; `windows-client/win_agent/byo_worker.py` remains the supervised child entry point and MUST NOT import or instantiate the supervisor (FR-011, FR-058; SC-003, SC-020)
- [X] T043 [US2] Consume the tracked fixture runtime-lock contract/digest through host/bundle compatibility metadata in `backend/tests/fixtures/runtime_reliability_060/`, `backend/orchestrator/agent_generator.py`, `windows-client/win_agent/byo_host.py`, and `windows-client/tests/test_byo_runtime_compatibility.py` without authoring or integrating the US4-owned final release lock/spec (FR-018)
- [X] T044 [US2] Run the US2 100-trial fault matrices and record exit/hang/promotion/cleanup distributions in `specs/060-runtime-reliability-hardening/verification/us2-byo-runtime.md` (SC-003, SC-004, SC-020)

---

## Phase 5: User Story 3 — Resume the Same Conversation After Interruption (Priority: P1)

**Goal**: Restore the intended chat, semantic transcript, and last committed canvas atomically on
web, Windows, Android, Apple, and watch-compatible paths while rejecting stale generations.

**Independent Test**: After a rendered turn, restart the service/client process and reorder frames
20 times per client; the same coherent snapshot returns within five seconds without welcome or blank
structured turns.

### Tests

- [X] T045 [P] [US3] Add conversation-commit atomicity for direct turns, component mutations, scheduled turns, persisted stream terminals, detached/REST mutations, and long-job results; structured/empty/error normalization; ownership; incomplete-snapshot rejection; exact web `_presentation` augmentation/rejection; explicit-clear-only behavior; and proof that exactly one `snapshot_purpose=commit` frame advances each commit. Cover the exact six-field `conversation_commit_ready` parser/reducer, fresh server generation, wrong/malformed/stale/busy-fence no-ops, and its one paired commit snapshot; retain the first-only hydration equal-revision/replay/conflict rules and prove transient progress cannot mutate committed state in `backend/tests/test_conversation_snapshot_060.py`, `backend/tests/test_runtime_reliability_protocol.py`, `backend/tests/test_client_conversation_continuity_060.py`, `backend/tests/test_long_running_job_progress.py`, and `backend/scheduler/tests/test_atomic_chat_publication_060.py` (FR-026–FR-031, including FR-027 locator retention; SC-006)
- [X] T046 [P] [US3] Add web locator, reload/reconnect with hydration-purpose equal-revision fresh-ID acceptance, same-ID replay, equal commit/new-turn plus same-generation conflict/lower/old-generation rejection, ROTE-adapted canvas replacement, transient-overlay reduction, explicit-clear, and welcome-suppression Playwright tests in `tooling/web-ci/tests/release-060.spec.js` and `backend/tests/test_client_conversation_continuity_060.py` (FR-026–FR-031; SC-006)
- [X] T047 [P] [US3] Add Windows locator retention across loss/restart, hydration-purpose equal-revision fresh-ID acceptance then replay/conflict/equal-commit rejection, four definitive clear actions, semantic decoder, one committed-snapshot revision, request-scoped transient-overlay reduction, and exact six-field `conversation_commit_ready` acceptance only for a fresh active-chat/current-connection/server generation without stealing an unfinished client commit in `windows-client/tests/test_conversation_continuity_060.py` (FR-026–FR-031; SC-006)
- [X] T048 [P] [US3] Add Android process recreation, hydration-purpose equal-revision fresh-ID acceptance then replay/conflict/equal-commit rejection, locator-before-register/retention, four definitive clear actions, structured recovery, committed-snapshot versus transient-overlay generation rejection, exact six-field `conversation_commit_ready` fresh/stale/malformed/busy-fence cases, and 20-trial connected tests in `android-client/app/src/test/kotlin/com/personalailabs/astraldeep/app/ConversationContinuityTest.kt` and `android-client/app/src/androidTest/kotlin/com/personalailabs/astraldeep/app/ConversationContinuityInstrumentedTest.kt` (FR-026–FR-031; SC-006)
- [X] T049 [P] [US3] Add iOS/macOS and shipping Watch app/test-target locator retention/four definitive clear actions, hydration-purpose equal-revision fresh-ID acceptance then replay/conflict/equal-commit rejection, exact six-field `conversation_commit_ready` fresh/stale/malformed/busy-fence cases, one committed-snapshot model update, transient-overlay sequencing, iOS/macOS relaunch, Watch process/reconnect, semantic parts, and generation tests in `apple-clients/AstralApp/AstralAppTests/ConversationContinuityTests.swift`, `apple-clients/AstralCore/Tests/AstralCoreTests/ConversationSnapshotTests.swift`, and `apple-clients/AstralWatchTests/ConversationContinuityTests.swift` (FR-026–FR-031; SC-006)

### Implementation

- [X] T050 [US3] Add durable `conversation_commit` staging/visibility for direct turns, component mutations, scheduled turns, persisted stream terminals, detached/REST mutations, and long-job results; revision-zero legacy handling; one repeatable-view semantic snapshot builder; and post-ROTE web-only exact `_presentation` augmentation from the canonical server renderer (never durable/client-authored) in `backend/shared/database.py`, `backend/orchestrator/conversation_publication.py`, `backend/orchestrator/history.py`, `backend/orchestrator/workspace.py`, `backend/orchestrator/orchestrator.py`, and `backend/scheduler/store.py` (FR-028, FR-030; SC-006)
- [X] T051 [US3] Validate owner-scoped resume registration and emit the current committed revision with `snapshot_purpose=hydration` for the client's explicit hydration generation. Use client-generated request UUID4s for client loads/turns; use fresh server UUID4s for scheduled/detached/persisted-stream/long-job updates and emit the exact six-field `conversation_commit_ready` immediately before each update's one matching `snapshot_purpose=commit` frame. Never let a prelude steal an unfinished client commit, never label a turn generation as hydration, make snapshots the only frames that advance/replace committed transcript/canvas, scope sequenced transient overlays, and use the scheduled job UUID4 as the stable fallback chat in `backend/orchestrator/orchestrator.py`, `backend/scheduler/store.py`, and `backend/shared/protocol.py` (FR-026, FR-029, FR-031)
- [X] T052 [P] [US3] Implement documented/JSDoc issuer+subject-digested active-chat storage, explicit clears, semantic decoding, exact all-or-nothing reserved web `_presentation` validation, purpose-aware atomic transcript+DOM snapshot replacement that accepts equal revision only for the first complete fresh-ID hydration frame in a generation explicitly opened for hydration, treats its same-ID replay as a no-op, rejects different-ID/content, commit-purpose, and normal-new-turn equals, accepts an exact six-field `conversation_commit_ready` only for a fresh active-chat/current-connection revision without stealing an unfinished client commit, and reduces request-scoped transient overlays in `backend/webrender/static/client.js` (FR-026–FR-031)
- [X] T053 [P] [US3] Implement the documented account-scoped QSettings locator, transient-loss retention, four definitive clear actions, semantic decoding, purpose-aware atomic snapshot replacement with the same first-complete fresh-ID hydration-only equal/replay/conflict rules as T052, exact six-field `conversation_commit_ready` fresh/stale/malformed/busy-fence handling, and request-scoped transient-overlay reduction in `windows-client/astral_client/protocol.py` and `windows-client/astral_client/app.py` (FR-026–FR-031)
- [X] T054 [P] [US3] Implement documented `ConversationResumeStore`, registration locator, transient-loss retention, four definitive clear actions, semantic decoding, purpose-aware atomic snapshot replacement with the same first-complete fresh-ID hydration-only equal/replay/conflict rules as T052, exact six-field `conversation_commit_ready` fresh/stale/malformed/busy-fence handling, and request-scoped transient-overlay reduction in `android-client/app/src/main/kotlin/com/personalailabs/astraldeep/app/auth/ConversationResumeStore.kt`, `android-client/app/src/main/kotlin/com/personalailabs/astraldeep/app/transport/OrchestratorClient.kt`, and `android-client/app/src/main/kotlin/com/personalailabs/astraldeep/app/ui/AppViewModel.kt` (FR-026–FR-031)
- [X] T055 [P] [US3] Implement documented `ConversationResumeStore`, transient-loss retention, four definitive clear actions, semantic decoding, main-actor purpose-aware atomic snapshot replacement with the same first-complete fresh-ID hydration-only equal/replay/conflict rules as T052, exact six-field `conversation_commit_ready` fresh/stale/malformed/busy-fence handling, and request-scoped transient-overlay filters in `apple-clients/AstralApp/AstralApp/ConversationResumeStore.swift`, `apple-clients/AstralApp/AstralApp/AppModel.swift`, `apple-clients/AstralCore/Sources/AstralCore/Protocol/ConversationContinuity.swift`, and `apple-clients/AstralCore/Sources/AstralCore/Protocol/Frames.swift` (FR-026–FR-031)
- [X] T056 [US3] Add a Watch-owned issuer+subject-digested active-chat store with the same four definitive clear rules, bind it before reconnect registration, preserve the selected chat independently of endpoint override sync, apply purpose-aware committed snapshots with the same first-complete fresh-ID hydration-only equal/replay/conflict rules as T052, accept the exact six-field `conversation_commit_ready` only for a fresh active-chat/current-connection server commit without stealing a client fence, and reject stale paired/transient frames in `apple-clients/AstralWatch/ConversationResumeStore.swift`, `apple-clients/AstralWatch/WatchModel.swift`, and `apple-clients/AstralWatch/WatchOverrideSync.swift` (FR-026–FR-031)
- [ ] T057 [US3] Run 20 live restart/reconnect trials per supported client and record five-second restoration plus semantic parity in `specs/060-runtime-reliability-hardening/verification/us3-continuity.md` (SC-006)

---

## Phase 6: User Story 4 — Install a Ready-to-Use Windows Release (Priority: P1)

**Goal**: Ship Windows 0.4.0 with one reviewed immutable profile, no clean-install configuration
dialog, deterministic whole-profile precedence, a fully locked runtime, and pre-sign artifact proof.

**Independent Test**: On a fresh Windows user hive with no overrides, the actual EXE validates its
profile/worker, opens without Configure AstralDeep, signs in, chats, hosts a benign agent, and proves
upgrade identity from 0.3.0.

### Tests

- [x] T058 [P] [US4] Add strict profile-schema, placeholder, production-nonlocal, URI userinfo/query/fragment rejection, generic/developer local-only, whole-profile precedence, immutable-resolution, no-fallback, redacted-report, built-in tools-agent profile consumption, and no post-resolution env/default reread tests in `windows-client/tests/test_deployment_profile_060.py` (FR-033–FR-039; SC-007)
- [x] T059 [P] [US4] Add fresh-HKCU no-dialog, actual frozen EXE/worker, built-in tools-agent endpoint/profile-digest agreement, ordinary rendered chat, benign hosted-agent round trip, offline retry, and clean termination tests in `windows-client/tests/test_packaged_release.py` (FR-034, FR-036–FR-039, FR-048; SC-007)
- [x] T060 [P] [US4] Add strict SemVer/update-from-0.3.0 and immutable asset identity tests that reject v-prefix, every whitespace/line terminator, leading-zero core/numeric prerelease identifiers and accept legal prerelease/build metadata in `windows-client/tests/test_integrity.py` (FR-040; SC-008)
- [x] T061 [P] [US4] Add two-clean-build hash-lock/package-manifest reproducibility tests in `windows-client/tests/test_release_lock_060.py` (FR-018, FR-040; SC-021)

### Implementation

- [x] T062 [US4] Implement documented strict `DeploymentProfile` parsing, whole-profile precedence, canonical digest, immutable effective profile, and redacted validation report in `windows-client/astral_client/deployment.py` (FR-033, FR-035–FR-039)
- [x] T063 [US4] Resolve the documented immutable effective profile before Qt/auth/transport/hosting, pass that same object into the built-in tools agent, retain it on failure/retry, and forbid post-resolution environment/default rereads or field mixing in `windows-client/main.py`, `windows-client/astral_client/app.py`, and `windows-client/win_agent/agent.py` (FR-034–FR-037; SC-007)
- [x] T064 [US4] Add the reviewed non-secret 0.4.0 bundled production profile in `windows-client/deployment/release-profile.json` (FR-033, FR-038)
- [x] T065 [US4] Bundle and preflight the profile, worker manifest, and generic required-lock metadata seam without claiming or embedding the not-yet-authored final lock in `windows-client/AstralDeep.spec` and `windows-client/main.py` (FR-038, FR-039, FR-048)
- [x] T066 [US4] Bump the client to strict semantic version 0.4.0 and correct newer-version comparison in `windows-client/astral_client/__init__.py` and `windows-client/astral_client/integrity.py` (FR-040; SC-008)
- [x] T067 [US4] Split direct requirements from the complete hashed Windows/Python 3.11 release set in `windows-client/requirements.in` and `windows-client/requirements-release.lock.txt` (FR-018, FR-053; SC-021)
- [x] T068 [US4] After T067, bind the actual final release-lock digest through bundle/host/package metadata and add a reusable build-once unsigned Windows candidate workflow that performs fresh-user profile validation, frozen worker/GUI smoke, two-build lock reproduction, artifact identity, and Windows Python coverage before archiving the exact matrix-input EXE/provenance by run+artifact ID/digest in `backend/orchestrator/agent_generator.py`, `windows-client/win_agent/byo_host.py`, `windows-client/AstralDeep.spec`, and `.github/workflows/build-windows-candidate.yml` (FR-018, FR-038–FR-040, FR-048; SC-007, SC-008, SC-021)
- [ ] T069 [US4] Run the Windows release proof on a fresh runner and record profile/version/artifact digests without secrets in `specs/060-runtime-reliability-hardening/verification/us4-windows-release.md` (SC-007, SC-008, SC-021)

---

## Phase 7: User Story 5 — Finish Apple First-Login LLM Setup Responsively (Priority: P1)

**Goal**: Acknowledge Save locally within 250 ms using `submitting`, remain interactive, show a
phase after one second, navigate promptly on success, and end/reconcile every attempt by ten seconds.

**Independent Test**: Run 30 valid/invalid/slow/unavailable trials on both macOS and iOS; at least
95% of valid trials advance within five seconds, all interactions stay within 250 ms, and no attempt
or late success survives ten seconds.

### Tests

- [X] T070 [P] [US5] Add accepted-operation single-flight, eight-second probe, ten-second whole-attempt terminal, corrective invalid-credential versus retryable provider/network outcomes, persistence/navigation, disconnect reconciliation, and no-late-success tests in `backend/llm_config/tests/test_operation_status_060.py` (FR-054–FR-056; SC-016)
- [X] T071 [P] [US5] Add Swift model tests for immediate local `submitting`, canonical server acceptance, phase/terminal ordering, ten-second client watchdog, durable submission lookup, duplicate Save, and editable retry in `apple-clients/AstralApp/AstralAppTests/LLMFirstLoginOperationTests.swift` (FR-054–FR-056)
- [X] T072 [P] [US5] Add deterministic iOS/macOS UI automation to the T005-scaffolded shared UI-test target for 250ms interaction, one-second phase, five-second success, ten-second terminal, focus/window/scene responsiveness, and accessibility in `apple-clients/AstralApp/AstralAppUITests/LLMFirstLoginUITests.swift` (FR-054–FR-057; SC-016)

### Implementation

- [X] T073 [US5] Route LLM Save through one operation/submission identity, emit corrective invalid-credential versus retryable provider/network terminals, enforce the ten-second outer deadline/no-late-success fence, and expose retained reconciliation through the actual dispatch/gate/API seams in `backend/llm_config/ws_handlers.py`, `backend/orchestrator/orchestrator.py`, `backend/orchestrator/llm_gate.py`, and `backend/orchestrator/api.py` (FR-054–FR-056)
- [X] T074 [US5] Bound provider probing to eight seconds and prevent post-deadline persistence/unlock in `backend/llm_config/probe.py` and `backend/llm_config/user_store.py` (FR-055, FR-056)
- [X] T075 [US5] Reduce `operation_status` and submission reconciliation with a monotonic ten-second watchdog on the main actor in `apple-clients/AstralApp/AstralApp/AppModel.swift` (FR-054–FR-056)
- [X] T076 [US5] Make ParamPicker Save immediately acknowledge, disable only duplicate submission, retain SecureField editing/retry, show accessible phases, and navigate once on completion in `apple-clients/AstralApp/AstralApp/Views/ComponentView.swift` (FR-054–FR-056)
- [X] T077 [US5] Wire the T005-scaffolded shared iOS/macOS UI-test and Watch unit-test targets into non-waivable first-login/continuity jobs, strict recursive `xcrun swift-format lint`, code-covered Xcode test result bundles, and mapped Apple/Watch coverage artifacts, selecting Xcode 26.6 while targeting supported iOS/watchOS 26.5 simulator runtimes, in `.github/workflows/apple-ci.yml` (FR-057)
- [ ] T078 [US5] Run 30 trials per Apple platform, including the reported Mac profile when available, and record timing distributions in `specs/060-runtime-reliability-hardening/verification/us5-apple-first-login.md` (FR-057; SC-016)

---

## Phase 8: User Story 6 — Author and Maintain Agents Without Race Corruption (Priority: P2)

**Goal**: Make draft transitions, generation, startup updates, maintenance, and registries safe under
multiple tabs/devices/replicas without lost updates, false completion, or event-loop starvation.

**Independent Test**: Race same-name creation, stale transitions, generation/publication, deletion,
two starters, partial synthesis, and 10,000 registry mutations; conflicts are explicit, successful
units only complete, and unrelated work remains responsive.

### Tests

- [x] T079 [P] [US6] Add 100 same-name/owner/device CAS, stale-revision conflict-with-refresh-under-1s, generation claim, and delete/register interleaving tests in `backend/tests/test_agent_authoring_concurrency_060.py` (FR-019–FR-021; SC-005)
- [x] T080 [P] [US6] Add staging/fsync/atomic-replace and crash-at-every-publication-boundary tests in `backend/tests/test_agent_artifact_publication_060.py` (FR-021; SC-005)
- [x] T081 [P] [US6] Stress the foundation-owned migration/advisory/policy APIs with 50 two-instance startup/crash and policy-only revalidation trials in `backend/tests/test_migrations_060.py` (FR-022, FR-059; SC-017)
- [x] T082 [P] [US6] Add partial-failure, lease-expiry, crash-after-replace, retry-identity, and success-only synthesis tests in `backend/tests/test_maintenance_claims_060.py` (FR-023; SC-009)
- [x] T083 [US6] After T021, add 10,000 registry interleavings and release-load maintenance/process latency tests in `backend/tests/perf/test_runtime_reliability_060.py` (FR-024, FR-025; SC-018, SC-019)

### Implementation

- [x] T084 [US6] Give drafts immutable owner-scoped UUID identities, state revisions, idempotency keys, generation claims, and database-backed expected-revision CAS responses for phase/analyze writes in `backend/orchestrator/agent_authoring.py`, `backend/orchestrator/agentic_creation.py`, and `backend/orchestrator/draft_archive.py` (FR-019, FR-020; SC-005)
- [x] T085 [US6] After T038/T040, stage authoring UUID/revision-specific artifacts, fsync files/directories, validate, atomically replace immutable revisions, and publish only under current operation/draft fences through a dedicated authoring seam in `backend/orchestrator/artifact_publication.py` and its `backend/orchestrator/agent_generator.py` caller without taking over runtime start/ready/promotion ownership (FR-021; SC-005)
- [x] T086 [US6] Integrate the foundation-owned guarded migration entry point into two-replica boot/crash recovery and remove any parallel startup migration ownership path in `backend/start.py` and `backend/shared/database.py` (FR-022; SC-017)
- [x] T087 [US6] Consume the foundation-owned independent user-agent policy marker on every boot and expose a non-sensitive revalidation outcome in `backend/orchestrator/agent_constitution.py` and `backend/start.py` without reimplementing schema ownership (FR-059; SC-017)
- [x] T088 [US6] Claim maintenance units/inputs durably, preserve retry identity, mark only successful inputs complete, and publish output atomically in `backend/orchestrator/knowledge_synthesis.py` (FR-023; SC-009)
- [x] T089 [US6] Move blocking generation/maintenance/filesystem/process work to bounded executors admitted separately from interactive work in `backend/orchestrator/agentic_creation.py` and `backend/orchestrator/knowledge_synthesis.py` (FR-024; SC-019)
- [x] T090 [US6] Replace cross-thread `agent_cards` and related maps with one immutable registry snapshot API in `backend/orchestrator/orchestrator.py` and `backend/orchestrator/runtime_registry.py` (FR-025; SC-018)
- [x] T091 [US6] Run the 100/50/10,000 concurrency and release-load profiles and record conflicts, completion truth, registry stability, p95≤2s, and max≤5s in `specs/060-runtime-reliability-hardening/verification/us6-data-concurrency.md` (SC-005, SC-009, SC-017–SC-019)

---

## Phase 9: User Story 7 — Trust Examples, Progress, Status, and Operating Guidance (Priority: P2)

**Goal**: Make examples match tools/results, lifecycle/progress converge on every client, and
operating instructions apply boot-time settings truthfully from a clean checkout.

**Independent Test**: Execute every curated example, all five lifecycle states on every client, a
long-running operation, and the documented enable/apply flow; narratives match normalized records,
status terminates once, links resolve, and the running setting is verifiable.

### Tests

- [X] T092 [P] [US7] Add curated prompt/tool-bound and exact normalized quantity/unit/bound/label/value narrative tests in `backend/tests/test_curated_examples_060.py` and `backend/tests/test_dice_roller_060.py` (FR-041, FR-042; SC-010)
- [X] T093 [P] [US7] Add accepted/phase/terminal and starting/online/updating/failed/offline web/Windows/Android/iOS/macOS/shipping-Watch-target contract and reducer tests in `backend/tests/test_status_lifecycle_060.py`, `backend/tests/test_client_js_contract.py`, `windows-client/tests/test_status_lifecycle_060.py`, `android-client/app/src/test/kotlin/com/personalailabs/astraldeep/app/StatusLifecycleTest.kt`, `apple-clients/AstralCore/Tests/AstralCoreTests/StatusLifecycleTests.swift`, `apple-clients/AstralApp/AstralAppTests/StatusLifecycleTests.swift`, and `apple-clients/AstralWatchTests/StatusLifecycleTests.swift` (FR-032, FR-043; SC-011, SC-022)
- [X] T094 [P] [US7] Add tracked-document link, ignored-directory, apply-recreate, and effective-setting verification tests in `backend/tests/test_documentation_060.py` (FR-044–FR-046; SC-013)

### Implementation

- [X] T095 [US7] Change the welcome request to exactly six six-sided dice and normalize rolls/sides/notation/result metadata in `backend/orchestrator/welcome.py` and `backend/agents/dice_roller/mcp_tools.py` (FR-041, FR-042; SC-010)
- [X] T096 [US7] Emit canonical `operation_status` for every operation exceeding two seconds and `agent_lifecycle` for all five states in `backend/orchestrator/orchestrator.py`, `backend/orchestrator/agent_lifecycle.py`, and `backend/orchestrator/chrome_events.py` (FR-032, FR-043; SC-011, SC-022)
- [X] T097 [P] [US7] Render/reduce canonical status and lifecycle sequences without reload in `backend/webrender/static/client.js` and `windows-client/astral_client/app.py` (FR-032, FR-043)
- [X] T098 [P] [US7] Render/reduce canonical status and lifecycle sequences without reload in `android-client/app/src/main/kotlin/com/personalailabs/astraldeep/app/ui/AppViewModel.kt`, `apple-clients/AstralApp/AstralApp/AppModel.swift`, and `apple-clients/AstralWatch/WatchModel.swift` (FR-032, FR-043)
- [X] T099 [US7] Track and unignore the personal-agent guide covering enablement, verification, hosting, lifecycle, recovery, compatibility, and rollback in `.gitignore` and `docs/byo-client-agents.md` (FR-044; SC-013)
- [X] T100 [US7] Make the documented boot-setting apply target recreate/reload the service and print a non-sensitive effective-value check in `Makefile` and `docs/byo-client-agents.md` (FR-045; SC-013)
- [X] T101 [US7] Implement a standard-library tracked-Markdown target validator, exercise all executable paths under tooling-Python coverage, and wire it into CI in `scripts/check_doc_links.py`, `backend/tests/test_documentation_060.py`, and `.github/workflows/ci.yml` (FR-046; SC-013)
- [ ] T102 [US7] Run all examples, 20 lifecycle sequences per client, long-operation terminality, and clean-checkout docs/apply verification and record results in `specs/060-runtime-reliability-hardening/verification/us7-operability.md` (SC-010, SC-011, SC-013, SC-022)

---

## Phase 10: User Story 8 — Prove Release Behavior Before Publication (Priority: P2)

**Goal**: Require same-SHA/digest candidate-staging evidence from the actual browser and shipping artifacts,
with explicit bounded exceptions and non-waivable Apple remediation evidence.

**Independent Test**: Run one candidate through backend, real browser, packaged Windows, connected
Android, macOS, iOS, watchOS, and docs jobs; the aggregator rejects missing/mismatched/duplicate or
expired evidence and passes only a complete same-artifact set.

### Tests

- [ ] T103 [P] [US8] Add schema/policy tests for every declared schema keyword, whitespace-strict SemVer, same-SHA/digest/release binding, quantitative trials, exact non-duplicated IDs/targets, platform-to-artifact/runner and exact attested producer-job binding, credential-free endpoint parsing, passing-versus-unavailable behavior, unavailable-report retention of exact artifact/stage plus protected attempted-target observation and distinct control producer, failed-product/backend/docs/staging/trust/policy/non-waivable rejection, mandatory-pass versus enumerated-N/A outcomes, one independently attested trust manifest per producer/stage/approval/debt-resolution and a final decision binding every manifest ID to its exact canonical artifact member/digest, protected-builder signer-digest/certificate pinning with candidate-modified-workflow, same-name-required-check spoof, and correct-HEAD/dirty-policy substitution rejection, protected release-owner API approval with immutable request bytes that contain no guessed reviewer/time/expiry, fixed-field compact sorted-key UTF-8 payload-hash vectors, duplicate/non-finite rejection, forged/self-approved rejection, and post-request/pre-approval or post-approval request-byte mutation rejection; cover protected registrar create-only debt/resolution commits, exact `debts/`/`resolutions/` path/digest receipts, stale/concurrently moved head, force-push/prior-entry mutation, duplicate/forged/partial/old-resolution rejection, debt A→later pass→resolution→new same-check debt isolation, and final-decision ledger commit/tree/snapshot plus `valid_until`; retain protected pinned-policy final-decision ownership with exact decision-artifact attestation binding and candidate-ignored-failure/substituted/expired-verdict rejection, required workers/fixture fingerprints/cross-report equality, canonical URI derivation plus traversal/symlink/mutable-reference rejection and byte re-hashing for bundle/GitHub-run-member/GitHub-release-asset/OCI provenance, candidate-capability truth, and post-readiness Windows provenance proving the unchanged build-once EXE plus re-downloaded `SHA256SUMS` and detached `cosign.bundle`, bridge denial without `actions: read`, exact constant-name/distinct-ID three-asset draft=true/count=3/tag/release/target identity with release-name=tag and latest-on-publish metadata, API-shaped shipped-v0.3.0 `/releases/latest` selection, API-backed protected-publisher approval/token-broker binding, moved-publisher or expired-between-decision-and-publication rejection, actual-v0.3.0 legacy-bridge checksum/Sigstore verification, no rebuild, and public transition only after draft verification in `backend/tests/test_release_evidence_validator.py`, `backend/tests/test_candidate_staging_060.py`, and `backend/tests/test_release_workflows_060.py` (FR-048–FR-051; SC-012)
- [x] T104 [P] [US8] Add lock-pinned `npm ci` and a digest-pinned official Playwright image matching the package lock/Chromium/Linux dependencies, cache/version/digest proof, and real-browser sign-in/chat/reconnect/status/lifecycle harness tests with pytest orchestration, real Keycloak UI auth, and no host/system-browser/source-DOM/mock-auth substitute in `tooling/web-ci/playwright-image.txt`, `tooling/web-ci/tests/release-060.spec.js`, and `backend/tests/e2e/test_release_browser_060.py` (FR-049, FR-050; SC-012)
- [ ] T105 [P] [US8] After T112–T118, add same-candidate artifact-report contract tests for packaged Windows, connected Android, macOS, iOS, and watchOS outputs, quantitative measurements/raw references, mandatory-pass flows where only the Watch report's canonical `personal_agent` authoring check is always N/A and `macos_personal_agent_host` is N/A only when the candidate-owned `/api/dashboard`/`system_config` feature-059 capability is valid and false; true requires structured v2 registration plus `agent_host_registered` and a pass, while missing/malformed/refused capability blocks and authoring/continuity remain applicable in `backend/tests/test_release_evidence_producers.py` (FR-048–FR-050; SC-012)

### Implementation

- [x] T106 [US8] Implement the documented auditable standard-library policy engine with every used schema keyword, fail-closed schema walk/JSON decoding, duplicate check/platform rejection, explicit validation of all three protected-archive schemas including production-nonlocal deployment URLs with no userinfo/query/fragment, platform artifact/runner enforcement, unavailable-only bounded client exception requests that retain exact artifact/stage and independently attested attempted-target observation, protected-environment/API approval by an allowlisted release owner other than the requester whose pre-review payload binds exact requester-known re-hashed request bytes, and separately attested protected-registrar debt/resolution append receipts; require exact N/A allow-list, normalized cross-report staging identity matched to independently attested exact-ID per-producer/stage/approval/resolution manifests, protected reusable-builder signer digest/certificate identity pinned outside candidate control, current repository/run/attempt/job/candidate and exact runner checks, candidate image/digest and 059 policy, canonical safe resolution/retrieval plus recomputed hashes for `bundle://`, GitHub run-member/release-asset `gh://`, digest-qualified `oci://`, and protected `ghgit://` ledger provenance with traversal/symlink/mutable-scheme rejection, exact measurements, protected-policy SHA, bounded `valid_until`, exact protected-ledger head/tree/canonical `debts/`+`resolutions/` snapshot, stale/concurrent-head rejection, one-time debt-resolution semantics, and `trusted_release_decision` generation; retain official three-asset detached-Sigstore Windows draft-verification lineage validation and use `--exception-ledger-repository`/`--exception-ledger-ref`/`--exception-ledger-commit` plus trusted approval/resolution inputs instead of candidate-tree history in `scripts/validate_release_evidence.py`; qualifying CI executes the copy pinned inside T107's protected verifier revision, never the candidate checkout (FR-038, FR-048–FR-051; SC-012)
- [ ] T107 [US8] After T112–T118 complete, author reusable `.github/workflows/release-readiness.yml`, explicit manual diagnostic reruns, and the eventual `.github/workflows/ci.yml` PR/main caller, but leave that automatic caller and required gate inactive until T120 finishes the first protected trust-root landing. Require an immutable PR-base/main-before/verified-manual base, reuse the CI-built image and T068 client artifacts, deploy the exact image digest on configured TLS staging, import tracked 057 SQL/realm/manifest through normal startup with real dependencies, and run all platform/docs jobs. Keep candidate jobs read-only and pin every third-party action by commit SHA with a version comment. Author proposed default-branch `.github/workflows/release-trusted-builder.yml` and `.github/workflows/release-exception-registrar.yml`, but make qualifying execution hard-block until T120 independently lands/pins their policy/all three schemas, protected debt ref, and identities. The registrar re-queries immutable request/approval or later passing-evidence inputs and appends exactly one create-only debt or resolution entry without prior mutation; the verifier reconstructs producer/stage/approval/resolution manifests and current ledger head/tree from bounded IDs/API state, rejects stale/concurrent heads, never attests arbitrary candidate claims or executes candidate policy, runs pinned policy/coverage after all inputs and required registrations exist, sets bounded `valid_until`, and attests the exact-input/ledger-snapshot final decision. Prepare the caller to consume that decision and schedule T125 without an early producer cycle; T120 performs the second-checkpoint activation and exact protected-workflow-identity rule. Missing stage/secrets/trust/reachability/attestations/non-waivable evidence or unexpected empty diff always blocks; an always-running control path may emit `unavailable` only after an independently observed target-runner/platform failure, retaining exact artifact/stage/observation and requiring the exact-byte-bound protected approval plus registered debt, never for product failure or missing policy input, in `docker-compose.staging.yml`, `scripts/run_candidate_staging.py`, `.github/workflows/ci.yml`, `.github/workflows/release-trusted-builder.yml`, `.github/workflows/release-exception-registrar.yml`, and `.github/workflows/release-readiness.yml` (FR-048–FR-051, FR-053; SC-012, SC-015)
- [ ] T108 [P] [US8] After T104, T107, and T112–T118, execute real Keycloak sign-in, rendered chat, reconnect/resume, terminal status, lifecycle, accessibility, and applicable authoring flows against the exact T107 staging endpoint before emitting quantitative candidate/artifact/raw-evidence-bound browser/backend reports and Playwright V8 precise coverage converted and executable-syntax-filtered by the lock-pinned producer into canonical Istanbul statement JSON in `tooling/web-ci/tests/release-060.spec.js`, `backend/tests/e2e/test_release_browser_060.py`, and `backend/tests/perf/release_backend_060.py` (FR-047, FR-049, FR-050)
- [ ] T109 [P] [US8] After T107 and T112–T118, download/re-hash and execute T068's archived build-once unsigned Windows EXE for chat/host/accessibility flow plus the connected Android sign-in/chat/resume/lifecycle/authoring/accessibility flow against the same trusted staging endpoint before emitting quantitative schema-valid reports/bundled raw references in `windows-client/tests/release_evidence_060.py` and `android-client/app/src/androidTest/kotlin/com/personalailabs/astraldeep/app/ReleaseEvidenceInstrumentedTest.kt` (FR-047–FR-050)
- [ ] T110 [P] [US8] After T107 and T112–T118, execute macOS authoring/continuity/accessibility, iOS sign-in/chat/resume/lifecycle/authoring/accessibility, and the shipping Watch app target on a booted watchOS simulator for sign-in/chat/resume/lifecycle/accessibility (plus physical Watch hardware only when the release runner explicitly provides it), with the Watch report's canonical `personal_agent` authoring check N/A, and non-waivable Apple first-login trials against the same staging endpoint; branch macOS hosting only from the recorded candidate capability, requiring structured v2 registration/`agent_host_registered`/host flow when true and N/A only when false, before emitting quantitative schema-valid reports/raw references in `apple-clients/AstralApp/AstralAppUITests/ReleaseEvidenceUITests.swift` and `apple-clients/AstralWatchTests/ReleaseEvidenceTests.swift` (FR-047, FR-050, FR-051, FR-057)
- [ ] T111 [US8] After T108–T110, run the request-correlated matrix as a non-qualifying producer-contract diagnostic and precommit the retrieval/topology/provenance template in `specs/060-runtime-reliability-hardening/verification/us8-release-evidence.md`; do not claim a protected aggregate decision before T120 installs the trust roots and T125/T128 execute the pinned aggregate (SC-012)

---

## Phase 11: User Story 9 — Keep Clients Operable Through Upcoming Platform Changes (Priority: P3)

**Goal**: Exercise a genuine next-major Android toolchain and give every changed interactive control
a stable accessible role, name, state, and focus behavior.

**Independent Test**: The isolated AGP-10/Gradle-10 canary asserts resolved majors and passes with
warnings as errors; automated semantics inspection finds no unnamed or unfocusable changed control.

### Tests

- [X] T112 [P] [US9] Add tests that the covered Python canary driver uses separately pinned major-10 tools once public, fails if shipping 9.x is reused, treats known-removal warnings as errors, and cleans its isolated checkout; while either tool is unpublished, require an independently verified official-metadata diagnostic, reject stale or fabricated `unreleased` declarations, and prove that diagnostic cannot report a passing canary in `backend/tests/test_android_next_major_canary.py` (FR-052; SC-014)
- [X] T113 [P] [US9] Add TalkBack/VoiceOver/Watch/Qt/browser role-name-state-focus tests for every changed control plus a native mobile keyboard/dismissal contract in `android-client/app/src/androidTest/kotlin/com/personalailabs/astraldeep/app/Accessibility060Test.kt`, `apple-clients/AstralApp/AstralAppUITests/Accessibility060UITests.swift`, `apple-clients/AstralWatchTests/Accessibility060Tests.swift`, `windows-client/tests/test_accessibility_060.py`, `backend/tests/webrender/test_accessibility_060.py`, and `backend/tests/test_native_keyboard_contract_060.py` (FR-047; SC-014)

### Implementation

- [X] T114 [US9] Remove built-in-Kotlin opt-outs, obsolete plugin/variant APIs, and Project-object dependency notation in `android-client/gradle.properties`, `android-client/build.gradle.kts`, `android-client/settings.gradle.kts`, and `android-client/app/build.gradle.kts` (FR-052)
- [ ] T115 [US9] Maintain explicit `unreleased` AGP-10/Gradle-10 sentinels with bounded official metadata endpoints and a tooling-coverage-measured fail-closed Python availability diagnostic; once both exact public artifacts exist, atomically replace every sentinel with independently resolvable version/URL/checksum pins and run the isolated major-asserting canary. The unavailable diagnostic never closes T115 or satisfies SC-014, in `android-client/gradle/next-major-canary.properties` and `scripts/run_android_next_major_canary.py` (FR-052; SC-014)
- [X] T116 [US9] Add non-shipping scheduled/PR compatibility, mandatory Android lint, and app+core Kover XML publication lanes for the isolated canary and cross-language changed-code gate in `.github/workflows/android-ci.yml` (FR-052; SC-014)
- [X] T117 [US9] Add stable role/name/state/focus behavior to changed Android, Apple, Watch, Windows, and web authoring/status controls, and retain native iOS/Android keyboard dismissal without an application-drawn Done accessory, in `android-client/app/src/main/kotlin/com/personalailabs/astraldeep/app/ui/Screens.kt`, `android-client/app/src/main/kotlin/com/personalailabs/astraldeep/app/ui/AdaptiveShell.kt`, `android-client/app/src/main/kotlin/com/personalailabs/astraldeep/app/render/renderers/Input.kt`, `apple-clients/AstralApp/AstralApp/Views/ComponentView.swift`, `apple-clients/AstralApp/AstralApp/Views/ChatView.swift`, `apple-clients/AstralWatch/Accessibility060.swift`, `apple-clients/AstralWatch/Views/WatchChatView.swift`, `apple-clients/AstralWatch/Views/WatchComponentView.swift`, `windows-client/astral_client/app.py`, and `backend/webrender/static/client.js` (FR-047; SC-014)
- [ ] T118 [US9] Run the bounded official-availability diagnostic and cross-client accessibility inspection and record the verified unavailable state plus zero unnamed controls; keep T118 open until both exact public tool versions resolve and the true next-major canary passes, then record those resolved versions in `specs/060-runtime-reliability-hardening/verification/us9-future-readiness.md` (SC-014)

---

## Phase 12: Polish and Cross-Cutting Verification

**Purpose**: Prove the integrated change under the repository's constitution and release profile.

- [ ] T119 After T103, T106, and T107, convert `.github/workflows/release-windows.yml` into an exact-byte-pinned legacy compatibility bridge signer and add the proposed protected publisher plus workflow/client contract tests in `.github/workflows/release-windows-publisher-controller.yml`, `.github/workflows/release-windows-publisher.yml`, `backend/tests/test_release_workflows_060.py`, `windows-client/astral_client/integrity.py`, and `windows-client/tests/test_integrity.py`. The bridge retains the shipped v0.3.0 SAN `.../release-windows.yml@refs/tags/v0.4.0`, has only `contents: read`, `actions: read`, and `id-token: write`, retrieves T068 bytes by exact originating run/attempt/artifact ID, re-hashes/signs only those bytes after its blob hash equals T120's installed template, and can run only for a new tag created by the protected publisher; it has no release mutation and denial without `actions: read` is tested. The owner-approved publisher executes only after an environment/broker verifies its full immutable workflow SHA before granting a scoped GitHub App publication token, consumes the exact attested decision, re-opens all used approval/ledger inputs, and rejects current time at/after decision `valid_until` or any approval expiry. It refuses existing tag/release/assets; creates exactly `v${release_version}` (`v0.4.0`) at the readiness SHA with release name equal to tag and latest-on-publish disposition; waits for and verifies the bridge bundle with the actual v0.3.0 verifier; uploads exactly three create-only draft assets; re-downloads/verifies them and protected-publisher-bound draft provenance; then in authorized official mode transitions public as latest and re-queries an API-shaped `/releases/latest` response through the shipped v0.3.0 parser. Pin actions by commit SHA; deny moved-main/modified-publisher, candidate write/OIDC, collision/overwrite, bare/mismatched tags, wrong release name/latest disposition, expiry between decision and publication, or bridge failure, deleting only the just-created tag/draft on pre-public failure. Test mode is isolated disposable-repository/draft-only with forced cleanup and no official tag/public transition (FR-048, FR-049; SC-008, SC-012)
- [ ] T120 After T106, T107, and T119, complete the independent two-checkpoint trust bootstrap before any qualifying evidence run. First land/review on protected default branch the verifier, pinned policy/all three schemas, bridge-signer template, exception debt/resolution registrar, immutable publisher/controller, and exact-workflow-SHA token-broker/deployment rules; initialize protected non-force-push/registrar-App-only `refs/heads/release-evidence-debt`; pin full commit/blob/certificate/App identities; and configure `release-evidence-exception` and `release-publisher` environments/reviewer allowlists plus publisher-only tag rules while the automatic PR/main caller and required gate remain disabled. Record non-secret identities/configuration in `specs/060-runtime-reliability-hardening/verification/release-trust-bootstrap.md`, rebase the candidate onto and verify that root, then in a second candidate checkpoint activate T107's caller and a repository rule requiring the exact installed protected workflow identity (not only `release-readiness / protected-decision` name); test candidate same-name-job rejection. Missing/unverifiable protected state, moved or force-pushed refs, dirty policy bytes, caller-before-root activation, or candidate/protected drift hard-blocks (FR-048, FR-049, FR-051; SC-012)
- [ ] T121 [P] After T120, run Ruff, tracked ESLint, public-API documentation guards, and the full backend default/module/performance plus release-tooling suites, verify no empty selections, emit separate backend and root `scripts/*.py` tooling coverage XML covering every executable Python tool, and record results in `specs/060-runtime-reliability-hardening/verification/final-backend.md` (SC-015)
- [ ] T122 [P] After T120, run Ruff plus the complete Windows source suite, the actual v0.3.0-verifier bridge compatibility test including API-shaped `/releases/latest` name/tag/latest selection, and fresh-runner packaged EXE/profile/worker proof, emit Windows Python coverage XML, and record artifact digests/results in `specs/060-runtime-reliability-hardening/verification/final-windows.md` (SC-007, SC-008, SC-020, SC-021)
- [ ] T123 [P] After T120, run Android lint/unit/app+core Kover XML/connected tests, 20 process-recreation trials, the true next-major canary, and accessibility inspection, recording report identities/results in `specs/060-runtime-reliability-hardening/verification/final-android.md` (SC-006, SC-014, SC-015)
- [ ] T124 [P] After T120, run strict recursive `xcrun swift-format lint`, AstralCore plus code-covered iOS/macOS and the shipping `AstralWatchTests` target on the booted watchOS simulator, and all first-login/continuity/accessibility trials using Xcode 26.6 with iOS/watchOS 26.5 runtimes; add physical Watch evidence only when the candidate release infrastructure explicitly supplies that device, emit mapped `xccov`/Swift coverage including Watch source, and record report identities/results in `specs/060-runtime-reliability-hardening/verification/final-apple.md` (SC-006, SC-016, SC-022)
- [ ] T125 After T108–T110 are implemented and T120 plus T121–T124 are complete, launch the installed workflow so its producer jobs rerun on the rebased candidate and execute the installed protected pinned readiness aggregate wired by T107: verify the workflow-supplied PR base/main `before`/manual ancestor SHA and candidate SHA; reconcile the exact protected ledger head, append/verify any newly earned debt-resolution receipts, reject concurrent movement, and bind the final debt/resolution snapshot plus bounded `valid_until`; run the protected copy of `scripts/check_changed_coverage.py` over backend/tooling/Windows Python XML, parser-filtered lock-pinned V8-to-Istanbul JavaScript statement JSON, counter-validated Android app/core Kover XML, and line-complete Apple app/core/Watch coverage; merge repeated source-line observations; fail raw/unfiltered V8, partial native reports, candidate-hidden or empty maintained hunks, any applicable missing/unmapped/unparseable report, unexpected empty executable diff, or per-language/combined result below 90%; and archive the attested mapping in `specs/060-runtime-reliability-hardening/verification/coverage.md` (FR-051, FR-053; SC-012, SC-015)
- [ ] T126 Audit every dependency diff, workflow action reference, and packaged manifest, documenting each new direct/transitive tool/package or action with exact version and immutable digest, purpose/rationale, transitive impact, product-artifact isolation proof, and approval disposition so the feature PR satisfies Constitution Principle V; prove no mutable third-party action, unapproved runtime dependency, or CI-only ESLint/Playwright package enters the protected workflow path, product images, or shipping artifacts in `specs/060-runtime-reliability-hardening/verification/dependencies.md` (FR-018, FR-053; SC-015, SC-021)
- [ ] T127 After T120, run `scripts/check_doc_links.py`, all contract drift guards, validate all three Draft 2020-12 schemas and declared regexes, and execute every command in `specs/060-runtime-reliability-hardening/quickstart.md` against the installed protected roots, recording deviations in `specs/060-runtime-reliability-hardening/verification/quickstart.md` (SC-013, SC-015)
- [ ] T128 After T111 and T119–T127, first commit the static retrieval/acceptance template in `specs/060-runtime-reliability-hardening/verification/release-candidate.md`, then select the clean rebased candidate SHA and run one final pre-publication same-SHA matrix with the attested protected-verifier decision, exact installed-workflow merge gate, protected staging/producers, exact-byte-bound approval and registered debt for any legal exception, attested resolution receipts, current protected-ledger snapshot, recomputed hashes, resolved debt, unexpired decision/approvals, complete pass/N-A policy, no non-waivable gap, build-once EXE lineage, and the T120-installed publisher in isolated disposable test mode. Exercise expiry-between-decision-and-publication rejection and v0.3.0 API-shaped latest-release selection. Store machine evidence/decision/draft provenance only as immutable run artifacts/job summary so recording cannot change the SHA; force-clean the disposable repository/draft and make no official tag or public release without separate explicit authorization (FR-048–FR-051; SC-012)

---

## Dependencies and Execution Order

### Phase Dependencies

- **Phase 1 → Phase 2**: Contract/fixture guardrails precede shared schema and protocol work.
- **Fixture consumers**: T001 precedes T008, T034, T035, T043, and T107; none may invent a private vector,
  lock-contract, database, realm, or manifest fixture.
- **Apple test targets**: T005 scaffolds the shared UI-test and shipping Watch unit-test targets/scheme
  actions before T049/T072/T093/T110/T113 add sources; T077 wires them into lint/coverage/evidence.
- **Phase 2 → all stories**: The schema, operation fence, supervisor, registry, and protocol manifest
  block every story.
- **Convergence guard**: Completed T129 closes preregistration refusal correlation across the server
  and all four client families and is a prerequisite for every remaining Phase 12 client/release gate.
- **US1, US2, US3, US5**: These P1 stories may proceed in parallel after Phase 2, subject to file
  ownership; US2 consumes the supervisor, US3 consumes generation fields, and US5 consumes operation
  status.
- **US4**: Starts after US2 T034–T043 because the frozen release proof exercises the BYO host/runtime
  contract; US4 alone authors the final Windows runtime lock. T065 establishes only generic metadata;
  T068 integrates/bundles the real lock and creates the unsigned artifact only after T067.
- **US6**: Starts after Phase 2; T085 consumes the runtime manifest only after T038/T040 and owns the
  separate authoring publication seam rather than the US2 runtime lifecycle file.
- **US7**: Backend status emission depends on canonical status/lifecycle from Phase 2 and integrates
  US2/US5 terminals; reducer tasks T097/T098 wait for US3 T052–T056 and US5 T075/T076 so they extend
  finalized continuity/operation reducers rather than racing their owners.
- **US8**: Contract/validator scaffolding T103/T104/T106 may start earlier, but T105 and workflow/
  producer/evidence completion T107–T111 wait for US9 T112–T118 because they consume the final
  accessibility controls, next-major tooling, and reports. T108–T111 are implementation/diagnostic
  tasks only; qualifying producer reruns and the protected decision occur after T120 in T125/T128.
- **US9**: Canary work T112/T114–T116 may start after Phase 2. Cross-client control changes T117 and
  accessibility verification T113/T118 wait for US7 T097/T098 so lifecycle/status UI is finalized.
- **Feature 059**: 060 has no implementation dependency on draft feature 059; macOS hosting evidence
  becomes applicable only when the candidate-owned capability map is valid and says supported. The
  existing spec directory, branch name, or a client claim never establishes applicability.
- **Release staging**: T107 constructs the workflow and its `stage-deploy` contract before
  T108/T109/T110 and every other platform producer. The protected aggregate executes only after all
  producer inputs exist; T125 performs that later aggregate/coverage execution rather than being a
  prerequisite for T107 construction. Always-run cleanup then removes the request namespace. T068's
  unsigned Windows artifact is an input, never rebuilt by T107.
- **Distribution**: T119 authors the exact-byte-pinned legacy bridge and proposed protected publisher.
  T120 first independently lands/configures the bridge, publisher, token broker, verifier, registrar,
  and protected debt ref without the caller, then rebases and activates the caller/exact-workflow
  rule in a second checkpoint before any qualifying validation; T128 then requires their unique passing same-SHA decision, consumes T068's
  archived unsigned bytes, and validates isolated disposable mode. Only a separately authorized
  protected official-mode dispatch may create `v0.4.0` and make a verified draft public.
- **Shared integration lanes**: Leaf modules may proceed in parallel, but shared integration files
  are serialized: `orchestrator.py` T025 → T030 → T037 → T039 → T050 → T051 → T073 →
  T090 → T096; `api.py` T030 → T037 → T073; Apple `AppModel.swift` T055 → T075 → T098
  (then functional dependency T098 → T117); Windows `app.py` T053 → T063 → T097 → T117;
  `agent_generator.py` T040 → T043 → T068 → T085; `byo_host.py` T041 → T042 → T043 →
  T068; `database.py` T011 → T050 → T086; browser release tests T046 → T104 → T108;
  `ci.yml` T005 → T101 → T107 → T120 activation; and backend release-policy tests T002 → T103. A later task
  integrates the earlier owner's completed seam.
- **Phase 12**: Depends on every selected story, all release-evidence producer implementations, and
  completed convergence guard T129.
  T119 authors the publication path, T120 establishes the independent protected roots/debt registrar,
  rebases the candidate, and separately activates the caller; T121–T127 validate that installed tree,
  then T128 selects the immutable candidate SHA and
  performs the final protected decision/non-public draft exercise without mutating tracked files.

### User-Story Completion Graph

```text
Setup → Foundation → {US1, US2→US4, US3, US5, US6, US9-canary}
                     {US2 + US3 + US5} → US7 → US9 UI/accessibility
                     {all completed story paths} → US8 → Final verification
```

### Within Each Story

1. Add tests and confirm the intended failure.
2. Implement durable models/repositories before coordinators and endpoints.
3. Implement server protocol behavior before client reducers/renderers.
4. Run focused tests and the story's exact independent trial profile.
5. Record non-sensitive evidence before declaring the story complete.

## Parallel Opportunities

- Phase-2 tests T006–T010 can run in parallel; protocol implementations T018–T020 touch different
  client trees.
- US1 tests T021–T024, US2 tests T032–T035, and US3 tests T045–T049 are independent within their
  story before implementation starts.
- After backend snapshot/status frames stabilize, web T052, Windows T053, Android T054, and Apple
  T055 can run in parallel.
- After US2 T034–T043, Windows release work T058–T069 and Apple first-login work T070–T078 are
  independent client trees.
- US8 evidence-producer implementations/diagnostics T108–T110 run in parallel after T106/T107;
  their qualifying rerun waits for T120 and is orchestrated by T125/T128.
- Final platform validations T121–T124 run in parallel after T120; T125 consumes their coverage,
  T126–T127 complete dependency/quickstart audits, and T128
  performs the final clean-SHA protected decision and non-public publication-contract exercise.

## Implementation Strategy

### MVP First

1. Complete Phase 1 and Phase 2.
2. Complete US1 (T021–T031).
3. Stop and validate the 1,000-frame plus 10,000-scheduler independent test before adding further
   stories.

### Incremental Delivery

1. Land bounded work/scheduler correctness (US1).
2. Land BYO failure/revision honesty (US2), conversation continuity (US3), Windows release readiness
   (US4), and Apple first-login recovery (US5) as independently testable P1 increments.
3. Land authoring/maintenance concurrency (US6) and truthful operability (US7) while US9 canary work
   proceeds; then finish US9 UI/accessibility once the shared controls stabilize.
4. Complete US8 release proof against the final US9 controls and execute Phase 12 on one candidate
   SHA.

## Format Validation

- Every executable item uses `- [ ] T### [P?] [US#?] Description with exact path`.
- Setup/foundation/polish items have no story label; every story-phase item has exactly one.
- IDs are sequential T001–T129; `[P]` appears only for non-overlapping files or read-only platform
  validation that can run concurrently.
- Tests precede implementation in every story and each story includes a standalone evidence task.

---

## Phase 13: Convergence

- [X] T129 Preserve each preregistration frame's canonical `submission_id`, emit one exact seven-field admission refusal for every queued and overflow-triggering submission before closing, prohibit null IDs in client-submission refusals, declare the strict refusal envelope in `backend/shared/ui_protocol.json`, and add backend plus web, Windows, Android, and Apple correlation/drift tests per FR-003, US1/AC3, and Constitution XII (partial)
