# Specification Quality Checklist: Real-Time Tool Streaming to UI

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-04-09
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- The user explicitly raised the architectural question "tool → agent → orchestrator → UI vs. tool → UI direct" and asked for security/performance research. The spec captures this as **FR-014** (a planning-phase deliverable) and **SC-008** (the decision must be recorded with reasoning), and **A-005** documents that the routing decision is intentionally deferred to `/speckit.plan`. The spec asserts the properties the chosen path must satisfy (auth boundary, isolation, fan-out, observability) so that requirements remain valid regardless of which path is selected.
- No `[NEEDS CLARIFICATION]` markers were inserted. All other gaps were filled with documented assumptions (A-001 through A-007).
- Items marked incomplete require spec updates before `/speckit.clarify` or `/speckit.plan`.

## Implementation Status

- **Implementation completed**: 2026-04-09. All 5 user stories (US1–US5) plus the foundational scaffolding shipped behind `FF_TOOL_STREAMING=false`.
- **Post-enable fixes (2026-04-13)**: First end-to-end dogfooding with `FF_TOOL_STREAMING=true` surfaced five integration bugs that 114 unit tests had missed — captured and fixed, new regression tests added:
  - **Agent message-loop deadlock (most severe)**: `BaseA2AAgent.handle_mcp_request` awaited `_handle_streaming_request` inline, so the agent's WebSocket message loop blocked for the entire lifetime of the stream. Because `live_system_metrics` is an unbounded `while True`, the agent could never accept another tool call. Fix: dispatch the streaming handler via `asyncio.create_task` so the loop keeps servicing other requests (and `ToolStreamCancel` messages). The handler still registers itself into `self._active_streams` for cancellation.
  - **Poll-tool registration**: legacy `streamable: {dict}` form (`get_system_status`, `get_cpu_info`, `get_memory_info`, `get_disk_info`) was rejected at `RegisterAgent` because `validate_streaming_metadata` required an explicit `streaming_kind`. Fix: `BaseA2AAgent._build_agent_card` now defaults `streaming_kind: "poll"` for the legacy dict form.
  - **Push auto-subscribe skipped**: the `ui_render` handler's stream-component guard (`if (isStreamComponent) continue;`) skipped both save AND subscribe, so push tools like `live_system_metrics` rendered a single snapshot and then never updated. Fix: split the guard so streaming components still trigger auto-subscribe via the push path.
  - **Wrong wire format on saved_components_list / chat_loaded**: both auto-subscribe sites always sent the poll-format message regardless of `cfg.kind`. Fix: centralised `sendStreamSubscribe(ws, toolName, cfg, params, chatId)` helper used by all three call sites; branches on `kind`.
  - **`_source_params` not tagged**: orchestrator now tags tool-call args onto the top-level component so the subscribe path replays the same arguments (needed for `interval_s` on `live_system_metrics`).
- **Test results**: 169 automated tests passing (98 backend pytest + 71 frontend vitest). New: `backend/tests/test_stream_system_status.py` (4 tests), `frontend/src/__tests__/stream_autosubscribe.test.tsx` (3 tests). Zero failures.
- **T099 manual quickstart**: pending operator walkthrough with the rebuilt container. All programmatic gates and unit invariants pass; first three quickstart steps (container healthy, agents registered without streaming-metadata rejections, frontend types green) pass automatically now that the fixes are deployed.
- **Deferred items** (unchanged): T023/T024 React.memo wraps (perf optimization), T092 30-min load test (structural bounds already verified by T091), T096/T097 coverage tooling (blocked on constitution V dep approval).
