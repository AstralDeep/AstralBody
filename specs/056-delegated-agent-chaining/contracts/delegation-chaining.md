# Contract: Delegation Chaining (runtime callback + hop lifecycle + gate authorizer)

**Feature**: 056-delegated-agent-chaining | **Date**: 2026-07-13

Backend-internal contracts. **No client-visible wire change** — hops are
orchestrator-mediated in-process; hop/sub-task progress rides EXISTING progress
frames (`ToolProgress`, `chat_status`), so `backend/shared/ui_protocol.json` and
every native client are unchanged (Constitution XII; spec Assumption "Progress
surfaces"). If a new progress frame ever proves unavoidable it follows the
drift-guard/manifest process and lands on all clients same-PR.

Everything below is gated by `FF_RECURSIVE_DELEGATION` (default off,
`feature_flags.py:107`). Flag off ⇒ none of these paths execute and behavior is
byte-identical to today's single-hop dispatch.

## 1. AgentRuntime callback seam (US1, D4)

New awaitable on the runtime injected into every tool
(`shared/agent_runtime.py`; injected at `base_agent.py:319-326`):

```python
async def call_agent_tool(
    self,
    callee_agent_id: str,
    tool_name: str,
    arguments: dict,
    *,
    timeout: float = 30.0,
) -> MCPResponse:
    """Request a mediated hop to a peer agent's tool. Returns the peer's
    MCPResponse or an honest error MCPResponse. NEVER talks to a peer directly;
    schedules a mediated hop onto the orchestrator via the loopback and awaits
    the correlated response future. The initiating agent holds NO token and NO
    mint capability."""
```

- Behaviour: constructs an in-process hop-request frame
  `{type:"agent_hop_request", request_id, initiator_agent_id, callee_agent_id,
  tool_name, arguments}` and routes it back through the same
  `LoopbackSocket.send_text` → `handle_agent_message` path the runtime already
  uses (`local_transport.py:38-45`), then awaits a future keyed like
  `pending_requests` (`orchestrator.py:1075-1078`).
- The orchestrator resolves the hop by calling `execute_single_tool` for
  `(callee_agent_id, tool_name, arguments)` (§3), threading the initiator's
  parent token as the parent authority (§2), then delivers the result back to
  the initiating agent's awaiting future.
- **Fail-closed**: if `callee_agent_id` is unknown, disabled, opt-out, over
  budget, or the hop is refused by any gate, `call_agent_tool` returns an error
  `MCPResponse` (never raises into the agent; never tears down the session,
  FR-028).
- External (networked) agents send the same `agent_hop_request` over their
  existing WS control channel (routed in `handle_agent_message`,
  `orchestrator.py:1067`), never a peer socket.

## 2. Child authority mint at the mediation point (US1, D2/D3)

At the dispatch site (`orchestrator.py:5977-6007`, the RFC 8693 token-inject
block), when the call is a **hop** (a parent delegation token is in scope for the
turn):

```
requested_scopes = scopes the callee tool needs (from tool_permissions + the
                   initiator's own granted scope set)
child = delegation.mint_child_delegation(parent_token_payload, callee_agent_id,
                                         requested_scopes)         # delegation.py:515
if child.scope == "" and requested_scopes:                        # D3 empty-∩ refusal
    audit delegation.hop.mint outcome=failure detail=empty_intersection
    return refusal MCPResponse (per-call, honest error)
ok, reason = delegation.authorize_chained_tool_call(child, tool_name,
                                                    required_scope)  # delegation.py:621
if not ok:
    audit delegation.hop.enforce outcome=failure detail=reason      # depth/tamper/scope/expiry
    return refusal MCPResponse
args["_delegation_token"] = <compact-encoded child>                 # replaces the flat token
```

- `DelegationDepthExceeded` (delegation.py:435) from the mint is caught and
  becomes a per-call depth-bound refusal (FR-002, US1-AS3).
- The child is compact-encoded/signed at the call site using the existing DPoP
  key custody (orchestrator is minter+verifier; no per-agent key — spec
  Assumption). A small helper on `delegation.py` MAY encode the decoded child
  payload to the same compact JWT/HMAC form `_create_mock_delegation_token`
  produces (delegation.py:312-329), or the Keycloak-mode enforced-scope path
  records the effective scope per 048 FR-013.
- Legacy single-hop tokens (no `delegation_depth`) are depth-0 roots and still
  honored (D17.1; `_token_depth` returns 0, delegation.py:470-475).

## 3. Hop re-enters the full single-path gate stack (US1, FR-003)

Every hop is dispatched by calling the same `execute_single_tool` entry a chat
tool call uses (`orchestrator.py:5706`), so it re-runs, in order:

1. system security-flag block (`5779-5790`)
2. per-user tool permission (`5792-5802`, `tool_permissions.is_tool_allowed`)
3. deterministic policy engine (`5804-5853`)
4. taint / data-flow sink gate (`5855-5875`)
5. supervisor + HITL (`5877-5910`)
6. per-(user, callee) credential injection (`5920-5925`) — never the initiator's
   credentials (FR-008)
7. RFC 8693 child mint + verify (§2)
8. PRE_TOOL_USE hook (`6009-6024`)
9. concurrency cap — charging BOTH initiating and executing slots (D6, `6026-6062`)
10. paired `ToolDispatchAudit` start/end (`6064-6089`)

**Meta-tool bypass is structurally unavailable to real-agent hops** (FR-003,
FR-018): the `__orchestrator__`/`__scheduler__`/`__memory__`/`__desktop_codegen__`
short-circuits (`5753-5777`) fire only for those reserved pseudo-agent ids; a hop
`callee_agent_id` is a real registered agent id, so it can never reach a meta-tool
handler.

## 4. Shared gate authorizer — dispatch-path parity (US3, D5, FR-017)

Extract the gate sequence (steps 1–9 above) into the gate stack. As
implemented this is TWO functions:

```python
async def _run_gate_stack(self, websocket, agent_id, tool_name, args, chat_id,
                          user_id, *, stream_params=None, parent_token=None,
                          initiating_agent_id=None):
    """Run the full gate stack once. Returns a PreparedDispatch NamedTuple
    (args, stream_params, cap_job_id, delegation_token, hop_correlation_id) on
    allow, or a GateRefusal NamedTuple (response, render_components,
    render_target, hop_audited) on any deny. parent_token triggers the child
    mint (§2); initiating_agent_id dual-charges the hop's cap slot (§5)."""

async def _authorize_and_prepare(self, ...same signature...):
    """Thin SC-002 wrapper over _run_gate_stack: when a HOP (parent_token set)
    is refused by any gate that fires BEFORE the delegation step (security
    flag, permission/opt-out, policy, taint, supervisor, HITL, cap), emit a
    delegation.hop.mint failure record so 100% of gate-violating hops carry
    audit evidence. Direct dispatch is unchanged (no hop record)."""
```

Both `execute_single_tool` and `execute_parallel_tools` call
`_authorize_and_prepare`; the mint/enforce refusals inside `_mint_child_for_hop`
set `hop_audited=True` so the wrapper does not double-record them.

- `execute_parallel_tools` (`orchestrator.py:6209`) replaces its partial inline
  prepare loop (`6220-6304` — which today applies ONLY creds/security/permission/
  no-agent) with `_authorize_and_prepare`, gaining policy, taint, supervisor,
  HITL, delegation token, concurrency cap, and PRE_TOOL_USE that it currently
  skips.
- Meta-tool parity: the parallel path gains the `__scheduler__`/`__memory__`/
  `__desktop_codegen__` branches it lacks today (`6261` handles only
  `__orchestrator__`).
- **Conformance test** (FR-017, SC-006): a shared gate-contract test drives the
  same violating call (disabled agent, blocked tool, out-of-scope, policy-deny,
  tainted sink, HITL-required, over-depth, empty-∩, cap-exceeded) down the single
  path, the parallel path, and a chained hop, asserting identical refusal
  outcomes and equivalent audit evidence.
- The two pre-existing supervisor-gate test failures 048 flagged
  (`test_security_gates_wiring.py::test_supervisor_off_is_noop` /
  `::test_supervisor_allows_when_intent_present`, `048/tasks.md:50`) are in scope
  here only insofar as US3 touches the supervisor gate (spec Assumption); the
  parity refactor fixes them as a bounded side effect.

## 5. Concurrency accounting for hops (US3, D6, FR-019)

A long-running hop charges the `ConcurrencyCap` (`concurrency_cap.py:21`,
`max_per_user_agent=3`) against BOTH `(user_id, executing_agent)` (today's
behavior) AND `(user_id, initiating_agent)`. Reject-not-queue is preserved
(`concurrency_cap.py:40-41`); a cap rejection surfaces to the planner as an honest
hop failure. Both slots are released on the hop's terminal `ToolProgress`
(`orchestrator.py:7893` handler) or dispatch error.

## 6. Sub-task decomposition (US4, D10, FR-020/FR-021/FR-023)

Implemented as `orchestrator/subtasks.py` with the `delegate_subtasks`
meta-tool (`__subtasks__` pseudo-agent, injected only under
`FF_RECURSIVE_DELEGATION`). The dispatch site computes `_parent_tools` from the
turn's tool map so a sub-task may use only tools the parent turn offered (never
a superset). Bounds: 2–5 sub-tasks, `DIGEST_CAP=1200`, `SUBTASK_TIMEOUT_S=90`,
each slice `max_hops // n`.

- Spawn: `BackgroundTask` + `VirtualWebSocket` (`async_tasks.py`), fresh
  context, a per-subtree slice of the `ChainBudget` (D9).
- **Authority (drift from the draft)**: a sub-task runs under the **same root**
  as the parent, not a minted child of it — `subtasks._run_one` copies the
  parent session claims onto the isolated `VirtualWebSocket`
  (`orch.ui_sessions[vws] = dict(parent_claims)`), so each dispatch inside it
  does the normal flat root exchange keyed to the same human principal, and
  only *hops started inside the sub-task* mint attenuated children (§2).
- Return: a bounded, provenance-tagged **digest** (never a raw transcript);
  scanned by the MAS defense (§7) before entering the parent/planner context.
- Global budget: `ChainBudget` bounds cumulative depth, total hop count, and
  wall clock across the whole tree; exhaustion → honest partial results + an
  audited `delegation.subtask.budget_stop`.
- Orphans: parent-ended / socket-gone / budget-exhausted sub-tasks are
  cancelled by plain `asyncio` task cancellation in `handle_meta_tool` (the
  sub-task `BackgroundTask` is constructed directly, not via
  `BackgroundTaskManager`) and their partial `outputs` are **cleared**
  (`task.outputs.clear()`), never attached to a later turn; the cancellation is
  audited (`delegation.subtask.{cancelled,orphaned}`).

## 7. MAS payload scan enforcement on hops (US4, D11, FR-007)

Every hop result and sub-task digest is scanned by `mas_defense.scan_message`
(`mas_defense.py:101-110`) — or the combined `is_safe_message`
(`mas_defense.py:113-128`) for per-edge scoping — BEFORE it enters another agent's
or the planner's context. A finding **quarantines** the payload (not delivered
upstream), records an audited reason, and returns an honest error to the
requester. This promotes the scanner from today's log-only posture
(`turn_hooks.scan_payload` → `logger.warning`, `orchestrator.py:3990-3996`) to
enforcing on inter-agent hops.

## 8. Peer-path retirement (US4, D12, FR-010)

`BaseA2AAgent.call_peer_tool` (`base_agent.py:682-719`) and its transport helpers
`_call_peer_via_ws` / `_call_peer_via_a2a` (`base_agent.py:726-841`) and the
`connect_to_peer` / `_peer_listen_loop` / peer-registry surface
(`base_agent.py:653-679`) are removed (or hard-refused with an audited error).
A regression test proves an agent cannot bypass orchestrator mediation
(SC-010: an attempted direct peer call fails 100% of the time, audited).

## 9. Refusal & failure semantics (FR-028)

- Every refusal (empty-∩, over-depth, tamper, out-of-scope, disabled agent,
  opt-out, policy/taint/HITL deny, cap reject, budget stop, quarantine) is
  **per-call, fail-closed, audited, never session-terminating**.
- Verification failures refuse the hop per-call and keep the session/socket open
  (`authorize_chained_tool_call` returns `(False, reason)`; the caller returns an
  error MCPResponse, delegation.py:632-639).
- No refusal records secret token bytes (FR-028); the audit carries actor/scope/
  depth metadata only (delegation.py:656-666).
