# Quickstart: verifying 055-uniform-artifacts

Everything runs in the `astraldeep` container (`docker compose up -d`); sync
edits with `docker cp <file> astraldeep:/app/<path>` + `docker restart
astraldeep`. Web at http://localhost:8001. Per Constitution X, each user story
is verified LIVE on every affected client target, not just by tests.

## US1 — first-turn loading contract

1. Fresh chat on **web**: welcome visible → type any message → the skeleton must
   appear instantly and remain until the first component lands. No blank-canvas
   window; welcome examples gone and never resurrected (also test a text-only
   first message, e.g. "just say hi with no tools").
2. **Windows client** (`python -m astral_client`): repeat with a TYPED composer
   send (previously broken path) and an example-card tap. No "interface appears
   here" hint mid-turn.
3. **Android emulator / iOS simulator**: after the first turn commits, swipe the
   canvas history — there must be NO "Canvas 1" welcome snapshot; a text-only
   first turn must not bring the examples back.
4. **watchOS simulator**: first turn's content must replace the welcome
   examples, not stack under them.
5. Regression: on any client, load an EMPTY chat / delete the chat from another
   tab — the authoritative empty render still clears the canvas (web now shows
   the idle hint via the components-array check).
6. `pytest tests/test_welcome_identity.py tests/test_first_turn_contract.py`;
   Android `CanvasClobberTest` + new welcome-purge tests; Apple/Windows twins.

## US2 — progressive artifacts

1. Invoke a streaming tool (system status stream). Watch one component with a
   stable identity fill in on web AND on one native client simultaneously.
2. Mid-stream, trigger a designed canvas refresh (2+ component turn) — the
   streamed component must survive (fresh anchor, stream continues).
3. Reload the chat: the final streamed state is persisted with source
   attribution; re-running the tool supersedes it (same identity).
4. Narrative honesty: stream a markdown-heavy answer; at no frame may raw
   `**`/backtick tokens appear (`tests/test_narrative_markdown_boundary.py`).
5. Leak stripping: inject the recorded `update_component<arg_key>…` fixture
   through the doc-card path; verify stripped output + diagnostic log + honest
   fallback (`tests/test_toolcall_leak_stripping.py`).
6. Kill the agent mid-stream: the component resolves to an honest failed state.

## US3 — cross-device canvas parity

1. Send the SAME multi-component prompt from web and from Android into two
   fresh chats; compare persisted state (`saved_components` + `workspace_layout`
   rows): both must have layout rows; re-hydrate each chat on the other device —
   arrangement-equivalent canvases.
2. Natives receive the designed canvas as a post-`done` full render — verify
   flat components appeared first (upsert-first), then the arranged canvas.
3. Two devices live on one chat: delete + combine components on web → the
   native canvas reconciles in ≤2 s without reload (and vice versa where the
   native exposes the verb).
4. Designer failure injection (`UI_DESIGNER_TIMEOUT_SECONDS=0`): flat canvases
   everywhere, no error surfaced, `ui_designer.fallback` logged.
5. Drift guards: backend `pytest tests/test_ui_protocol_manifest.py`, Windows
   manifest tests, Android `ProtocolManifestTest`, Apple `ManifestDriftTests`.

## US4 — refine + provenance

1. On web: produce a table → its chrome shows the provenance badge (grounded)
   and the refine affordance → "add a totals row" → the SAME component updates
   in place; history shows v1 restorable; restore works and is audited.
2. On one native client: provenance badge renders; refine affordance works
   (Windows/Android/iOS); watch shows neither (declared divergence).
3. A hallucinated metric (no tool source) renders `generated` — visually
   distinct from a grounded one on EVERY target (screenshot set).
4. Timeline mode: refine refused read-only. Unconfigured-LLM user: refine
   refused by the 054 gate.
5. `pytest tests/test_component_refine.py tests/test_provenance_stamp.py`
   (includes the property test: agent-supplied provenance always overwritten).

## US5 — export + share

1. Table CSV: export a paginated table → all rows present (source re-invoked),
   formula-injection guard verified. `?stored_only=1` path on a dead agent.
2. Canvas HTML: opens from disk with no network; charts degraded readably;
   provenance + date stamped.
3. Share: mint → open in an incognito window (no auth) → read-only snapshot,
   noindex headers; revoke → immediate 404. PHI fixture refuses at mint with
   `share.refused_phi` audit. `FF_ARTIFACT_SHARING` off (default) ⇒ routes 404.

## Cross-cutting

- **Flags-off equivalence (SC-009)**: run the full suite + drift guards with all
  six 055 flags forced off — zero diffs (dedicated CI job variant).
- **Migrations**: boot against a representative dump; verify
  `component_version`/`share_grant` created idempotently (second boot no-ops);
  rollback per data-model.md.
- Full suite: `docker exec astraldeep bash -c "cd /app/backend && python -m pytest -q"`;
  `ruff check .` from repo root on host; Android `./gradlew test`; Apple
  `swift test --package-path apple-clients/AstralCore`; Windows
  `python -m pytest windows-client/tests -q`.
