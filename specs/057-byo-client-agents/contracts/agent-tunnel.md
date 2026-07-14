# Contract: Agent-Frame Tunnel + Owner Binding

**Purpose**: how a user's desktop-hosted agent reaches the orchestrator (inward), authenticated to exactly one owner, and how it goes offline. Reuses `handle_agent_message` and the existing gate stack; adds owner binding and honest-offline.

## Transport

- The desktop host's agent frames are **tunneled over the client's already-authenticated UI WebSocket** (the socket already carries the validated OIDC principal in `ui_sessions[ws]`). No second auth handshake; no reliance on the shared `AGENT_API_KEY` for owner identity.
- Tunneled frames are the existing agent-channel frames — `RegisterAgent`, `MCPResponse`, `AgentHopRequest`/`AgentHopResponse`, tool-progress/stream — wrapped in a UI-channel envelope (e.g. `agent_tunnel {frame}`) that the orchestrator unwraps and feeds to `handle_agent_message` via a `.send`-shaped adapter (LoopbackSocket pattern). **Agent-channel frames do not enter `ui_protocol.json`** (Constitution XII).
- Alternative (documented, not chosen for v1): a standalone authenticated inbound `/agent` WS route mirroring `handle_ui_connection_fastapi`, carrying the owner bearer token on the handshake.

## Registration handshake (owner binding — the load-bearing addition)

On `RegisterAgent` received over a user's tunnel:

1. Resolve `owner_sub = ui_sessions[ws].sub` (authenticated; **never** from the card or any agent-supplied field — Constitution A/H, FR-015).
2. Look up `user_agent[card.agent_id]`. **Refuse fail-closed** unless it exists AND `owner_user_id == owner_sub` AND `status ∈ {validated, live}` AND `revalidation_required == FALSE`.
3. Refuse if `card.agent_id` collides with a built-in/public/reserved (`__*`) id or another user's id.
4. On success: store the socket in an owner-scoped registry keyed by `(owner_sub, agent_id)`; set `status='live'`, `host_session_id`, `host_last_seen_at`; supersede any stale socket for the same key (reconnect/duplicate resolution).

**Invariant**: no code path may bind an agent to an owner derived from anything the agent presents.

## Dispatch (reuse, unchanged)

A live user agent is dispatched through the **existing** single/parallel/hop paths → `_authorize_and_prepare/_run_gate_stack`, which overwrites `args[user_id]` with the session principal, checks `is_tool_allowed` (live owner grants), mints RFC 8693 delegation, and applies policy/taint/PHI/supervisor/HITL/cap. **No new authz path** (FR-007/FR-018).

- The untrusted agent is **not** handed the `_delegation_token` bytes or per-user secrets on the direct path (mirror the 054 in-process-only credential rule); the orchestrator re-authorizes at dispatch.

## Liveness & offline (FR-010/FR-011, SC-005)

- Liveness ⇔ the tunnel/UI socket is connected AND `host_last_seen_at` fresh; a heartbeat ping bounds detection to a few seconds.
- On disconnect: deregister `(owner_sub, agent_id)`, set `status='live'`→(runtime offline; status unchanged), emit a UI `agent_offline` frame to the owner's sockets (**this frame IS on `ui_protocol.json`** — it crosses the UI wire).
- Invoking an offline user agent returns a **prompt honest-offline** `MCPResponse` — never the `agent_urls` reconnect + retryable "not connected" fallback (wrong for a NAT'd host).

## Per-owner ingress bound (FR-017/SC-008)

- A per-owner rate + in-flight-frame cap on the tunnel (extending `concurrency_cap`/`ChainBudget`), scoped to externally-connected user-agent sockets only (never throttling in-process built-ins or legit long chains). A flooding agent degrades only its owner.

## Failure modes (all fail-closed)

| Condition | Result |
|-----------|--------|
| Owner mismatch / missing ownership row | Registration refused, audited; no socket stored. |
| Id collision / reserved id | Registration refused. |
| `revalidation_required` | Registration refused until re-Analyze passes. |
| `FF_BYO_AGENTS` off | Tunnel + registration inert (byte-identical to today). |
| Agent offline | Prompt honest-offline dispatch result. |
