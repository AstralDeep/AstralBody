---
description: "Task list for feature 058 — BYO client-side agents runtime, hosting & authoring UX"
---

# Tasks: BYO Client-Side Agents — Runtime, Hosting & Authoring UX

**Input**: `specs/058-byo-agents-runtime/spec.md` + the **057 design artifacts** (agent-constitution, contracts/, data-model, research) which this feature implements against.

**Depends on**: feature **057 merged** (registry schema, `FF_BYO_AGENTS`, agent constitution + loader, Analyze gate, `can_user_use_agent` isolation, grant-hole fix — all reused unchanged).

**Migrated from 057**: these are the transport/host/authoring-UX/lifecycle tasks 057 deferred because they need a live desktop client to build + verify. The 057 task ids are cited for traceability.

**Tests**: INCLUDED for the security-critical + integration paths (tunnel/offline, transport adversarial, lifecycle).

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Transport & owner-bound registration (US1 core — the linchpin)

- [X] T001 [US1] Direct-tunnel **transport seam** (was 057 T008, FR-001): unwrap an `agent_tunnel {frame}` envelope on the client's authenticated connection and feed `handle_agent_message` via a `.send`-shaped adapter (LoopbackSocket pattern), behind a small transport-adapter interface so Mode 2 slots in later — in `backend/orchestrator/orchestrator.py` (per 057 `contracts/agent-tunnel.md`)
- [X] T002 [US1] **Owner-binding** at `RegisterAgent` over an owner tunnel (was 057 T009, FR-002): resolve owner from the authenticated session `sub` (never the card); refuse unless `user_agent.owner_user_id == sub` AND `status ∈ {validated, live}` AND `revalidation_required == FALSE`; owner-scoped registry keyed `(owner_sub, agent_id)`; supersede a stale socket on reconnect — `orchestrator.py`; additive owner-auth field on `RegisterAgent` in `backend/shared/protocol.py`
- [ ] T003 [US1] **Owner-namespaced identity + collision refusal** (was 057 T023): refuse a `RegisterAgent` id that is reserved (`__*`), a built-in/public id, or another user's id; add owner-token binding alongside `AGENT_API_KEY` in `backend/orchestrator/auth.py`
- [ ] T004 [US1] Add the UI-facing `agent_offline` / `host_status` frame to `backend/shared/ui_protocol.json` + a liveness heartbeat so drops are caught within seconds (was 057 T012, SC-005)
- [X] T005 [US1] **Honest-offline** (was 057 T011, FR-003): on tunnel disconnect deregister `(owner_sub, agent_id)` + emit `agent_offline`; short-circuit dispatch of an offline user agent to a prompt honest-offline `MCPResponse` (replace the `agent_urls` reconnect fallback for user agents) — `orchestrator.py`
- [ ] T006 [US1] **Code-delivery seam** (was 057 T013, FR-004): after `generate_code`, package the 3-file bundle and push `agent_bundle_deliver` over the owner tunnel; do NOT call `start_draft_agent` (Popen) for byo agents; on inward register call `user_agents.go_live` (status='live', stamp constitution_version, insert agent_ownership row) — `backend/orchestrator/agent_lifecycle.py` + `agentic_creation.py`
- [ ] T007 [US1] **Self-test relocation** (was 057 T013b, G1/SC-002): any pre-delivery self-test is ephemeral/torn-down orchestrator sandbox OR host-side with the result reported back — never a persistent server-side agent — `backend/orchestrator/agent_lifecycle.py`
- [ ] T008 [US1] **Codegen target** (was 057 T016): generated bundle is self-contained for the desktop-host runtime (not the backend `shared` package) OR the host ships a compatible shim — `backend/orchestrator/agent_generator.py` + `windows-client`
- [ ] T009 [US1] **Minimal one-shot authoring path** (was 057 T014): deliberate entry, `origin='byo_client'`, `create_draft` → existing static gates → `generate_code` → deliver; register the `user_agent` row + stamp `AGENT_CONSTITUTION_VERSION` + mark validated (full 5-phase is Phase 4) — `agentic_creation.py`
- [ ] T010 [P] [US1] Integration test (was 057 T007, U1): owner-tunnel register → dispatch through the existing gate stack → **assert the audit row attributes the action to the owning human** → disconnect → honest-offline — `backend/tests/test_byo_tunnel.py`
- [ ] T011 [US1] SC-002 guard/test: assert **zero user-agent processes on the orchestrator host** after go-live — `backend/tests/test_byo_offserver.py`

## Phase 2: Windows desktop host runtime (US1 client)

- [ ] T012 [US1] **Windows host** (was 057 T015, C1/FR-003): write + run a delivered bundle as a **separate, client-supervised child process** (re-invoke `sys.executable`/frozen exe with a worker-entry flag — NOT in-process); relay frames through the client's authenticated tunnel; supervise lifecycle + stop on client close — `windows-client/win_agent/` (+ `astral_client/app.py`). **Requires live-client integration testing.**

## Phase 3: Boundary hardening completion (US3)

- [ ] T013 [US3] **Per-owner ingress bound** (was 057 T021, FR-017/SC-008): rate + in-flight-frame cap on user-agent tunnels (extend `concurrency_cap`/`ChainBudget`), scoped to external user-agent sockets only — `orchestrator.py`
- [ ] T014 [US3] **No secrets to untrusted agents** (was 057 T022): do not attach `_delegation_token` bytes / per-user secrets on the direct dispatch path for user-hosted agents (mirror the 054 in-process-only rule) — `orchestrator.py`
- [ ] T015 [P] [US3] **Transport adversarial suite** (was 057 T018 remainder): forged identity/token over the tunnel, undeclared-tool, flood, offline — each denied fail-closed + audited — extend `backend/tests/test_byo_boundary_adversarial.py`

## Phase 4: Guided authoring UX (US2)

- [ ] T016 [US2] Wire the 057 Analyze gate **pre-generation** (was 057 T027, FR-003): call `agent_analyze.check` immediately before `generate_code`; on fail do not generate + do not advance; re-run on revision + revalidation — `agentic_creation.py`
- [ ] T017 [US2] 5-phase authoring state machine over `draft_agents` (was 057 T028) — `backend/orchestrator/agent_authoring.py`
- [ ] T018 [US2] `agent_authoring` chrome surface (was 057 T029, FR-005): `backend/webrender/chrome/surfaces/authoring.py` exporting BOTH `render()` (web) and `components()` (native); register in `surfaces/__init__.py`; `chrome_author_*` phase handlers; assistant-drafted + editable artifacts (per 057 `contracts/authoring-surface.md`)
- [ ] T019 [US2] Hard-gate handlers (was 057 T030): `chrome_author_clarify` + `chrome_author_analyze` decline to advance with plain-language notices; `chrome_author_generate` reachable only post-Analyze-pass

## Phase 5: Cross-client parity (US4)

- [ ] T020 [P] [US4] Android author+manage parity via the SDUI chrome path (was 057 T031) — `android-client`
- [ ] T021 [P] [US4] Apple parity: iOS author-only; macOS MAS build author-only (was 057 T032) — `apple-clients`
- [ ] T022 [P] [US4] Web author+manage parity via `render()` HTML (was 057 T033)
- [ ] T023 [US4] Verify **watch exclusion** (was 057 T034) + guard test — `backend/tests/test_byo_watch_excluded.py`
- [ ] T024 [US4] FR-024 non-host messaging: "runs on your desktop host / offline when none online" driven by `host_last_seen_at` (was 057 T035) — `authoring.py`
- [ ] T025 [US4] macOS host gating docs (was 057 T036): direct-download build hosts; MAS build author-only — `apple-clients` + `docs/`

## Phase 6: Lifecycle (US5)

- [ ] T026 [US5] List my agents with derived running/offline status on the `agent_authoring` surface (was 057 T038) — `authoring.py`
- [ ] T027 [US5] Revise: re-enter authoring; re-pass Analyze; prior live version keeps running until the revision registers (host-side rollback) (was 057 T039) — `agent_authoring.py` + `agent_lifecycle.py`
- [ ] T028 [US5] Delete (soft): stop the host agent, remove routing/visibility, `user_agents.soft_delete` (retain row + audit) (was 057 T040) — `agent_authoring.py` + `orchestrator.py`
- [ ] T029 [US5] Constitution-version re-validation flow: the 057 guarded migration sets `revalidation_required`; the tunnel/registration check refuses routing until re-Analyze passes (was 057 T041, FR-028)
- [ ] T030 [US5] Confirm no share/publish/transfer path (was 057 T042) — `authoring.py`
- [ ] T031 [P] [US5] Lifecycle test (was 057 T037): owner-only list, revise-requires-revalidation, delete-stops-host, no-share, cross-user invisibility — `backend/tests/test_byo_lifecycle.py`

## Phase 7: Polish

- [ ] T032 [P] Update `CLAUDE.md` (Recent Changes + Active Technologies) for the completed 057+058 feature
- [ ] T033 [P] `docs/`: production enablement note for `FF_BYO_AGENTS` + desktop-host packaging (Windows child process; macOS direct-download gating)
- [ ] T034 Full backend `pytest` + `ruff` + diff coverage-gate; smoke with `FF_BYO_AGENTS` on and off (flag-off byte-identical)
- [ ] T035 [P] Audit completeness: every user-agent action + denial emits an audited row

## Phase 8: Cresco Mode-2 transport (DEFERRED)

- [ ] T036 [DEFERRED] Cresco Mode-2 adapter (was 057 T047, FR-010): route frames via a user/operator-run **external** Cresco fabric through the feature-050 `wsapi` bridge; no JVM/broker in the product image; gated on a Constitution-V decision if any client-bundled JVM is contemplated. References `specs/050-cresco-integration-decision/`.

## Dependencies & MVP

- **Phase 1 (transport core)** is the linchpin — everything else depends on an agent actually connecting inward and running. **MVP = Phase 1 + Phase 2** (a user creates + runs an agent on Windows).
- Phase 3 (hardening) must land before production enablement.
- Phases 4–6 build on the transport; Phase 7 last; Phase 8 deferred.
- **Note:** Phase 1 T001/T002/T005/T006 (orchestrator connection surgery) and Phase 2 T012 (Windows host) require **live-client integration testing** — a running Windows client dialing in — which is the practical reason 057 deferred them here.
