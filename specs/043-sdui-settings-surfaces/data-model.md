# Phase 1 Data Model: Native SDUI Settings Surfaces

Surfaces are **computed, not stored** — there is no new table. Each is a role-aware projection built on demand from server state and composed as `astralprims` component dicts. This document defines the delivery payload, the per-surface component vocabulary, the one additive primitive extension, and the theme-channel model, so every client renders each surface identically (Constitution II/XII).

## Entity: ChromeSurface (the native delivery payload)

The structured twin of the web's `ChromeRender` HTML modal, pushed when a menu item opens on a native SDUI target. Defined in `backend/shared/protocol.py` beside `ChromeRender` / `ChromeMenu`.

| Field | Type | Notes |
|-------|------|-------|
| `type` | string | `"chrome_surface"`. |
| `region` | string | `"modal"` (the surface's host region; matches `ChromeRender.region`). An empty/closing surface reuses `chrome_close` (existing). |
| `surface_key` | string | Which surface (`llm`, `personalization`, `theme`, `guide`). |
| `title` | string | Modal/sheet title = the surface module's `TITLE`. |
| `admin_only` | bool | Echoes the surface's `ADMIN_ONLY` (all five are `false`); the server still enforces. |
| `components` | `Component[]` | `astralprims` `.to_dict()` nodes, **ROTE-adapted** for the device's `supported_types`. |
| `mode` | string? | `"replace"` (default) — replace the modal body; parity with `ChromeRender.mode`. |

`Component` is the existing SDUI wire node already consumed by every client's renderer (`type` + `attributes` + `children`/`content` + optional `id`) — **no new component-envelope contract is introduced**; surfaces compose from the existing vocabulary plus the D2 `ParamPicker` extension.

## Entity: Component vocabulary per surface

The types each surface composes from. All are already rendered by both native clients (Windows `renderer.py:814-844` = 29 types; Android `render/Renderer.kt` = 31 types) **except** `color_picker`/`theme_apply` (native renderers added in Foundational) and the `ParamPicker` action-submit fields (extension, below).

| Surface | Key | Primitives used | Actions (existing `chrome_*` keys) | New rendering needed |
|---------|-----|-----------------|-------------------------------------|----------------------|
| **User guide** | `guide` | `Container`, `Tabs`/`List_` (TOC), `Button` (TOC nav → `chrome_open` w/ `section`), `Text`/`Card` (article) | — (nav only, generic `chrome_open`) | none — existing vocab |
| **Theme** | `theme` | `Card`, `Button` (preset → `chrome_theme_preset`), swatch `Container`s; `color_picker`×7 (fine-tune); `theme_apply` (side-effect) | `chrome_theme_preset` | `color_picker`, `theme_apply` renderers (both clients) |
| **LLM settings** | `llm` | `Card`, `Badge` (saved/not-configured), `ParamPicker` (base_url/api_key/model form), `Button`×≤4 (models/test/save/clear), `Alert` (test/notice) | `chrome_llm_models`, `chrome_llm_test`, `chrome_llm_save`, `chrome_llm_clear` | `ParamPicker` action-submit + `password` field kind |
| **Personalization** | `personalization` | `Tabs` (soul/memory/skills/schedule/dreaming), `ParamPicker` (soul form; per-row memory edit), `Button` rows (memory save/delete, skill toggle, job pause/resume/run/delete, dreaming toggle/trigger), `List_`/`Card`/`Badge`/`KeyValue` (rows, status, run history) | `chrome_profile_save`, `chrome_memory_update`, `chrome_memory_delete`, `chrome_skill_toggle`, `chrome_job_pause`, `chrome_job_resume`, `chrome_job_delete`, `chrome_job_run_now`, `chrome_dreaming_toggle`, `chrome_dreaming_trigger` | `ParamPicker` action-submit + `textarea` field kind |

**Admin/audience filtering (not a whole-surface gate)**: `guide` drops `admin`-audience sections for non-admins (`_visible_sections`, `guide.py:29-39`), applied inside `components(...)` exactly as inside `render(...)`. None of the four ported surfaces sets `ADMIN_ONLY`. (`tour` is **not** ported — it is omitted from the native menu channels, D5; its web `render()` is unchanged.)

## Entity: ParamPicker action-submit extension (the one additive change)

`astralprims.ParamPicker` today: `fields[]` (kinds `text|number|boolean|select|checklist`), `submit_label`, `submit_message_template` → on submit the web client interpolates the template and **sends a chat message**. The additive extension gives it an **action-submit mode** for settings forms:

| Field | Type | Notes |
|-------|------|-------|
| `submit_action` | string? | When present, submit posts `ui_event{action: submit_action, payload:{fields:{…}, …submit_payload}}` **instead of** a chat message. Value is an existing `chrome_*` key (e.g. `chrome_llm_save`). |
| `submit_payload` | object? | Extra static payload merged alongside the collected `fields` (e.g. `{tab:"soul"}`, or a row `id`). |
| field kind `password` | — | Renders masked; write-only (blank = keep existing), matching the LLM API-key semantics (`llm.py` `_resolve_api_key`). |
| field kind `textarea` | — | Multi-line, for personalization goals/personality notes. |

`fields` collection mirrors the web `collectChromeFields` semantics (checkbox→bool, number→Number, else string) so a native submit produces the **same `payload.fields`** shape the existing handlers already parse (`_fields`, `llm.py:60-78`). Backward-compatible: a `ParamPicker` without `submit_action` behaves exactly as today (chat-message submit) — no existing canvas usage changes.

## Entity: Theme preset + channels (US3)

| Field | Type | Notes |
|-------|------|-------|
| `preset` | enum | `midnight` \| `daylight` \| `ocean` \| `sunset` \| `forest` (the `PRESETS` keys, `theme.py:29-45`). Persisted to `user_preferences.theme` by `chrome_theme_preset` (existing). |
| `channels` | object | 7 hex values `{bg, surface, primary, secondary, text, muted, accent}` for the active preset. Shipped to native (register bootstrap + the preset re-render side-effect) as **tokens, not CSS**. |

Native mapping: Windows → `theme.py` runtime tokens + re-applied `APP_STYLESHEET`; Android → `AstralTheme(colorScheme = …)` from the held preset. No stored channels needed unless custom fine-tune colors are persisted later (then a guarded `_init_db` delta).

## Serialization & rendering rules

- A surface's `components(orch, user_id, roles, params)` returns a `list[dict]` of `astralprims` `.to_dict()` nodes; the orchestrator ROTE-adapts them per the connecting device before emitting `chrome_surface` (native) or renders them to HTML for the web modal where a surface delegates its `render()` to `components()` (D6).
- Every action binding inside a surface uses the **same `chrome_*` action string** the HTML uses today, so `HANDLERS` (`collect_handlers`, `surfaces/__init__.py:55-68`) and their persistence/audit are unchanged.
- Forward-compat: clients MUST ignore unknown `component.type` and degrade to a labeled placeholder (Windows `_r_fallback`; Android `Placeholder`) rather than fail. ROTE additionally substitutes an unsupported type down its fallback ladder (`adapter.py:51-94`) before the client sees it.
- Role/audience filtering happens **before** serialization; a client never receives content it must not see.

## State & transitions

- A surface is (re)built on `chrome_open` and after any handler that returns `(surface, params, notice)` (`chrome_events.py:140-165`) — the re-render carries the success/error notice as an `Alert` (native) or notice HTML (web).
- Theme: the active preset persists in `user_preferences.theme`; on connect the register bootstrap carries it so every client themes from first paint (SC-004).
- No persisted surface state; personalization and LLM read their live backends each render exactly as the web `render()` does.

## Migration impact

None expected (computed surfaces; theme in existing `user_preferences`). Any future stored field ships as an idempotent guarded `_init_db` delta with rollback (Constitution IX).
