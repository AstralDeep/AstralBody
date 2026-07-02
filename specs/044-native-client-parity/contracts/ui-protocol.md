# Contract — UI Protocol Manifest & Drift Guards (044)

**Satisfies**: FR-001, FR-002 (logging), FR-014, FR-023, SC-001 | **Research**: R1, R2

## 1. The manifest artifact

`backend/shared/ui_protocol.json` — committed, versioned (`"version": 1`), reviewed like code.
Schema per [data-model.md §1](../data-model.md). It enumerates:

- **`push_types` (47)** — every frame type the orchestrator can send on the UI WebSocket:
  - bootstrap: `rote_config, chrome_menu, user_preferences, system_config, agent_list, agent_registered`
  - auth: `auth_required`
  - canvas/SDUI: `ui_render, ui_update, ui_upsert, ui_append, ui_stream_data`
  - chrome: `chrome_render, chrome_surface`
  - chat: `chat_status, chat_step, chat_created, chat_loaded, chat_deleted, history_list, user_message_acked, task_started, task_completed, tool_progress, workspace_timeline_mode, heartbeat`
  - streaming: `stream_subscribed, stream_unsubscribed, stream_list, stream_data, stream_error`
  - component verbs: `component_saved, component_save_error, saved_components_list, component_deleted, combine_status, combine_error, components_combined, components_condensed`
  - permissions: `agent_permissions, agent_permissions_updated`
  - llm: `llm_config_ack, llm_usage_report`
  - audit: `audit_append` · creation: `agent_creation_progress`
  - notification: `notification` *(scheduler push — newly catalogued; was absent from every prior inventory)*
  - error: `error`
- **`accept_actions`** — the full `ui_event` action vocabulary (chat, component verbs,
  permissions, streaming, `table_paginate`, `save_theme`, `update_device`, all `chrome_*`,
  draft/revision decisions).
- **`component_types` (35)** — must equal `webrender.allowed_primitive_types()`.

Adding a frame type, action, or component type **requires editing this file in the same PR**;
the guards below make omission a build failure. The authoritative per-client disposition for
each entry lives in [parity-matrix.md](../parity-matrix.md).

## 2. Guard tests (all run per-PR in CI)

| Guard | Where | Asserts |
|---|---|---|
| Component-vocabulary equality | backend pytest | `manifest.component_types == sorted(webrender.allowed_primitive_types())` |
| Send-site sweep | backend pytest | every `"type": "<literal>"` sent on the UI socket (regex sweep of orchestrator/stream/chrome/audit/llm/scheduler send modules, minus an explicit inbound/voice allowlist) ∈ `manifest.push_types` |
| Windows frame coverage | windows-client pytest | `protocol_manifest.CLASSIFICATION.keys() == manifest.push_types` (exact — no unclassified, no stale) |
| Windows vocabulary | windows-client pytest (existing guard re-anchored) | client `supported_types()` ∪ `KNOWN_DEGRADED` ⊇ `manifest.component_types`; `KNOWN_DEGRADED ⊆ manifest.component_types` |
| Android frame coverage | `:core` JUnit | `ProtocolManifest.CLASSIFICATION.keys() == manifest.push_types` (JSON read repo-relative) |
| Android vocabulary | `:app` JUnit (existing `VocabularyParityTest` re-anchored) | registry keys ∪ excluded == `manifest.component_types` |

## 3. Runtime routing rule (both natives)

The message router resolves every inbound frame:

1. type classified `handled` → its handler.
2. type classified `ignored` → `log.info("ignored frame type=<t>")`, drop.
3. anything else (including future server types) → `log.warning("unhandled frame type=<t>")`,
   drop — **never a crash, never an unlogged drop** (spec Edge Case 1, SC-001's injected
   unknown-type test).

## 4. `error` frame shapes (documentation + new emission)

Clients MUST decode all three existing shapes through one normalizer
(`code+message` | `payload.message` | `message`) and present: transient banner/toast +
transcript notice + terminal turn state.

**New (additive) emission**: the orchestrator's generic `ui_event` failure path
(`handle_ui_message` outer catch) emits `{"type":"error","code":"internal","message":<safe
summary>}` in addition to its log line. The web client gains matching toast handling. Existing
shapes are grandfathered unchanged (renaming/merging them would be a breaking wire change).

## 5. Backward compatibility

The manifest is descriptive, not a wire negotiation: old clients ignore it entirely. All new
emissions in this feature are additive types/paths that pre-044 clients already drop (unlogged
— which is precisely what this contract eliminates going forward).
