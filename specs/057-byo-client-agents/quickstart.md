# Quickstart: Bring-Your-Own Client-Side Agents (Feature 057)

Validation scenarios that prove the feature end-to-end. Backend runs in the `astraldeep` container (per CLAUDE.md); the desktop host is the `windows-client`. `FF_BYO_AGENTS` must be **on** for these (default off — fail-closed).

## Prerequisites

- `docker compose up -d` (postgres + astraldeep); `ASTRAL_ENV=development`.
- `FF_BYO_AGENTS=true` in the container env.
- Agent-constitution present at `backend/agent_constitution/agent_constitution.md` (byte-identical to the specs copy).
- A signed-in user session on a supported client (web or Windows for the full loop; Windows for hosting).

## Scenario 1 — Create + run on my device (US1, SC-001/SC-002/SC-005)

1. From the client, open **Create agent** → author a trivial agent ("greet me by name") through the phases; pass Analyze; Generate.
2. **Expect**: the bundle is delivered to the Windows host, which starts it locally and registers inward; the agent appears in the user's agent list as *running*.
3. Invoke it in chat → correct result, attributed to the user in `audit_events`.
4. **Verify off-server**: no new agent process on the orchestrator host (`docker exec astraldeep bash -c "ps aux | grep -c _agent.py"` unchanged; SC-002).
5. Close the client → within a few seconds the agent shows *offline* (SC-005); invoking it returns a prompt honest-offline message, not a hang (FR-011).

## Scenario 2 — Guided authoring blocks a constitution violation (US2, SC-004)

1. Author an agent whose Plan requests a scope no declared capability uses (violates Constitution C), or that references another user (violates D).
2. **Expect**: the **Analyze** phase does not advance; it lists the violated principle(s) in plain language tied to the offending field; **no code is generated** (`draft_agents.phase` never reaches `generated`).
3. Fix the spec → Analyze passes → Generate proceeds. Confirm the live agent's declared tools/scopes exactly match the approved plan (FR-006).

## Scenario 3 — Nefarious agent cannot cross the boundary (US3, SC-003) — the critical suite

Drive a **deliberately-tampered** local agent (a test harness posing as a user's host) and assert every attempt is denied fail-closed and audited:

1. **Out-of-scope tool**: request a tool the owner does not hold → denied (`is_tool_allowed`), audited. No execution.
2. **Cross-user data**: reference another user's id/data → denied; the other user's data never returned.
3. **Forged identity**: present a fabricated token/user_id/actor claim → ignored; the acting principal is the owner from the orchestrator's own record (`args[user_id]` overwrite).
4. **Grant-hole probe**: as user B, call `set_agent_permissions` on user A's private agent → refused by `can_user_use_agent` (this is the pre-existing hole this feature closes).
5. **Flood**: issue runaway requests → bounded by the per-owner ingress cap; a second user's latency/success is unaffected (SC-008).

Run: `docker exec astraldeep bash -c "cd /app/backend && python -m pytest tests/test_byo_boundary_adversarial.py -q"`.

## Scenario 4 — Cross-client parity + watch exclusion (US4, SC-006)

1. Complete authoring on web, Windows, Android, and Apple (iOS/macOS) → equivalent capability and outcome (the single `agent_authoring` surface renders on each).
2. On a non-host client (web/Android/iOS), confirm the explicit "runs on your desktop host / offline when none online" state (FR-024).
3. On the watch, confirm **no** create-agent affordance (FR-023).

## Scenario 5 — My agent stays mine; manage it (US5, SC-007)

1. As user A, create an agent; as user B, confirm it is entirely invisible and unroutable (list, dispatch, grant) — SC-007/FR-019.
2. Revise the agent → the revision must re-pass Analyze before it is usable; the prior version keeps running until then (FR-026).
3. Delete it → the host agent stops and it disappears from the list/routing (FR-027).
4. Confirm there is **no** share/publish control anywhere (FR-020).

## Scenario 6 — Constitution version binding (Constitution L, FR-028)

1. Bump the agent-constitution MAJOR version; reboot the backend.
2. **Expect**: existing agents validated against the old MAJOR get `revalidation_required=TRUE` and the boundary refuses to route them until they re-pass Analyze.
3. Confirm the byte-identity test between `backend/agent_constitution/agent_constitution.md` and the specs copy passes (`pytest tests/test_agent_constitution_identity.py`).

## Fail-closed check (FR-029)

- With `FF_BYO_AGENTS` **off**, confirm behavior is byte-identical to today: no tunnel, no registration, no authoring surface entry.
- With a required secret / owner binding unavailable, confirm registration and dispatch refuse rather than proceed unverified.
