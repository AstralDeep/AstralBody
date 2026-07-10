# Quickstart: 052-perf-comment-hygiene — Measurement & Verification Runbook

## Reference environment (binding, per clarification 2026-07-08)

- Dev machine, `docker compose up -d` (postgres + astraldeep), browser/clients on the
  same host. `.env` has `ASTRAL_ENV=development`.
- P95 = 95th percentile over **≥20 trials**, cold trial discarded unless the metric is
  itself a cold-start metric. Record machine load conditions with each capture.
- All captures land in `specs/052-perf-comment-hygiene/baselines.md` (before) and the
  final verification report (after). A one-time production capture of the SC-001/003/004
  metrics against the deployed instance is a required evidence deliverable (SC-014, not
  a gate).

## Server-side timings

Grep the orchestrator log for the `perf` lines (`shared/perf.py` spans):

```bash
docker logs astraldeep 2>&1 | grep '^perf ' | sort | awk '{...}'   # or the helper below
docker exec astraldeep bash -c "cd /app/backend && python scripts/perf_report.py"  # summarizes P50/P95 per span
```

Spans of record: `surface.render.<key>` (SC-001 server budget ≤150ms),
`register_ui.*`/`welcome.render` (SC-003 server share), `turn.*` (SC-006 ≤1.0s non-model
overhead), `boot.init_db` (SC-010 ≤250ms fast path), `boot.jwks_warm`, `boot.phi_warm`.

## Client-side measurements

- **SC-001 (surfaces, web)**: browser DevTools performance panel — click a settings menu
  item; indicator must appear ≤100ms (skeleton node insertion), `chrome_render` content
  ≤400ms P95. Repeat per surface: agents (list+detail), history, audit, attachments,
  personalization, theme, timeline.
- **SC-001 (Windows/Android)**: existing placeholder dialogs/screens count as the
  indicator; content timing from the WS frame receipt logs / Android logcat timestamps.
- **SC-003 (first login)**: DevTools → preserve log → complete IdP sign-in → measure
  redirect→welcome-cards-painted. Warm-cache run = second sign-in same profile; cold =
  fresh profile. No request to a non-localhost origin may appear before first paint.
- **SC-004 (repeat transfer)**: DevTools network panel, second visit, `/static/*`
  transferred bytes <100KB total.
- **SC-008 (Windows launch)**: `pytest windows-client/tests/test_launch_timing.py`
  (offscreen harness, auth stubbed) asserts window-visible ≤1s; manual stopwatch run on
  reference hardware for the report.
- **SC-011 (concurrency)**: `python backend/tests/perf/concurrent_surfaces.py --n 20`
  (in-process VirtualWebSocket harness) — P95 ≤ 2× single-user P95.

## Automated gates (run in CI, runnable locally)

```bash
docker exec astraldeep bash -c "cd /app/backend && python -m pytest -q"      # full suite incl.:
#   - event-loop detector (BlockingDBOnEventLoop on any sync DB call on the loop)
#   - query-count assertions (history==1, agent detail<=3, agents list<=2, attachments bulk==1)
#   - schema fast-path test + SCHEMA_REVISION source-hash guard
#   - streaming discrimination + fallback tests; designer upsert-first tests
ruff check .                                                                  # repo root, host/CI
python scripts/comment_policy.py --check --diff origin/main                   # PR 2 gate (mechanical rules)
python scripts/comment_policy.py --report backend/orchestrator                # sweep worklist per area
```

Android: `cd android-client && ./gradlew :app:testDebugUnitTest` (reducer
reference-identity test) and inspect the Compose compiler stability report (debug build)
for the annotated types. Windows: `cd windows-client && python -m pytest -q`.

## Kill switches / rollback levers

| Lever | Effect |
|---|---|
| `DB_POOL_DISABLE=1` | legacy connect-per-query |
| `FF_LLM_STREAMING=0` | non-streamed narrative (today's behavior) |
| `UI_DESIGNER_MAX_ROUNDS=3` | restore multi-round designing |
| `FF_UI_DESIGNER=0` | designer off (existing flag) |
| `DELETE FROM schema_meta WHERE key='revision'` | force full migration run next boot |
| Revert shell tag / loader commit | plotly back in `<head>` |

## Definition of done (maps to SCs)

1. `baselines.md` captured **before** the first optimization merge (FR-032).
2. Every SC-001..SC-011 target met in the reference environment; numbers recorded.
3. CI green (all Constitution XI gates + new detector/query-count/asset checks); protocol
   drift guards green on web/Windows/Android; `ui_protocol.json` diff empty.
4. Live three-client check: browser + Windows client + Android emulator against the dev
   backend — surfaces, first login, a rich chat turn (streamed narrative + designed
   refinement), theme switch.
5. SC-014 production evidence report attached to the feature dir.
6. PR 2 only: `comment_policy.py --check` clean repo-wide; directive count unchanged
   (588); full suite green; diff is comment/docstring-only.
