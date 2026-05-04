# Phase 0 Research: Fix Agent Creation, Test, and Management Flows

**Feature**: 012-fix-agent-flows
**Date**: 2026-05-01

The Technical Context in plan.md introduced no NEEDS CLARIFICATION markers — every decision flowed from the Clarifications session in spec.md plus the existing code. This research file therefore confirms the four bug roots in the actual source and records the design decisions that resolve them, with rejected alternatives.

---

## R1. Story 1 — Why the user never reaches a working Test screen

### Decision
The Test WebSocket in `CreateAgentModal.tsx` will be opened as soon as the user is on Step 4 and the draft has reached any post-generation status that supports testing (`generated`, `testing`). The backend will flip status from `generated` to `testing` once the test WS connects (so the existing per-status UX cues still work). When generation fails, Step 4 mounts in an explicit error state with retry / edit / close actions instead of a frozen empty chat.

### Rationale
Confirmed in code: [`CreateAgentModal.tsx:252`](../../frontend/src/components/CreateAgentModal.tsx#L252) gates the WS connection on `draft?.status === "testing"`. `generate_agent` (backend) sets status to `"generated"` on success. The user lands on Step 4 with no socket; `sendTestMessage` checks `testWsRef.current?.readyState !== WebSocket.OPEN` and returns silently. No code path ever flips status to `"testing"` without the user having already sent a message — a deadlock.

Connecting on `generated` plus flipping to `testing` from the backend on first WS open is the smallest change that:

- preserves the existing status taxonomy already used by the drafts list ([`DashboardLayout.tsx:471–483`](../../frontend/src/components/DashboardLayout.tsx#L471-L483)),
- gives the user a working chat without a manual "Start Testing" click (FR-003),
- still shows an active "testing" badge once messages start flowing.

### Alternatives considered
- **Auto-flip status to `testing` on the backend immediately after generation completes.** Rejected: it lies about what the system is doing — `testing` should mean "user is actively testing," and many users will leave Step 4 idle before sending a message.
- **Add an explicit "Start Testing" button on Step 4 that flips status before opening the WS.** Rejected: it adds a click for no value (FR-003 says start happens on demand). Useful only if we ever want a manual gate; we don't here.
- **Drop the `testing` status entirely and route on `generated`.** Rejected: the rest of the system (dashboard badges, lifecycle reports) already keys off `testing`; removing it is bigger than this feature.

---

## R2. Story 2 — Why the draft doesn't run/respond once the user is on Step 4

### Decision
`start_draft_agent` will surface subprocess startup failures (port-discovery timeout, non-zero exit, captured stderr tail) to the caller as a structured error and to the user via a Test-screen error state. Chat routing will short-circuit with a typed "draft not running" error event over the WS instead of dropping the message when the agent isn't yet in `agent_cards`. A retry path (the same WS event, or an explicit retry button) re-runs `start_draft_agent` once.

### Rationale
Confirmed in code: [`agent_lifecycle.py:484–522`](../../backend/orchestrator/agent_lifecycle.py#L484-L522) starts a subprocess via `Popen` and retries port discovery 6× × 2s. `proc.poll()` is checked but stderr is only logged, never returned. Chat routing at [`orchestrator.py:1756`](../../backend/orchestrator/orchestrator.py#L1756) requires the agent in `agent_cards`; if discovery never succeeded, the user's test message is dropped silently.

Surfacing the actual error (and offering retry) satisfies FR-005 ("clear, recoverable error state") and SC-002 ("95% of test messages receive a complete response within 60 s") — the few percent that fail must fail visibly so the user can act. Capturing stderr on subprocess exit also gives us the observability required by Constitution Principle X.

### Alternatives considered
- **Block Step 4 until port discovery succeeds.** Rejected: it pushes the failure earlier but still strands the user without any chat UI; FR-005 wants a recoverable state on Step 4 itself.
- **Auto-restart the subprocess silently on failure.** Rejected: hides a real generation defect from the user (e.g., a missing tool import) and burns CPU. The retry must be explicit and bounded.
- **Pre-spawn a sandbox process per draft at creation time.** Rejected: violates clarification Q1 (no sandbox) and would also be wasted work for drafts that are never tested.

---

## R3. Story 3 — Why approval doesn't reliably make the agent live

### Decision
On auto-approval, `agent_lifecycle.approve_agent` will:

1. Flip `draft_agents.status` to `live` (already happens).
2. Remove the `.draft` marker file (already happens).
3. **Re-call `set_agent_ownership`** with the now-live `agent_id` to guarantee the ownership row exists and points at the live agent (not the pre-promotion subprocess identity).
4. **Register the live agent in `orchestrator.agent_cards`** via the same path the orchestrator uses on startup, so it persists beyond `_draft_processes`.
5. **Broadcast a fresh dashboard / `agent_list` event** over the user's WebSocket so the live-agents UI updates within SC-003's 10-second budget without a page reload.

The frontend will, in addition, treat the `agent_list` event as authoritative and re-render the live agents list on receipt; if the user is currently in `CreateAgentModal` Step 4 and the active draft transitioned to `live`, the modal will show a "now live" success state and offer to close.

Approval idempotency (FR-011, "no duplicate live agents") is preserved by guarding step 4 on `agent_id not in agent_cards` and step 1 on `status != "live"`.

### Rationale
Confirmed in code: [`agent_lifecycle.py:956–966`](../../backend/orchestrator/agent_lifecycle.py#L956-L966) does flip status and remove the marker but never (a) re-asserts ownership or (b) registers the agent into `orchestrator.agent_cards` permanently. [`orchestrator.py:3989–4020`](../../backend/orchestrator/orchestrator.py#L3989-L4020) explicitly hides drafts from `send_dashboard`, but post-flip the agent is already non-draft — the dashboard simply isn't re-broadcast on its own, so the frontend can't see the change until the next periodic broadcast. The broadcast on promotion is the missing piece.

### Alternatives considered
- **Have the frontend poll `/api/agents` after clicking Approve.** Rejected: introduces a polling pattern this codebase doesn't use elsewhere and races with the security-check completion (which is async).
- **Restart the live agent process on promotion to "fully reset" it.** Rejected: causes a multi-second blip and risks losing the in-flight test conversation; the running process is already the same code path live agents use.
- **Skip the dashboard broadcast and rely on the user manually navigating away and back.** Rejected: violates SC-003 and SC-005 (no manual reload) directly.

---

## R4. Story 4 — Why the Permissions modal "closes and refreshes the page"

### Decision
`openPermissionsModal` will be restructured so the Permissions modal mounts **immediately** with a loading state when `permModalAgent` is set, instead of waiting for the permissions fetch to populate `agentPermissions.agent_id`. The Agents modal will **stay open underneath** until the Permissions modal has mounted; the Agents modal closes either when the Permissions modal explicitly mounts or is dismissed by the user — never as a side effect of starting the fetch. The render-gate at [`DashboardLayout.tsx:915`](../../frontend/src/components/DashboardLayout.tsx#L915) (`agentPermissions && agentPermissions.agent_id === permModalAgent`) will be split: the modal mounts on `permModalAgent` alone, and the inner content swaps between loading / loaded / error.

### Rationale
The user's "modal closes and refreshes the page" report is an observation, not an implementation detail. There is no `<form>` submit, no `<a href>` navigation, and no `window.location.reload()` in the click path — the previous explore agent confirmed that. The actual cause is the bait-and-switch in [`openPermissionsModal`](../../frontend/src/components/DashboardLayout.tsx#L230): the agents modal closes (`setAgentsModalOpen(false)`) before the permissions modal can render (it's gated on async data). For the duration of the fetch — and forever, if the fetch fails or returns mismatched data — the user sees only the bare dashboard. That blink is what they perceive as "closing and refreshing."

The fix above (1) eliminates the blink because the Permissions modal mounts on the same render as the agents-modal close, and (2) eliminates the "modal never appears" failure mode because the modal renders even before data has arrived. Loading-state rendering also keeps focus inside the modal, satisfying acceptance scenario 4.2 (interactions stay inside the screen).

### Alternatives considered
- **Keep the agents modal open and stack the Permissions modal on top.** Rejected as the primary design because the existing UX treats "Permissions" as a deeper pivot, not a sub-modal. We do, however, briefly overlap them during mount — that's the safest cure for the perceived flash.
- **Pre-fetch all agent permissions when the agents modal opens.** Rejected: O(N) extra requests on a list view, only one of which the user will read.
- **Add a redirect/route change for Permissions.** Rejected: increases scope; user did not ask for a URL change, and the rest of the app uses modals here.

---

## R5. Schema & migrations

### Decision
No schema change. The existing `draft_agents` table at [`database.py:217–238`](../../backend/shared/database.py#L217-L238) already carries every column needed:

- `status` covers all spec'd lifecycle states (including `rejected` and `live`).
- `error_message`, `security_report`, `validation_report`, `generation_log` carry everything the user sees in the rejected/error states.
- `created_at` and `updated_at` timestamps are sufficient for any visible "last touched" UI.

`agent_ownership` is sufficient for FR-008/FR-009 (live agent visible to its owner). FR-016/FR-017 are satisfied by hard-deleting the `draft_agents` row via the existing `delete_draft` endpoint at [`api.py:1014`](../../backend/orchestrator/api.py#L1014); we do not need a `deleted_at` column because deletion is terminal and the spec does not require an "undo delete" path.

### Rationale
Constitution Principle IX is a hard gate on schema changes; every avoided column is one less migration to write, test, and roll back. The existing schema is genuinely sufficient — confirmed by reading the table definition and tracing every FR through it.

### Alternatives considered
- **Add `deleted_at BIGINT` for soft delete.** Rejected: spec does not require it, and "indefinite retention until owner deletes" + hard delete is simpler and consistent with how user content is treated elsewhere.
- **Add a separate `rejected_at` column.** Rejected: `updated_at` plus `status='rejected'` is enough for any UI ordering; `error_message` carries the *why*.

---

## R6. Observability requirements (Principle X)

### Decision
Add the following structured logs (no metrics infrastructure changes):

- `start_draft_agent`: log on subprocess spawn (info), on every retry attempt (debug), on port-discovery success (info), and on terminal failure (warning) — including stderr tail and exit code.
- `approve_agent`: log on entry with `draft_id`/`user_id`; on auto-promote success with `agent_id`; on rejection with which check failed.
- `_register_live_agent` (new helper invoked from approve_agent): log card registration with `agent_id` and `port`.
- Frontend (`CreateAgentModal`, `DashboardLayout`): no new client telemetry — toast errors via `sonner` for user-visible failures, browser console for developer-visible diagnostics.

### Rationale
Principle X requires observability sufficient to diagnose production incidents without code changes. Each fix above introduces a new failure mode; each gets a structured log that names the failing draft and the step that failed. We avoid adding a metrics library because no third-party deps are allowed (Principle V) and the existing logging infrastructure is sufficient.

---

## Open questions deferred from `/speckit.clarify`

| Area | Why deferred | Resolution |
|---|---|---|
| Accessibility / localization | Low impact for a bug-fix feature; existing components inherit existing a11y posture. | Maintain parity with existing components; no new a11y work in scope. |
| Scalability of draft processes | Not impacted by this change — failure modes addressed are per-draft, not throughput-bound. | None. |
| Detailed observability metrics | Principle V forbids new deps; structured logs (above) are sufficient for incident triage. | None. |

No NEEDS CLARIFICATION markers remain.
