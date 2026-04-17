# Contract: General-Agent File Tools

**Feature**: 002-file-uploads
**Authoritative source**: `TOOL_REGISTRY` entries in `backend/agents/general/mcp_tools.py` and reader implementations under `backend/agents/general/file_tools/`.

All tools are registered as plain-dict entries in `TOOL_REGISTRY`, matching the project's existing pattern (no decorator framework). Each entry provides `function`, `scope`, `description`, and `input_schema`.

**Common preconditions for every tool**:

1. The dispatcher resolves `attachment_id` against `user_attachments`.
2. The Attachment's `user_id` MUST equal the calling user's Keycloak `sub` (FR-009). Mismatch → tool returns a structured `not_found` error; the agent MUST NOT see the attachment.
3. The Attachment MUST NOT be `DELETED`.
4. The dispatcher uses `python-magic` to confirm the stored content type still matches `category`; mismatch surfaces an `unreadable_file` error rather than silent garbage (FR-008).

**Common error shape** returned by every tool:

```json
{ "error": { "code": "not_found | unreadable_file | parse_failed | unsupported", "message": "human-readable detail" } }
```

---

## Tool: `read_document`

Read text from a document-class file: PDF, DOCX, RTF, ODT.

**Input schema**:

```json
{
  "type": "object",
  "properties": {
    "attachment_id": { "type": "string", "format": "uuid" },
    "page_range":    { "type": "string", "description": "Optional. e.g., '1-5,9'. PDFs only; ignored for other formats." },
    "max_chars":     { "type": "integer", "minimum": 1, "default": 200000 }
  },
  "required": ["attachment_id"]
}
```

**Behavior**:
- PDF: try `pypdf` text extraction first. If extracted text length is below a small threshold (e.g., 32 chars total across requested pages), fall back to OCR (FR-013): rasterize via `pdf2image` and run `pytesseract`. If that also fails, return the page images as base64 data for the connected vision model under the response's `images` array.
- DOCX/RTF/ODT: extract text directly with the corresponding library.

**Success response**:

```json
{
  "filename": "Q4-report.pdf",
  "content_type": "application/pdf",
  "page_count": 12,
  "text": "...extracted text...",
  "truncated": false,
  "ocr_used": false,
  "images": []
}
```

If the OCR fallback also yields nothing, `text` is empty, `ocr_used` is `true`, and `images` contains the page images so the agent can hand them to the vision tool.

---

## Tool: `read_spreadsheet`

Read tabular data from XLSX, XLS, ODS, TSV, CSV.

**Input schema**:

```json
{
  "type": "object",
  "properties": {
    "attachment_id": { "type": "string", "format": "uuid" },
    "sheet_name":    { "type": "string", "description": "Optional. Defaults to the first sheet. Ignored for CSV/TSV." },
    "max_rows":      { "type": "integer", "minimum": 1, "default": 1000 }
  },
  "required": ["attachment_id"]
}
```

**Success response**:

```json
{
  "filename": "cohort.xlsx",
  "sheet_name": "Sheet1",
  "sheet_names": ["Sheet1", "Notes"],
  "columns": ["patient_id", "age", "diagnosis"],
  "rows": [["P001", 47, "..."], ["P002", 53, "..."]],
  "row_count": 1284,
  "truncated": true
}
```

`truncated` is `true` when `row_count > max_rows`; the agent can issue follow-up calls with a higher `max_rows` if needed.

---

## Tool: `read_presentation`

Read slide text from PPTX, ODP. (`.ppt` legacy is rejected at upload time per research.md §2.)

**Input schema**:

```json
{
  "type": "object",
  "properties": {
    "attachment_id": { "type": "string", "format": "uuid" },
    "slide_range":   { "type": "string", "description": "Optional. e.g., '1-5,9'." }
  },
  "required": ["attachment_id"]
}
```

**Success response**:

```json
{
  "filename": "kickoff.pptx",
  "slide_count": 18,
  "slides": [
    { "slide_number": 1, "title": "Q4 Goals", "text": "...", "speaker_notes": "..." }
  ]
}
```

---

## Tool: `read_text`

Read plain-text and structured-text files: TXT, MD, JSON, YAML, XML, HTML, LOG, and code (PY/JS/TS/TSX/JSX/SQL/SH/PS1/CSS).

**Input schema**:

```json
{
  "type": "object",
  "properties": {
    "attachment_id": { "type": "string", "format": "uuid" },
    "max_chars":     { "type": "integer", "minimum": 1, "default": 200000 }
  },
  "required": ["attachment_id"]
}
```

**Behavior**: Decode as UTF-8; on failure, fall back to a charset sniff. For HTML/XML, parse via `defusedxml`/stdlib and return both the raw source (`text`) and a stripped plaintext rendering (`plaintext`).

**Success response**:

```json
{
  "filename": "config.yaml",
  "content_type": "text/yaml",
  "language": "yaml",
  "text": "...raw file contents...",
  "plaintext": null,
  "truncated": false
}
```

---

## Tool: `read_image`

Deliver an image to the connected vision-capable model (FR-010).

**Input schema**:

```json
{
  "type": "object",
  "properties": {
    "attachment_id": { "type": "string", "format": "uuid" }
  },
  "required": ["attachment_id"]
}
```

**Behavior**: Open with Pillow; verify decodability; resize so the largest dimension ≤ 2048 px; re-encode (PNG for files originally ≤ 1 MB or with transparency, JPEG quality 90 otherwise); return base64-encoded bytes with the canonical content type.

**Success response**:

```json
{
  "filename": "screenshot.png",
  "content_type": "image/png",
  "width": 1920,
  "height": 1080,
  "image_base64": "iVBORw0KGgoAAAANSUh..."
}
```

The agent's runtime is responsible for forwarding `image_base64` + `content_type` to the vision model; this tool's contract ends at producing those fields.

---

## Tool: `list_attachments`

Convenience tool letting the agent enumerate the user's available attachments without leaving the chat. Mirrors `GET /api/attachments` but is callable from the agent's tool surface.

**Input schema**:

```json
{
  "type": "object",
  "properties": {
    "category": { "type": "string", "enum": ["document", "spreadsheet", "presentation", "text", "image"] },
    "limit":    { "type": "integer", "minimum": 1, "maximum": 200, "default": 50 }
  }
}
```

**Success response**: same shape as `GET /api/attachments`.

---

## Registry diff (informative)

These five new tools are added to `TOOL_REGISTRY` in `backend/agents/general/mcp_tools.py`:

```
read_document, read_spreadsheet, read_presentation, read_text, read_image, list_attachments
```

No existing tool is removed or renamed.
