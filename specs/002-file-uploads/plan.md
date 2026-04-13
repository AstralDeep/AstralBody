# Implementation Plan: Common File Type Uploads in Chat UI

**Branch**: `002-file-uploads` | **Date**: 2026-04-13 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/002-file-uploads/spec.md`

## Summary

Expand the chat composer's paperclip control from the four current text formats (`.csv`, `.txt`, `.json`, `.md`) to ~30 common formats spanning documents (PDF/DOCX/RTF/ODT), spreadsheets (XLSX/XLS/ODS/TSV), presentations (PPTX/PPT/ODP), structured text/code, and images. On the backend, extend the existing Keycloak-protected `/api/upload` endpoint to accept the new types under a unified 30 MB cap, store files under a **user-scoped** location (not session-scoped) so they appear inline across all the user's chats, and add a new tool surface on the AstralBody general agent that reads each file category into a representation the agent can reason over (text, structured data, image bytes for the connected vision model). PDFs and image-only documents try OCR first and fall back to the vision model when text extraction yields nothing.

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript 5.x on Vite + React 18 (frontend)
**Primary Dependencies**:
- Existing: FastAPI, `python-multipart`, `openpyxl`, Keycloak (via `backend/orchestrator/auth.py`), Lucide React icons.
- New (require lead-developer approval per Constitution V): `pypdf` (PDF text extraction), `python-docx` (DOCX), `python-pptx` (PPTX), `odfpy` (ODT/ODS/ODP), `striprtf` (RTF), `xlrd` (legacy `.xls`), `Pillow` (image normalization), `pytesseract` + `pdf2image` (OCR fallback), `defusedxml` (safe XML parsing for HTML/XML files), `python-magic` (content-type sniffing for FR-008).
- System dependency: Tesseract OCR + Poppler (for `pdf2image`) — added to backend Docker image.
**Storage**: Local filesystem on the backend container at `backend/tmp/{user_id}/{file_id}/{filename}` (note the change from today's `{user_id}/{session_id}/{filename}` to user-scoped). Metadata persisted in the existing user/profile database (table `user_attachments`).
**Testing**: pytest for backend (target ≥90% coverage on changed code per Constitution III), Vitest + Testing Library for frontend, with an end-to-end happy-path test per file category.
**Target Platform**: Linux server (backend Docker image), modern desktop browsers (Chromium, Firefox, Safari).
**Project Type**: Web application — `backend/` (FastAPI) + `frontend/` (Vite/React/TS).
**Performance Goals**: Per SC-001, agent reply within 15 s for files ≤ 5 MB. Upload validation rejection within 2 s (SC-003). Parser tool latency target: ≤ 3 s for non-OCR paths on a 5 MB file; OCR fallback may take longer and MUST stream a "processing" status to the chat UI.
**Constraints**: 30 MB per-file cap (FR-003), no fixed per-message attachment count, user-scoped retention bounded by account/file deletion (FR-012), PHI must not leave the existing data-class boundaries (FR-011), authentication MUST use the existing Keycloak `require_user_id` dependency (Constitution VII).
**Scale/Scope**: Single-tenant clinical-analyst user base (existing). Expected order-of-magnitude: tens of users, hundreds of attachments per user, low single-digit concurrent uploads. Not designed for multi-MB/s sustained throughput.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Primary Language (Python backend) | PASS | All new backend code is Python; parser tools live under `backend/agents/general/`. |
| II. Frontend Framework (Vite + React + TS) | PASS | All UI changes are in `frontend/src/components/ChatInterface.tsx` and a new attachment hook, all TypeScript. |
| III. Testing Standards (≥90% coverage, unit + integration) | PASS (with plan) | Each new parser tool gets unit tests with sample fixtures per file type plus an integration test exercising `/api/upload` → tool dispatch. Vitest covers the composer changes. |
| IV. Code Quality (PEP 8 / ESLint) | PASS | New files conform to existing ruff and ESLint configs; no new lint exceptions introduced. |
| V. Dependency Management (lead approval) | **GATE — needs approval** | Ten new Python packages and one system package (Tesseract). Listed in plan; PR description must record lead-developer approval before merge. Documented under Complexity Tracking. |
| VI. Documentation (docstrings, /docs) | PASS | Every new tool function gets a Google-style docstring. The `/api/upload` endpoint's expanded contract is reflected automatically in FastAPI's `/docs`. New agent tools self-describe via `TOOL_REGISTRY` `description` + `input_schema`. |
| VII. Security (Keycloak, RFC 8693, input validation) | PASS | Reuses `Depends(require_user_id)`. Filenames continue to be sanitized via `os.path.basename`. Content-type sniffing (`python-magic`) closes the FR-008 mislabeling gap. XML parsed via `defusedxml`. PHI handling unchanged. Agent calls into file tools continue to use the existing RFC 8693 attenuated-token path. |
| VIII. User Experience (primitive components, dynamic generation) | PASS | The paperclip, chip, and drop overlay already exist as primitives; this feature extends their accepted-type set and adds an attachment library panel. No new primitive component is introduced. |

**Result**: Gate PASSES contingent on lead-developer dependency approval being recorded in the implementation PR (tracked under Complexity Tracking). No principle violations.

## Project Structure

### Documentation (this feature)

```text
specs/002-file-uploads/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── upload-api.md    # /api/upload, /api/attachments
│   └── agent-tools.md   # General-agent file-handling tool schemas
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
backend/
├── orchestrator/
│   ├── auth.py                       # CHANGE: switch storage path to user-scoped, return attachment_id
│   ├── api.py                        # CHANGE: add /api/attachments (list, get, delete)
│   └── attachments/                  # NEW
│       ├── __init__.py
│       ├── store.py                  # filesystem layout, path resolution, deletion
│       ├── repository.py             # SQL access for user_attachments table
│       ├── content_type.py           # extension allow-list + python-magic sniffing
│       └── models.py                 # Pydantic schemas for Attachment / AttachmentRef
├── agents/general/
│   ├── mcp_tools.py                  # CHANGE: register new file-handling tools in TOOL_REGISTRY
│   └── file_tools/                   # NEW
│       ├── __init__.py
│       ├── read_document.py          # PDF, DOCX, RTF, ODT
│       ├── read_spreadsheet.py       # XLSX, XLS, ODS, TSV, CSV
│       ├── read_presentation.py      # PPTX, PPT, ODP
│       ├── read_text.py              # TXT, MD, JSON, YAML, XML, HTML, LOG, code
│       ├── read_image.py             # PNG, JPG, GIF, WEBP — returns bytes ref for vision model
│       └── ocr.py                    # shared OCR + page-rasterization helpers
└── tests/
    ├── attachments/
    │   ├── test_store.py
    │   ├── test_repository.py
    │   ├── test_content_type.py
    │   └── test_upload_endpoint.py
    └── agents/general/file_tools/
        ├── fixtures/                 # one minimal sample per supported extension
        ├── test_read_document.py
        ├── test_read_spreadsheet.py
        ├── test_read_presentation.py
        ├── test_read_text.py
        ├── test_read_image.py
        └── test_ocr_fallback.py

frontend/
├── src/
│   ├── components/
│   │   ├── ChatInterface.tsx         # CHANGE: expand `accept`, drag-drop validation, multi-attachment chip list
│   │   └── AttachmentLibrary.tsx     # NEW: cross-chat panel listing the user's uploaded files (FR-009)
│   ├── hooks/
│   │   └── useAttachments.ts         # NEW: state + REST calls for attachment CRUD
│   └── lib/
│       └── attachmentTypes.ts        # NEW: shared accepted-extension list, MIME map, 30 MB cap
└── src/test/
    ├── ChatInterface.attachments.test.tsx
    ├── useAttachments.test.ts
    └── AttachmentLibrary.test.tsx
```

**Structure Decision**: Web application (Constitution-mandated `backend/` + `frontend/`). New code is grouped into two cohesive modules — `backend/orchestrator/attachments/` for storage/metadata and `backend/agents/general/file_tools/` for parser tools — to keep the upload concern (auth, persistence) cleanly separate from the agent-side reading concern. The frontend introduces a small `useAttachments` hook plus one new primitive-composing component (`AttachmentLibrary`) so the UX changes do not bloat `ChatInterface.tsx`.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| 10 new Python deps + 1 system dep (Tesseract/Poppler) — gated by Constitution V | Each dep covers a distinct file format the spec requires (FR-001) or the OCR fallback (FR-013). Office formats (DOCX/PPTX/ODT/ODS/ODP/RTF/XLS) have no shared parser; OCR requires a binary engine. | Writing custom parsers per format would balloon LOC, surface area for bugs, and PHI risk. A single "convert via headless office" alternative (e.g., LibreOffice in a sidecar) was rejected: heavier image, slower per-call latency, harder to sandbox, and harms the SC-001 15 s budget. |
| User-scoped storage path migration (today: `tmp/{user_id}/{session_id}/`, new: `tmp/{user_id}/{file_id}/`) | Spec clarification: files are global to the user and appear inline across chats (FR-009, FR-012). Session-scoped paths cannot satisfy this. | Adding a symlink layer per chat was rejected — it doubles failure modes and complicates retention. A clean cut to user-scoped paths plus a SQL `user_attachments` table is simpler and matches the data model. |
