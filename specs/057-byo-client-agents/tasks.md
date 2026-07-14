---
description: "Task list for feature 057 — bring-your-own client-side agents"
---

# Tasks: Bring-Your-Own Client-Side Agents

**Input**: Design documents from `specs/057-byo-client-agents/`

**Prerequisites**: plan.md, spec.md, agent-constitution.md, research.md, data-model.md, contracts/ (agent-tunnel, analyze-gate, authoring-surface, user-agent-registry), quickstart.md

**Tests**: INCLUDED — the security-critical ones are non-negotiable (SC-003 adversarial boundary suite, byte-identity, Analyze-gate rules, tunnel/offline, lifecycle). Broad unit coverage otherwise follows the repo's normal pattern.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable (different files, no incomplete-task dependency)
- **[Story]**: US1–US5 (maps to spec user stories); Setup/Foundational/Polish carry no story label
- All paths are repo-relative

## Phase order (from plan.md phasing A–E)

Setup → Foundational → **US1** (Phase A, MVP) → **US3** (Phase B, boundary hardening — land before any production enablement) → **US2** (Phase C, guided authoring) → **US4** (Phase D, parity) → **US5** (Phase E, lifecycle) → Polish.

---

## Phase 0: Transport Decision (gates US1 transport tasks T008–T016)

- [ ] T000 Confirm the transport per the spec's Transport model (FR-032): **v1 default = the direct tunnel** over the client's existing authenticated connection (zero new dep) is the implementation scope of this feature. The **Cresco edge-mesh** transport (Mode 2) is the sanctioned path for the broader cross-device/edge-compute scenario and is built against the same seam later, under the feature-050 external-infrastructure posture. **Scope the two Cresco postures explicitly (X1)**: (a) *050-compliant* — a user/operator-run **external** Cresco fabric reached via the Python `wsapi` bridge (no new orchestrator/product-image dependency); (b) *client-bundled JVM Cresco agent* — a NEW client-side dependency **beyond** 050's server-side clearance, requiring its own Constitution V decision before adoption. Owner-binding + delegation + boundary re-verification run unchanged in either. Record the confirmed default in `research.md`.

---

## Phase 1: Setup (Shared Infrastructure)

- [ ] T001 [P] Add `FF_BYO_AGENTS` feature flag (default **off**, fail-closed) in `backend/shared/feature_flags.py`
- [ ] T002 [P] Create `backend/agent_constitution/agent_constitution.md` as a **byte-identical** copy of `specs/057-byo-client-agents/agent-constitution.md`, plus `backend/agent_constitution/README.md` documenting provenance + the byte-identity invariant (baked into the image; `.specify/`/`specs/` are not — `Dockerfile:49`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: no user-story work begins until this phase completes.

- [ ] T003 Add the `user_agent` table (incl. `deleted_at TIMESTAMPTZ` for soft-delete) + additive `draft_agents` columns (`phase`, `clarify_answers`, `plan_json`, `analyze_result`, `constitution_version`, `host_binding`) + `origin='byo_client'`; bump `SCHEMA_REVISION 055.002 → 057.001`; add guarded `_migrate_revalidate_on_constitution_change`; `is_public BOOLEAN CHECK(is_public=FALSE)` — all idempotent per `data-model.md` in `backend/shared/database.py`
- [ ] T004 [P] Add `backend/orchestrator/agent_constitution.py` loader: `AGENT_CONSTITUTION_VERSION` (semver from header) + `load_checklist()` → the A–L principle list, resolving the baked asset `__file__`-relative (mirror `knowledge_synthesis.AUTHORED_KNOWLEDGE_DIR`; do NOT hand-copy prose)
- [ ] T005 [P] Add the `user_agent` registry accessors (create / get / list-by-owner / set-status / set-host-liveness) in a new `backend/orchestrator/user_agents.py`, keyed on canonical `owner_user_id` (OIDC `sub`); write the companion `agent_ownership` row (`is_public=FALSE`) on go-live
- [ ] T006 [P] Add the `can_user_use_agent(user_id, agent_id) = is_public OR owner_user_id == user_id` predicate in `backend/orchestrator/tool_permissions.py` (reads `user_agent`/`agent_ownership`)

**Checkpoint**: schema, flag, constitution loader, registry, and the isolation predicate exist. User stories can begin.

---

## Phase 3: User Story 1 - Create an agent and run it on my own device (Priority: P1) 🎯 MVP

**Goal**: author a trivial agent that runs on the user's desktop host, is usable in chat, and goes offline on client close — off the orchestrator entirely.

**Independent Test**: create "greet me by name" on Windows; invoke it (correct result, user-attributed); confirm no agent process on the orchestrator host; close the client → offline within seconds; another user cannot see or invoke it.

### Tests for User Story 1

- [ ] T007 [P] [US1] Integration test: owner-tunnel register → dispatch through the existing gate stack → **assert the tool-call audit row attributes the action to the owning human (FR-012, finding U1)** → disconnect → honest-offline dispatch, in `backend/tests/test_byo_tunnel.py`

### Implementation for User Story 1

- [ ] T008 [US1] Direct-tunnel **agent-frame transport** behind a small **transport-adapter seam** (so Mode 2 can be added without touching owner-binding/dispatch, FR-032): unwrap an `agent_tunnel {frame}` envelope on the client's authenticated connection and feed `handle_agent_message` via a `.send`-shaped adapter (LoopbackSocket pattern), in `backend/orchestrator/orchestrator.py` (per `contracts/agent-tunnel.md`)
- [ ] T009 [US1] **Owner-binding** at `RegisterAgent` over an owner tunnel: resolve owner from `ui_sessions[ws].sub` (never from the card); refuse unless `user_agent.owner_user_id == sub` AND `status ∈ {validated, live}` AND `revalidation_required == FALSE`; store an owner-scoped registry keyed `(owner_sub, agent_id)`; supersede a stale socket on reconnect — in `orchestrator.py`; add the additive owner-auth field to `RegisterAgent` in `backend/shared/protocol.py`
- [ ] T010 [US1] **Owner==user tool-list visibility** filter in `_collect_eligible` so a private user agent is invisible to non-owners independent of scope rows (FR-019, scenario 4), in `backend/orchestrator/orchestrator.py`
- [ ] T011 [US1] **Honest-offline**: on tunnel disconnect deregister `(owner_sub, agent_id)` + emit `agent_offline`; short-circuit dispatch of an offline user agent to a prompt honest-offline `MCPResponse` (replace the `agent_urls` reconnect fallback for user agents), in `orchestrator.py`
- [ ] T012 [US1] Add the UI-facing `agent_offline` / `host_status` frame to `backend/shared/ui_protocol.json` + a liveness heartbeat so drops are caught within seconds (SC-005)
- [ ] T013 [US1] **Code-delivery seam**: after `generate_code`, package the 3-file bundle and push `agent_bundle_deliver` over the owner tunnel; **do NOT** call `start_draft_agent` (Popen) for byo agents; on inward register set `status='live'`, stamp `constitution_version`, insert the `agent_ownership` row — in `backend/orchestrator/agent_lifecycle.py` + `agentic_creation.py` (per `contracts/user-agent-registry.md`)
- [ ] T013b [US1] **Relocate the self-test off the live-server path (finding G1, SC-002)**: any pre-delivery self-test runs as an **explicitly ephemeral, bounded** orchestrator sandbox that is torn down immediately, **or** on the desktop host with the result reported back over the tunnel — never leaving a persistent user-agent process on the orchestrator (`_self_test_draft`/`start_draft_agent` must not become the live agent) — in `backend/orchestrator/agent_lifecycle.py`
- [ ] T014 [US1] **Minimal one-shot authoring path** (deliberate entry, `origin='byo_client'`): `create_draft` → existing static gates (`code_security` + `agent_validator`) → `generate_code` → deliver; stamp `AGENT_CONSTITUTION_VERSION`; mark `validated` (full 5-phase Analyze is US2), in `backend/orchestrator/agentic_creation.py`
- [ ] T015 [US1] **Windows host**: write + run a delivered user bundle as a **separate, client-supervised child process** (re-invoke `sys.executable`/the frozen exe with a worker-entry flag — NOT an in-process daemon thread, so the generated code cannot reach the client's own memory/tokens/files, finding C1/FR-013); relay its frames through the client's authenticated tunnel; supervise lifecycle + stop on client close — in `windows-client/win_agent/` (+ `windows-client/astral_client/app.py`)
- [ ] T016 [US1] **Codegen target**: make the generated bundle self-contained for the desktop-host runtime (not the backend `shared` package) OR ship a compatible host shim — `backend/orchestrator/agent_generator.py` + `windows-client`
- [ ] T017 [US1] Add an SC-002 guard/test asserting **zero user-agent processes on the orchestrator host** after go-live, in `backend/tests/test_byo_offserver.py`

**Checkpoint**: US1 is a working, demonstrable MVP — create + run client-side + offline-on-close, with the existing gate stack as baseline safety.

---

## Phase 4: User Story 3 - Nefarious local agents cannot cross the boundary (Priority: P2, co-critical) 🔒

**Goal**: a tampered/hostile user agent cannot reach another user's data or an ungranted tool; every attempt is denied fail-closed and audited; a flooding agent degrades only its owner.

**Independent Test**: drive a tampered local agent (out-of-scope tool, cross-user reference, forged identity, self-grant on another user's private agent, flood) → all denied fail-closed + audited; no other user's data returned; no cross-user latency impact.

### Tests for User Story 3

- [ ] T018 [P] [US3] Adversarial boundary suite in `backend/tests/test_byo_boundary_adversarial.py`: out-of-scope tool, cross-user data reference, forged identity/token, the `set_agent_permissions` grant-hole probe, and a flood — each denied fail-closed + audited (SC-003/SC-008)

### Implementation for User Story 3

- [ ] T019 [US3] **Close the pre-existing grant hole**: enforce `can_user_use_agent` at the grant endpoint `set_agent_permissions` in `backend/orchestrator/api.py` (refuse a non-owner granting themselves scopes on a private agent)
- [ ] T020 [US3] Enforce `can_user_use_agent` inside the **dispatch permission gate** (`_authorize_and_prepare`/`is_tool_allowed` path) in `backend/orchestrator/orchestrator.py` — defense in depth so a crafted request can't bypass the UI list
- [ ] T021 [US3] **Per-owner ingress bound**: a rate + in-flight-frame cap on user-agent tunnels (extend `backend/orchestrator/concurrency_cap.py` / `chain_authority.ChainBudget`), scoped to externally-connected user-agent sockets only (never throttling in-process built-ins/legit chains), wired in `handle_agent_message`
- [ ] T022 [US3] **No secrets to untrusted agents**: do not attach `_delegation_token` bytes or per-user secrets on the direct dispatch path for user-hosted agents (mirror the 054 in-process-only credential rule) in `backend/orchestrator/orchestrator.py`
- [ ] T023 [US3] **Owner-namespaced identity** + registration collision refusal (built-in/public/reserved `__*`/other-user ids) in `register_agent`; add owner-token binding **alongside** `AGENT_API_KEY` in `backend/orchestrator/auth.py`

**Checkpoint**: the boundary holds against a hostile local agent; production enablement is now safe.

---

## Phase 5: User Story 2 - Guided spec-driven authoring against the agent constitution (Priority: P2)

**Goal**: the hybrid Specify→Clarify→Plan→Tasks→Analyze flow, with Clarify and Analyze as mandatory pre-generation gates against the agent constitution.

**Independent Test**: author an agent that violates a constitution rule → Clarify surfaces the ambiguity, Analyze blocks progression with a plain-language cited reason and generates no code; fixing the spec lets it proceed and the live agent's declared tools/scopes match the plan exactly.

### Tests for User Story 2

- [ ] T024 [P] [US2] Analyze-gate rule tests (each A–L check pass/fail + cited offending field) in `backend/tests/test_agent_analyze.py`
- [ ] T025 [P] [US2] Byte-identity test between `backend/agent_constitution/agent_constitution.md` and `specs/057-byo-client-agents/agent-constitution.md` in `backend/tests/test_agent_constitution_identity.py`

### Implementation for User Story 2

- [ ] T026 [US2] `backend/orchestrator/agent_analyze.py`: deterministic `check(draft_spec, constitution) → AnalyzeResult(passed, constitution_version, violations[])` implementing A–L per `contracts/analyze-gate.md` (rule-decided; LLM only for phrasing)
- [ ] T027 [US2] Wire Analyze **immediately before** `generate_code`: on `passed=False` do not generate and do not advance (structural FR-003/SC-004); re-run on revision + on `revalidation_required` — in `backend/orchestrator/agentic_creation.py`
- [ ] T028 [US2] 5-phase authoring state machine over `draft_agents` (`specify|clarify|plan|tasks|analyze|generate`) with mandatory Clarify+Analyze gates, in `backend/orchestrator/agent_authoring.py`
- [ ] T029 [US2] `backend/webrender/chrome/surfaces/authoring.py` — the `agent_authoring` surface exporting **both** `render()` (web HTML) and `components()` (native SDUI); register in `surfaces/__init__.py::SURFACE_MODULES`; `chrome_author_specify/_clarify/_plan/_tasks/_analyze/_generate` handlers returning `("agent_authoring", {session_id}, notice)`; assistant-drafted + user-editable artifact per phase (per `contracts/authoring-surface.md`)
- [ ] T030 [US2] Hard-gate the handlers: `chrome_author_clarify` and `chrome_author_analyze` decline to advance with plain-language notices until resolved; `chrome_author_generate` reachable only after an Analyze pass

**Checkpoint**: non-experts produce constitution-compliant agents; Analyze failures never reach code-gen.

---

## Phase 6: User Story 4 - Author from any client except the watch (Priority: P2)

**Goal**: equivalent authoring + management on web, Windows, Android, Apple; watch excluded; non-host clients clearly show where the agent runs.

**Independent Test**: complete the journey on each supported client; watch shows no create affordance; a non-host client shows the "runs on your desktop host / offline when none online" state.

- [ ] T031 [P] [US4] Android author+manage parity: render the `agent_authoring` SDUI surface via the existing chrome path in `android-client`
- [ ] T032 [P] [US4] Apple parity: iOS author-only; macOS MAS build author-only via `components()` in `apple-clients`
- [ ] T033 [P] [US4] Web author+manage parity via `render()` HTML (webrender chrome shell)
- [ ] T034 [US4] Verify **watch exclusion**: no `agent_authoring` entry in watch channels/`menu_model`; add a guard test in `backend/tests/test_byo_watch_excluded.py`
- [ ] T035 [US4] FR-024 non-host messaging: "runs on your desktop host / offline when none online" (incl. "no desktop host connected") driven by `host_last_seen_at`, in `backend/webrender/chrome/surfaces/authoring.py`
- [ ] T036 [US4] macOS host gating (deferred): document that hosting requires the Developer-ID-signed, notarized **direct-download** build (bundled python-build-standalone); the sandboxed MAS build is author-only (feature-053 entitlements) — `apple-clients` + `docs/`

**Checkpoint**: consistent cross-client authoring; watch structurally excluded.

---

## Phase 7: User Story 5 - Manage my agents; my agent stays mine (Priority: P3)

**Goal**: list/revise/delete my agents; revisions re-validate before going live; private by construction; no share/publish surface.

**Independent Test**: list (owner-only); revise (must re-pass Analyze, prior version keeps running); delete (stops the host agent); confirm no share/publish control and cross-user invisibility.

### Tests for User Story 5

- [ ] T037 [P] [US5] Lifecycle test in `backend/tests/test_byo_lifecycle.py`: owner-only list, revise-requires-revalidation (prior keeps running), delete-stops-host-agent, no-share-surface, cross-user invisibility (SC-007)

### Implementation for User Story 5

- [ ] T038 [US5] List my agents with derived running/offline status on the `agent_authoring` surface in `backend/webrender/chrome/surfaces/authoring.py`
- [ ] T039 [US5] Revise: re-enter authoring at `specify`; re-pass Analyze; the prior live version keeps running until the revision registers (reuse `apply_revision` rollback semantics, host-side) — `backend/orchestrator/agent_authoring.py` + `agent_lifecycle.py`
- [ ] T040 [US5] Delete (**soft**, finding I1): stop the host agent, remove routing/visibility, set `status='disabled'` + `deleted_at` (retain the row + `audit_events` for the tamper-evident trail, Constitution VII) — `backend/orchestrator/agent_authoring.py` + `orchestrator.py` + `user_agents.py`
- [ ] T041 [US5] Constitution-version re-validation: the guarded migration sets `revalidation_required`; the tunnel/registration check refuses routing until re-Analyze passes (FR-028) — `backend/shared/database.py` + `orchestrator.py`
- [ ] T042 [US5] Confirm no share/publish/transfer path exists (surface has no control; `is_public CHECK=FALSE` enforced) — `authoring.py` + verify against `data-model.md`

**Checkpoint**: full private lifecycle; the public path remains a manual repo contribution only.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T043 [P] Update `CLAUDE.md` (Recent Changes + Active Technologies) for feature 057
- [ ] T044 [P] `docs/`: production enablement note for `FF_BYO_AGENTS` + desktop-host packaging (Windows client-supervised child process; macOS direct-download gating)
- [ ] T045 Full backend `pytest` (both invocations) + `ruff` + diff coverage-gate; smoke (healthz/readyz) with `FF_BYO_AGENTS` **on** and **off** (assert flag-off is byte-identical to today — FR-029)
- [ ] T046 [P] Audit completeness pass: confirm every user-agent action AND denial emits an audited row (`delegation`/`agent_tool_call` classes), including the boundary refusals

---

## Phase 9: Cresco edge-mesh transport (Mode 2 — DEFERRED, FR-032)

**Deferred**: implemented only when a broader cross-device/edge-compute mesh initiative is greenlit. Built against the T008 transport seam; owner-binding + delegation + boundary re-verification are unchanged.

- [ ] T047 [DEFERRED] Cresco Mode-2 transport adapter: route agent frames via a user/operator-run **external** Cresco fabric through the feature-050 Python `wsapi` bridge (reuse `backend/agents/cresco/` wsapi client posture); no JVM/broker in the product image; the desktop participates in the fabric. Gated on a Constitution-V decision if any client-bundled JVM is contemplated (per T000 posture (b)). References `specs/050-cresco-integration-decision/`.

---

## Dependencies & Execution Order

- **T000 (transport decision)** gates the US1 transport tasks (T008–T016) — resolve before implementing the tunnel; everything else can proceed.
- **Setup (T001–T002)** → **Foundational (T003–T006)** block everything.
- **US1 (T007–T017)** depends on Foundational (and T000 for its transport tasks). **This is the MVP** — stop here for a first demo.
- **US3 (T018–T023)** depends on US1's tunnel/registry; **must land before production enablement** (closes the live grant hole). T019 (grant-hole fix) is independently shippable and could be pulled forward as a standalone security fix.
- **US2 (T024–T030)** depends on Foundational (constitution loader) + US1 (delivery seam); replaces US1's minimal authoring with the full guided flow.
- **US4 (T031–T036)** depends on US2's `agent_authoring` surface existing.
- **US5 (T037–T042)** depends on US2 (authoring) + US1 (registry/host).
- **Polish (T043–T046)** last.

### Parallel opportunities

- Setup: T001 ‖ T002.
- Foundational: T004 ‖ T005 ‖ T006 (T003 first — schema).
- US1: T007 (test) alongside; T015/T016 (Windows host) ‖ backend T008–T014 (different codebases).
- US4: T031 ‖ T032 ‖ T033 (three client codebases).
- Tests T018, T024, T025, T037 are each `[P]` within their story.

## Implementation Strategy

- **MVP = US1 (Phase 3)**: create + run client-side + offline-on-close, safe on the existing gate stack. Demonstrable alone.
- **Gate to production = US3 (Phase 4)**: do not enable `FF_BYO_AGENTS` in production until the boundary hardening + adversarial suite pass (SC-003). T019 can ship independently now as a security fix.
- **Then US2 → US4 → US5** deepen authoring, spread across clients, and complete the lifecycle.
- Every phase is an independently testable increment; `FF_BYO_AGENTS` stays **off** until US1+US3 are green.

## Task summary

- **Total**: 49 tasks (T000–T047)
- **Transport decision**: 1 (T000) · **Setup**: 2 · **Foundational**: 4 · **US1**: 12 (incl. T013b) · **US3**: 6 · **US2**: 7 · **US4**: 6 · **US5**: 6 · **Cresco Mode 2 (deferred)**: 1 (T047) · **Polish**: 4
- **Tests**: T007, T017, T018, T024, T025, T034, T037 (security-critical + parity + lifecycle)
- **MVP scope**: US1 (T001–T017)
