# Phase 0 Research: Cross-Client Chrome & Settings Parity

All decisions are grounded in the existing code found during discovery. Exact source-of-truth: `backend/webrender/chrome/topbar.py` (menu already data-driven via `_menu_entries`), `backend/orchestrator/chrome_events.py` (surface dispatch + server-side admin gate), `backend/rote/capabilities.py` (device profiles incl. `windows`/`android` with `supported_types`).

## D1 — How do native clients obtain the menu model?

**Decision**: One server-side builder `build_menu_model(roles, *, pulse_enabled, ...)` produces the canonical model; it is (a) rendered to HTML by `topbar.render_topbar` for the web (no visual change), (b) serialized and pushed to native clients as a `chrome_menu` WS frame emitted right after the `register_ui` acknowledgment, and (c) served by a role-aware `GET /api/chrome/menu` for re-fetch and tests. The served model is **already role-filtered and flag-resolved** so a client renders it verbatim.

**Rationale**: The register handshake is the natural bootstrap point (native clients already send device caps there), giving the menu with no extra user-visible round trip. A REST twin mirrors how the Windows client already uses REST (`GET /api/audit`) and gives a clean unit/integration test target. A single builder guarantees the web and native renderings can never diverge (Constitution XII).

**Alternatives rejected**: (i) Hard-coding the menu per client — the drift this feature exists to kill. (ii) Only a REST endpoint — adds a round trip and a loading state to the top bar. (iii) Only inline in the register ack with no REST — harder to test and no re-fetch path.

## D2 — How is a settings surface delivered as SDUI to native clients?

**Decision**: `chrome_events._render_surface` branches on the connecting device target. Web (`browser`) keeps the existing HTML modal (`chrome_render {region:"modal", html}`). Native SDUI targets (`windows`, `android`) receive the surface's **astralprims components** (a new `components()` path on each surface), ROTE-adapted, as a `chrome_surface {region:"modal", surface_key, title, components:[...]}` frame the client renders through its **existing** component renderer (Android `render/Renderer.kt` + `CanvasHost`; Windows `renderer.py`) into a modal/sheet. As each surface gains `components()`, the **web** modal also renders from those components (the orchestrator renderer already maps components→HTML), so each converted surface has one source for all targets. Until a surface is converted, native `chrome_open` returns a labeled placeholder component (FR-013) while the web keeps its current HTML.

**Rationale**: Reuses the fully-built native SDUI renderers (no per-surface native code), keeps the web working throughout, and lets conversion proceed surface-by-surface (P2) without a big-bang. Matches Constitution II/XII (astralprims-composed, orchestrator-rendered, ROTE-adapted; thin clients).

**Alternatives rejected**: (i) Native re-implementation of each surface — violates thin-client/XII and drifts. (ii) Embedding a web view for chrome on native — explicitly excluded by both native clients' design (no QtWebEngine; no Android WebView).

## D3 — Role-gating on native clients

**Decision**: The served menu model is role-filtered server-side (ADMIN TOOLS omitted for non-admins), so clients render it verbatim — no client-side role logic needed for visibility. Server-side authorization stays authoritative: `chrome_events._render_surface` continues to refuse `ADMIN_ONLY` surfaces for non-admins and audit the refusal, independent of any client. Native clients that already decode the JWT keep doing so only for display niceties, never as the authority.

**Rationale**: Least client logic, strongest guarantee. A compromised/old client cannot reveal admin items (they aren't in its model) and cannot invoke admin surfaces (server refuses). Matches Constitution VII + XII.

**Alternatives rejected**: Sending the full model to all clients and gating client-side — leaks the admin item set and duplicates the authority.

## D4 — Theme on native clients (P3)

**Decision**: The Theme surface (SDUI) offers the same presets; selecting one persists to `user_preferences.theme` (existing `set_user_preferences`) and emits the active theme's 7 channels (bg/surface/primary/secondary/text/muted/accent) to the client. Native clients map those channels to their native theme tokens (Android Compose color scheme replacing the fixed `AstralColors`; Windows Qt palette in `theme.py`) and re-style live. The register bootstrap includes the user's active theme so a client themes correctly on connect.

**Rationale**: Reuses the existing preset model and persistence; ships tokens (not CSS) to native. This is genuine native work (both clients are dark-only today) → scheduled in P3, after the menu and surfaces.

**Alternatives rejected**: A top-bar light/dark toggle — the web has none; adding one would *break* parity (spec Assumptions).

## D5 — Sign-out semantics on native clients

**Decision**: Native "Sign out" performs a real logout: call the server logout path (which revokes the Keycloak refresh token + feature-025 offline grants, per feature 028) then clear local tokens and return to the sign-in entry point. Windows (`_sign_out`, currently a local quit) and Android (`signOut`, currently a local token clear) both gain the server round-trip.

**Rationale**: Matches web `/auth/logout` (FR-018); a local-only clear leaves a live server session/refresh token.

**Alternatives rejected**: Local-only sign-out — fails FR-018 and leaves a revocable credential valid.

## D6 — Verification tooling on this host

**Decision**: Backend via `docker compose up` (Docker 29 present). Web via a real browser (claude-in-chrome / puppeteer) against `http://localhost:8001`. Windows client via `pip install PySide6` + `python windows-client/main.py`, screenshotted. Android via the committed Gradle wrapper + local Android SDK (adb present at `%LOCALAPPDATA%\Android\Sdk`) + JDK; build `:app:assembleDebug` and run on an emulator/AVD if one is available, screenshot + drive live; otherwise fall back to `:core`/`:app` JVM unit tests plus the CI `instrumented` job (`workflow_dispatch`).

**Rationale**: Uses the requester's requested verification path (emulator screenshots + live tests, Windows screenshots) where the host supports it, and degrades to the automated pipeline where it doesn't — while device-independent logic stays covered by tests that need no device (FR-022) so the feature is always CI-verifiable.

**Open risk**: The 041 spec noted the primary environment "cannot build or run the mobile app directly." This host *does* have the Android SDK + JDK + Gradle wrapper, so a build is likely feasible, but emulator availability (a configured AVD + hardware acceleration) is confirmed at verification time; if absent, Android acceptance leans on JVM tests + the CI instrumented job.

## D7 — Migrations / schema

**Decision**: No new tables expected. The menu model is computed, not stored. Theme already persists in `user_preferences`. If any column/preference key is added, it ships as an idempotent guarded `_init_db` delta with a documented rollback (Constitution IX).

## D8 — Dependencies

**Decision**: Zero new third-party runtime dependencies on the server or either client. All work reuses FastAPI/websockets/astralprims/webrender/rote (backend), Compose/OkHttp/kotlinx.serialization (Android), PySide6 (Windows). CI-only tooling unchanged. (Constitution V.)
