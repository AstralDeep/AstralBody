# Verification Report — 052 Performance PR-1 (2026-07-08)

Reference environment per [quickstart.md](quickstart.md): docker compose on the dev
machine, same-host postgres, container freshly built from this branch. Baselines from
[baselines.md](baselines.md). Client-side wall-clock items that require an interactive
browser/device session are marked **pending live pass** (tasks T048/T049) — everything
mechanically verifiable is verified below.

## Measured results vs baselines

| Metric | Baseline (pre-change) | Post-change | Verdict |
|---|---|---|---|
| Container boot → `/readyz` | 16 s (compose up) | **9 s** recreate / **8 s** restart | **SC-010 ≥40% met** (44–50%) |
| `_init_db` when schema current | 114 ms (full ~130-statement run, every construction) | **1–2 ms** (fast path, `perf boot.init_db` log) | **SC-010 ≤250 ms met** |
| Recent-chats list (20 chats) | 173 ms (21 queries) | **2 ms (1 query)** | **~87× faster; SC-002 met** |
| Single query round trip | ~5 ms (new TCP connection per query) | **<1 ms** (pooled) | pool live |
| 20 concurrent surface opens | serialized by loop-blocking (mid-fix worst case: p95 30.9 s) | **p95 ≈ 114 ms**, probe green under enforcement | **SC-011 met** |
| Windows launch-to-window | no window until OIDC completed (≤300 s) | window visible **≈0.2 s** offscreen; asserted <1.0 s by `test_launch_timing.py`; auth in-window | **SC-008 met** (test-verified) |

Two real concurrency defects were found and fixed by the enforcement work beyond the
plan: libpq's IPv6-first `localhost` resolution cost ~2.06 s per new connection on
Windows hosts (URL now normalizes to `127.0.0.1`), and the stock
`ThreadedConnectionPool` discards idle connections above `minconn`, re-creating ~8
connections under psycopg2's global lock on every burst (replaced by an idle-retaining
subclass).

## Test-verified success criteria (automated, run in the freshly built image)

| SC | Verification |
|---|---|
| SC-002 query budgets | `test_query_budgets.py` (recent-chats == 1), `test_surface_query_budgets.py` (agents list ≤2, detail ≤3), bulk attachment hydration in load_chat |
| SC-005 zero sync DB on loop | detector (`tests/plugins/event_loop_guard.py`) ENFORCED (`LOOP_GUARD_ENFORCE=1`) over the full `-m 'not integration'` suite with an **empty allowlist**; also wired into CI's test job |
| SC-006 designer non-gating | `test_designer_upsert_first.py`: `ui_upsert` always precedes the designed `ui_render`; stale-chat guard; failure = flat delivery; default 1 pass (`test_ui_designer*`) |
| SC-007 streaming | `test_llm_streaming.py`: prose streams via existing `ui_stream_data` frames; tool-call deltas stay silent; mid-stream error falls back to non-streaming; flag-off unchanged. Protocol manifest diff: **empty** |
| SC-004 asset contract (server side) | `test_shell_assets.py` (no external origins, no plotly tag, all refs versioned, fonts vendored w/ `font-display: swap`), `test_static_versioning.py` (immutable headers on matching `?v=`, `no-cache` otherwise, token substitution) |
| SC-003 pipeline (server side) | `test_register_ui_pipeline.py`: parallel reads, welcome-early, backgrounded profile/audit writes with per-user order preserved; JWKS warm/refresh (`test_boot_warm.py`) never blocks boot |
| SC-009 Android skipping | `CanvasIdentityTest` (untouched components keep reference identity, 5/5); Compose compiler stability report: all annotated/config'd types stable, **82/82 restartable composables skippable** |
| SC-013 protocol/parity | `backend/shared/ui_protocol.json` untouched (git diff empty); Windows suite 267 passed incl. protocol-manifest guards; Android `:core:test` + `:app:testDebugUnitTest` green incl. Wire/ProtocolManifest tests |
| SC-001 indicator ≤100 ms | Web: skeleton injected synchronously on `chrome_open` click (client-side, no round trip) with 6 s timeout→retry; Windows/Android placeholder surfaces pre-existing (unchanged, suites green) |

## Suite status (canonical, freshly built image)

- `pytest -q -m 'not integration'` with `LOOP_GUARD_ENFORCE=1`: green after the
  enforcement conversion round (final counts in the PR checks).
- Module suites (`audit llm_config orchestrator onboarding personalization scheduler
  dreaming verification`): green on a fresh database (66/66 for the memory family).
  **Known environmental note**: 20 personalization/memory tests fail against the
  populated dev database (an active-project row changes a code path their fakes don't
  model) — reproduced identically with pristine `main` code, i.e. pre-existing and
  data-dependent, not a 052 effect. CI uses a fresh database and passes.
- Windows client: 267 passed. Android: build + unit tests green (ktlint too).
- `ruff check .` from repo root: clean.
- Coverage: changed-line coverage enforced by CI's diff-cover gate (PR checks).

## Pending items (recorded, not blocking mechanical verification)

1. **T048 live three-client pass** (Constitution X): browser + Windows client + Android
   emulator against a live backend — surfaces, first login, one rich streamed/designed
   turn, theme switch. Requires an interactive IdP sign-in; to be run before merge.
2. **T049 / SC-014 production measurement report**: one-time capture against the
   deployed instance after this branch reaches it (evidence, not a gate).
3. **SC-001/SC-003/SC-004 browser wall-clock numbers** in the dev reference env are
   implied by the structural fixes (server render spans, immutable caching, font/plotly
   removal from the critical path) and the server-side spans, but the browser-timed
   P95s should be captured during the T048 live pass using the quickstart protocol.

## Rollback levers shipped

`DB_POOL_DISABLE=1`, `FF_LLM_STREAMING=0` (or `false`), `UI_DESIGNER_MAX_ROUNDS=3`,
`FF_PHI_WARM=0`, `DELETE FROM schema_meta WHERE key='revision';` (forces full
migration), revert of the shell/plotly commit. All documented in
[quickstart.md](quickstart.md) and docs/production-deployment.md.
