# Phase 0 Research: Chat Attachment Upload & Universal Parsing

All Technical-Context unknowns are resolved below. Each item: **Decision / Rationale / Alternatives considered**, grounded in the existing codebase.

## R1. Attachment affordance in the chat input — chrome vs primitive vs raw HTML

- **Decision**: Render a paperclip **button + a chips row** directly in the server-rendered shell (`shell.html`, inside `#astral-form`), reusing the existing `astral-file-upload` client hook for the hidden `<input type="file">`. Use the existing astralprims `badge` primitive's CSS conventions for chips. Provide a richer **attachment library/picker** as a new **chrome surface** (`webrender/chrome/surfaces/attachments.py`) opened from the paperclip menu (US3 browse/reuse/delete).
- **Rationale**: The chat input shell is already server-rendered HTML with placeholder injection; `client.js` already has the `astral-file-upload` change-listener and a `file_upload` primitive renderer exists. App-chrome surfaces (top bar, modals) are explicitly *not* astralprims and are the established home for picker/management panels (feature 027). This keeps Constitution II satisfied (orchestrator renders; ROTE adapts) with the least new surface area.
- **Alternatives considered**: (a) A brand-new astralprims primitive (`attachment_tray`) — rejected: requires an astralprims release + renderer + docs for marginal benefit; the `badge`/`file_upload` primitives already cover the visuals. (b) A floating React widget — rejected: violates Constitution II.

## R2. Delivering attachments to the agent — structured refs vs the text hack

- **Decision**: Extend the `chat_message` WS payload with `attachments: [{attachment_id, filename, category}]`. The orchestrator persists turn→attachment links (`message_attachment` table), injects a concise, structured **"Attachments on this turn"** block into the user message content (listing `attachment_id`, filename, category, and whether a parser exists), and continues to inject `user_id` into tool args so `read_*` tools verify ownership. Retire the `"[Attachment: …]"` / `"I have uploaded …"` regex hack for new turns (kept tolerant for old transcripts).
- **Rationale**: The current text hack is brittle (regex-parsed) and loses structure. The agent already receives `user_id` at dispatch (orchestrator ~line 4391) and the `read_*` tools already take `attachment_id`; giving the model the real ids in a structured block lets it call the correct parser deterministically. `load_chat` re-hydration can use `message_attachment` to restore references.
- **Alternatives considered**: (a) OpenAI multimodal `content` arrays with inline image parts — rejected for now: images already flow through `read_image` returning base64 for the vision model; reusing the tool path keeps one code path and respects per-user ownership checks. (b) Keep the text hack — rejected: not production-grade, can't carry category/coverage metadata cleanly.

## R3. Broadening the accepted-type allowlist (and which types drive auto-creation)

- **Decision**: Broaden `ACCEPTED_EXTENSIONS` substantially. Most additions map to **existing** parsers (especially text/code → `read_text`, more document/spreadsheet formats where current libs already handle them). Introduce explicit **no-parser categories** (`data`, `archive`) for accepted types that have **no** reader yet (e.g. `parquet`, `avro`, `feather`, `zip`, `tar`, `gz`, `7z`, `epub`, …). A new `parser_registry` coverage map declares, per extension/category, the covering tool — or `None` (→ triggers auto-creation). Each new category gets an explicit `MAX_BYTES` cap. The allowlist stays **curated** (no "any arbitrary binary"), per the clarification.
- **Rationale**: The clarification chose "broaden + auto-create." Auto-creation can only ever fire if some accepted type lacks a parser; today every accepted type has one, so the no-parser categories are what make US2 reachable and demonstrable. Mapping textual additions to `read_text` is free and high-value.
- **Alternatives considered**: (a) Accept literally any file — rejected by clarification (attack surface). (b) Keep the current list — rejected: auto-creation would never fire.

## R4. Eager (on-upload) gap detection — how to trigger without an LLM chat turn

- **Decision**: In `POST /api/upload`, after a successful insert, look up the uploaded extension/category in the `parser_registry` coverage map. If uncovered **and** no live/pending parser exists for that format (dedup via `attachment_parser` + `draft_agents.gap_fingerprint`), enqueue a **background** autoparse task (`attachment_autoparse.start(...)` via `asyncio.create_task`) that drives the lifecycle primitives directly (`lifecycle.create_draft` → `generate_code` → `start_draft_agent` → self-test with the uploaded file as the sample → persist `self_test`). The upload response returns immediately with a `parser_status: "preparing" | "pending_admin_approval" | "covered"` hint; the uploader's chat/WS receives a status card.
- **Rationale**: The clarification chose eager-on-upload. Feature 027's `create_capability` is LLM-decided inside a chat turn — wrong trigger for "on upload". The lifecycle building blocks (`create_draft`, `generate_code`, `_self_test_draft`, security gate) are callable directly; wrapping them in a deterministic, format-seeded background flow reuses all the safety machinery without needing the model to "decide". Background execution keeps the upload request fast and the chat turn unblocked.
- **Alternatives considered**: (a) Lazy detection when an agent fails to parse mid-turn — rejected by clarification. (b) Run autoparse inline in the upload request — rejected: codegen + 120 s self-test would block the HTTP response.

## R5. Admin-only approval

- **Decision**: Gate the draft-approval action to admins. The draft-decision handler (`_h_draft_approve` in `agentic_creation.py`) currently checks only ownership; add a server-side `"admin" in roles` check (roles already extracted from JWT in `chrome_events.py`), audit non-admin attempts as a lifecycle failure, and mark the drafts chrome surface `ADMIN_ONLY` for `auto_attachment`-origin drafts so the dispatcher's admin re-check also covers it. The uploading (non-admin) user sees a read-only "pending admin approval" card.
- **Rationale**: The clarification requires an admin (not the uploader) to approve before a parser goes live. The canonical admin pattern already exists (`session_roles`, `_roles`, `ADMIN_ONLY`, `_audit_admin_rejection`). Reusing it keeps enforcement server-side and fail-closed.
- **Alternatives considered**: (a) Any-user approval (027 default) — rejected by clarification. (b) Auto-approve on a clean security gate — rejected: violates the explicit human-in-the-loop admin requirement.

## R6. Global promotion of an approved parser

- **Decision**: When an `auto_attachment` draft is approved, promote it as today **but** set `agent_ownership.is_public = True` and enable the read scope so the new `parse_<fmt>` tool is dispatchable by **every** user, then write an `attachment_parser` row mapping the format → live agent/tool (status `live`). On approval, re-parse the originating attachment (looked up via `draft_agents.source_attachment_id`) and continue the uploader's request. Format-scoped dedup prevents a second draft while one is pending/live.
- **Rationale**: The clarification chose global scope. `agent_lifecycle.approve_agent` already registers ownership (`set_agent_ownership(..., is_public=False)`) and inits scopes — flipping `is_public=True` for this origin and enabling read scope is the minimal, well-trodden change. The `attachment_parser` registry gives an O(1) "is this format covered globally?" lookup for future uploads and the dedup key.
- **Alternatives considered**: (a) Per-user parser (027 default) — rejected by clarification; also wasteful (every user re-creates the same reader). (b) One mega "format parser" agent gaining tools via `extend_agent` — rejected: `extend_agent` requires user ownership and only stages a revision (no real self-test); a public micro-agent per format reuses the full self-tested create path.

## R7. No new dependencies for auto-created parsers (Constitution V)

- **Decision**: Constrain codegen for parser tools to **standard library + already-installed packages only**. Add an explicit instruction to the generator prompt ("you may import only the Python standard library and packages already importable in this image; do not assume any pip install; if the format needs an unavailable library, perform best-effort structural extraction — e.g. treat OOXML/epub/zip-based formats as zip+XML, columnar/binary as a documented partial read — and clearly state the limitation in the output"). The existing `code_security.py` import gate already blocks `subprocess`/`importlib`/`runpy`, so no parser can shell out to install anything. The self-test verifies the parser produces usable, non-empty output before it can be approved.
- **Rationale**: FR-026 + Constitution V forbid new runtime deps; auto-generated code must not smuggle them in. Many "exotic" accepted formats are actually zip/XML or text under the hood and are parseable with stdlib. Honest partial extraction beats a hard failure and is surfaced to the user.
- **Alternatives considered**: (a) Allow the generator to `pip install` — rejected: violates V and the security gate. (b) Refuse any format needing an absent lib — rejected: needlessly narrow; best-effort stdlib extraction covers many cases and the self-test enforces a usefulness floor.

## R8. Persistence model — new tables vs reuse

- **Decision**: Add `message_attachment` (turn→attachment link, for delivery + `load_chat` re-hydration) and `attachment_parser` (format→global-parser registry + dedup + provenance). Add one guarded column `draft_agents.source_attachment_id` so an approved parser can re-parse the file that triggered it. Reuse `user_attachments`, `draft_agents` (origin=`auto_attachment`, `gap_fingerprint`, `self_test`, `source_chat_id`), `agent_ownership`, `audit_events` unchanged in shape.
- **Rationale**: Minimal, additive, idempotent. The `message_attachment` link is cleaner than overloading the path-based `chat_files` mapping. The `attachment_parser` registry is the natural home for "global coverage" + the dedup key. All via the `_init_db` guarded pattern (`_column_exists`, `CREATE TABLE IF NOT EXISTS`).
- **Alternatives considered**: Overloading `chat_files` for structured attachments — rejected: it's path/text-oriented and tied to the legacy hack.

## R9. Feature flag & fail-closed posture

- **Decision**: Add `FF_ATTACHMENT_AUTOPARSE` (default **on**) following the `feature_flags.py` convention. When off, unsupported uploads are accepted but report "no reader available for this type" instead of drafting a parser (the upload/parse path for *covered* types is unaffected and not flag-gated). All paths fail closed: an unapproved/pending/failed parser yields a clear "cannot read this type yet" outcome; auto-generated code never runs against a user file outside the gate + self-test + admin approval.
- **Rationale**: Matches the project's flag idiom and lets operators disable autoparse without losing core upload/parse. Fail-closed satisfies FR-019/SC-005 and the project's `ASTRAL_ENV`-unset==production posture.
- **Alternatives considered**: No flag — rejected: autoparse spawns background LLM codegen; operators should be able to disable it.

## R10. Observability & audit

- **Decision**: Reuse the `agent_lifecycle` audit class with a single `correlation_id = draft_id` across `gap_detected → auto_created → self_test → approved/rejected`, adding `inputs_meta` for `{extension, category, attachment_id, gap_fingerprint, trigger:"upload"}`. Log (structured) rejected uploads, ownership-denied references, and parse failures under the existing `file` audit class / logger. Non-admin approval attempts audit as a lifecycle failure.
- **Rationale**: FR-023/FR-024 + Constitution X. The audit helper (`_audit`) and recorder (`record(AuditEventCreate(...))`) already exist; correlation-by-draft-id is the established pattern.
- **Alternatives considered**: A new audit class — rejected: `agent_lifecycle` already models exactly this lifecycle.

## Open risks (carried into tasks, not blockers)

1. **Best-effort parsers**: stdlib-only extraction may yield partial content for proprietary binary formats; mitigated by the self-test usefulness floor + an explicit limitation notice in tool output. (R7)
2. **Background-task surfacing**: the uploader's WS may be on a different chat/socket; reuse the feature-028 fan-out / notification path to deliver the status card to all of the user's sockets. (R4)
3. **Admin availability**: a parser stays pending until an admin acts; document the pending state clearly to the uploader so it isn't perceived as a hang. (R5)
