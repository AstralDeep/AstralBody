# Phase 0 Research: LLM Text-Only Chat

**Feature**: 008-llm-text-only-chat
**Date**: 2026-05-01

This document records the research decisions taken to resolve all open questions before design. No `NEEDS CLARIFICATION` items remained after `/speckit.clarify`; this phase documents the implementation-level decisions implied by the spec and the existing codebase.

---

## Decision 1 — Reuse `_call_llm` directly with empty `tools_desc`

**Decision**: Do NOT introduce a new dispatch path; pass `tools_desc=[]` (or `None`) into the existing `_call_llm` (`backend/orchestrator/orchestrator.py:2471`) when the resolved tool list is empty. Keep the rest of the multi-turn ReAct loop intact — the loop will simply terminate after one assistant turn because no tool_calls arrive.

**Rationale**: `_call_llm` at lines 2507–2515 already conditionally adds `tools` and `tool_choice` to the provider kwargs only when `tools_desc` is truthy. So an empty/None list cleanly produces a tool-less chat completion call. This means the entire feature on the dispatch side is a *removal* of the early-return guard (lines 1831–1835), not a parallel code path.

**Alternatives considered**:
- A separate `_call_llm_text_only()` helper. Rejected — duplicates retry/credential resolution logic for no gain.
- A short-circuit that bypasses `_call_llm` and calls the LLM client directly. Rejected — would skip the existing audit-event emission and credential resolution invariants.

---

## Decision 2 — Inject text-only system-prompt addendum after canvas context block

**Decision**: When the resolved tool list is empty, append a fixed addendum to the system prompt (built at `orchestrator.py:1837–1896`) immediately after the canvas-context block (after line 1885) and before the knowledge-synthesis block. The addendum tells the LLM (a) it has no tools available, (b) it MUST NOT fabricate tool output, (c) when the user asks for an action requiring an agent it should briefly say so and suggest enabling agents.

**Rationale**: This was the recommended option in `/speckit.clarify` Q1 and matches the spec's FR-006a. Injecting after canvas context preserves the existing logical structure (instructions → file context → canvas context → mode-specific addendum → optional routing hints). The base prompt for tool-augmented turns is unchanged (FR-011).

**Alternatives considered**:
- A standalone minimal system prompt for text-only mode (Option D in clarify Q1). Rejected — discards file-context awareness, hurts continuity of multi-turn chats that started in tool-augmented mode.
- Pre-classifying user intent before dispatch (Option C). Rejected — brittle; the LLM is a better judge of "is this asking for an action".

---

## Decision 3 — Extend `agent_list` WS message with `tools_available_for_user` flag

**Decision**: Add a single boolean field `tools_available_for_user` to the existing `agent_list` WebSocket message (currently sent at `orchestrator.py:893, 911, 4037`). The flag is computed by running the existing `tool_permissions.is_tool_allowed` filter loop over all registered, non-security-blocked tools for the requesting user and returning `True` if at least one tool would be available on a fresh chat dispatch.

**Rationale**: The frontend already subscribes to `agent_list` (see `frontend/src/hooks/useWebSocket.ts:319-321`) and stores the agents array used by `DashboardLayout` and `ChatInterface`. A new boolean piggybacking on the same message is the minimum change that reaches every relevant React component without a new subscription. It also collapses three independent reasons for "no tools" (no agents / all permissions denied / all security-blocked) into a single signal the banner can render against — exactly what FR-007a needs.

**Alternatives considered**:
- A new dedicated `tool_availability` WS message. Rejected — adds a parallel state stream the frontend would have to keep in sync with `agent_list`.
- Computing the flag entirely on the frontend by walking the `agents` array. Rejected — duplicates the security_flags + tool_permissions logic, which is policy that must remain authoritative on the backend.

---

## Decision 4 — Reuse `_record_llm_call` with `feature="chat_dispatch_text_only"`

**Decision**: Emit an audit event for every text-only dispatch by calling the existing `_record_llm_call` (defined in `backend/llm_config/audit_events.py:195`) with `feature="chat_dispatch_text_only"`. The same call is already used for tool-augmented dispatches with `feature="tool_dispatch"`.

**Rationale**: This satisfies FR-009 ("MUST emit the same observability signals... distinguishable from agent-backed turns") with zero new audit machinery. Operators can filter by the `feature` field to count fallback usage. Aligns with Constitution Principle X observability requirement.

**Alternatives considered**:
- Brand-new audit event type. Rejected — duplicates existing schema.
- Plain structured-log line only, no audit event. Rejected — operators rely on the audit recorder for compliance traceability.

---

## Decision 5 — Banner is a new React component, not a backend-pushed `Alert`

**Decision**: Build a new frontend component `TextOnlyBanner.tsx` mounted at the top of the chat-messages region in `ChatInterface.tsx`. It reads the `tools_available_for_user` flag from the existing agents/state plumbing in `useWebSocket.ts` and conditionally renders. An `onOpenAgentSettings` callback prop opens the existing agents modal in `DashboardLayout`.

**Rationale**: The banner needs to react to per-turn state changes (FR-005) without a backend round-trip every render. Pushing an SDUI `Alert` from the backend would either be too late (after dispatch begins) or too noisy (re-pushed every state change). A frontend component reading the already-broadcasted state flag stays in sync with no extra messages. The current chat surface uses the same convention — Tailwind + Framer Motion, no registered UI primitive — so the banner doesn't introduce new design vocabulary.

**Alternatives considered**:
- Render via a sonner toast. Rejected — toasts are transient; FR-007a requires a persistent banner.
- Backend-pushed SDUI `Alert` reused on every text-only turn. Rejected — couples banner visibility to dispatch timing instead of live state.

---

## Decision 6 — Tutorial step added via the existing seed SQL

**Decision**: Add a new tutorial step `enable-agents` (audience='user', display_order=35) to `backend/seeds/tutorial_steps_seed.sql`, slotted right after the existing `open-agents-panel` step (display_order=30). The new row uses `ON CONFLICT (slug) DO NOTHING` per the file's existing convention.

**Rationale**: The existing onboarding subsystem (feature 005) already loads tutorial steps from this seed file. Adding an idempotent INSERT means deploys will pick it up automatically. The existing `open-agents-panel` step ("Browse available agents") points to the panel but doesn't explicitly tell users to *turn agents on* — the new step bridges that gap, satisfying FR-007b and the user's clarification ("add a part to the tutorial to tell users to turn on agents").

**Alternatives considered**:
- Edit the body of `open-agents-panel` in place. Rejected — the user explicitly asked to "add a part", implying a new step. Also, admin edits to existing steps are preserved (per file header), so editing the seed would not propagate to environments where an admin already touched the step.
- Add the step via the admin REST API at runtime. Rejected — not a deployable artifact; would not appear in fresh environments.

---

## Decision 7 — Draft-agent test chats keep their current behavior

**Decision**: Honor FR-010 by keeping the existing draft-test branch (`if draft_agent_id:` at `orchestrator.py:1792`) unchanged. The text-only fallback only fires for *non-draft* chats; in a draft test chat with zero usable tools, the existing draft-test diagnostics still surface.

**Rationale**: A user explicitly opted into testing a specific draft. Silently falling through to text-only would mask misconfiguration that the draft author needs to see. The simplest implementation: gate the new fallback on `not draft_agent_id`.

**Alternatives considered**:
- Apply text-only fallback uniformly. Rejected — violates FR-010 and degrades draft-development feedback.

---

## Open items: NONE

All FRs from spec.md map to the decisions above. No `NEEDS CLARIFICATION` markers remain.
