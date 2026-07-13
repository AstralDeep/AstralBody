# US4 + US5 — live workflow verification (real auth, web), 2026-07-13

**Setup**: backend serving branch @ 0beeb6f (+ versions-hydration fix),
`USE_MOCK_AUTH=false`, operator's real Keycloak session in Chrome, operator's
real LLM provider (`api-llm-factory.ai.uky.edu`). Driven end-to-end in the
browser as the operator's requested functional scenario: *find medical/defense
grants → select currently open → draft the application → download.*

## What was verified

1. **US2 visual (chat-driven)**: "stream live system metrics" → skeleton →
   the Live System Metrics card FILLED LIVE mid-turn and kept morphing in
   place (CPU 0.6%→0.4% across frames) under ONE canvas node
   (`wc_ca87307a091f644d`) — no `stream-<id>` twin, no double render.
2. **US4 provenance derivation, live**: web-research result cards render
   **✓ tool data** (grounded); the model-synthesized Document card renders
   **✦ AI-generated** — distinct trust marks from the same turn's data.
3. **US4 refine, full pipeline**: dice-roll card → ✎ refine → "add a row
   showing the average roll value" → the SAME component gained an
   AVERAGE ROLL 4 metric (correct) and its badge flipped to **≈ estimated**
   (D10: refined without re-running the source tool).
4. **Grant workflow**: 3 research turns over live DuckDuckGo (real 2026 data:
   DARPA BTO HR001126S0003, RAPIID DARPA-PA-26-09 due 7/29/26, CDMRP FY25
   PRMRP/PRCRP, NIH DP2 RFA-RM-27-002…); synthesis turn correctly EXCLUDED
   the STO BAA (closed 2025-12-19) and flagged the unverifiable CDMRP
   deadline; pre-proposal draft rendered as a full canvas document.
5. **US5 canvas export**: ⬇ Export page → `canvas-<chat>.html` (137 KB)
   downloaded; self-contained (content links only), carries the full
   pre-proposal and the "Generated 2026-07-13 by AstralDeep" stamp.

## Findings (none block 055; filed as follow-ups)

- **F1 — round exhaustion on research turns** (2× reproduced): the 10-round
  loop empties `tools_desc` before multi-agency research can synthesize; the
  model keeps searching. Wants a synthesis nudge or a per-class round budget.
- **F2 — misleading exhaustion alert**: the all-tools-denied break renders
  "All available tools are restricted by your permission settings" when the
  actual cause is the round budget. Honest-UX fix: context-aware message.
- **F3 — stale page token 401**: a long-lived web tab's in-memory bearer
  expires while the WS session silently renews; REST calls (export, upload)
  then 401 until reload. Pre-existing pattern; wants a 401→`/auth/session`
  refetch-and-retry in `client.js`.
- **F4 — `word_document` JSON fragility**: long tool arguments from the
  operator's model broke JSON at ~2.5 KB; surfaced honestly, retried, failed
  honestly. Upstream-model robustness; the doc-card path is the workaround.
- **F5 — chat-rail bold rendering**: the rail bubble shows literal `**…**`
  for the long-answer summary (canvas renders it correctly).

## Native targets

Windows-twin/Android/Apple live drives remain the operator's pass: the iOS
sim reinstall reset its token store back to the sign-in screen (screenshots
in `us1/sims/`); the macOS Debug app is running under the operator's session.
All native behaviors are pinned by their committed unit tests (Windows 348,
AstralApp 30, Android CI).
