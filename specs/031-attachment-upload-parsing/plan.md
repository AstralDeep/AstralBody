# Implementation Plan: Chat Attachment Upload & Universal Parsing

**Branch**: `031-attachment-upload-parsing` | **Date**: 2026-06-15 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/031-attachment-upload-parsing/spec.md`

## Summary

Add a visible, server-rendered attachment (paperclip) control to the chat input so users can attach a broad set of file types to a message; deliver those attachments to the handling agent as structured references (replacing today's `"[Attachment: …]"` text hack) so existing parser tools (`read_document`, `read_spreadsheet`, `read_presentation`, `read_text`, `read_image`, plus the medical tools) actually run on them; and — for an accepted file type that **no** existing tool can read — **eagerly on upload** spin up a safe, auto-created backend parser by reusing the feature-027 agentic-creation lifecycle (draft → security gate → isolated VirtualWebSocket self-test → decision → live), with two deliberate, clarified changes to that lifecycle: final approval is **admin-only**, and an approved parser is promoted **globally** (public) so every user can read that type thereafter.

The upload endpoint, user-scoped storage, the `user_attachments` table, content sniffing, and the per-category parsers already exist (feature 002). The security gate, codegen, self-test, draft lifecycle, audit class, and admin-role plumbing already exist (features 012/027). This feature is therefore mostly **integration + two gated extensions**, plus broadening the accepted-type allowlist and wiring attachments through the chat turn — with **zero new third-party runtime dependencies**.

## Technical Context

**Language/Version**: Python 3.11+ (backend production image); ES5-compatible vanilla JS + CSS in the orchestrator render layer (`backend/webrender/static/`, no build step)
**Primary Dependencies**: Existing only — FastAPI, websockets, psycopg2, the OpenAI-compatible LLM client (`_call_llm` via `llm_config.client_factory`), `python-magic` (already used for content sniffing), astralprims ≥0.2.0 (defines `file_upload`/`badge` primitives, consumed unchanged), `shared.external_http`. Parsing of already-supported types uses the libraries feature 002 already installed (pypdf/python-docx/openpyxl/python-pptx/Pillow/etc.). **No new third-party runtime libraries** (Constitution V); auto-created parsers are constrained to the standard library + already-installed packages.
**Storage**: PostgreSQL via `shared/database.py::_init_db()` idempotent, guarded startup migrations. Reuses `user_attachments`, `draft_agents` (origin/gap_fingerprint/self_test/source_chat_id columns), `agent_ownership`, `audit_events`. Deltas: new `message_attachment` table (turn→attachment links); new `attachment_parser` table (format→global-parser registry + dedup); one guarded column add `draft_agents.source_attachment_id`. Blob storage reuses `{UPLOAD_ROOT}/{user_id}/{attachment_id}/{filename}`.
**Testing**: pytest (the two invocations from CLAUDE.md — repo default suite + module suites), run inside the `astralbody` container against postgres. New tests under `backend/tests/attachments/`, `backend/tests/chrome/`, `backend/agents/general/tests/file_tools/`, and orchestrator unit tests.
**Target Platform**: Linux server (containerized); web client target rendered server-side (HTML/CSS/JS) and adapted by ROTE.
**Project Type**: Server-driven web application (backend-only source of truth; no standalone SPA).
**Performance Goals**: Upload stays streaming (256 KiB chunks, existing). Attachment delivery adds no extra round-trips to the chat turn. Auto-parser creation runs **in the background** (off the upload request and off the chat turn) within the existing 120 s self-test budget; the uploader gets an immediate "preparing a reader / pending admin approval" acknowledgement.
**Constraints**: No new runtime deps (V); server-driven UI only (II); idempotent guarded migrations only (IX); user-scoped attachment ownership verified on every read (VII); fail-closed (an unapproved/failed parser yields "cannot read this type yet", never silent code execution); changed-code coverage ≥90% (III, XI).
**Scale/Scope**: Per-message attachment cap = 10 (tunable). Existing size caps: 30 MB standard categories, 2 GB medical; new categories get explicit caps. One auto-created parser **per file-type gap** (deduped), promoted once globally.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. Primary Language (Python) | ✅ PASS | All backend in Python; client assets are render-layer JS/CSS (permitted). |
| II. UI Delivery Architecture (SDUI) | ✅ PASS | Attachment control + chips + library are server-rendered (shell HTML injection + chrome surface) using existing astralprims `file_upload`/`badge` primitives; no SPA reintroduced. Rendering stays in the orchestrator render layer; ROTE adapts. |
| III. Testing Standards (≥90% changed) | ✅ PASS | Unit + integration tests for: broadened allowlist, structured attachment wiring, gap detection, admin-gated approval, global promotion, fail-closed paths. |
| IV. Code Quality (PEP 8 / lint) | ✅ PASS | ruff from repo root; render-layer JS passes lint. |
| V. Dependency Management (no new deps) | ✅ PASS | Zero new runtime deps. Auto-created parsers may import only already-installed packages + stdlib (enforced by the existing `code_security.py` import gate + a codegen instruction); best-effort extraction otherwise. CI-only tooling unchanged. |
| VI. Documentation | ✅ PASS | Google-style docstrings; the broadened primitive usage and the parser-autocreate contract documented in this spec dir; `/docs` reflects new/changed REST behavior. |
| VII. Security | ✅ PASS | Keycloak roles gate admin approval; ownership enforced on every attachment read (404 for non-owner); auto-generated code passes the AST/import/regex security gate; admin (not uploader) approves before any global activation. |
| VIII. User Experience | ✅ PASS | UI composed from astralprims primitives rendered by the orchestrator; chrome (non-primitive) used only for app-chrome surfaces, consistent with feature 027. |
| IX. Database Migrations | ✅ PASS | Two new tables + one guarded column via `_init_db()` idempotent guarded pattern (`_column_exists`); rollback documented in data-model.md. |
| X. Production Readiness | ✅ PASS | Background autoparse has structured logs + audit; no stubs; observability for rejected uploads, ownership denials, parse failures, lifecycle events. |
| XI. Continuous Integration | ✅ PASS | Existing CI gates apply unchanged; no new product dependency. |

**Gate result: PASS** (no violations). One posture change is explicitly *chosen and gated*, not a violation — see below.

### Tracked posture change (not a violation)

Feature 027 promotes auto-created capabilities **per-user** with approval by the **owning user**. The clarifications for this feature deliberately choose **admin-only approval** and **global promotion** for *attachment parsers specifically* (origin `auto_attachment`). This is a tightening of who may approve (admin ≥ user) plus a scoped broadening of reach (global), both audited and gated — it does not weaken any principle. Recorded here so reviewers see it is intentional. No Complexity Tracking entry required (no principle is violated).

## Project Structure

### Documentation (this feature)

```text
specs/031-attachment-upload-parsing/
├── plan.md              # This file
├── spec.md              # Feature spec (with Clarifications)
├── research.md          # Phase 0 — decisions & rationale
├── data-model.md        # Phase 1 — entities, tables, migrations, rollback
├── quickstart.md        # Phase 1 — how to exercise & verify the feature
├── contracts/
│   ├── attachments-protocol.md   # WS/REST shapes: chat_message attachments[], upload, picker chrome
│   └── parser-autocreate.md      # Auto-create lifecycle contract (states, admin gate, global promote)
├── checklists/
│   └── requirements.md  # Spec quality checklist (from /speckit-specify)
└── tasks.md             # Phase 2 — created by /speckit-tasks
```

### Source Code (repository root)

Backend-only (server-driven UI; no `frontend/` source of truth). Concrete touch points:

```text
backend/
├── orchestrator/
│   ├── attachments/
│   │   ├── content_type.py        # CHANGE: broaden ACCEPTED_EXTENSIONS + MAX_BYTES + new categories; parser-coverage map
│   │   └── router.py              # CHANGE: on successful upload, detect parser gap → enqueue autoparse (eager)
│   ├── attachment_autoparse.py    # NEW: programmatic gap-detect + draft-create (reuses lifecycle primitives), dedup by format, notify uploader, re-parse on approval
│   ├── orchestrator.py            # CHANGE: accept structured `attachments[]` on chat_message; persist turn links; inject attachment refs into the agent user message; expose attachment_ids to tools
│   ├── agentic_creation.py        # CHANGE: admin-gate _h_draft_approve; on auto_attachment approval, promote global (is_public=True) + register parser; format-scoped dedup
│   ├── chrome_events.py           # (reuse) admin re-check path for draft-decision actions
│   └── parser_registry.py         # NEW (or helper in file_tools): map extension/category → covering tool; "is this type parseable?" lookup
├── agents/general/
│   ├── file_tools/__init__.py     # CHANGE: export coverage map (which extensions/categories have a parser)
│   └── mcp_tools.py               # (reuse) existing file-tool registry entries
├── webrender/
│   ├── templates/shell.html       # CHANGE: add paperclip control + #astral-attachments chips row in #astral-form
│   ├── static/client.js           # CHANGE: file-pick→upload→chip lifecycle; send structured attachments[] on chat_message; render autoparse status cards
│   ├── static/astral.css          # CHANGE: chip + paperclip styles
│   └── chrome/surfaces/attachments.py  # NEW: attachment library/picker chrome surface (US3 browse/reuse/delete)
├── shared/
│   ├── database.py                # CHANGE: _init_db deltas — message_attachment, attachment_parser tables; guarded draft_agents.source_attachment_id
│   └── feature_flags.py           # CHANGE: add FF_ATTACHMENT_AUTOPARSE (default on)
└── tests/
    ├── attachments/               # broadened allowlist, wiring, autoparse trigger, dedup, fail-closed
    ├── chrome/                    # attachments surface; admin-gated draft approval
    └── ../agents/general/tests/file_tools/  # coverage map
```

**Structure Decision**: Single backend project, server-driven UI. The feature is overwhelmingly integration of existing subsystems (attachments 002 + agentic-creation 027) plus two new small modules (`attachment_autoparse.py`, the attachments chrome surface) and two new tables. No new top-level structure.

## Complexity Tracking

> No Constitution violations — table intentionally empty. The admin-approval + global-promotion posture change is documented above under "Tracked posture change" and is a gated tightening/broadening, not a principle violation.
