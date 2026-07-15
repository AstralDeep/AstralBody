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
- [X] T003 [US1] **Owner-namespaced identity + collision refusal** (was 057 T023): refuse a `RegisterAgent` id that is reserved (`__*`), a built-in/public id, or another user's id; add owner-token binding alongside `AGENT_API_KEY` in `backend/orchestrator/auth.py`
- [X] T004 [US1] Add the UI-facing `agent_offline` / `host_status` frame to `backend/shared/ui_protocol.json` + a liveness heartbeat so drops are caught within seconds (was 057 T012, SC-005)
- [X] T005 [US1] **Honest-offline** (was 057 T011, FR-003): on tunnel disconnect deregister `(owner_sub, agent_id)` + emit `agent_offline`; short-circuit dispatch of an offline user agent to a prompt honest-offline `MCPResponse` (replace the `agent_urls` reconnect fallback for user agents) — `orchestrator.py`
- [X] T006 [US1] **Code-delivery seam** (was 057 T013, FR-004): after `generate_code`, package the 3-file bundle and push `agent_bundle_deliver` over the owner tunnel; do NOT call `start_draft_agent` (Popen) for byo agents; on inward register call `user_agents.go_live` (status='live', stamp constitution_version, insert agent_ownership row) — `backend/orchestrator/agent_lifecycle.py` + `agentic_creation.py`
- [X] T007 [US1] **Self-test relocation** (was 057 T013b, G1/SC-002): BYO validation is now **pure-AST static** (`agent_validator.validate_static` — registry shape + return-format + stdlib∪astralprims import allowlist; NEVER imports/exec/compiles the code). The exec-in-a-child path (`validator_worker.py`) is **deleted**; runtime behavior is the desktop host's business. Sandbox decision keys off the draft `origin`, not the caller's `target`. Empirically re-verified: the prior file-write+socket exploit runs zero code — `backend/orchestrator/agent_validator.py`, `agent_lifecycle.py`
- [X] T008 [US1] **Codegen target** (was 057 T016): `AgentCodeGenerator.generate_byo_files` emits a **self-contained** bundle (`agent_main.py` deterministic JSON-lines-over-stdio runner + `manifest.json`; LLM `mcp_tools.py` imports only astralprims). `byo_import_violations` gate refuses `shared`/`agents.`/`sys.path.insert`; prompt & gate reconciled (BYO required-imports block carries no shim). Owner-namespaced `agent_id` baked in. **Proven via real subprocess smoke test** — `backend/orchestrator/agent_generator.py`, `agent_spec.py` + `windows-client/win_agent/byo_worker.py`
- [X] T009 [US1] **Minimal one-shot authoring path** (was 057 T014): deliberate entry, `origin='byo_client'`, `create_draft` → existing static gates → `generate_code` → deliver; register the `user_agent` row + stamp `AGENT_CONSTITUTION_VERSION` + mark validated (full 5-phase is Phase 4) — `agentic_creation.py`
- [X] T010 [P] [US1] Integration test (was 057 T007, U1): owner-tunnel register → dispatch through the existing gate stack → **assert the audit row attributes the action to the owning human** → disconnect → honest-offline — `backend/tests/test_byo_tunnel.py`
- [X] T011 [US1] SC-002 guard/test: assert **zero user-agent processes on the orchestrator host** after go-live — boot-relaunch query gained `AND (origin IS NULL OR origin <> 'byo_client')`, `start_draft_agent` **raises** on a byo draft (structural), and the origin is stamped before generate — `backend/tests/test_byo_offserver.py`

## Phase 2: Windows desktop host runtime (US1 client)

- [X] T012 [US1] **Windows host** (was 057 T015, C1/FR-003): `win_agent/byo_host.py` (supervisor: writes bundle → Popen child → pumps child stdout→`agent_tunnel`, inbound tunnel→child stdin; rehydrate-on-connect; re-register on reconnect; terminate on close/sign-out/`agent_stop`; registration-timeout reap; realpath traversal guard) + `win_agent/byo_worker.py` (`--byo-worker` re-invoke BEFORE Qt; frozen-build no-stdout rebind) + `astral_client/app.py` wiring + `main.py` branch + `astralprims` added to `requirements.txt`/`AstralDeep.spec`. **Seam proven via real subprocess smoke test** (register→tools/list→tools/call→real astralprims Card→−32601/−32603→exit 0). **Live author→deliver→run→offline E2E pending user sign-in.**

## Phase 3: Boundary hardening completion (US3)

- [X] T013 [US3] **Per-owner ingress bound** (was 057 T021, FR-017/SC-008): rate + in-flight-frame cap on user-agent tunnels (extend `concurrency_cap`/`ChainBudget`), scoped to external user-agent sockets only — `orchestrator.py`
- [X] T014 [US3] **No secrets to untrusted agents** (was 057 T022): do not attach `_delegation_token` bytes / per-user secrets on the direct dispatch path for user-hosted agents (mirror the 054 in-process-only rule) — `orchestrator.py`
- [X] T015 [P] [US3] **Transport adversarial suite** (was 057 T018 remainder): `backend/tests/test_byo_transport_adversarial.py` — undeclared-tool (non-owner denied fail-closed; get_tool_scope never inherits a declared scope), forged identity in the register frame (another user's id / built-in id / reserved `__*` all refused by `authorize_registration`), pre-validation + revalidation-required status gates. Flood/offline already in `test_byo_tunnel.py`; denial-audit now covered by T035.

## Phase 4: Guided authoring UX (US2)

- [X] T016 [US2] Wire the 057 Analyze gate **pre-generation** (was 057 T027, FR-003): call `agent_analyze.check` immediately before `generate_code`; on fail do not generate + do not advance; re-run on revision + revalidation — `agentic_creation.py`
- [X] T017 [US2] 5-phase authoring state machine over `draft_agents` (was 057 T028): Specify→Clarify→Plan→Tasks→Analyze→generate, assistant-drafted (user's LLM) + human-editable, explicit advance, Analyze-approved tool list persisted to `tools_spec` and enforced as a superset gate on the generated `TOOL_REGISTRY` — `backend/orchestrator/agent_authoring.py`
- [X] T018 [US2] `agent_authoring` chrome surface (was 057 T029, FR-005): `backend/webrender/chrome/surfaces/authoring.py` exports BOTH `render()` (web) and `components()` (native, feature-043 shape); registered in `surfaces/__init__.py`; `chrome_author_*` handlers; "My agents" menu item (flag-gated); every entry point re-checks `byo_enabled()` (FR-009). **Native-client live render pending (T020–T022).**
- [X] T019 [US2] Hard-gate handlers (was 057 T030): clarify won't advance with unresolved questions; `chrome_author_analyze` runs `agent_analyze.check` and blocks generate on fail; generate is **structurally** unreachable pre-Analyze-pass; re-run on revision/revalidation

## Phase 5: Cross-client parity (US4)

- [X] T020 [P] [US4] Android author+manage parity via the SDUI chrome path (was 057 T031) — **PROVEN LIVE 2026-07-15** on the Android emulator (Mac): the full 5-phase flow (Specify→Clarify→Plan→Tasks→Analyze→Generate) rendered natively via the 043 SDUI chrome path — every component type (text/alert/card/button/badge/param_picker) drew with **zero `[type]` placeholders**; the Clarify **hard gate** refused a blank advance (behavioral, cited the count + first question), the Analyze **structural gate** withheld Generate until pass, and Generate on a phone produced the honest **`no_host`** message. (Env quirk: the emulator's stylus-handwriting hijacks text fields — `settings put secure stylus_handwriting_enabled 0`.) — `android-client`
- [ ] T021 [P] [US4] Apple parity: iOS author-only; macOS MAS build author-only (was 057 T032) — **PARTIAL 2026-07-15**: AstralApp **builds** for the iOS sim + runs signed-in, top-bar order matches web/Android; the authoring-surface **render is NOT yet verified** — the iOS Simulator's Metal content is opaque to macOS accessibility and takes no synthetic taps (no `idb`; `cliclick` events don't register), so it needs a couple of human taps (gear → "My agents"). — `apple-clients`
- [X] T022 [P] [US4] Web author+manage parity via `render()` HTML (was 057 T033) — **PROVEN LIVE 2026-07-14**: the full 5-phase author + generate + manage flow was driven end-to-end in the web client (Settings → "My agents"), delivering to a Windows host.
- [X] T023 [US4] Verify **watch exclusion** (was 057 T034) + guard test — `backend/tests/test_byo_watch_excluded.py`: "My agents" is the single flag-gated authoring affordance in `menu_model`; `watch` is absent from `chrome_events._NATIVE_SDUI_DEVICE_TYPES` (the device list that gates chrome-menu delivery + surface render), keeping the surface off the wrist (FR-023). Host-marking has no server-side device gate (watch host exclusion is client-side — no host UI on the wrist); noted in the test.
- [X] T024 [US4] FR-024 non-host messaging: delivery now targets **host-capable sockets only** (`_agent_host_sockets`; additive `RegisterUI.agent_host`/`host_session_id` + mark-by-demonstration) — a browser tab never receives a code bundle; the `no_host` branch tells the truth ("open your desktop client and re-run Generate") — `orchestrator.py`, `authoring.py`
- [X] T025 [US4] macOS host gating docs (was 057 T036): direct-download build hosts; MAS build author-only — `apple-clients` + `docs/` (docs/byo-client-agents.md §"macOS host gating" + a pointer in apple-clients/README.md; docs-only, no Swift touched)

## Phase 6: Lifecycle (US5)

- [X] T026 [US5] List my agents with derived running/offline status on the `agent_authoring` surface (was 057 T038) — `authoring.py`
- [X] T027 [US5] Revise: re-enter authoring; re-pass Analyze; prior live version keeps running until the revision registers (host-side rollback) (was 057 T039). Server half was already in place (`agent_authoring.revise` keeps the same `agent_id`, deliberately does NOT flip `revalidation_required`). **Host half implemented + tested 2026-07-15** (`windows-client/win_agent/byo_host.py`): the old **stop-then-start** `deliver()` is replaced by **staging + swap-on-ack** — a revision stages under `<agent_id>.pending` and runs alongside the live child; promote (swap the on-disk dir, retire the old child) only on the revised child's `agent_registered` ack; on timeout/crash reap the pending child + keep the running version. Pending-aware teardown (stop_all/remove/rehydrate). **4 new tests; 41 byo_host + 421 windows-client green, ruff clean** (commit `a96846a`). NOT live-verified on a running host (no macOS host, no Windows machine this session) → see feature **059**. — `windows-client/win_agent/byo_host.py`
- [X] T028 [US5] Delete (soft): stop the host agent, remove routing/visibility, `user_agents.soft_delete` (retain row + audit) (was 057 T040) — `agent_authoring.py` + `orchestrator.py`
- [X] T029 [US5] Constitution-version re-validation flow: the 057 guarded migration sets `revalidation_required`; the tunnel/registration check refuses routing until re-Analyze passes (was 057 T041, FR-028)
- [X] T030 [US5] Confirm no share/publish/transfer path (was 057 T042) — `authoring.py`
- [X] T031 [P] [US5] Lifecycle test (was 057 T037): owner-only list, revise-requires-revalidation, delete-stops-host, no-share, cross-user invisibility — `backend/tests/test_byo_lifecycle.py`

## Phase 7: Polish

- [X] T032 [P] Update `CLAUDE.md` (Recent Changes + Active Technologies) for the completed 057+058 feature — added a 057+058 Recent-Changes entry (top of the list) + two Active-Technologies lines (tech + schema); caveats honest (Android/Apple parity + host-side revise rollback not live-verified, Cresco Mode-2 deferred)
- [X] T033 [P] `docs/`: production enablement note for `FF_BYO_AGENTS` + desktop-host packaging (Windows child process; macOS direct-download gating) — new docs/byo-client-agents.md (enable flow, security posture, Windows packaging, macOS host gating, flag-off guarantee, known limitations); linked from docs/production-deployment.md (companion-docs index + a short BYO section)
- [ ] T034 Full backend `pytest` + `ruff` + diff coverage-gate; smoke with `FF_BYO_AGENTS` on and off (flag-off byte-identical)
- [X] T035 [P] Audit completeness: every user-agent action + denial emits an audited row — `orchestrator._audit_user_agent` (event_class `agent_lifecycle`, attributed to the owning human) wired at go_live, `deliver_agent_bundle`, `delete_user_agent`, refused `authorize_registration`, and the user-agent-scoped `GateRefusal` denial path; tool dispatch keeps its `agent_tool_call` pair. `backend/tests/test_byo_audit_completeness.py` (6 real guards, formerly xfail gaps).

## Phase 8: Cresco Mode-2 transport (DEFERRED)

- [ ] T036 [DEFERRED] Cresco Mode-2 adapter (was 057 T047, FR-010): route frames via a user/operator-run **external** Cresco fabric through the feature-050 `wsapi` bridge; no JVM/broker in the product image; gated on a Constitution-V decision if any client-bundled JVM is contemplated. References `specs/050-cresco-integration-decision/`.

## Dependencies & MVP

- **Phase 1 (transport core)** is the linchpin — everything else depends on an agent actually connecting inward and running. **MVP = Phase 1 + Phase 2** (a user creates + runs an agent on Windows).
- Phase 3 (hardening) must land before production enablement.
- Phases 4–6 build on the transport; Phase 7 last; Phase 8 deferred.
- **Note:** Phase 1 T001/T002/T005/T006 (orchestrator connection surgery) and Phase 2 T012 (Windows host) require **live-client integration testing** — a running Windows client dialing in — which is the practical reason 057 deferred them here.

## Session 2026-07-14 (Windows-machine resume) — status

**MVP (Phase 1 + Phase 2) is code-complete and the T008↔T012 seam is proven** via a real
subprocess smoke test (generate BYO bundle → run `byo_worker` as a child → register→tools/list→
tools/call→real astralprims Card→−32601/−32603→exit 0). Remaining before "shipped": the **live
author→deliver→run→offline E2E on a signed-in Windows client** (interactive; needs the user's LLM),
and the native authoring-surface **render parity passes T020 (Android)/T021 (Apple)/T022 (web)**.

Also landed this session (found + fixed 4 blockers via adversarial review, all re-verified "ship"):
the empty-bundle + agent_id-mismatch defects, the prompt-vs-gate contradiction, unpersisted
Analyze-approved tools, and (the deep one, proven empirically) BYO tool code executing unsandboxed
in the orchestrator — now eradicated (static AST validation, exec path deleted).

Out-of-band client fixes (separate user requests, not 058 tasks): **Android LLM-provider dropdown**
(`param_picker` `select`+`checklist` branches — the field was already `kind:"select"` on the wire;
Android was the sole under-renderer) + the 4 BYO frames classified IGNORED in Android's
`ProtocolManifest` drift guard; **Windows top-bar order parity** (Constitution XII — actions cluster
moved after New/Recent; Recent-chats clock→speech-bubble); **Windows app icon** regenerated from the
brand master (was off-brand white bg); **LLM first-run dialog** now names the signed-in account
("saved to your account, applies to all devices") — the "creds didn't sync" report was two different
Keycloak logins, not a bug.

- [X] **T012-live** [US1] Live E2E on a signed-in Windows host — **PROVEN 2026-07-14** (web-authored):
  author → 5-phase + Analyze gate → generate (owner's GLM-5.2) → static-validate → **delivered to 1
  desktop host socket** → child process Popen'd (`--byo-worker`) → registered inward over the tunnel →
  passed boundary security re-review → **invoked from chat** (`generate_greeting_card → ua-greeter-58e0d4ff`,
  agent_eval pass^1=1.000) → astralprims Card rendered in the workspace; "My agents" shows running/live.
  Surfaced + fixed 3 seam bugs no unit test caught: client didn't declare `agent_host` at register_ui;
  BYO codegen used the unset system LLM instead of the owner's; the owner couldn't use the tool they
  authored (permission baseline). (offline-on-close still to observe.)
- [ ] **T034-partial** full-suite smoke with `FF_BYO_AGENTS` on AND off (flag-off byte-identical).

## Session 2026-07-15 (Mac resume) — status

Picked up on the Mac. **T020 (Android render parity) PROVEN LIVE** on the emulator — the full
5-phase authoring flow renders natively with zero `[type]` placeholders, both gates behave
(Clarify hard-gate + Analyze structural), and Generate on a phone gives the honest `no_host`
message (detail on T020 above). **T027 host-side rollover implemented + tested** (staging +
swap-on-ack; a failed revision keeps the running agent; 41 byo_host + 421 windows-client green —
commit `a96846a`).

**T021 (Apple) — partial:** AstralApp builds for the iOS sim (incl. the iOS chat keyboard fix —
auto-dismiss on send + a Done accessory bar, commit `8658650`), runs signed-in, top-bar order
matches web/Android; the authoring-surface **render is not yet verified** (the iOS Simulator's
Metal content is opaque to macOS accessibility and takes no synthetic taps — needs a couple of
human taps: gear → "My agents").

**macOS agent host** does not exist (apple-clients is author-only; the App Sandbox forbids child
processes), so live revise/offline-on-close can't be exercised on a Mac without building one.
Specced as new feature **059** (`specs/059-macos-agent-host/`, specify step only).

Also committed: android gradle sync (`ca3ff53`). Remaining 058 opens: **T021** (Apple authoring
render), **T034** (flag on/off smoke), offline-on-close live-observe.
