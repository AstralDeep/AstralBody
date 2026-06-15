# Phase 1 Data Model: Chat Attachment Upload & Universal Parsing

All schema changes ship as **idempotent, guarded** deltas in `backend/shared/database.py::_init_db()` (Constitution IX), using the established `CREATE TABLE IF NOT EXISTS` + `_column_exists()` guards. Rollback documented at the end.

## Entities

### Attachment (existing — `user_attachments`, reused unchanged)

Already created by feature 002. No shape change.

```sql
CREATE TABLE IF NOT EXISTS user_attachments (
    attachment_id TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL,
    filename      TEXT NOT NULL,
    content_type  TEXT NOT NULL,
    category      TEXT NOT NULL,      -- now may be a broadened/no-parser category (see R3)
    extension     TEXT NOT NULL,
    size_bytes    BIGINT NOT NULL,
    sha256        TEXT NOT NULL,
    storage_path  TEXT NOT NULL,
    created_at    BIGINT NOT NULL,
    deleted_at    BIGINT
);
-- existing indexes: idx_user_attachments_user(user_id, created_at DESC),
--                   idx_user_attachments_live(user_id) WHERE deleted_at IS NULL
```

Ownership rule (unchanged): every read goes through `repository.get_by_id(attachment_id, user_id)` / `resolve_attachment()`; a non-owner gets a uniform not-found (404), never another user's data.

### MessageAttachment (NEW — `message_attachment`)

Links a sent chat turn to the attachments the user included, so the orchestrator can (a) deliver structured references to the handling agent and (b) re-hydrate references on `load_chat`.

```sql
CREATE TABLE IF NOT EXISTS message_attachment (
    id            TEXT PRIMARY KEY,        -- uuid4
    chat_id       TEXT NOT NULL,
    message_id    TEXT,                    -- nullable: links to the persisted user message when available
    attachment_id TEXT NOT NULL,           -- FK→user_attachments.attachment_id (app-enforced)
    user_id       TEXT NOT NULL,           -- denormalized owner for fast ownership filter
    created_at    BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_message_attachment_chat ON message_attachment(chat_id, created_at);
CREATE INDEX IF NOT EXISTS idx_message_attachment_att  ON message_attachment(attachment_id);
```

- **Validation**: `attachment_id` must resolve to a live attachment owned by `user_id` at send time; up to **10** rows per turn (per-message cap). Rows referencing a since-deleted attachment are tolerated at read time (agent reports "no longer available").
- **Lifecycle**: inserted when a `chat_message` with `attachments[]` is processed; never updated; read on turn build + `load_chat`.

### AttachmentParser (NEW — `attachment_parser`)

Registry of globally-available parsers keyed by file type, plus the dedup/provenance for the auto-creation flow. One row per file-type gap.

```sql
CREATE TABLE IF NOT EXISTS attachment_parser (
    id                  TEXT PRIMARY KEY,    -- uuid4
    extension           TEXT,                -- normalized extension (e.g. 'parquet', 'nii.gz'); nullable if category-scoped
    category            TEXT NOT NULL,       -- attachment category the parser serves
    gap_fingerprint     TEXT NOT NULL,       -- stable hash of the format gap (dedup key)
    status              TEXT NOT NULL,       -- 'pending' | 'live' | 'failed' | 'discarded'
    draft_agent_id      TEXT,                -- FK→draft_agents.id (the draft being / that was created)
    live_agent_id       TEXT,                -- the promoted public agent id once live
    tool_name           TEXT,                -- the parse_<fmt> tool name once live
    source_attachment_id TEXT,               -- the upload that first triggered creation
    source_chat_id      TEXT,                -- originating chat (for the uploader status card)
    requested_by        TEXT,                -- uploading user_id
    approved_by         TEXT,                -- admin user_id who approved (NULL until live)
    created_at          BIGINT NOT NULL,
    updated_at          BIGINT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_attachment_parser_gap ON attachment_parser(gap_fingerprint);
CREATE INDEX IF NOT EXISTS idx_attachment_parser_status ON attachment_parser(status);
```

- **Dedup**: `uq_attachment_parser_gap` guarantees at most one row per format gap. A new upload of the same uncovered type finds an existing `pending`/`live` row and does **not** spawn a second draft (FR-018, SC-007).
- **State transitions**:
  - `pending` → `live` (admin approves; `live_agent_id`/`tool_name`/`approved_by` set; backing agent made public)
  - `pending` → `failed` (security gate or self-test fails irrecoverably; surfaced, refine/discard available)
  - `pending` → `discarded` (admin discards)
  - `failed`/`discarded` → `pending` (a later upload may re-trigger; same row re-opened or replaced under the same fingerprint)
- **Coverage lookup**: on each upload, after the static `parser_registry` coverage map says "no built-in parser," consult `attachment_parser` for a `live` row → if present, the type is already globally covered (no new draft).

### DraftAgent (existing — `draft_agents`, reused + one guarded column)

Reused with `origin = 'auto_attachment'`. Existing 027 provenance columns (`origin`, `source_chat_id`, `gap_fingerprint`, `self_test`) carry the autoparse lifecycle. One additive guarded column:

```sql
-- guarded add (idempotent), via _column_exists(cursor, 'draft_agents', 'source_attachment_id')
ALTER TABLE draft_agents ADD COLUMN source_attachment_id TEXT;
```

- Purpose: after admin approval, re-parse the exact file that triggered creation and continue the uploader's request (FR-017).

### ParserCapability (conceptual — no new table)

The runtime ability to read a type. Backed by either a built-in `read_*` tool (existing) or a promoted public auto-created agent's `parse_<fmt>` tool. Its provenance/registry lives in `attachment_parser`; its live execution uses the existing agent fleet + `agent_ownership(is_public=True)`.

## Coverage map (`parser_registry`)

A pure-Python, in-process map (no table) declaring which extension/category has a built-in parser, mirroring the `read_*` tool category mapping:

| category | built-in tool | parseable? |
|---|---|---|
| document (pdf, docx, doc, rtf, odt, …) | `read_document` | yes |
| spreadsheet (xlsx, xls, ods, tsv, csv, …) | `read_spreadsheet` | yes |
| presentation (pptx, ppt, odp, …) | `read_presentation` | yes |
| text (txt, md, json, yaml, xml, html, code, + broadened text/code adds) | `read_text` | yes |
| image (png, jpg, jpeg, gif, webp, …) | `read_image` | yes |
| medical (dcm, nii, nii.gz, czi, …) | medical tools | yes |
| **data** (parquet, avro, feather, ndjson*, …) | — | **no → auto-create** |
| **archive** (zip, tar, gz, 7z, epub*, …) | — | **no → auto-create** |

\* Items that are genuinely textual (e.g. `ndjson`) are mapped to `text`/`read_text` instead; the `data`/`archive` buckets hold only types with no existing reader, which is what makes auto-creation reachable. Exact final assignment is enumerated in `content_type.py` during implementation.

## Size caps (`MAX_BYTES_BY_CATEGORY` additions)

Existing: document/spreadsheet/presentation/text/image = 30 MB; medical = 2 GB. New:

| category | cap |
|---|---|
| data | 100 MB |
| archive | 100 MB |

(Values tunable; chosen to allow realistic data/archive files without enabling abuse. Per-message cap = 10 attachments.)

## Idempotency & ordering

- All deltas run in `_init_db()` at startup; safe to re-run (guards: `IF NOT EXISTS`, `_column_exists`).
- `attachment_parser` and `message_attachment` have no FK constraints to avoid ordering fragility across the existing `_init_db` sequence; referential integrity is app-enforced (consistent with the repo's existing approach).
- No data backfill required (purely additive).

## Rollback

- **Down path**: `DROP TABLE IF EXISTS message_attachment; DROP TABLE IF EXISTS attachment_parser; ALTER TABLE draft_agents DROP COLUMN IF EXISTS source_attachment_id;` Removing these is non-destructive to existing features (the legacy text-hack path still functions; built-in parsers unaffected). Auto-created public parser agents, if any were promoted, remain as ordinary public agents and can be retired via the existing agent-retirement path.
- **Forward-compat**: because every delta is guarded, rolling back code without dropping tables is safe (the columns/tables simply go unused).
