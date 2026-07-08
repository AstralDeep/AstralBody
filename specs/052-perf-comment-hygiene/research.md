# Phase 0 Research: 052-perf-comment-hygiene

All decisions below were made against verified current code (four read-only verification
sweeps, 2026-07-08; file:line citations reflect that snapshot). No `NEEDS CLARIFICATION`
items remain.

## R1 — Database connection pooling

- **Decision**: Introduce `psycopg2.pool.ThreadedConnectionPool` inside `shared/database.py::Database`.
  `_get_connection()` borrows from the pool; every `fetch_one/fetch_all/execute` returns the
  connection via `putconn` in `finally` instead of `close()`. Pool bounds from env
  (`DB_POOL_MIN` default 2, `DB_POOL_MAX` default 10). Stale-connection recovery: on
  `psycopg2.OperationalError`/`InterfaceError` from a borrowed connection, discard it
  (`putconn(close=True)`) and retry once with a fresh connection. Kill switch
  `DB_POOL_DISABLE=1` restores today's connect-per-call behavior.
- **Rationale**: Verified: `psycopg2.connect()` per query at `database.py:25-28` and
  open/close in each of `execute/fetch_one/fetch_all` (`:1263-1296`); no pool import exists
  anywhere in the repo. `psycopg2.pool` ships inside the already-approved psycopg2 package —
  zero new dependencies (Constitution V). `ThreadedConnectionPool` (not `Simple`) because
  calls arrive from multiple threads (`asyncio.to_thread` workers, audit recorder thread,
  in-process agent tools).
- **Alternatives considered**: pgbouncer sidecar (new infra, rejected — deployment change);
  per-thread cached connections via `threading.local` (leaks under to_thread's growing
  thread pool; no bound); async driver (asyncpg/psycopg3 — new dependency, forbidden).
- **Sizing note**: `DB_POOL_MAX` must be ≥ tool-parallelism (`_MAX_PARALLEL_CONCURRENCY`)
  plus surface-render concurrency headroom; 10 covers the SC-011 20-concurrent-opens test
  because opens queue on the pool rather than each opening a TCP connection.

## R2 — Getting synchronous DB off the event loop

- **Decision**: Add an async facade on `Database`: `afetch_one/afetch_all/aexecute` =
  `await asyncio.to_thread(<sync twin>)`. Migrate the async call sites reachable from
  HTTP/WS/chat paths (orchestrator request handlers, chrome surface `render()`s,
  `HistoryManager`, `WebSessionStore`, `WorkspaceManager`, `ToolPermissionManager`,
  attachment repos) to the facade. Sync contexts (scripts, tests, thread-side code, the
  audit repository's already-offloaded insert) keep the sync methods.
- **Rationale**: Verified that outside `audit/recorder.py:89,178` and the `/readyz` ping
  (`orchestrator.py:8313`), **every** repository DB call runs directly on the loop.
  Wrapping at the `Database` seam (one class) is the smallest change that fixes all
  callers; per-call-site `to_thread` sprinkling would be unreviewable and incomplete.
- **Alternatives considered**: run the whole app under more uvicorn workers (doesn't fix
  intra-user blocking, changes deployment model — out of scope); rewrite on an async
  driver (new dependency).

## R3 — Event-loop blocking detector (FR-017, SC-005)

- **Decision**: Test-harness guard: a pytest fixture (enabled for the orchestrator/webrender
  suites) monkeypatches `Database.fetch_one/fetch_all/execute` (and `_get_connection`) to
  call `asyncio.get_running_loop()`; if it *succeeds* (we are on the loop thread), the guard
  raises `BlockingDBOnEventLoop` with the call stack. Runs green in CI as part of the normal
  test job. A short allowlist (module-level, checked in) covers deliberate sync-context
  calls during the migration window and must be empty by feature completion.
- **Rationale**: Deterministic, zero-dependency (stdlib), and precise — it fails the exact
  offending call rather than sampling latency. `loop.slow_callback_duration` logging is kept
  as a dev-mode aid (`ASTRAL_DEBUG_SLOW_CALLBACKS=1`) but is too noisy/probabilistic to gate CI.
- **Alternatives considered**: asyncio debug mode assertions (coarse, whole-callback
  granularity); runtime production detector (overhead + false positives — rejected).

## R4 — Hot-path query consolidation (FR-003, FR-020, SC-002)

- **Decision**:
  - `get_recent_chats` (`history.py:222-232`): single query using a correlated subquery
    for the last-message preview (portable through `_translate_query`), replacing the
    verified 1+N loop (default 21 queries → 1).
  - `load_chat` attachments (`orchestrator.py:1627-1645`): one bulk query joining
    `message_attachment` × `user_attachments` for all message ids (`WHERE message_id IN`),
    replacing per-message + per-attachment lookups.
  - Agent detail (`webrender/chrome/surfaces/agents.py:474-490`): remove the per-render
    `backfill_per_tool_rows` (it re-scans `tool_overrides` every open even when there is
    nothing to backfill — verified unguarded) by running the backfill once as a guarded
    `_init_db` migration; merge `get_effective_tool_permissions`' two `fetch_all`s
    (`tool_permissions.py:390-404`) into one (`permission_kind IS NULL OR NOT NULL`, split
    in Python); combine ownership + disabled + safe reads. Net ≤3 round trips.
  - Agents list: combine `get_all_agent_ownership` + `get_user_disabled_agents` scans into
    ≤2 queries; add supporting index only if measurement demands (Constitution IX delta).
- **Rationale**: Verified N+1s are the dominant per-open cost after connection overhead;
  all fixes are plain SQL against existing tables.
- **Alternatives considered**: response caching to hide the N+1s (masks the defect, adds
  staleness surface — rejected as primary fix; see R6).

## R5 — Permission-resolution memoization (FR-019)

- **Decision**: A per-turn memo dict keyed `(user_id, agent_id, tool, kind)` threaded
  through the tool-dispatch path (created in `handle_chat_message`, passed to
  `is_tool_allowed`), so the verified 3-query pattern (`tool_permissions.py:255-283`) runs
  at most once per distinct tool per turn. No cross-turn reuse — next turn re-reads, so a
  revocation is visible on the next message (spec's staleness bound). The existing 30s
  safe-agent caches (`:309-312`, `:338`) stay as-is (already precedent).
- **Alternatives considered**: TTL cache across turns (violates the request-scoped-only
  clarification for permission decisions); batch-prefetch all tools' rows at turn start
  (viable future optimization, more invasive — deferred).

## R6 — Surface latency: skeleton-first, then bounded queries; no HTML caching in v1

- **Decision**: (a) Web modal skeleton: on `chrome_open` click, `client.js` immediately
  renders the modal shell with the existing skeleton pattern (reusing
  `astral-skeleton` CSS, `client.js:213-228`) and a client-side ~6s timeout → retry state
  (mirroring the Windows T040 surface-timeout pattern); `chrome_render` replaces it.
  Windows/Android already show placeholder dialogs/screens (verified) — no change beyond
  keeping their suites green. (b) Server render cost is fixed by R1/R2/R4 rather than by
  caching rendered HTML. FR-004's cache allowance is held in reserve: only if measured
  post-fix P95 misses SC-001 do we add a user-scoped, write-invalidated, pre-ROTE data
  cache (never cross-user, never past-TTL permission data).
- **Rationale**: With pooling + off-loop + ≤3 queries, surface renders are tens of ms of
  DB work; caching would add invalidation risk for little gain. Skeleton fixes perceived
  latency immediately and satisfies FR-002.

## R7 — Web asset pipeline (FR-007..FR-010, SC-004)

- **Decision**:
  - **Versioned immutable caching**: extend `_static_asset_version` (verified: hashes only
    `client.js`+`astral.css`, `orchestrator.py:325-347`) to a per-file version map covering
    vendor JS, fonts, and images; shell URLs carry per-file `?v=<hash>`. `_NoCacheStaticFiles`
    becomes version-aware: requests whose `?v` matches the current file hash get
    `Cache-Control: public, max-age=31536000, immutable`; unversioned/mismatched requests
    keep today's `no-cache` + ETag flow. Shell stays `no-store`.
  - **Fonts self-hosted**: vendor the woff2 files for the weights actually used (audit
    usage; Inter + JetBrains Mono, same families per Constitution XII) under
    `webrender/static/fonts/`, replace the `@import` to googleapis.com (`astral.css:11`,
    verified the only font source, zero vendored files today) with `@font-face` +
    `font-display: swap` and `<link rel="preload">` in the shell. No external origin
    remains on the render path.
  - **Plotly lazy-load**: remove `plotly.min.js` from the shell `<head>` (verified
    render-blocking, no defer, `shell.html:31`). `client.js` gains a loader: first
    chart-bearing render injects the script; `initCharts` (verified to silently no-op when
    `Plotly` is undefined and never re-init, `client.js:130-131`) gains an on-load re-scan of
    pending chart nodes; `requestIdleCallback` prefetch warms it after boot so the first
    chart turn is usually already warm.
  - **Tailwind stays** — verified load-bearing (≈450+ utility sites incl. arbitrary values,
    responsive variants, and runtime theme-reactive `astral-*` color utilities bound to live
    CSS vars; astral.css defines zero generic utilities). It becomes immutable-cached like
    other vendor assets; it remains render-blocking by design (deferring it would FOUC).
  - **Connect delay removed**: `setTimeout(connect, 200)` (`client.js:1026`) → immediate
    `connect()`.
- **Alternatives considered**: dropping/hand-trimming Tailwind (verified infeasible without
  visual regression); build-time Tailwind purge (introduces a web build step — out of
  scope by spec); system-font stack (changes the visual design language — conflicts with
  Constitution XII consistency).

## R8 — Sign-in handshake pipeline (FR-011, FR-012)

- **Decision**: (a) JWKS warm: startup task fetches `get_jwks(jwks_url)` (verified no boot
  warm exists; 600s TTL, request-path-only callers) and a background task refreshes every
  ~500s so the cache never goes stale for interactive validation; IdP failure at boot logs
  and retries with backoff — boot and `/readyz` are not blocked; validation behavior stays
  fail-closed. (b) `register_ui` pipeline: welcome `ui_render` is sent as early as possible;
  independent reads (user prefs, `compute_tools_available_for_user`, dashboard data) run
  concurrently via `asyncio.gather` over the R2 facade; non-essential writes (profile save,
  audit emission) move off the critical path via `create_task` while preserving audit
  completeness (records still written per turn, order within the user's chain preserved by
  the existing per-user audit lock).
- **Alternatives considered**: longer JWKS TTL (stale-key rotation risk); caching the
  welcome render (it's already static-cheap once the pipeline unblocks).

## R9 — Designer: upsert-first delivery + 1-pass default (FR-013, FR-014)

- **Decision**: In `_deliver_round_components` (`orchestrator.py:6892`), the web/voice
  design path sends the `ui_upsert(ops)` to the client **immediately** (exactly what the
  native branch at `:6915-6918` and the failure fallback at `:6987-6988` already do), then
  runs the design passes; on success the designed full-canvas `ui_render` is pushed as an
  in-place refinement (existing `_push_canvas`/morph-anchor machinery preserves component
  identity). The designed push is dropped if the socket's active chat changed meanwhile.
  Default `DEFAULT_MAX_ROUNDS` 3 → 1 (per clarification); `UI_DESIGNER_MAX_ROUNDS` still
  overrides; per-pass 8s cap unchanged; `FF_UI_DESIGNER` semantics unchanged.
- **Rationale**: Verification settled the contested fact: today the web user receives **no
  component frame until `design_round` returns** (persistence-only upsert at `:6922`; first
  frame at `:6983`/`:6988`) — up to 24s behind native clients on the same turn. Upsert-first
  makes designer latency invisible and converts its failure mode to "arrangement never
  arrives," which is the already-shipped fallback rendering.
- **Alternatives considered**: killing the designer (loses a shipped feature); designing
  before tool results render (impossible — needs the components).

## R10 — Narrative token streaming via existing frames (FR-015)

- **Decision**: Stream the final narrative turn through the **existing** streaming frame
  path (`ui_stream_data` — verified already handled by web `client.js:329`, Android
  `Streaming.kt:65`, Windows `streaming.py`; frame types already in `ui_protocol.json`'s
  streaming category — zero manifest change). Mechanics: `_call_llm` gains an opt-in
  streaming mode used by the chat loop; the sync OpenAI client iterates
  `stream=True` chunks inside the existing `to_thread` worker and posts deltas to the loop
  (`loop.call_soon_threadsafe`); because the loop can't know a priori that an iteration is
  the final (tool-free) one, chunks are buffered until the first delta discriminates:
  `delta.tool_calls` → abort streaming, fall through to today's non-streamed handling;
  `delta.content` → open a narrative stream and emit. Final `ui_render` still lands as the
  authoritative replace (existing morph). Gated by `FF_LLM_STREAMING` (default on) with
  automatic per-call fallback to non-streaming on any provider error (router/provider
  variance is a known quirk); non-streaming providers behave exactly as today (SC-007 is
  conditional by spec).
- **Alternatives considered**: new dedicated frame types (needless manifest change —
  violates the additive-minimal posture); SSE side-channel (parallel transport, rejected).

## R11 — Schema fast-path marker (FR-027)

- **Decision**: New table `schema_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)` (name
  deliberately avoids the existing, unrelated `audit_events.schema_version` column) with a
  `revision` row holding `SCHEMA_REVISION`, a constant in `database.py` bumped by any PR
  that touches `_init_db`. Boot: read marker (1 query); match → skip the verified ~130+
  DDL/guard statements; mismatch/absent → run full idempotent migrations then upsert the
  marker. A unit test hashes the `_init_db` (+ helpers) source and fails when the hash
  changes without a revision bump — making "forgot to bump" impossible to merge. Rollback:
  `DELETE FROM schema_meta WHERE key='revision'` forces a full run next boot (documented in
  data-model.md).
- **Alternatives considered**: per-migration ledger table (bigger change than needed for a
  single-file migration runner); hashing the live schema via information_schema each boot
  (that inspection cost is the thing being removed).

## R12 — PHI analyzer pre-warm (FR-028)

- **Decision**: At orchestrator startup, a daemon thread calls `get_phi_gate()` (verified
  lazy module singleton, `phi_gate.py:190-198`, no boot preload today, `/readyz` untouched)
  so the 2–5s Presidio+spaCy load happens in the background. Readiness does not wait on it;
  a first request racing the warm-up simply blocks on the singleton as today (no worse).
  Honors the existing enable/disable flag semantics.

## R13 — start.py readiness polling (FR-029)

- **Decision**: Replace the fixed `time.sleep(2)` after orchestrator launch
  (`start.py:85`) with a bounded `/healthz` poll (fast path: proceeds the moment the
  orchestrator answers), and drop the 1s-per-custom-agent sleep (`:119`) in favor of
  registration-independent spawning (agents already retry registration). Supervisor loop
  and production exit-code semantics unchanged.

## R14 — Windows: window-first launch (FR-023, FR-024)

- **Decision**: Reorder `main()` (`app.py:2635-2652`): construct and show `MainWindow`
  immediately with a "Signing in…" in-window status; run `resolve_auth` (discovery/loopback
  wait/exchange — verified blocking up to 300s pre-window today) in a worker thread
  (`QThread`); on token arrival reuse the **existing** rebuild-with-new-token flow
  (`app.py:1936-1953`, feature 036) to start the transport — no new token-injection
  mechanism needed. Cancel button aborts the loopback wait and offers retry/quit. The
  first-run config prompt and `_init_workspace` picker (verified: workspace only gates
  win_agent file tools, not rendering) are deferred until after first paint / first actual
  use. Theme restyle: keep the intentional full rebuild (verified rationale: renderers read
  palette globals at render time, so effectively all components are palette-dependent —
  FR-024's "unaffected components" set is empty for theme changes and the requirement is
  satisfied by documenting exactly that); the per-frame path keeps deep-equality reuse with
  a cheap early-exit (skip compare when the incoming list is reference/`==`-identical).
  Launch-to-window timing test extends the existing offscreen harness + stub pattern
  (`tests/conftest.py:10`, `test_message_routing.py:49-54`).
- **Alternatives considered**: adding `OrchestratorClient.set_token()` (needless — rebuild
  path exists and is tested); pre-window splash screen (still no interactivity; rejected).

## R15 — Android: stability annotations + verified skipping (FR-025)

- **Decision**: Annotate `@Immutable` on the core wire/UI types (`Component` — sound:
  kotlinx `JsonObject` is an immutable Map; `Agent`, `ChatSummary`, `ChatTurn`,
  `ChromeMenuModel`/`MenuItem`, `ThemePalette`, `UiState` and friends — verified zero
  stability annotations exist today). `Canvas.apply` already preserves reference identity
  for untouched components (verified `Canvas.kt:19-39`), so annotations directly unlock
  Compose skipping. Enable Compose compiler metrics/reports in debug builds (greenfield
  gradle flag) and add a reducer test asserting untouched components keep reference
  identity across `apply` (guards the skipping precondition). SC-009 verification = the
  reference-identity test + compiler stability report showing the annotated types stable.
- **Alternatives considered**: `strongSkipping` compiler experiments (version-dependent
  behavior change; annotations are explicit and sufficient).

## R16 — Timing instrumentation (FR-030)

- **Decision**: New tiny `shared/perf.py` (stdlib-only): `perf_span(name, **ctx)` context
  manager emitting one structured log line `perf <name> duration_ms=<int> <ctx>` via the
  standard logger, following the existing `int((time.monotonic()-start)*1000)` idiom
  (verified in `audit/middleware.py:54-63`, `llm_config/api.py:167-204`; no shared helper
  exists). Instrument: chrome surface render (per surface key), `register_ui` phases,
  chat-turn phases (route/tools/designer/narrative), boot phases (`_init_db`, JWKS warm,
  PHI warm), static-asset version map build. Log-only (no schema, no PHI/PII — names and
  ids only). The measurement protocol in quickstart.md consumes these lines.
- **Alternatives considered**: audit-event metadata (write amplification on the hash
  chain); a metrics dependency (forbidden).

## R17 — Comment-hygiene tooling & execution (FR-033..FR-039)

- **Decision**: New CI/dev-side checker `scripts/comment_policy.py` (repo root `scripts/`
  or `backend/scripts/` — final home chosen in tasks; stdlib only: `tokenize` + `ast` for
  Python; conservative string-aware line lexers for JS/CSS and Kotlin). Two modes:
  - `--report`: full inventory (all comment categories, including judgment-required ones).
  - `--check`: **mechanical rules only**, wired as a CI step: missing file-purpose header;
    section-banner patterns; commented-out-code heuristic (≥2 consecutive comment lines
    that parse as code via `ast.parse`); spec-marker breadcrumbs (`\b(T\d{3}|FR-\d{3}|US\d+)\b`
    in comments); directive-loss guard (a diff may not delete `noqa`/`type: ignore`/
    `pragma`/`fmt`/eslint directives — checked against git diff). Rationale-comment
    worthiness ("would a senior dev be confused?") is explicitly NOT machine-judged; it
    stays in human review (default adopted after the question dialog was declined; see
    plan.md "Open defaults").
  - The sweep itself is executed per-area (backend modules, webrender static, windows,
    android) with the checker's `--report` guiding manual edits; behavior-neutrality is
    proven by the full suite + lint + a per-area `python -m compileall`/AST-shape spot check.
- **Alternatives considered**: fully scripted auto-strip (unacceptable false-positive risk
  on rationale comments and string edge cases); full permanent gate with allowlist
  (friction on every future justified comment); one-time-only check (repo drifts back).

## R18 — Delivery/PR strategy

- **Decision** (default adopted after the question dialog was declined; override anytime):
  **Two sequential PRs from this one spec.** PR 1 = all performance work + tests +
  instrumentation (this branch, `052-perf-comment-hygiene`). PR 2 = the comment-hygiene
  sweep + checker CI wiring (follow-up branch cut after PR 1 merges, e.g.
  `052-perf-comment-hygiene-b`). tasks.md phases map 1:1 onto the two PRs.
- **Rationale**: The hygiene diff (~800 files, comment-only) would bury the perf diff in
  one PR; separated, PR 2 is verifiable-at-a-glance as behavior-neutral, and the perf PR's
  coverage gate isn't diluted. Perf-first ordering avoids rewriting freshly-cleaned hot
  files during surgery.
- **Alternatives considered**: one PR with ordered commits (reviewable per-commit but one
  giant gate run and unreadable file list); hygiene-first (cleans files right before the
  perf surgery rewrites them).

## Baseline capture (FR-032)

First implementation task (before any optimization lands): record P95 baselines in
`specs/052-perf-comment-hygiene/baselines.md` for — each surface open (server render +
click-to-content), first-login-to-cards (warm/cold), chat-turn non-model overhead, Windows
launch-to-window, container boot-to-ready, and repeat-visit static transfer — using the
quickstart.md protocol, in the dev reference environment. SC-010's ≥40% boot improvement
and the production evidence report (SC-014) both reference these.
