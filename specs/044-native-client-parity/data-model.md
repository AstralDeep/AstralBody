# Data Model — Cross-Client Native Parity Review & Remediation (044)

**Date**: 2026-07-01 | **Plan**: [plan.md](plan.md) | **Research**: [research.md](research.md)

This feature is a review-and-remediation pass: almost all of its "data" is contract and
evidence artifacts, not database state. **Database delta: exactly one additive column**
(§8). Everything else below defines artifact schemas and client-side state machines.

## 1. Protocol Manifest (`backend/shared/ui_protocol.json`)

The committed, machine-readable single source for the UI wire vocabulary (R1). Consumed by
backend pytest, Windows pytest, and Android JUnit via repo-relative paths.

```json
{
  "version": 1,
  "push_types": [
    {"name": "chat_status", "category": "chat", "shapes": ["status", "message"]},
    {"name": "error",       "category": "error", "shapes": ["code+message", "payload.message", "message"]}
  ],
  "accept_actions": ["chat_message", "table_paginate", "chrome_open", "..."],
  "component_types": ["container", "text", "...35 total..."]
}
```

- `push_types` — all **47** server→client frame types (46 audited + `notification`).
  `category ∈ {bootstrap, auth, canvas, chrome, chat, streaming, component_verbs,
  permissions, llm, audit, creation, notification, error}`. `shapes` is documentation-grade
  (notably `error`'s three legacy shapes).
- `accept_actions` — the `ui_event` action vocabulary (from `orchestrator.py:1364-2294` +
  `chrome_events.py`).
- `component_types` — must equal `webrender.allowed_primitive_types()` (asserted).

**Validation rules**: backend test = manifest ↔ code equality (components) + send-site sweep
(push types); per-client tests = classification tables cover `push_types` exactly.

## 2. Per-client Frame Classification

`windows-client/astral_client/protocol_manifest.py` and
`android-client/core/.../protocol/ProtocolManifest.kt`:

```
CLASSIFICATION: dict[frame_type, "handled" | "ignored"]
```

- `handled` — the client has a routing branch that consumes the frame.
- `ignored` — deliberate: the client logs `unhandled frame type=<t>` once per receipt and
  drops it. (There is no third state; an unlisted type fails the guard test.)
- Runtime rule: the message router's default branch logs any type not classified `handled` —
  including brand-new server types not yet in the manifest (never a crash, never silent).

## 3. Parity Matrix (`specs/044-native-client-parity/parity-matrix.md`)

The organizing artifact (FR-001). Two tables: frame types × clients, component types ×
clients. Cell schema:

| Field | Values |
|---|---|
| `disposition` | `native` (renders/handles natively) · `native-equivalent` (different affordance, same capability) · `server-substituted` (ROTE degrade ladder) · `degraded` (labeled placeholder) · `ignored` (deliberate, logged, documented) · `web-only` (sanctioned carve-out per Constitution XII v2.3.1) |
| `evidence` | link into `verification/` (screenshot / test id / scenario result); `pending` until verified |

Invariant: **no cell may be empty or "unknown"** at feature completion (SC-001/SC-002).
Seeded with target dispositions during planning; finalized with evidence during verification.

## 4. Defect Register (`specs/044-native-client-parity/defect-register.md`)

Every audited + newly-found defect:

```
| id | severity (P1/P2/P3) | client(s) | summary | disposition (fixed | deferred) | rationale-if-deferred | evidence |
```

Seed content: baseline-findings §2.5/§3.5 gap lists + the four cross-cutting backend flags
(chrome HTML error paths, cookie-bound logout, unregistered `notification` type, no manifest).
Known deferrals entering with rationale: agents/audit surface convergence (native-equivalent
screens stay), `:app` Kover gating, Android in-app endpoint override.

## 5. Verification Bundle (`specs/044-native-client-parity/verification/`)

```
verification/
├── README.md            # regeneration procedure (mirrors quickstart.md)
├── results.md           # per-acceptance-scenario outcomes (US1–US6), dated, per client
├── web/                 # browser captures: gallery + journeys
├── windows/             # dev-machine captures (real platform, font-gated)
└── android/             # emulator captures (adb screencap)
```

Rules: all text legible (the capture harness *fails* rather than emit tofu — font sanity
gate); every capture named `<scenario>-<client>.png`; `results.md` rows link matrix cells →
evidence. Regenerable from a clean checkout per README (SC-007).

## 6. Client-side state machines (behavioral models, no persistence)

### 6.1 Connection state (both natives — shared vocabulary)

```
connecting → connected → (socket drop) → reconnecting(attempt n, delay = min(1s·2^(n-1), 30s))
                                        ↘ auth_required → refreshing → connected
                                                        ↘ (no refresh credential / refresh failed)
                                                          → signed_out (explicit sign-in affordance)
signed_out —(interactive login)→ connecting
```

- Visible at all times (top-bar `status` control text/tint + banner while not `connected`).
- Outbound while not `connected`: bounded queue (64); overflow → visible failure notice
  (never a silent drop). Queue flushes FIFO on `connected`.
- `connected` entry: send `register_ui`, re-discover agents, re-pull history (existing).

### 6.2 Surface load state (both natives)

```
opening (skeleton, ≤10 s) → loaded (chrome_surface arrived)
                          → timeout → error+Retry (re-emits chrome_open)
action-submitted (in-flight ≤10 s) → refreshed (re-pushed chrome_surface, leading Alert = feedback)
                                   → timeout → error+Retry
```

### 6.3 Windows attachment staging (mirrors Android `StagedAttachment`)

```
picked → uploading → ready(parser_status=covered)
                   → attention(parser_status ∈ {preparing, pending_admin_approval, unavailable})
                   → failed (visible on chip; removable)
send: chips with attachment_id attach to chat_message.payload.attachments; strip clears
remove: chip deleted client-side (server row remains, as on web/Android)
```

Chip fields: `attachment_id, filename, category, parser_status, state`.

### 6.4 Turn progress (both natives)

```
sent → acked (user_message_acked) → active (chat_status thinking/executing/fixing/processing_async,
       chat_step*, tool_progress*) → [task_started → detached async → task_completed]
     → terminal: done | failed (error frame / server Alert / disconnect-resolved)
```

Invariant: every turn reaches a visible terminal state (SC-006); disconnect while active →
turn marked interrupted, not perpetually "thinking".

## 7. Theme palette (existing persistence, new client model)

Server-stored (existing `user_preferences`, key `theme`): `{"preset": name}` and/or
`{"colors": {bg, surface, primary, secondary, text, muted, accent}}` and/or single
`{color_key, color_value}` patches. Client-side:

- **Windows** `Palette` (mutable object replacing module constants): 7 channels + derived
  (`SURFACE_2`, `BORDER`, `PRIMARY_SOFT`, `VARIANT_COLORS`, `GRAD`) recomputed from channels;
  `build_stylesheet(palette)` regenerates the app QSS.
- **Android** `ThemePalette` in `UiState`: 7 channels → `ColorScheme` mapping (bg→background,
  surface→surface, primary→primary, secondary→secondary, text→onBackground/onSurface,
  muted→onSurfaceVariant, accent→tertiary); null → static defaults.
- Sources (priority = latest event): boot `user_preferences.theme` → `theme_apply` component →
  local echo of `save_theme` fine-tune.

## 8. Database delta (the only schema change)

| Table | Change | Migration | Rollback |
|---|---|---|---|
| `auth_revocation_queue` | **ADD COLUMN** `client_id TEXT NULL` | idempotent guarded `ALTER TABLE … ADD COLUMN IF NOT EXISTS` in `shared/database.py::_init_db` | `ALTER TABLE auth_revocation_queue DROP COLUMN client_id` (documented; NULL-compatible — old rows and old code paths keep working, retrier falls back to the configured web client id when NULL) |

No other tables, columns, indexes, or seeds change. Tested against a representative dataset
(existing queue rows) per Constitution IX.

## 9. New/changed wire surface (all additive; contracts/ has full detail)

| Surface | Kind | Contract |
|---|---|---|
| `POST /api/auth/logout` | new REST | [contracts/session-lifecycle.md](contracts/session-lifecycle.md) |
| `error {code:"internal"}` on generic ui_event failure | new emission of existing type | [contracts/ui-protocol.md](contracts/ui-protocol.md) |
| Device-aware `chrome_surface` error/close frames | new emission path | [contracts/chrome-parity.md](contracts/chrome-parity.md) |
| `components()` for workspace_timeline / pulse / attachments | new surface payloads | [contracts/chrome-parity.md](contracts/chrome-parity.md) |
| `attach_existing` client-local action | new component action semantics | [contracts/chrome-parity.md](contracts/chrome-parity.md) |
| `backend/shared/ui_protocol.json` | new committed artifact | [contracts/ui-protocol.md](contracts/ui-protocol.md) |
