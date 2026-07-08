# Data Model: 052-perf-comment-hygiene

Persistent schema deltas are minimal (Constitution IX): one new table, one promoted
backfill, optional indexes. Everything else is in-memory or log-shaped.

## 1. `schema_meta` (NEW table — R11)

| Column | Type | Notes |
|---|---|---|
| `key` | TEXT PRIMARY KEY | e.g. `revision` |
| `value` | TEXT NOT NULL | current `SCHEMA_REVISION` string |

- Written by `_init_db` after a successful full migration run; read (1 query) at boot.
- `revision` match → fast path (skip the ~130-statement idempotent run, ≤250ms budget);
  mismatch or missing row/table → full run, then upsert marker.
- `SCHEMA_REVISION` is a constant in `shared/database.py`, bumped by any PR touching
  `_init_db` or its migration helpers; a unit test hashes that source region and fails if
  the hash changes without a bump (prevents silent staleness).
- Name deliberately distinct from the existing, unrelated `audit_events.schema_version`
  column.
- **Rollback**: `DELETE FROM schema_meta WHERE key='revision';` (or `DROP TABLE
  schema_meta;`) — next boot runs the full idempotent migration set exactly as today.
  Table creation itself is `CREATE TABLE IF NOT EXISTS` (idempotent, guarded).

## 2. `tool_overrides` per-kind backfill (PROMOTED, not new — R4)

- The existing `backfill_per_tool_rows` logic moves from per-detail-render execution to a
  one-time guarded `_init_db` migration (`_migrate_backfill_tool_kinds_052`), idempotent
  via its existing `ON CONFLICT DO NOTHING` inserts.
- No column/table change. **Rollback**: none needed (rows are the same ones the runtime
  path would have produced; removing the per-render call is code-level).

## 3. Optional hot-path indexes (CONDITIONAL — R4)

- Added only if post-fix measurement misses SC-001/SC-002 budgets; candidates:
  `messages(chat_id, created_at DESC)` (last-message subquery),
  `message_attachment(message_id)`. Ship as `CREATE INDEX IF NOT EXISTS` deltas with
  rollback `DROP INDEX IF EXISTS`.

## 4. In-memory structures (no schema)

| Structure | Scope & lifetime | Keys / invalidation |
|---|---|---|
| Connection pool (`ThreadedConnectionPool`) | process | `DB_POOL_MIN/MAX`; stale conns discarded on OperationalError; `DB_POOL_DISABLE=1` kill switch |
| Permission memo (R5) | one chat turn | `(user_id, agent_id, tool, kind)`; created per `handle_chat_message`, never crosses turns — revocations visible next turn |
| Static asset version map (R7) | process, rebuilt on boot | file path → sha1[:12]; deploy = new process = new hashes |
| JWKS cache (existing) + warm task (R8) | process | url → keys; warmed at boot, refreshed ~500s; kid-miss escape unchanged |
| Designer in-flight guard (R9) | per socket/chat | designed `ui_render` dropped if the socket's active chat changed |
| PHI gate singleton (existing, R12) | process | warmed by boot thread; identical fail-closed behavior |

## 5. Perf timing record (log-shaped — R16)

One structured log line per span, stdlib logging, no PHI/PII (ids only):

```
perf <span_name> duration_ms=<int> [surface=<key>] [chat=<id>] [user=<opaque-id>] [phase=<name>]
```

Span names (initial set): `surface.render.<key>`, `register_ui.total`,
`register_ui.validate`, `register_ui.reads`, `welcome.render`, `turn.route`,
`turn.tools`, `turn.designer`, `turn.narrative`, `boot.init_db`, `boot.jwks_warm`,
`boot.phi_warm`, `static.version_map`. quickstart.md's protocol greps these.

## 6. Comment-policy categories (checker model — R17)

Every comment token classifies into exactly one category:

| Category | Definition | Checker treatment |
|---|---|---|
| `file-header` | first docstring (py) / leading comment block (js/css/kt) stating file purpose | REQUIRED — missing ⇒ `--check` failure |
| `doc-comment` | function/method/class docstring, KDoc, JSDoc | allowed |
| `directive` | shebang, encoding, `noqa`, `type: ignore`, `pragma`, `fmt:`/isort/ruff, eslint | MUST survive — deletion in a diff ⇒ failure |
| `rationale` | single-line comment carrying non-obvious invariant/race/quirk/workaround | allowed; human-judged, NOT machine-gated |
| `banner` | `# ---- Section ----` style separators | forbidden ⇒ failure |
| `dead-code` | ≥2 consecutive comment lines parsing as code (`ast.parse`) | forbidden ⇒ failure |
| `spec-marker` | `\b(T\d{3}\|FR-\d{3}\|US\d+)\b` inside a comment | forbidden ⇒ failure |
| `narration` | everything else | forbidden by policy; removed in sweep; flagged in `--report` (not `--check`, to avoid false-positive gating of rationale lines) |

Scope: `backend/` (py + static js/css), `windows-client/`, `android-client/`, `scripts/`;
excluded: `apple-clients/`, vendored assets (`webrender/static/vendor/`, fonts),
generated artifacts, `.venv*`, SQL seeds, Markdown.

## 7. Key entities from spec — disposition

| Spec entity | Realization |
|---|---|
| Schema Version Marker | §1 `schema_meta` |
| Timing Measurement | §5 log record |
| Versioned Static Asset | §4 version map + contracts/static-asset-caching.md |
| User-Scoped Surface Cache Entry | reserved (research R6): only if post-fix P95 misses SC-001; would be user-keyed, pre-ROTE, write-invalidated |
| Comment Policy Category | §6 |
