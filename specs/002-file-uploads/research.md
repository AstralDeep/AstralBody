# Phase 0 Research: Common File Type Uploads

**Feature**: 002-file-uploads
**Date**: 2026-04-13

The spec was clarified in `/speckit.clarify` so there are no `NEEDS CLARIFICATION` markers carried into this plan. This document records the dependency, parsing-strategy, and storage decisions needed before Phase 1 design.

---

## 1. PDF text extraction

**Decision**: Use `pypdf` for embedded-text extraction; rasterize with `pdf2image` + Poppler and run `pytesseract` for the OCR fallback path mandated by FR-013.

**Rationale**:
- `pypdf` is pure Python, MIT-licensed, no system deps, and handles the dominant "PDF with selectable text" case in well under the 3 s parser budget.
- `pdf2image` + Poppler is the established Python wrapper for page-to-image rasterization needed before OCR.
- `pytesseract` wraps the Tesseract binary, which is the only credible open-source OCR engine of usable quality. Bundling Tesseract into the existing backend Docker image is a one-line `apt-get install`.

**Alternatives considered**:
- `PyMuPDF (fitz)`: faster and supports rendering in one library, but AGPL-licensed — incompatible with the project's Apache 2.0 license per Constitution.
- `pdfminer.six`: text-only, slower, awkward API; no rendering path so we'd still need a separate library for OCR rasterization.
- Cloud OCR (AWS Textract, Google Vision): rejected — sends PHI to a third party not currently in the data-class boundary (FR-011 violation).

---

## 2. Office formats (DOCX, XLSX, PPTX, RTF, ODT/ODS/ODP, legacy `.doc`/`.xls`/`.ppt`)

**Decision**:
- DOCX → `python-docx`
- XLSX → existing `openpyxl` (already in use)
- PPTX → `python-pptx`
- RTF → `striprtf`
- ODT / ODS / ODP → `odfpy`
- Legacy `.xls` → `xlrd` (pinned to a version that still supports `.xls`)
- Legacy `.doc` / `.ppt` → out of scope for direct parsing; surface a clear "legacy binary format not supported, please save as `.docx`/`.pptx`" message to the user.

**Rationale**:
- Each format has a well-maintained, permissively-licensed pure-Python library that returns text (and, for spreadsheets, structured rows).
- Legacy `.doc` and `.ppt` (OLE compound binary) have no good pure-Python parser; the only credible path is invoking LibreOffice in headless mode, which contradicts the lightweight-parser approach in Complexity Tracking and has been rejected at the plan level.

**Alternatives considered**:
- `tika-python`: one library covers most formats, but requires a JVM sidecar — adds significant image weight and an out-of-stack runtime.
- `unstructured`: high-level wrapper around many parsers; pulls in a very large transitive dependency tree, much of it unused.
- `pandas.read_excel`: already available, but pandas is a heavy dep to lean on for a single file type when `openpyxl` is already direct.

---

## 3. Plain text, code, markup

**Decision**:
- TXT, MD, JSON, YAML, LOG, code files: read as UTF-8 with a `chardet`-style charset fallback only if UTF-8 decode fails (use Python's built-in `codecs` module with a small custom sniffing helper — no new dep).
- HTML/XML: parse with `defusedxml.ElementTree` (XML) and `html.parser` from stdlib (HTML). Avoid `lxml`/`BeautifulSoup` — the spec needs a textual representation, not full DOM traversal, and stdlib + `defusedxml` gets us there with one approved dep.
- For Markdown specifically, no rendering is needed; the agent reasons over raw Markdown source.

**Rationale**: Minimizes new dependencies (only `defusedxml`) and avoids XXE attacks on user-supplied XML/HTML.

**Alternatives considered**:
- `BeautifulSoup4` + `lxml`: feature-rich but unnecessary for a "give me readable text" path.

---

## 4. Image normalization for the vision model

**Decision**: Use `Pillow` to (a) confirm decodability, (b) re-encode to a single canonical format (`PNG` for lossless, `JPEG` for photographs over a size threshold), and (c) cap the largest dimension at 2048 px to keep token cost predictable for the downstream vision model.

**Rationale**: Pillow is the de facto standard, Apache 2.0–compatible (PIL/HPND), and lets us deliver a sanitized image to the vision model without re-implementing decoders.

**Alternatives considered**:
- Send raw uploaded bytes through unchanged: rejected because malformed or pathological images (giant resolutions, polyglot files) become the vision model's problem and hurt SC-001 latency.

---

## 5. Content-type sniffing (FR-008)

**Decision**: Use `python-magic` (libmagic bindings) to detect the actual content type from file bytes, in addition to extension-based allow-listing. Mismatches raise a clear "file type does not match its extension" error.

**Rationale**: FR-008 explicitly demands content-based detection, not extension-based. `libmagic` is already present in most base images; the Python wrapper is small and well-maintained.

**Alternatives considered**:
- `filetype` (pure Python): supports fewer formats and misses several Office variants.
- Trust the extension only: rejected — directly contradicts FR-008.

---

## 6. Storage layout and retention

**Decision**: Move the on-disk layout from `backend/tmp/{user_id}/{session_id}/{filename}` to `backend/tmp/{user_id}/{attachment_id}/{filename}`, with `attachment_id` being a UUIDv4 generated at upload time. Persist a `user_attachments` row keyed by `attachment_id` containing `user_id`, original filename, content type, byte size, sha256, created_at, and `deleted_at` (nullable).

**Rationale**:
- The spec clarification made files **user-scoped**, not session-scoped (FR-009, FR-012). Session-scoped paths must go.
- A UUID directory (rather than putting files directly under `{user_id}/`) avoids filename collisions when the same user uploads two files with the same name.
- A SQL row is the single source of truth for whether a file is live, who owns it, and what the original metadata was — trivially supports the cross-chat library panel and the deletion paths in FR-012.

**Alternatives considered**:
- Object storage (S3-compatible): cleaner long-term, but adds a new infrastructure dependency and isn't required at current scale (tens of users). Can be migrated later behind the same `attachments/store.py` interface.
- Storing metadata only on the filesystem (no DB row): would force a directory walk for every "list my files" request, doesn't scale, and complicates soft-delete semantics.

---

## 7. Per-file size limit enforcement

**Decision**: Enforce the 30 MB cap (FR-003) at three layers:

1. Browser: `accept` attribute + an early JS `file.size` check before the network request, so the user gets a sub-2 s rejection (SC-003) for the common case.
2. FastAPI route: Reject during streaming receive once cumulative bytes exceed the cap, returning HTTP 413.
3. Reverse proxy / ASGI server config (if used in deployment): set `client_max_body_size` (or equivalent) above 30 MB but below the FastAPI default to make the limit observable at the edge.

**Rationale**: Layered defense; the JS check is for UX, the FastAPI check is the authoritative limit, the proxy check guards the network.

---

## 8. Per-tool dispatch on the general agent

**Decision**: Add one tool per file *category* (`read_document`, `read_spreadsheet`, `read_presentation`, `read_text`, `read_image`) registered in the existing `TOOL_REGISTRY` dict in `backend/agents/general/mcp_tools.py`. Each tool takes an `attachment_id` (string) plus optional category-specific arguments (e.g., `sheet_name` for spreadsheets, `page_range` for documents). A small dispatcher resolves the attachment, verifies the calling user owns it, sniffs the content type, and routes to the right reader implementation.

**Rationale**:
- Matches the existing tool-registration pattern (no decorator framework, plain dict entries with `function`, `scope`, `description`, `input_schema`).
- One tool per category (rather than one per extension) keeps the agent's tool list short and prompts simpler, while the dispatcher still picks the right backend per actual content type.
- Ownership re-check inside the tool closes the FR-009 cross-user-leak hole even if the agent is somehow handed a foreign `attachment_id`.

**Alternatives considered**:
- A single uber-tool `read_attachment(attachment_id)` that returns "whatever the parser produced": simpler tool list, but the agent loses the ability to ask category-shaped questions (e.g., "what sheets are in this spreadsheet?"). Rejected.
- One tool per extension: too many tools, lots of duplicated boilerplate, harder for the agent to plan.

---

## Summary of approvals required (Constitution V)

The implementation PR description must explicitly request and record lead-developer approval for these new Python packages: `pypdf`, `python-docx`, `python-pptx`, `odfpy`, `striprtf`, `xlrd`, `Pillow`, `pytesseract`, `pdf2image`, `defusedxml`, `python-magic`. It must also call out the new system packages added to the backend Docker image: `tesseract-ocr`, `poppler-utils`, `libmagic1`.
