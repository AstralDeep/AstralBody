# T033 — Real-browser gate (evidence)

**Date**: 2026-06-10 | **Verdict**: PASSED-WITH-NOTES (critic)
**Environment**: rebuilt `astraldeep` container (py3.11) on `:8001`, mock auth (admin),
LLM `deepseek-ai/DeepSeek-V4-Pro`. Headless Chromium (Playwright); WS frames captured.
Scripts: `backend/tmp/e2e/t033_*.py`; screenshots in this directory.

## CHROME scenario — 9/9 PASS

- Top bar + full static menu served at `GET /` (admin group present under mock-admin).
- Menu: mouse + full keyboard semantics (Enter opens/focuses first item, arrows move,
  Escape closes + focus restore, outside click closes) — FR-017.
- All 7 surfaces open with correct titles, non-trivial bodies, zero error blocks;
  Escape clears the modal each time.
- Permissions round-trip on general-1: toggle → Save → "Permissions saved." notice →
  persisted across fresh reopen → restored (FR-016/FR-012-013 heritage).
- Theme: Ocean preset applied instantly (`--astral-primary` 99 102 241 → 14 165 233),
  **persisted across full page reload** via the `user_preferences` frame; restored.
- Audit surface: 50 rows, detail with correlation id, back, `event_class` filter re-render.
- Tour: 14 steps loaded from `tutorial_step`, highlight applied to resolvable targets,
  skip works; `chrome_tour_event started/skipped` frames captured.
- Sign-out: `/auth/logout` 303 chain clean (mock auth re-signs in by design).
- Zero console errors / uncaught exceptions across the whole run.

## AGENTIC scenario — 7/7 PASS (SC-001/SC-002/SC-007)

Prompt: *"Convert the Roman numeral MCMXCIV to an integer. I know you don't have a
tool for this — build one."* — triggered `create_capability` on the **first attempt**.

- Creation card ("Draft agent: Roman Numeral Converter") with Approve/Refine/Discard
  + self-test verdict rendered ~110 s after send (generation + self-test, ≪ 10-min SC-001).
- Drafts surface listed the draft with the "from chat" badge (origin=auto_chat in DB) — SC-007.
- Approve → security gate → **live in ~11 s** → re-sent the original request →
  the new agent's `roman_to_integer` tool ran → canvas rendered **1994**.
- Dedup (FR-007): repeating the request created **no** second draft.
- Audit: 4 `agent_lifecycle` events (`gap_detected → auto_created → self_test → approved`)
  share one correlation_id (= draft id).
- `docker logs`: zero tracebacks.

## Notes / follow-ups (non-blocking, fixes applied post-gate)

1. **Fixed**: tour Next-click closed the settings menu before the in-menu highlight was
   visible (client.js outside-click now ignores `#astral-tour-card`).
2. **Fixed**: self-test summary undercounted tools ("0 tool(s) exercised") —
   `_summarize_outputs` now also attributes via component `_source_tool` tags.
3. **Fixed**: "from chat" badge contrast raised for the dark theme.
4. Environment-constrained partials (compensated by unit tests): audit cursor "Next"
   click (covered by `test_surface_audit.py`); literal signed-out screen (mock auth
   re-signs in; verify the Keycloak login landing once against the real realm).
   Non-admin DOM-absence is unit-proven (`test_topbar.py`, `test_chrome_events.py`) since
   mock auth makes every browser session admin.
