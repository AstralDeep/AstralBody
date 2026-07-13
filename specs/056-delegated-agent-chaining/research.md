# Phase 0 Research: Delegated Agent Chaining

**Feature**: 056-delegated-agent-chaining | **Date**: 2026-07-13

Evidence base: the 2026-07-13 multi-agent code audit cited by the spec's "Why
now" section (dispatch control-flow trace, 048 implementation-maturity audit,
machine-turn authority probe), re-verified against the current tree for this
plan. Every claim below carries a file:line anchor confirmed in
`056-delegated-agent-chaining`'s worktree. This feature **wires existing tested
machinery** — feature 048 merged the recursive-delegation mechanism with zero
production call sites (`delegation.py:400-668`, gated by
`FF_RECURSIVE_DELEGATION`, default off, `feature_flags.py:107`) and deferred its
own wiring (T014) and two-hop audit-reconstruction evidence (T018) to
"flag-on integration". This spec is that integration. Each decision lists
alternatives considered; where the spec is silent, the conservative fail-closed
choice is recorded with rationale.

---

## D1 — Both chaining seams route through the single-path gate stack; the mediation point is the only hop authority

**Decision**: Agent-to-agent hops are minted, verified, and dispatched **only**
at the orchestrator. The two in-scope seams — (a) the deterministic
agent-runtime callback and (b) LLM-planned nested sub-turns — both converge on
**`Orchestrator.execute_single_tool`** (`orchestrator.py:5706`), the one dispatch
path that runs the complete gate stack. No hop is ever dispatched by an agent
directly, and no hop reuses the parent's token: each mints a fresh child
authority at the mediation point (D2). A hop request from an agent arrives as an
in-process control frame that the orchestrator resolves to `(callee_agent_id,
tool_name, args, parent_token)` and then feeds through the same
`execute_single_tool` entry a chat-loop tool call uses.

**Rationale** (verified):
- `execute_single_tool` is the only path that applies, in order: system security
  block (`orchestrator.py:5779-5790`), per-user permission
  (`5792-5802` → `tool_permissions.is_tool_allowed`, `tool_permissions.py:272`),
  the deterministic policy engine (`5804-5853`), the taint/data-flow sink gate
  (`5855-5875`), the intent-alignment supervisor + HITL (`5877-5910`), file-path
  mapping (`5912-5918`), per-(user, callee) credential injection
  (`5920-5925`), the RFC 8693 delegation-token mint with fail-closed production
  posture (`5977-6007`), the PRE_TOOL_USE hook (`6009-6024`), and the
  concurrency cap (`6026-6062`), all wrapped in paired `ToolDispatchAudit`
  start/end records (`6064-6089`). Re-entering this function is how a hop
  provably gets "the same gates as if the user had invoked that tool directly"
  (FR-003, US1-AS4).
- The orchestrator already owns DPoP key custody and is both minter and verifier
  of delegation tokens (`delegation.py:59-65` generates the EC key;
  `_get_delegation_token`, `orchestrator.py:6798`, mints; there is no separate
  per-agent key), so "hops stay orchestrator-mediated / possession-proof binding
  remains with the orchestrator's key custody" (FR-004) is satisfied by keeping
  minting at the same site.
- The in-process loopback substrate already routes agent frames back to the
  orchestrator (`shared/local_transport.py::LoopbackSocket.send_text` →
  `handle_agent_message`, `orchestrator.py:1067`), so an "in-process hop" has no
  network transport at which to present a token — verification runs as the same
  authority check at the mediation point with identical audit output (spec edge
  case "In-process hops").

**Alternatives considered**:
- *Let agents call peers directly over A2A/WebSocket, forwarding the delegation
  token* — this is exactly the dormant `BaseA2AAgent.call_peer_tool`
  (`base_agent.py:682-719`) and `_call_peer_via_ws`/`_call_peer_via_a2a`
  (`base_agent.py:726-841`), which forward `delegation_token` **unattenuated**
  as `params._delegation_token` / `Authorization: Bearer` (`base_agent.py:756`,
  `812-813`). Rejected as a confused-deputy seam and retired (D12): it bypasses
  the orchestrator's gate stack entirely and cannot mint a narrower child.
- *A separate lightweight hop dispatcher that re-implements a subset of gates* —
  rejected: any second dispatch path that is "cheaper" than the single path is
  precisely the weakest-path amplification the spec forbids (US3); the parallel
  path is already such a gap (D5), and we are closing it, not adding another.

## D2 — Child authority = `mint_child_delegation` at dispatch, verified per call by `authorize_chained_tool_call`

**Decision**: When `execute_single_tool` dispatches a call that carries a parent
delegation token (a hop), it mints the child with the already-tested
`delegation.mint_child_delegation(parent, callee_agent_id, requested_scopes)`
(`delegation.py:515-567`) instead of the flat single-hop
`exchange_token_for_agent`. Before execution it re-derives authority with
`delegation.authorize_chained_tool_call(child, tool_name, required_scope)`
(`delegation.py:621-639`), which internally runs `verify_delegation_chain`
(`delegation.py:570-618`) + `is_tool_in_scope` (`delegation.py:370-397`). The
child is injected as `args["_delegation_token"]` exactly as the flat token is
today (`orchestrator.py:5982`), so the downstream `_execute_in_process` /
`_execute_via_a2a` credential-forwarding path is unchanged
(`orchestrator.py:6729-6731`).

**Rationale** (verified): `mint_child_delegation` already enforces every 048
invariant the spec's FR-002 restates — scopes = `attenuate_scopes(parent,
requested)` intersection (`delegation.py:543`, `452-462`); `aud`/`iss` inherited
never widened (`556-557`); `exp` capped at parent (`552`, `560`); depth =
parent+1 with `DelegationDepthExceeded` past the bound
(`533-541`, default `DEFAULT_MAX_DELEGATION_DEPTH = 3`, `delegation.py:416`);
nested `act` chain terminating at the human `sub` (`547-554`); DPoP `cnf` carried
(`565-566`). `verify_delegation_chain` enforces them again at use, fail-closed,
per call, without a socket teardown (`delegation.py:632-639` returns `(ok,
reason)`; the caller refuses the hop and keeps the session). This is the
"mid-session re-derivation over the persistent transport" 048 built for but never
called (048 tasks T014/T018 deferred).

**Alternatives considered**:
- *Mint the child inside the agent runtime and present it to the orchestrator* —
  rejected: violates D1 (agent would hold a mint capability) and FR-001 ("never
  ambient authority"); the runtime carries only a request, never a token.
- *Skip re-verification because the orchestrator just minted the token it is
  about to check* — rejected: FR-004 and US1-AS5 require every hop to pass
  verification and emit the paired provenance record; re-verifying is cheap
  (pure function, no round trip) and closes the tamper surface if a future seam
  ever accepts an externally-presented child.

## D3 — Empty scope intersection refuses the hop, fail-closed and audited (resolves 048's open policy)

**Decision**: A hop whose `attenuate_scopes(parent, requested)` yields the empty
set is **refused**, not silently narrowed to a do-nothing token. The refusal is
audited with the requested-vs-granted scopes recorded, and the parent task
receives an honest per-call error. `mint_child_delegation` will still produce an
empty-scope child structurally; the orchestrator wrapper checks the resulting
scope set and, when empty AND the requested set was non-empty, refuses before
dispatch.

**Rationale**: The spec resolves 048's stated open question ("mint yields an
empty-scope token OR refuses per stated policy", `048/spec.md:110`,
`FR-004`) explicitly toward **refuse + audit** (spec FR-005, Edge Cases "Empty
scope intersection"). Fail-closed matches the repo posture and avoids a silent
"the hop ran but could do nothing" outcome that reads as success. Recording the
requested and granted scope sets closes 048's FR-004 audit gap
(`048/spec.md:125`).

**Alternatives considered**:
- *Silently narrow to the empty token and let the callee no-op* — rejected by the
  spec's own resolution; also produces an unattributable "why did nothing
  happen" failure.
- *Refuse the whole turn* — rejected: FR-028 mandates per-call, never
  session-terminating refusals; the parent must be able to work around a denied
  hop (US1-AS2).

## D4 — Agent-runtime callback seam: `AgentRuntime.call_agent_tool` returns a request the orchestrator mediates

**Decision**: Extend `AgentRuntime` (`shared/agent_runtime.py:26`, today only
`start_long_running_job`, `agent_runtime.py:45`) with an awaitable
`call_agent_tool(callee_agent_id, tool_name, arguments)` that does **not** talk
to any peer. It schedules a mediated hop onto the orchestrator via the same
loopback the agent already uses for frames, correlates a response future
(mirroring `pending_requests`, `orchestrator.py:1075-1078`), and returns the
`MCPResponse` (or an honest error). The orchestrator resolves it by calling
`execute_single_tool` for `(callee_agent_id, tool_name, arguments)` under the
child mint (D2), threading the initiating agent's parent token as the parent
authority.

**Rationale** (verified): The runtime is constructed once per MCP request inside
`BaseA2AAgent.handle_mcp_request` (`base_agent.py:319-326`) with `ws`, `msg`,
`agent_id`, and `loop` — everything needed to route a control frame back and to
await a future on the agent's loop, exactly as `start_long_running_job` already
does (`agent_runtime.py:64-76` via `asyncio.run_coroutine_threadsafe`). The
LoopbackSocket path already round-trips agent frames to
`handle_agent_message` and resolves request-id↔future correlation
(`local_transport.py:38-45`, `orchestrator.py:1075-1078`), so an in-process
built-in can initiate a hop with no new transport. External (networked) agents
initiate the same hop over their existing WS control channel (a new mediated
frame type, contracts/wire-contract.md), never a peer connection.

**Alternatives considered**:
- *Reuse `call_peer_tool`'s signature but route it through the orchestrator* —
  rejected: `call_peer_tool` is being retired (D12); its peer-registry /
  peer-connection machinery (`base_agent.py:653-679`) is the direct-transport
  path this feature removes.
- *A synchronous in-agent helper that imports the orchestrator* — rejected:
  agents must not hold an orchestrator reference (trust-boundary inversion);
  the runtime already provides the sanctioned event-loop bridge.

## D5 — Dispatch-path parity (US3): factor the single-path gate stack into a shared authorizer both paths call

**Decision** (prerequisite hardening, lands with/before US1 flag-on): extract the
gate sequence from `execute_single_tool` into a shared
`_authorize_and_prepare(...)` that returns either a prepared `(agent_id, args,
cap_job_id, delegation_token)` tuple or a refusal `MCPResponse`. Both
`execute_single_tool` (`orchestrator.py:5706`) and `execute_parallel_tools`
(`orchestrator.py:6209`) call it, so a violating call is refused identically on
either path with equivalent audit evidence, and a chained hop (D1) — which
re-enters `execute_single_tool` — inherits it for free. A shared gate-contract
test drives the same violating call down single / parallel / chained and asserts
identical refusals (FR-017, SC-006).

**Rationale** (verified — this is the load-bearing finding): the parallel path's
prepare loop (`orchestrator.py:6220-6304`) applies only credential injection
(`6269-6273`), the system security block (`6276-6285`), the permission check
(`6288-6296`), and the no-agent check (`6298-6302`). It **skips** the policy
engine, the taint sink gate, the supervisor + HITL gates, the RFC 8693
delegation-token mint, the concurrency cap, and the PRE_TOOL_USE hook that
`execute_single_tool` applies at `5804-6062`. Most consequentially, a
production-posture parallel batch dispatches with **no delegation token at all**
— the fail-closed `_delegation_required` refusal (`orchestrator.py:5983-6007`,
`6783-6796`) never runs on the parallel path — so parallel tool calls proceed
UNSCOPED where the single path would refuse. Feature 040 already routed the
parallel path through `_execute_with_retry_audited` for audit parity
(`orchestrator.py:6176-6207`, `6322`/`6351`), establishing the precedent that
the two paths must converge; this decision completes it for the enforcement
gates. The parallel path also handles only the `__orchestrator__` meta-tool
(`6261-6267`) while the single path handles `__orchestrator__`, `__scheduler__`,
`__memory__`, and `__desktop_codegen__` (`5753-5777`) — the shared authorizer
resolves that asymmetry too (FR-018).

**Alternatives considered**:
- *Duplicate the missing gates inline into the parallel loop* — rejected: two
  copies drift (the current gap is exactly that drift); a shared function is the
  only way a single gate-contract test can prove parity.
- *Route the parallel path through `execute_single_tool` per call* — rejected:
  `execute_single_tool` renders errors/alerts and does per-call UI side effects
  tuned for one-at-a-time delivery; the parallel path batches error rendering
  (`orchestrator.py:6364-6412`). The authorizer is the gate logic without the
  single-call delivery, leaving each path's delivery intact.

## D6 — Concurrency accounting for hops charges both the initiating and executing agents' user-scoped slots

**Decision**: A hop that starts long-running work charges the concurrency cap
(`ConcurrencyCap`, `concurrency_cap.py:21`, `max_per_user_agent = 3`,
`orchestrator.py:467`) against **both** the executing `(user_id, callee_agent)`
slot (as the single path does today, `orchestrator.py:6030-6062`) **and** the
initiating `(user_id, initiating_agent)` slot, so a fan-out cannot multiply a
user's effective concurrency past the per-agent cap. Cap rejection stays
reject-not-queue (`concurrency_cap.py:40-41`) and surfaces to the planner as an
honest hop failure (spec Assumption "Concurrency accounting").

**Rationale**: The cap is per-`(user_id, agent_id)` and in-process
(`concurrency_cap.py:24-27`). Charging only the callee would let one initiating
agent fan out to N callees and hold N×cap slots; charging both bounds the tree
(FR-019, US3-AS4). The spec's default is explicit: "charging both the initiating
and executing agents' user-scoped slots" (Assumptions).

**Alternatives considered**:
- *Charge only the executing agent* (today's single-path behavior) — rejected:
  permits unbounded effective fan-out concurrency, the FR-019 failure mode.
- *A single global per-user chain slot* — rejected: conflates with the existing
  per-agent cap semantics and would reject legitimate independent direct calls;
  the global bound is the chain budget (D9), a separate mechanism.

## D7 — Machine-turn authority: one shared derivation seam all machine-turn classes inherit

**Decision**: Introduce a single `MachineTurnAuthority` derivation (a small
orchestrator module) that every machine-turn class calls to obtain a root
subject-token before it runs a real-agent turn: (1) scheduled runs
(`scheduler/runner.py:88`, `run_scheduled_turn`, `orchestrator.py:2923`),
(2) attachment-parser replay (`attachment_autoparse.auto_continue_after_go_live`,
`attachment_autoparse.py:87`), and (3) draft self-tests
(`agentic_creation._self_test_draft`, `agentic_creation.py:323`). It loads the
owner's durable consent (offline grant), refuses fail-closed on
missing/revoked/expired consent, mints a fresh access token
(`offline_grant.mint_access_token`, `offline_grant.py:107`), narrows to
(consented ∩ current) scopes (reusing the runner's `_intersect_scopes`,
`scheduler/runner.py:29-31`), and returns a root token the turn threads into
`handle_chat_message` so real-agent dispatch runs delegated in production, and
any further hops mint children off it (D2). The derivation is threaded but stays
behind `FF_SCHEDULER_EXECUTION` (default off, `feature_flags.py:47`) for the
scheduler class per its pending security review (D14).

**Rationale** (verified): The scheduler runner already validates the grant, mints
a fresh token, and computes the scope intersection
(`scheduler/runner.py:104-134`), but `run_scheduled_turn` **drops the minted
token** — its docstring states the deep-threading "is the explicit scope of the
T057 security review before the flag is enabled in production"
(`orchestrator.py:2946-2949`) and it calls `handle_chat_message` with no token
(`orchestrator.py:2980`). Because the VirtualWebSocket carries no session token,
production posture's `_delegation_required` refuses every real-agent dispatch
fail-closed (`orchestrator.py:5983-6007`) — so scheduled jobs, parser replay, and
self-tests are development-mode-only today (spec "Why now" §3). One shared seam
(rather than three ad-hoc threadings) satisfies FR-012's "one shared mechanism
all machine-turn classes inherit" and FR-015's "one authority model, two roots".

**Alternatives considered**:
- *Thread the token only into the scheduler path* — rejected: parser replay
  (`attachment_autoparse.py:87-146`) and self-tests (`agentic_creation.py:323`)
  run the identical VirtualWebSocket substrate and hit the same fail-closed wall;
  FR-012 requires all machine-turn classes at one seam.
- *Give machine turns a synthetic always-valid token* — rejected: that is the
  ambient-authority anti-pattern FR-001 forbids and would over-reach past the
  user's current grants; the offline grant is the sanctioned consent primitive.

## D8 — Consent capture is an explicit, scoped, durable step at schedule/approval time

**Decision**: Add an explicit consent-capture step wherever durable machine
authority is created — the scheduling consent card (`schedule_decision`
`ui_event`, dispatched via `scheduling_chat`, `orchestrator.py:5758-5764`) and
any capability-approval that will later run on the user's behalf. Capture records
the granted scopes, the durable (365-day-capped) nature, and the revocation path,
then calls the existing `OfflineGrantStore.capture(user_id, refresh_token,
agent_id)` (`offline_grant.py:64`) and links the returned `grant_id` onto the job
(`scheduler/store.py:71-74`, `set_grant`). No durable consent is created
implicitly.

**Rationale** (verified — a genuine gap): `OfflineGrantStore.capture` exists and
is correct (encrypts the refresh token at rest, fails closed without the key,
`offline_grant.py:64-83`) but has **no production caller** — a repo-wide search
finds it invoked nowhere outside tests, and both job-creation sites hardcode
`offline_grant_id=None` with a comment that the grant is "granted later via
Settings (consent-capture flow)" (`scheduling_chat.py:295`) / "set by the
consent-capture flow (T042)" (`scheduler/api.py:120`). The refresh token needed
for capture is already held in the encrypted web session
(`session_store.py:178-189`, `_dec` at `207`). FR-011 requires this explicit
step; without it every scheduled job is unauthorizable and pauses on first run
(`scheduler/runner.py:104-112`).

**Alternatives considered**:
- *Auto-capture the session refresh token on every login* — rejected: FR-011
  mandates an explicit consent step naming the scopes; silent capture of a
  365-day durable grant is precisely the "no durable consent implicitly"
  prohibition.
- *Capture at first run instead of at scheduling time* — rejected: the user is
  not present at run time to consent; the offline-grant model requires a live
  session to capture the `offline_access` refresh token (`offline_grant.py:70`).

## D9 — Global chain budget bounds cumulative depth, hop count, and wall clock per turn

**Decision**: A per-turn `ChainBudget` (small in-process object, seeded when a
turn starts, keyed by chat/turn) bounds the whole nested tree: cumulative depth
(capped by the 048 depth bound of 3, `delegation.py:416`), total hop count, and
a wall-clock ceiling. It composes with — and is distinct from — the existing
per-turn `MAX_TURNS = 10` orchestrator ReAct bound (`orchestrator.py:3796`,
`3810`). Budget exhaustion yields honest partial results and an audited
budget-stop, never runaway recursion; it applies to machine turns too.

**Rationale**: The depth bound (048) limits one chain's length but nothing today
bounds the *breadth × depth* of a decomposed turn or its wall clock across
nested sub-turns (spec "Why now" §5: "no global depth/budget bound across nested
turns"). FR-021 requires cumulative depth + hop count + wall clock as one
ceiling; the conservative default is a small hop budget and a bounded wall clock
consistent with the existing `SELF_TEST_TIMEOUT_S` / tool-timeout posture.

**Alternatives considered**:
- *Rely on the per-hop depth bound alone* — rejected: depth 3 with wide fan-out
  at each level is still an unbounded tree (FR-021's runaway-recursion concern).
- *A global process-wide budget* — rejected: must be per-user-turn so one turn's
  fan-out cannot starve another; a per-turn object scoped like the taint tracker
  (`orchestrator.py:5673-5685`) is the right granularity.

## D10 — Sub-task decomposition (US4): bounded isolated sub-turns via the VirtualWebSocket substrate, results returned as digests

**Decision**: LLM-planned decomposition spawns bounded, isolated sub-tasks on the
existing `BackgroundTask` + `VirtualWebSocket` substrate
(`async_tasks.py:29-105`) — each with fresh context, a child authority derived
from the turn's root (D2), and a per-subtree slice of the chain budget (D9).
Sub-task results return to the parent as bounded, provenance-tagged digests (not
raw transcripts), and every inter-agent digest passes the MAS payload scan (D11)
before entering the parent/planner context. Orphaned sub-tasks (parent ended,
socket gone, budget exhausted) are cancelled via the existing
`BackgroundTaskManager.cancel` (`async_tasks.py:191-198`) and audited; their
partial output is discarded, never attached to a later turn.

**Rationale** (verified): The isolated-sub-turn machinery already exists — draft
self-tests run a full chat turn on a fresh `test_chat_id` VirtualWebSocket
(`agentic_creation.py:337-350`), and the fan-out planner
(`fanout.decompose`, `fanout.py:54`) already splits oversized waves into bounded
batches consumed at `orchestrator.py:3966-3973`. This decision binds those to
child authority + budget + digest-return rather than inventing a new substrate
(FR-020/FR-023). The orphan-cancel path is the existing task cancel; the "never
silently attach to a later turn" rule is enforced by discarding a cancelled
task's `outputs` (`async_tasks.py:161-163` already marks CANCELLED).

**Alternatives considered**:
- *Return raw sub-task transcripts to the parent* — rejected: unbounded context
  growth and an un-scanned injection channel; FR-020 mandates bounded digests.
- *A new dedicated sub-task executor* — rejected: duplicates the
  BackgroundTask/VirtualWebSocket substrate that already captures outputs,
  supports cancel, and persists to chat history.

## D11 — Inter-agent payloads pass the MAS defense scan; flagged payloads are quarantined and audited

**Decision**: Every hop result returned to a requesting agent or the planner, and
every sub-task digest, is scanned by `mas_defense.scan_message`
(`mas_defense.py:101-110`) before it enters another context. A finding quarantines
the payload (it is not delivered upstream), records an audited reason, and returns
an honest error to the requester. This wires the C-S14 scanner into the hop path
(FR-007, US4-AS4).

**Rationale** (verified): The scanner exists and is pure/stdlib
(`mas_defense.py:101-110`, markers at `36-40`) but on the tool path today it is
**only logged, never enforced** — `turn_hooks.scan_payload`
(`turn_hooks.py:175-182`) returns findings and the chat loop merely
`logger.warning`s them (`orchestrator.py:3990-3996`) with no quarantine. Chaining
turns one agent's output into another agent's input (the multi-agent flow C-S14
was built for), so the spec elevates the scan from advisory to enforcing on
inter-agent hops. The combined gate `is_safe_message`
(`mas_defense.py:113-128`) additionally offers per-edge scoping and signature
verification the hop path can adopt.

**Alternatives considered**:
- *Keep scanning advisory (log only)* — rejected: FR-007 requires quarantine
  with an audited reason and an honest error; a logged-but-delivered malicious
  digest is the confused-deputy propagation the spec closes.
- *Scan only planner-bound payloads, not agent-bound* — rejected: US4-AS4 covers
  "any inter-agent payload (hop result or sub-task digest)"; both directions carry
  the injection risk.

## D12 — Retire the dormant direct peer-call path with a regression test

**Decision**: Remove (or hard-refuse with audit) `BaseA2AAgent.call_peer_tool`
and its transport helpers `_call_peer_via_ws` / `_call_peer_via_a2a` and the
`connect_to_peer` / `_peer_listen_loop` / peer-registry machinery
(`base_agent.py:653-841`). A regression test proves an agent cannot bypass
orchestrator mediation (an attempted direct peer call fails 100% of the time with
an audited refusal, SC-010). The sanctioned replacement is the mediated
`AgentRuntime.call_agent_tool` (D4).

**Rationale** (verified): `call_peer_tool` is dead code — the only definition is
`base_agent.py:682`, with **zero callers** anywhere in the tree (repo-wide search
finds no invocation outside the definition). It forwards the caller's delegation
token unattenuated (`base_agent.py:756`, `812-813`) — a confused-deputy seam the
spec explicitly retires (FR-010, US4-AS5, Assumptions "Direct agent-to-agent
transport is out of scope and the existing dormant path is retired"). Removing it
also deletes the peer-connection/registry surface (`base_agent.py:653-679`),
shrinking the trust boundary.

**Alternatives considered**:
- *Leave it in place but never call it* — rejected: FR-010 requires it removed or
  hard-refused with a regression test; dormant confused-deputy code is a
  standing liability and contradicts the "structurally unavailable to real
  agents" guarantee (FR-003).
- *Repurpose it to route through the orchestrator* — rejected: it is transport
  machinery (WS/A2A peer sockets), not a mediation seam; the runtime callback
  (D4) is the correct, orchestrator-owned replacement.

## D13 — Machine principal: a defined audit identity carrying the owning human, replacing "legacy"/"unknown"

**Decision**: Machine-initiated turns are audited under a defined machine
principal of the form `machine:<class>` (e.g. `machine:scheduled_job`,
`machine:parser_replay`, `machine:draft_self_test`) that always carries the owning
human's `actor_user_id` and the run's consent reference. The audit hook resolves
this from the VirtualWebSocket's turn context rather than falling to "legacy",
and cost/authority records distinguish the paying system LLM credential from the
authorizing human (FR-014, US2-AS4/AS5, SC-005). A new `"delegation"` value is
added to the audit `EVENT_CLASSES` tuple (`audit/schemas.py:30-65`) for hop
provenance records (D15).

**Rationale** (verified — a real gap): `actor_principal_from_claims` returns
`("legacy", "legacy")` when a turn has no claims (`audit/hooks.py:38-39`), and
every audit helper **skips recording entirely when `user == "legacy"`**
(`hooks.py:59-60`, `105-106`, `150`, `250-251`, `273-274`, `317`). A machine turn
runs on a VirtualWebSocket that is absent from `ui_sessions`, so
`ToolDispatchAudit` receives `claims=None` (`orchestrator.py:6066` /
`_execute_with_retry_audited` at `6187`) → machine-turn tool calls are recorded
as `legacy` and therefore **dropped**. The 054 machine-billing convention already
distinguishes the paying system credential from the human
(`_llm_context_user_id` returns `None` for VirtualWebSocket, treating it as a
SYSTEM LLM context, `orchestrator.py:4545-4565`; `_llm_audit_principals` returns
`("system","system")` for `websocket=None`, `4624-4640`) — this decision extends
that convention to the *authority* principal so cost and authority never blur
(FR-014). There is no `"delegation"` event class today (`audit/schemas.py:30-65`
lists 30+ classes, none for delegation hops), so hop provenance needs one added
(a Python-tuple edit, not a schema migration).

**Alternatives considered**:
- *Keep machine turns as "legacy" but stop dropping them* — rejected: FR-014
  demands attribution to the owning human, not an anonymous machine marker; the
  consent reference must travel with the record.
- *Reuse `agent_tool_call` class for hop provenance* — kept for the tool
  start/end pair (that parity is FR-003), but the *chain hop* provenance record
  (parent→child linkage, D15) is a distinct record type warranting its own class
  for clean reconstruction queries (SC-003).

## D14 — Flag posture: `FF_RECURSIVE_DELEGATION` gates chaining; `FF_SCHEDULER_EXECUTION` stays off pending T057

**Decision**: The chaining capability ships behind the existing default-off
`FF_RECURSIVE_DELEGATION` (`feature_flags.py:107`); with it off, behavior is
byte-for-byte today's single-hop path and the existing delegation (11) +
tool-permission (26) suites pass unchanged (FR-009, SC-009). The **dispatch-path
parity work (D5) ships independent of the flag** — it is pure hardening that must
hold on the single/parallel paths regardless — but the delegation-token portion
of parity (giving the parallel path its own token) is what the flag's off-state
preserves as today's behavior. Machine-turn authority (D7/D8) ships **dark**
behind `FF_SCHEDULER_EXECUTION` (default off, `feature_flags.py:47`) for the
scheduler class until the recorded offline-grant security review (025 T057 / 030
FR-004/FR-005) lands; the review gate is inherited, not bypassed (FR-016,
SC-004's "under production posture with consent captured" is gated on the review).

**Rationale** (verified): `FF_RECURSIVE_DELEGATION` already exists and defaults
off, fail-closed (`feature_flags.py:99-107`). `FF_SCHEDULER_EXECUTION` already
gates the scheduler execution loop (`orchestrator.py:8765-8787`,
`feature_flags.py:47`) and its comment states it "MUST stay OFF until the
lead-dev security review of offline_grant.py is recorded"
(`feature_flags.py:41-47`). Two roots, two flags: the interactive chaining seam
under `FF_RECURSIVE_DELEGATION`, the machine root under
`FF_SCHEDULER_EXECUTION`, so US2 machinery is shippable dark without changing
runtime behavior until the review is recorded (FR-016).

**Alternatives considered**:
- *One combined flag* — rejected: the two roots carry different review gates
  (T057 governs only the machine/offline-grant root); a single flag would either
  block interactive chaining on T057 or ship the machine root without its review.
- *Default `FF_RECURSIVE_DELEGATION` on for a "real" integration* — rejected:
  FR-009/SC-009 require the off default and byte-equivalence for safe rollback;
  the thesis measurement (US5) runs the off-vs-on comparison, which needs the off
  baseline intact.

## D15 — Provenance hop records ride the hash-chained audit; two-hop reconstruction is a pinned regression test

**Decision**: Every mint and every enforced hop appends the 048 provenance record
(`delegation.delegation_chain_audit_record(parent, child, operation, tool)`,
`delegation.py:642-667`) to the existing hash-chained audit as a paired
start/end pair under a shared correlation id, using the new `"delegation"` event
class (D13). A two-hop chain is reconstructable from the audit log alone
(`AuditRepository.verify_chain`, `audit/repository.py:365`, walks and validates
the HMAC chain), and that reconstruction is pinned as a regression test — closing
048's deferred T018 / SC-003.

**Rationale** (verified): 048 built `delegation_chain_audit_record` mapping a hop
onto the HIPAA field checklist (`delegation.py:645-667`: `acting_agent`,
`parent_actor`, `human_authorizer`, `operation`, `scope`, `delegation_depth`,
`actor_chain`, `timestamp`) but it is a pure record builder with no wiring to the
audit chain — 048 T011 built it, T018 deferred the end-to-end reconstruction
evidence "with the T014 flag-on integration" (`048/tasks.md:40`). The audit
chain's tamper-evidence is supplied by `chain_hmac` (`audit/pii.py:150`) and
verified forward by `verify_chain` (`audit/repository.py:365-408`). Emitting the
hop record through the normal `Recorder` path makes the full chain
reconstructable (FR-026, SC-003, US1-AS5).

**Alternatives considered**:
- *Store hop records in a new table* — rejected: FR-026/SC-003 require
  reconstruction from the *tamper-evident audit log*; a side table is not
  hash-chained. The existing `audit_events` chain is the substrate 048 chose.
- *Emit only on mint, not on enforced use* — rejected: FR-008/US1-AS5 require
  paired records (the mint and the enforced use) with correlation linkage so the
  "attempted vs. effected" distinction survives.

## D16 — Benchmark gains chained-attack scenarios through the real dispatch path (US5)

**Decision**: Extend the 047 security-benchmark harness
(`backend/security_benchmark/`) with chained-attack scenarios — confused deputy,
cross-hop scope escalation, depth-bound violation, actor-chain forgery, and
chained-consent replay — added as new cases in the existing adapter/adjudicator
core (`adapters/base.py`, `adjudicator.py`, `envelope.py`), executed through the
real dispatch path via the `inprocess` driver
(`security_benchmark/drivers/inprocess.py`). A comparison run (chaining off vs.
on) is producible on demand, reporting per-scenario outcomes and overall ASR with
the acceptance bar "no ASR regression with chaining on"; each blocked attack is
attributed to the named layer that stopped it. This work is **eval-only** and
adds zero product-runtime dependencies (Constitution V, XI carve-out).

**Rationale** (verified): The harness core is stdlib-only, isolation-guarded, and
CI-gating (`047/plan.md:8-26`, `security_benchmark/isolation_check.py`), with a
deferred T021 to wire the `inprocess` driver's live turn execution end-to-end
(`047/tasks.md:49`). 047 explicitly names 048/056 as the enforcement it measures
at the system level (`047/spec.md:146`, sibling non-blocking). Adding scenarios
to the existing adjudicator (4-outcome, attempt-vs-effect, `047/tasks.md:15`) is
"only a new adapter" per its design (SC-003 of 047), so the chained scenarios
reuse the reporting/ablation core (FR-024/FR-025, SC-008).

**Alternatives considered**:
- *A separate chaining-only test harness* — rejected: duplicates the 047
  adjudication/reporting core the spec says to extend (FR-024 "The security
  benchmark MUST gain chained scenarios"); the harness is designed for exactly
  this.
- *Measure with the synthetic driver only* — rejected: FR-024 requires the real
  dispatch path so the measured blocks are genuine gate enforcement, not scripted
  (047 FR-006's "attack blocked vs. never attempted" distinction).

## D17 — Legacy-token interop, dev-mode posture, and revocation-during-derivation

**Decision** (three conservative resolutions of spec edge cases):
1. **Legacy single-hop tokens are honored as depth-0 roots.** A token with no
   `delegation_depth` claim is depth 0 (`delegation._token_depth`,
   `delegation.py:470-475` returns 0 for the absent claim), and
   `verify_delegation_chain` accepts a depth-0 single-actor chain
   (`delegation.py:598-604`), so mixed old/new traffic interoperates during
   rollout (spec Edge Case "Legacy tokens", FR-009).
2. **Dev-mode still exercises real minting for hops and machine turns.**
   Development posture keeps today's unscoped fallback for *direct* dispatch
   (`_delegation_required` returns False in dev, `orchestrator.py:6791-6796`), but
   chained hops and machine turns run real `mint_child_delegation` /
   consent-derivation even in dev so the paths ship tested (spec Edge Case
   "Dev-mode fail-open"), with the same observable refusals.
3. **Revocation is checked at authority derivation, not only at expiry.** A
   new-hop mint or a machine-turn derivation re-checks grant validity
   (`OfflineGrantStore.is_valid`, `offline_grant.py:97-105`, and
   agent-disabled/opt-out via `tool_permissions.is_tool_allowed`) at derivation
   time, so mid-chain logout/revocation prevents any *new* hop mint after the
   event while in-flight hops complete or abort per their own gates (FR-006, spec
   Edge Case "Mid-chain revocation").

**Rationale** (verified): `_token_depth` and `verify_delegation_chain` already
handle depth-0 legacy tokens; `_delegation_required` already differentiates
dev/prod; `is_valid` already checks `revoked_at`/`expires_at`
(`offline_grant.py:101-104`). These are wiring decisions, not new mechanisms.
The fail-closed default (refuse a new hop the moment authority cannot be
re-derived) matches FR-028.

**Alternatives considered**:
- *Reject legacy tokens once the flag is on* — rejected: breaks rollout
  interop (FR-009) and every existing single-hop test.
- *Skip real minting in dev for speed* — rejected: the spec's explicit edge case
  requires dev to exercise minting "else the paths ship untested".

## Resolved spec assumptions & fail-closed choices where the spec is silent

- **Both seams in scope, orchestrator-mediated; direct P2P retired** (spec
  Assumptions) → D1, D4, D12.
- **Child-token signing is orchestrator-local** using existing DPoP key material
  (spec Assumptions) → D2 (no per-agent key; the mediation point mints and
  verifies).
- **Per-hop permissions are both-ANDed** — token-scope attenuation AND
  per-(user, callee) permission both must pass (spec Assumptions) → D1/D2
  (re-entering `execute_single_tool` runs `is_tool_allowed`; the child token
  independently constrains scope).
- **Empty intersection = refuse fail-closed** (spec resolves 048's open
  question) → D3.
- **Concurrency charges both sides of a hop** (spec Assumptions) → D6.
- **Depth bound stays 3** (spec Assumptions; operator-configurable is
  nice-to-have) → D2 (048 default retained).
- **Machine turns bill the system LLM credential** (existing owner decision, 054)
  while attribution names the human → D13.
- **Silent where spec is quiet, chosen fail-closed & recorded**:
  (a) *Wall-clock ceiling value for the chain budget* — the spec names wall clock
  as a budget axis (FR-021) but not a number; chosen conservatively at a small
  bound consistent with `SELF_TEST_TIMEOUT_S` / tool timeouts, documented as a
  tunable (D9). (b) *What happens to an in-flight hop at the exact revocation
  instant* — the spec says in-flight hops "complete or abort per their gates";
  chosen: no new mint after revocation, in-flight completes if already past its
  gate, else its gate refuses (D17.3). (c) *MAS-scan on a hop payload that is
  itself a legitimate quoted attack sample* (e.g. a security agent summarizing an
  injection) — chosen: quarantine + honest error is fail-closed and correct for
  the chaining threat model; a quoting agent re-requests without the marker (D11).
