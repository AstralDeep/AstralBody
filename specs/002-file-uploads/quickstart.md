# Quickstart: Common File Type Uploads

**Feature**: 002-file-uploads
**Audience**: A developer picking up the implementation, or a reviewer validating the running feature end-to-end.

## Prerequisites

- A working AstralBody dev environment (backend + frontend running, Keycloak reachable).
- Backend Docker image rebuilt to include the new system packages: `tesseract-ocr`, `poppler-utils`, `libmagic1`.
- New Python deps installed (lead-developer approval recorded in PR per Constitution V): `pypdf`, `python-docx`, `python-pptx`, `odfpy`, `striprtf`, `xlrd`, `Pillow`, `pytesseract`, `pdf2image`, `defusedxml`, `python-magic`.
- A vision-capable model wired into the general agent (separate, prerequisite work — this feature only delivers image bytes to it).

## End-to-end smoke test

1. **Start** backend (`uvicorn backend.orchestrator.api:app --reload`) and frontend (`npm run dev` in `frontend/`).
2. **Sign in** through the chat UI using a test Keycloak user.
3. **Click the paperclip** in the chat composer. Confirm the picker accepts each of these (drag-drop should accept the same set):
   - Document: a small `.pdf`, a `.docx`, an `.rtf`.
   - Spreadsheet: an `.xlsx`, a `.csv`.
   - Presentation: a `.pptx`.
   - Text/code: a `.json`, a `.py`, a `.yaml`.
   - Image: a `.png`.
4. **Attach two files** (e.g., the PDF and the XLSX) in one message. Confirm both chips render with filename, category icon, and remove control.
5. **Send** with the prompt: *"Summarize the PDF and tell me how many rows the spreadsheet has."* Expect a reply that references content from the PDF and a row count from the XLSX, returned within 15 s for files ≤ 5 MB (SC-001).
6. **Open a different chat** and click the new AttachmentLibrary panel. Confirm both files from step 4 are listed (FR-009 cross-chat). Re-attach the PDF into this new chat without re-uploading.
7. **Sign in as a different test user** and confirm the AttachmentLibrary panel does NOT show user-1's files (SC-006).

## Validation matrix (manual, per-category)

| File type | Expected agent behavior |
|-----------|-------------------------|
| Text-bearing PDF | Summarizes content; `ocr_used: false` if you inspect the tool call. |
| Scanned/image-only PDF | Summarizes content; `ocr_used: true`; or, if OCR yields nothing, falls back to vision-model description (FR-013). |
| DOCX | Returns prose summary referencing actual paragraphs. |
| XLSX with multiple sheets | Names all sheets; reads from the requested one. |
| PPTX | Returns slide-by-slide titles + body text. |
| Markdown / JSON / YAML | Reasons over the raw structure. |
| PNG screenshot | Describes elements visible in the image (assumes vision model is connected). |

## Negative-path checks

- **Oversize**: try to attach a 40 MB file. The composer must reject it within ~2 s (SC-003) and name both the file and the 30 MB limit. The backend must also reject it with `413` if the client check is bypassed (FR-003).
- **Unsupported extension**: try to attach a `.dwg` file. The composer rejects it; if forced through, the backend returns `415` listing the supported categories (FR-006).
- **Mislabeled extension**: rename a `.exe` to `.pdf` and attempt upload. Backend returns `415` with the content-type mismatch detail (FR-008).
- **Cross-user access**: as user-1, copy an `attachment_id` from the AttachmentLibrary; sign in as user-2; try `GET /api/attachments/{that_id}` → expect `404` (not 403).
- **Deletion**: delete a file from the AttachmentLibrary. Confirm a chat that previously referenced it now shows the chip in the "no longer available" state and that the agent's tool call returns `not_found` if it tries to read it.

## Test commands

```bash
# Backend unit + integration
pytest backend/tests/attachments backend/tests/agents/general/file_tools \
  --cov=backend/orchestrator/attachments \
  --cov=backend/agents/general/file_tools \
  --cov-fail-under=90

# Frontend
cd frontend && npm run test -- ChatInterface.attachments useAttachments AttachmentLibrary
```

The 90% threshold (Constitution III) is enforced on both `backend/orchestrator/attachments/` and `backend/agents/general/file_tools/` packages.

## Rollout notes

- The on-disk layout changes from `tmp/{user_id}/{session_id}/{filename}` to `tmp/{user_id}/{attachment_id}/{filename}`. Existing files under the old layout (if any in non-prod environments) will not be visible after deploy; document this in the PR. No production migration is required because no attachments persist in production today (current behavior treated uploads as transient session blobs).
- The new system packages bump backend image size by ~150 MB; coordinate with the deployment owner.
