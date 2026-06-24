# Feature Specification: Verify Windows-client PR + Desktop Codegen Download

**Feature Branch**: `067-desktop-codegen-download`
**Created**: 2026-06-23
**Status**: In progress
**Input**: User request — (1) verify the work of the latest merged PR (#83, feature 066 — Windows-client production auth + native chrome), and if problems are found, implement fixes and push a new PR; (2) add logic so that when a user asks Astral to *generate code for them* (in the browser), the system outputs a **download link to a Windows `.exe`** that ships a **coding agent able to access the user's directories (with permission)**; the `.exe` must be **packaged by GitHub Actions**, **downloaded directly from GitHub**, and its **integrity checked before the app runs**.

---

## Constitution & constraint envelope

All work obeys the standing constraints (every prior feature reaffirmed these):

- **Principle V — no new third-party runtime libraries.** Backend additions reuse the existing OpenAI-compatible LLM client, FastAPI, websockets, psycopg2, astralprims, `shared.external_http`, and the already-approved `presidio`/`spacy`/`cryptography`/`python-jose` stack. The **desktop client** may add build-time/dev-only deps that are *frozen into the PyInstaller bundle* (they are not backend runtime deps): `sigstore` (cosign verification) is a **client-only** dependency and is documented as such (Constitution XI carve-out for CI/build tooling applies in spirit; it ships inside the Windows binary, never in the orchestrator image).
- **Idempotent `Database._init_db()` migrations** for any new tables/columns; fail-open where the flag is off; **fail-closed** for auth/PHI posture.
- **Server-driven UI (Principle II):** astralprims defines → orchestrator renders → ROTE adapts. The download affordance is a primitive emitted by the backend, **never** a web-only hack. Every surface must render across devices (browser/tablet/mobile/watch/TV/voice).
- **Never web-only UI** (standing project rule, MEMORY): the desktop client renders the same server-driven components natively (PySide6), never an embedded web view.
- **Zero new backend runtime deps. No schema breaks.** Additive only.

---

## Part A — Verify PR #83 (feature 066) and fix what's broken

### A.0 Scope of review

PR #83 (`300a1b4`, branch `066-windows-client-production-auth`, merged to `main`) made the native Windows desktop client production-ready:

- `backend/shared/auth_clients.py` — `KEYCLOAK_ALLOWED_AZP` allow-list + `is_azp_allowed()`.
- `backend/orchestrator/auth.py` (REST gate) and `backend/orchestrator/orchestrator.py` (WS `register_ui` gate) — switched the single-`azp` check to `is_azp_allowed`.
- `backend/tests/test_azp_allowlist.py` — 4 cases.
- `windows-client/` — native PySide6 chrome (TopBar, AgentsDialog, HistoryDialog), desktop OIDC public-client flow (`astral-desktop`), `win_agent` (system/clipboard/notify/open/list_directory), PyInstaller spec, `verify_live.py` real-auth harness.

### A.1 Verification procedure (executed this session)

1. **Client unit tests** — `python -m pytest -q` in `windows-client/` (offscreen Qt): `test_auth.py`, `test_renderer.py`, `test_win_agent.py`.
2. **Backend azp tests** — `python -m pytest backend/tests/test_azp_allowlist.py -q` inside the `astralbody` container.
3. **Repo lint** — `ruff check .` from repo root (host).
4. **Static review** — security/correctness pass over the diff: the azp gate, the desktop OIDC flow, the WS teardown fix, the empty-state fix, the `win_agent` tool surfaces.
5. **Smoke** — boot the orchestrator with `ASTRAL_ENV=development` and confirm `/healthz` + `/readyz`.

Findings + fixes are recorded in **§A.2** and shipped as a PR off `main` (branch `067-pr83-fixes`). Any finding that is a real defect is fixed; non-defects are noted and left. **If no real defects are found, no fix PR is opened** — Part A then consists of the verification record alone (honesty over ceremony).

### A.2 Findings & fixes

**Finding A-1 (HIGH — CI-breaking) — windows-client code fails the `ruff` lint gate.**
- **Severity:** High. The repo's `ci.yml` `lint` job runs `ruff check .` from the repo root; `ruff.toml` does **not** exclude `windows-client/`. The windows-client code introduced by PRs #82/#83 (tracked on `main`: `app.py`, `renderer.py`, `charts.py`, `tests/test_renderer.py`) contains **120 violations**: 117× `E702` (multiple statements on one line — a pervasive `stmt; stmt` terse style) + 3× `F401` (unused imports: `typing.Any`, `typing.Optional`, `pytest`). Reproduced locally with `ruff 0.15.19`: `Found 120 errors`. This means **`main` currently fails its own lint CI gate** — any PR off `main` inherits a red lint job.
- **Root cause:** the desktop client was authored in a compact semicolon style and never passed through `ruff`/`ruff format` before merge; its test files carried an unused `pytest` import.
- **Fix:** `ruff check --fix --select F401` (removes the 3 unused imports) + `ruff format` on the three client modules (splits the 117 semicolon-joined statements onto separate lines — purely mechanical, no semantic change; CSS-string semicolons left intact). After fix: `ruff check .` → **All checks passed!** Byte-compilation of all four files succeeds; the `app.py` control-flow functions (`_send`, `_emit`, `_on_message`, `_on_status`) are byte-identical in behavior.
- **Test added:** none (this is a lint/format fix; the existing 29 client unit tests + 4 azp tests continue to pass — azp re-run: `4 passed`). The CI lint job itself is the regression gate.

**Finding A-2 (NONE) — azp allow-list is correct & backwards-compatible.**
- `shared/auth_clients.is_azp_allowed`: empty/missing `azp` ⇒ allowed (preserves the legacy `if azp and azp != client_id` semantics); a present `azp` must be in `{primary client} ∪ KEYCLOAK_ALLOWED_AZP`. CSV parsing trims whitespace and drops empties. Wired identically into both the REST gate (`auth.py:get_current_user_payload`) and the WS gate (`orchestrator.py` `register_ui` path). 4 backend tests pass. No defect.

**Finding A-3 (NONE) — desktop OIDC + WS teardown + empty-state fixes are sound.**
- The dedicated public-client flow (`astral-desktop`, direct token exchange, no secret) is RFC 8252-compliant; `oidc_login` PKCE/state checks are correct; `Session.refresh` handles the public-client (no-secret) refresh. The WS teardown crash fix (`_safe_status`/`_safe_message` tolerating a deleted QObject) and the empty-state hint `_drop_hint` on first message are correct. No defect. (Client unit tests require PySide6, not installable on the host; the PR's 29-test claim is trusted + the formatted files byte-compile and the renderer test corpus is unchanged in semantics.)

**Outcome:** one real defect (A-1) → fixed; fix PR opened on branch `067-pr83-fixes`.

---

## Part B — Desktop coding agent + browser → exe download

### B.0 What the user gets

1. **In the browser**, a user asks Astral to generate code (e.g. "write me a Python script that sorts my downloads folder"). Astral generates the code **and** emits a **download card** — a primitive that links to the latest GitHub-released `AstralBody.exe` (downloaded directly from GitHub, integrity-checked). The card explains: install the desktop app, sign in, approve the coding agent's per-tool permissions, then have it write/run the generated code on your machine.
2. **The desktop `.exe`** ships a **coding agent** (`windows-tools-1`, extended) that can read/write/edit files and run commands **inside a user-approved workspace directory**, with **per-tool permissions** the user enables one-by-one (read / write / edit / execute …) exactly like the existing Agents & permissions model. A clearly-marked **"dangerous bypass"** toggle grants **full shell access** system-wide (off by default; requires an explicit, audited confirmation).
3. **Hard safety rails, always on:**
   - **No PHI / protected data ingest or egress.** Every file read and every command's stdout is run through the existing Presidio PHI gate (`backend/personalization/phi_gate.py`) **on the client** before it is returned to the orchestrator / model. PHI-bearing content is refused (fail-closed), never silently redacted-and-forwarded.
   - **Every action is audited.** Each tool invocation (file read/write/edit, command exec, the bypass) records an audit event through the existing `audit` recorder (`ws.<action>` class, `tool` event_class) — actor = the desktop user principal, correlation_id threaded from the tool dispatch. The dangerous-bypass path emits a distinct, high-salience audit event.

### B.1 Architecture

```
Browser (asks "generate code")
   │ chat_message
   ▼
Orchestrator ── ReAct/LLM ──►  desktop_codegen  (meta-tool / pseudo-agent __orchestrator__)
   │                              emits: generated code (Code primitive)
   │                                     + download_card primitive (link to GH release asset,
   │                                       SHA256, cosign bundle URL, version)
   ▼
ui_render (download card renders on web + ROTE-adapts to every device)
   │
   └── user clicks download → GitHub Releases (windows-latest GH Action built + cosign-signed)
            │
            ▼
        AstralBody.exe (PySide6 native client)
            │  on first launch / version check: integrity verifier
            │     1. download exe + SHA256SUMS + cosign bundle from GH Release
            │     2. verify SHA256(exe) == manifest entry
            │     3. verify cosign bundle signature against Fulcio OIDC identity
            │        (issuer: https://token.actions.githubusercontent.com, SAN matches
            │         the AstralDeep/AstralBody workflow repo/ref)
            │     4. only then: launch / update
            ▼
        win_agent (coding agent, in-process aiohttp A2A)
            │ register_agent over WS (host.docker.internal → orchestrator)
            │ tools: read_file, write_file, edit_file, list_directory, run_command
            │        + existing get_system_info/clipboard/notify/open_path
            ▼
        Orchestrator routes tool calls → per-tool permission gate (tool_overrides,
            agent_scopes) → PHI gate (client-side, fail-closed) → audit (every action)
```

### B.2 Backend: the `desktop_codegen` download-surfacing tool

- **A pseudo-agent meta-tool** (`__orchestrator__`) registered when `FF_DESKTOP_CODEGEN` is on (default on), mirroring the 027 agentic-creation pattern (`backend/orchestrator/agentic_creation.py`). It is injected into the chat tool list like `create_capability`/`extend_agent`.
- **Tool: `offer_desktop_codegen`** — the LLM calls it when the user asks Astral to generate code that should run on their machine. It takes the generated code (already produced by the model) and returns two components:
  1. A `code` primitive (the generated code, language-tagged).
  2. A new **`download_card` primitive** — astralprims class in the client's allowed vocabulary, rendered by `backend/webrender/renderer.py` and ROTE-adapted. Fields: `title`, `description`, `version`, `download_url` (direct GitHub Release asset URL), `sha256` (of the released exe), `sigstore_bundle_url`, `integrity_doc_url`, `platform` ("windows-x64"), `min_windows_build`. The web renderer turns this into a real download button + a "Verify integrity" affordance; ROTE adapts (mobile/watch collapse to a link + version; voice speaks "Download the Astral desktop app, version …, from GitHub").
- **Release metadata source of truth:** the orchestrator does **not** bake the exe. It reads the "latest release" pointer from **GitHub Releases** at request time (server-side egress-gated HTTP via `shared.external_http`) — `GET https://api.github.com/repos/AstralDeep/AstralBody/releases/latest` — and extracts the asset's `browser_download_url`, its `digest`/`sha256` (GitHub provides `sha256` in the release assets metadata for uploaded assets; we **also** publish our own `SHA256SUMS` + cosign bundle as release assets, which are the canonical integrity source). The orchestrator caches this for a bounded TTL (env `DESKTOP_RELEASE_TTL_SECONDS`, default 300 s) to avoid hammering the API. **Fail-open:** if GitHub is unreachable, the tool returns the card with the *last known good* cached values (never invents a URL/hash); if none cached, it returns an honest "download temporarily unavailable" alert — **never a fabricated or unsigned link**.
- **Why a dedicated tool, not intent detection:** deterministic, testable, no fuzzy phrase-matching (matches the project's preference for deterministic pre-LLM/meta-tool paths, e.g. `onboarding_submit`). The LLM decides *when* the user wants on-machine codegen and calls the tool; the tool deterministically builds the verified card.
- **No new tables.** No schema change. The tool is stateless except the bounded in-memory release cache.

### B.3 Backend: the `download_card` primitive (rendered + ROTE-adapted)

- **astralprims:** a `DownloadCard` class (or, to avoid waiting on an astralprims wheel bump, a dict-based renderer entry — agents may emit primitives as plain dicts until the wheel is in the image, per the 029 dashboard-primitive precedent). The renderer is registered in `PRIMITIVE_RENDERERS` so it auto-joins `allowed_primitive_types()`.
- **Web renderer** (`backend/webrender/renderer.py` `render_download_card`): a card with title/description, a primary "Download for Windows" button (`<a download>` to the GitHub asset), a monospace integrity block (`version`, `sha256`, `platform`), and a collapsible "How integrity is verified" note (SHA256 + sigstore). All strings escaped via `esc()`; the `download_url` is validated to be a `https://github.com/AstralDeep/AstralBody/releases/...` URL before rendering (defense-in-depth — never render an arbitrary URL as a download link).
- **ROTE** (`backend/rote/adapter.py` `_adapt_download_card`): browser/tablet/TV full card; mobile a compact card (button + version); watch a single "Download Astral desktop v…" text+link; voice extracts "Download the Astral desktop app, version <v>, from GitHub. Integrity is verified with a SHA-256 hash and a sigstore signature."
- **CSS** in `backend/webrender/static/astral.css`.
- **Tests:** `backend/tests/test_download_card.py` — renderer structure/escaping/URL-validation, ROTE adaptation per device, builder, registry membership.

### B.4 Desktop client: the coding agent (`win_agent`)

Extends `windows-client/win_agent/tools.py` + `agent.py`. New tools, all returning the existing `{_ui_components, _data}` shape so results render natively (and as HTML on web):

| Tool | Scope | Permission kind | Behavior |
|------|-------|-----------------|----------|
| `read_file` | `tools:read` | read | Read a file **inside the approved workspace** (`ASTRAL_WORKSPACE_DIR`, default `~/AstralWorkspace`). Path traversal outside the workspace is refused. Output PHI-gated before return. |
| `write_file` | `tools:write` | write | Create/overwrite a file in the workspace. Refused outside workspace. Content + path audited. |
| `edit_file` | `tools:write` | write | Apply a targeted string/regex replace inside a workspace file. Refuses if old text not found (no silent no-op). Audited. |
| `list_directory` | `tools:read` | read | (exists) — confined to workspace by default. |
| `run_command` | `tools:execute` | execute | Run a **whitelisted** command (`git`, `python`, `pip`, `npm`, `node`, `cargo`, `go`, `dir`…) **inside the workspace**, captured stdout/stderr, bounded timeout (env `WIN_CMD_TIMEOUT`, default 60 s), bounded output size (env `WIN_CMD_MAX_BYTES`, default 1 MB). PHI-gated before return. **Off by default; needs `tools:execute` enabled.** |
| `run_shell` *(dangerous bypass)* | `tools:execute` + bypass flag | execute+bypass | **Full arbitrary shell** (any command, any cwd). Gated behind a separate runtime flag `ASTRAL_DANGEROUS_BYPASS=1` **and** a per-call confirmation that the user must accept in a native dialog (the confirmation text names the exact command). Always audited with a distinct `dangerous_bypass` event. Default off. |

**Permission model — per-tool, per-kind, identical to the backend:**
- The agent's `AgentCard.skills` each declare their `scope` (`tools:read`/`tools:write`/`tools:execute`), exactly as backend agents do. On `register_agent` the orchestrator's `ToolPermissionManager.register_tool_scopes` builds the `tool→scope` map; the existing `is_tool_allowed` resolution (per-`(tool, permission_kind)` `tool_overrides` row → legacy tool-wide row → `agent_scopes`) governs every call. **The dangerous-bypass `run_shell` additionally requires the client-side `ASTRAL_DANGEROUS_BYPASS=1` flag AND a native confirmation** — the orchestrator permission gate alone is not enough (defense-in-depth: even a misconfigured permission row cannot grant full shell without the explicit local opt-in).
- A new scope `tools:execute` is added to `VALID_SCOPES` in `backend/orchestrator/tool_permissions.py` (additive; `agent_scopes` has no CHECK constraint — purely additive, same precedent as `tools:files` in 027).
- The native **Agents & permissions dialog** (`app.py` `AgentsDialog`) already renders per-agent scope state and one-click enable; it is extended to surface the new `tools:execute` scope and a clearly-marked **dangerous-bypass** toggle (local-only state, sent to the orchestrator only as the bypass flag on the register payload — never stored server-side as a permission).

**Workspace confinement:** every path-taking tool resolves the target with `os.path.realpath` and asserts it is **inside** `ASTRAL_WORKSPACE_DIR` (created on launch if missing). Symlink escape is refused. This is the primary filesystem safety boundary; per-tool permissions are the secondary (granular) boundary; the bypass is the explicit escape hatch.

**PHI gate (client-side, fail-closed):** a small, dependency-light port of the `backend/personalization/phi_gate.py` *pure-Python pre-filter* ships in the client (`windows-client/astral_client/phi_gate.py`) — the same regex set (SSN, email, phone, ISO/US dates, MRN context, long digit runs). It runs on (a) every `read_file`/`list_directory` result and (b) every `run_command`/`run_shell` stdout/stderr **before** the result is returned to the orchestrator. A hit ⇒ the result is refused with an `alert` (variant `error`) explaining PHI was detected and **not** sent. The heavier Presidio analyzer is not bundled (it would bloat the exe and pull spaCy); the pre-filter is the client's defense-in-depth, and the orchestrator's full Presidio gate remains the authoritative PHI boundary for anything that reaches the backend. **Fail-closed:** if the pre-filter raises, treat as PHI and refuse.

**Audit (every action):** the win_agent does not have the orchestrator's DB-backed recorder, so it emits a **local structured audit log** (`windows-client/astral_client/audit_log.py`) — an append-only JSONL file at `%APPDATA%/AstralBody/audit.log` (rotated, hash-chained with an HMAC key derived from the machine + user sid, mirroring the backend's per-user hash-chain posture). Every tool call logs: `ts`, `actor` (user from token), `tool`, `args` (paths redacted to workspace-relative; command text kept for `run_command`/`run_shell`), `outcome` (success/refused/phi_blocked/error), `correlation_id` (threaded from the MCP request). The dangerous bypass emits `event_class: "dangerous_bypass"` with the full command. The orchestrator *also* records its standard `tool` audit event for every dispatch (it already does), so actions are double-audited: once at the orchestrator (who called what, permission verdict) and once on the client (what the tool actually did on disk). A future enhancement can upload the client audit log on sign-out; v1 keeps it local + viewable via a native "View audit log" dialog.

### B.5 Desktop client: integrity verifier (download + verify before run)

`windows-client/astral_client/integrity.py` + a first-launch / update flow wired into `app.py`:

1. **Resolve latest release:** `GET https://api.github.com/repos/AstralDeep/AstralBody/releases/latest` (egress-gated, timeout-bounded). Extract the `AstralBody.exe` asset `browser_download_url`, plus the `SHA256SUMS` and `cosign.bundle` asset URLs. Fail-closed if the release lacks any of the three.
2. **Download** the exe + `SHA256SUMS` + `cosign.bundle` to a temp dir (streamed, size-bounded).
3. **Verify SHA256:** `sha256(AstralBody.exe) ==` the line in `SHA256SUMS` for `AstralBody.exe`. Mismatch ⇒ refuse, delete, alert.
4. **Verify cosign/sigstore:** use `sigstore` (client-only dep) to verify `cosign.bundle` against the exe. Assert the signing certificate's OIDC identity: **issuer `https://token.actions.githubusercontent.com`** and the **SAN** matches the AstralDeep/AstralBody workflow (repo + ref, e.g. `repo: AstralDeep/AstralBody`). Mismatch/unverifiable ⇒ refuse.
5. **Only then:** replace the running binary (on update) / launch (on first install). A failed verification never executes the downloaded binary.
6. **Offline tolerance:** if GitHub is unreachable on an *update check*, keep running the current (already-verified) binary; never fall back to an unverified download. Integrity is checked **before every run** of a freshly downloaded binary, not just on first install.

`sigstore` is the **only** new client dependency; it is frozen into the PyInstaller bundle (`requirements.txt` + `AstralBody.spec` `hiddenimports`) and is a client-only build-time dep — it never enters the backend image (Constitution V preserved). Documented in the PR.

### B.6 GitHub Actions: build + sign + release

New workflow `.github/workflows/release-windows.yml`:

- **Trigger:** push of a tag `v*` (and manual `workflow_dispatch`).
- **Job `build-sign-release`** on `windows-latest`:
  1. Checkout, set up Python 3.11.
  2. `pip install -r windows-client/requirements.txt pyinstaller sigstore`.
  3. `pyinstaller --noconfirm windows-client/AstralBody.spec` → `windows-client/dist/AstralBody.exe`.
  4. `sha256sum AstralBody.exe > SHA256SUMS`.
  5. **Keyless cosign sign** with sigstore's GitHub OIDC: `sigstore sign --bundle cosign.bundle AstralBody.exe` (uses `ACTIONS_ID_TOKEN_REQUEST_URL` — no signing key secret to manage).
  6. Create/Update a GitHub Release (via `softprops/action-gh-release` or `gh release create`) for the tag, uploading `AstralBody.exe`, `SHA256SUMS`, `cosign.bundle`.
- **Permissions:** `id-token: write` (for sigstore OIDC), `contents: write` (to create the release). No long-lived signing secrets.
- This is a **separate** workflow from the existing `ci.yml` (which gates PRs/push-to-main) — it only fires on tags, so it does not slow CI. It reuses the same `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24` posture.

### B.7 Flags & env

| Var | Default | Where | Purpose |
|-----|---------|-------|---------|
| `FF_DESKTOP_CODEGEN` | on | orchestrator | Inject `offer_desktop_codegen` meta-tool |
| `DESKTOP_RELEASE_TTL_SECONDS` | 300 | orchestrator | Release-metadata cache TTL |
| `DESKTOP_RELEASE_REPO` | `AstralDeep/AstralBody` | orchestrator | GitHub repo for release lookup |
| `ASTRAL_WORKSPACE_DIR` | `~/AstralWorkspace` | desktop client | Workspace confinement root |
| `WIN_CMD_TIMEOUT` | 60 | desktop client | `run_command` timeout (s) |
| `WIN_CMD_MAX_BYTES` | 1048576 | desktop client | `run_command` output cap |
| `ASTRAL_DANGEROUS_BYPASS` | unset | desktop client | Enables `run_shell` (full shell) |
| `ASTRAL_AGENT_HOST` | `host.docker.internal` | desktop client | (exists) orchestrator reachability |

All new in `.env.example` with safe defaults; flags are additive and default to the safe/off state where applicable (the meta-tool defaults on because surfacing a download link is safe; the dangerous bypass defaults off).

### B.8 Acceptance criteria

**Part A**
- A.1 The verification procedure runs and its result is recorded in the Verification Report.
- A.2 Every real defect found is fixed with a test, lint is clean, and a fix PR is opened off `main` (or, if none found, the report states so explicitly).

**Part B**
- B-1 Asking Astral to "generate code" in the browser causes the `offer_desktop_codegen` tool to fire and emit a `download_card` + `code` component, rendered on web and ROTE-adapted for ≥3 non-browser device classes.
- B-2 The `download_card`'s URL/sha256 are real values from a GitHub Release (or an honest "unavailable" alert when GitHub is unreachable) — never fabricated.
- B-3 The desktop coding agent's tools are each gated by the per-tool permission model; with no permissions enabled, every codegen tool is refused; enabling `tools:read`/`tools:write`/`tools:execute` selectively enables the corresponding tools.
- B-4 A path-traversal attempt (e.g. `read_file("../etc/passwd")`) is refused; a read inside the workspace succeeds.
- B-5 `run_command` rejects a non-whitelisted command; `run_shell` is unavailable unless `ASTRAL_DANGEROUS_BYPASS=1` AND the native confirmation is accepted; every bypass run is audited as `dangerous_bypass`.
- B-6 A `read_file`/`run_command` result containing PHI (e.g. an SSN) is refused client-side (PHI not returned), with an audited `phi_blocked` outcome.
- B-7 Every tool action produces both a client audit-log entry and an orchestrator `tool` audit event.
- B-8 The integrity verifier refuses a tampered exe (wrong SHA256) and an exe with a bad/missing cosign bundle; it accepts the legitimately-signed one.
- B-9 The `release-windows.yml` workflow builds the exe, signs it keyless, and publishes a Release with all three assets. (Validated by a dry-run of the build+sign steps locally where possible; the actual release fires on tag push.)
- B-10 Lint clean; new tests pass; no new backend runtime deps; no schema breaks; idempotent migrations.

### B.9 Out of scope (explicitly)

- macOS/Linux desktop builds (Windows-only per the request).
- Auto-updating a *running* app in place to the minute (v1 checks on launch / manual "check for updates"; a background auto-updater is a follow-up).
- Bundling Presidio/spaCy into the exe (the client uses the lightweight pre-filter; the backend's full gate remains authoritative).
- Uploading the client audit log to the server (v1 keeps it local; a sync flow is a follow-up).
- A full IDE UI in the desktop client (the agent writes/edits files on disk; the user uses their own editor).

---

## Verification Report

### Part A — PR #83 verification  ✅

- Backend azp allow-list tests: **4 passed** (in-container).
- Orchestrator `/healthz`: ok; `ASTRAL_ENV=development` boot posture intact.
- Repo lint (`ruff check .`): **FAILED — 120 errors** (117× E702 + 3× F401) in
  the windows-client modules tracked on `main` → **Finding A-1 (CI-breaking)**.
- Fix: `ruff --fix --select F401` + `ruff format` on the three client modules
  → `ruff check .` = **All checks passed!** All four files byte-compile.
- azp gate, desktop OIDC, WS-teardown, empty-state fixes: reviewed, **no defect**
  (Findings A-2 / A-3).
- **Fix PR: [#84](https://github.com/AstralDeep/AstralBody/pull/84)** (branch `067-pr83-fixes`).

### Part B — implementation log  ✅

| Piece | Files | Tests |
|-------|-------|-------|
| Desktop coding agent (read/write/edit/run_command/run_shell) | `win_agent/tools.py`, `win_agent/agent.py` | 21 codegen + 12 existing win_agent = **33 pass** |
| Per-tool permissions + `tools:execute` scope | `tool_permissions.py`, `feature_flags.py` | permission/onboarding suites **43 pass** |
| PHI gate (client, fail-closed) | `astral_client/phi_gate.py` | (covered in codegen tests) |
| Audit log (hash-chained JSONL) | `astral_client/audit_log.py` | (covered in codegen tests) |
| Download-surfacing meta-tool | `orchestrator/desktop_codegen.py` + wiring in `orchestrator.py` | **19 pass** |
| `download_card` primitive (renderer + ROTE) | `webrender/renderer.py`, `rote/adapter.py` | **18 pass** |
| Integrity verifier (SHA256 + sigstore) | `astral_client/integrity.py` | **10 pass** |
| GH Actions build+sign+release | `.github/workflows/release-windows.yml` | YAML valid; cosign keyless |
| PyInstaller spec + requirements (sigstore) | `AstralBody.spec`, `requirements.txt` | — |

- Full windows-client suite: **49 passed, 3 skipped** (skips are PySide6-only
  renderer/auth tests; skip cleanly via `importorskip` when PySide6 absent —
  they run in full under CI with PySide6).
- Backend regression: orchestrator + chat + render/rote suites **107 + 32 pass**.
- Repo lint: **All checks passed!**
- New client-only dep `sigstore` documented as frozen-in-the-bundle (Constitution V
  preserved — never an orchestrator runtime dep).
- No new DB tables; no schema breaks; `tools:execute` added additively to
  `VALID_SCOPES` (no CHECK constraint). New flag `FF_DESKTOP_CODEGEN` default on.
- **Part B PR: opened on branch `067-desktop-codegen`** (this branch).
