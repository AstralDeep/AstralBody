# Data Model: Uniform Cross-Device Artifacts & First-Turn Loading Contract

**Feature**: 055-uniform-artifacts | **Date**: 2026-07-13

## Entity overview

| Entity | Storage | New? |
|--------|---------|------|
| Artifact (workspace component) | `saved_components` (existing) | No — extended semantics only |
| Welcome component | in-memory / wire only | No storage (invariant: never persisted) |
| Stream-backed component | `saved_components` on terminal | No new table |
| Designed arrangement | `workspace_layout` (existing) | No — origin-independence only |
| Provenance mark | field inside the component dict | No schema delta |
| Component version | **`component_version`** | **NEW table** |
| Share grant | **`share_grant`** | **NEW table** |

## Identity namespaces (extended registry)

| Prefix | Meaning | Persisted? | Introduced |
|--------|---------|-----------|------------|
| `au_` | author-supplied explicit id | yes | 028 |
| `wc_` | fingerprint-derived workspace id | yes | 028 |
| `dg_` | designer garnish | yes (layout refs) | 029 |
| `ly_` | layout row key | yes | 029 |
| **`wel_`** | **welcome canvas component (ephemeral)** | **NEVER** | **055** |

Rules: `wel_` ids are stamped in `welcome.py` via the existing `Primitive.id`
field (`wel_hero`, `wel_enable`, `wel_ex_<slug>` per example, `wel_hint`). The
workspace upsert path MUST refuse any `wel_`-prefixed identity defensively
(components with such ids are never routed to `workspace.upsert`, and a guard
rejects them if one arrives — keeps rule 1 "explicit id wins" from ever adopting
a welcome id). Clients purge `wel_` components from canvas state at turn start
and exclude them from any history/archive.

## Component dict field additions (wire-level, no schema delta)

- **`provenance`**: `"grounded" | "estimated" | "generated"`, stamped by the
  orchestrator in `_tag_source` AFTER agent/designer output is final; any
  agent-supplied value is overwritten (trust cannot be self-upgraded). Persisted
  inside the `saved_components` component JSON; carried in snapshots/exports.
  ROTE preserved-field: never stripped by host bounds.
- (Existing `_source_agent/_source_tool/_source_params/_source_correlation_id`
  unchanged — provenance derives from them.)

## NEW TABLE: `component_version`

Bounded per-component history behind `FF_COMPONENT_REFINE` (US4).

```sql
CREATE TABLE IF NOT EXISTS component_version (
    id            BIGSERIAL PRIMARY KEY,
    chat_id       TEXT      NOT NULL,
    user_id       TEXT      NOT NULL,
    component_id  TEXT      NOT NULL,
    version_no    INTEGER   NOT NULL,           -- monotonic per component_id
    component     JSONB     NOT NULL,           -- the archived component dict
    reason        TEXT      NOT NULL,           -- 'refine' | 'restore'
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (chat_id, component_id, version_no)
);
CREATE INDEX IF NOT EXISTS idx_component_version_lookup
    ON component_version (chat_id, component_id, version_no DESC);
```

- **Write path**: `artifact_versions.archive(chat_id, user_id, component_id,
  current_dict, reason)` is called BEFORE a refine/restore overwrites a live
  row; assigns `version_no = 1 + max(existing)`; then prunes rows beyond the
  newest **5** per (chat_id, component_id).
- **Read path**: `list_versions` (id, version_no, created_at, reason, title
  digest) and `get_version` for restore.
- **Ownership**: all reads/writes scoped by `(chat_id, user_id)` exactly like
  `saved_components` (workspace.py:220-226 pattern).
- **Cascade**: component deletion and chat deletion delete its version rows
  (same sweep that prunes layout refs).
- **State transitions**: live component → (refine) → archived v(n) + new live →
  (restore v(k)) → archived v(n+1) + live=v(k) copy. Restores never delete
  archived rows; pruning is count-based only.

## NEW TABLE: `share_grant`

Snapshot-scoped public read grants behind `FF_ARTIFACT_SHARING` (US5,
fail-closed default off).

```sql
CREATE TABLE IF NOT EXISTS share_grant (
    id             BIGSERIAL PRIMARY KEY,
    token_sha256   TEXT      NOT NULL UNIQUE,   -- hash only; raw token never stored
    user_id        TEXT      NOT NULL,
    chat_id        TEXT      NOT NULL,
    scope          TEXT      NOT NULL,          -- 'component' | 'canvas'
    component_id   TEXT,                        -- when scope='component'
    snapshot_html  TEXT      NOT NULL,          -- self-contained rendition at mint
    snapshot_json  JSONB     NOT NULL,          -- component dict(s) at mint
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at     TIMESTAMPTZ,                 -- NULL = until revoked
    revoked_at     TIMESTAMPTZ,
    open_count     INTEGER   NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_share_grant_owner ON share_grant (user_id, created_at DESC);
```

- **Mint** (`POST /api/share`): authed owner; renders the snapshot (component
  fragment or full canvas via `render_workspace`), runs the **PHI gate
  fail-closed** over snapshot text (refusal audited), generates a 256-bit
  urlsafe token, stores only `sha256(token)`, returns the token once.
- **Serve** (`GET /share/{token}`): hash lookup; refuse when revoked/expired;
  increments `open_count`; response headers `X-Robots-Tag: noindex, nofollow` +
  no-cache; renders `snapshot_html` only (never live rows). Constant-time hash
  compare via indexed lookup on the digest.
- **Revoke** (`DELETE /api/share/{id}`): owner-scoped; sets `revoked_at`.
- **Audit**: `share.minted` / `share.opened` / `share.revoked` /
  `share.refused_phi` (class `conversation`), no token material in rows.

## Migration & rollback (Constitution IX)

Both tables ship as idempotent guarded deltas in
`shared/database.py::_init_db()` (`CREATE TABLE IF NOT EXISTS` + guarded index
creation), inert while their flags are off. Representative-dataset evidence:
run against a dump containing existing `saved_components`/`workspace_layout`
rows and verify no interaction (the migration touches no existing table).

**Rollback**: both tables are additive and consumed only by 055 code paths —
`DROP TABLE IF EXISTS component_version; DROP TABLE IF EXISTS share_grant;`
after disabling `FF_COMPONENT_REFINE`/`FF_ARTIFACT_SHARING`/`FF_ARTIFACT_EXPORT`.
No existing table is altered; no data backfill exists to reverse. Schema
revision bump per the 052 `schema_meta` fast-path convention (054.001 → 055.001).

## Validation rules (from spec FRs)

- `wel_` ids never reach `saved_components` (FR-003 guard; unit-tested).
- `component_version` retains ≤5 rows per component (FR-024 bound).
- `share_grant.snapshot_*` immutable after mint (no UPDATE path exists).
- Refine output must validate against `allowed_primitive_types()` and same-type
  constraint before upsert (FR-022); failure = honest error, no version burn.
- Provenance stamp is orchestrator-final (FR-026): stamping happens after all
  agent/designer mutation points; property test asserts agent-supplied
  `provenance` values are always overwritten.
