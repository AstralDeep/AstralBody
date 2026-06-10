# Contract: Settings Surfaces (027)

Each surface = one render function in `backend/webrender/chrome/surfaces/` (registered in
`SURFACE_RENDERERS`) + its `ui_event` actions in `chrome_events.py`. Handlers call the SAME
internals the REST routers use (services / lifecycle manager / DB helpers) — never HTTP-to-self.
After a mutating action, the handler re-renders the surface with a success/error notice and
pushes `chrome_render`. Every text interpolation goes through `esc()`.

## Menu (rendered statically into the shell at GET /)

Groups & entries (FR-013; omission rules FR-019; admin gating FR-014 server-side at render):

- **Account**: Agents & permissions → `agents`; LLM settings → `llm`; Personalization →
  `personalization`; Audit log → `audit`; Theme → `theme`
- **Help**: Take the tour → `tour`; User guide → `guide`
- **Admin tools** (roles ∋ `admin` only): Tool quality / Tutorial admin → `admin_tools`
- **Session**: Sign out → plain link `GET /auth/logout` (016 semantics; no JS dependency)

Topbar also carries: brand, connection status (`#astral-status` preserved), and
`data-tour-target` attributes for D7.

## Surfaces

### `agents` (params: `{tab?: mine|public|drafts, agent_id?}`)
- Data: orchestrator agent cards + `agent_ownership`/visibility + per-user disabled state +
  draft list (drafts tab shares the `drafts` surface renderer).
- Detail view (`agent_id` set): per-tool permission matrix (`{tool: {permission_kind: bool}}`),
  visibility toggle (owner only), credentials status + set/delete, agent enable/disable.
- Actions: `chrome_perms_save {agent_id, fields}` (explicit save, FR-016) →
  `set_agent_permissions` internals; `chrome_visibility_set {agent_id, is_public}`;
  `chrome_credentials_save {agent_id, fields}` / `chrome_credential_delete {agent_id, key}`;
  `chrome_agent_enabled {agent_id, enabled}`.

### `drafts` (params: `{draft_id?}`)
- Unified drafts list (manual + auto_chat + revision; origin badged) — SC-007.
- Create flow: description form → `chrome_draft_create {fields}` → create+generate, then the SAME
  approve/refine/discard cards as chat (US3 convergence). Resume/test/approve/delete existing
  drafts (`draft_approve`/`draft_refine`/`draft_discard`/`revision_apply`/`revision_discard`
  shared with chat).

### `llm`
- Form: base_url, api_key (write-only display), model; actions `chrome_llm_models {fields}` →
  `list_models` internals; `chrome_llm_test {fields}` → connection test verdict rendered;
  `chrome_llm_save {fields}` → session-scoped `llm_config_set` semantics +
  `chrome_llm_clear` (006 storage model unchanged — A6).

### `personalization` (params: `{tab: soul|memory|skills|schedule|dreaming}`)
- soul: profession/goals/personality form → `chrome_profile_save {fields}` (PHI-gated by the
  existing service; 025 precedence note rendered).
- memory: list + edit/delete → `chrome_memory_update {id, value}` / `chrome_memory_delete {id}`.
- skills: catalog with scope/availability → `chrome_skill_toggle {agent_id, tool_name, enabled}`.
- schedule: job list + detail (runs) → `chrome_job_pause|resume|delete|run_now {job_id}`;
  creation deep-links to chat (jobs are created conversationally per 025).
- dreaming: enabled toggle + recent sweeps + `chrome_dreaming_toggle {enabled}` /
  `chrome_dreaming_trigger`.

### `audit` (params: `{cursor?, event_class?, outcome?, q?}`)
- Filterable list (cursor pagination) + `chrome_open {surface:"audit", params:{event_id}}`
  detail drawer. Action: `chrome_audit_page {params}` re-renders with new filters/cursor.

### `theme`
- Preset cards (midnight/daylight/ocean/sunset/forest) + per-key color pickers (embedded
  `color_picker` primitives rendered via `render_one` — client side-effects already wired).
- Actions: `chrome_theme_preset {preset}` → persists via save_theme semantics AND returns a
  rendered `theme_apply` block so vars apply instantly; individual pickers keep the existing
  `save_theme` path.

### `tour`
- `chrome_open {surface:"tour"}` returns the ordered step payload (from `tutorial_step`, audience-
  filtered) as JSON embedded in the modal (`data-tour-steps`); client.js runs the step sequence
  (highlight `[data-tour-target]` when resolvable, centered card otherwise, skip unresolvable
  static targets with a note — A10). `chrome_tour_event {event: started|completed|skipped|dismissed,
  step_id?}` persists via onboarding-state internals.

### `guide`
- TOC + sections from `chrome/guide_content.py` (ported from the former React UserGuidePanel).
  Action: `chrome_open {surface:"guide", params:{section}}`.

### `admin_tools` (admin only — server-side role check in handler AND render)
- Tabs: Tool quality (feedback-admin internals: quality signals, proposals, quarantine) and
  Tutorial admin (step list incl. archived, create/edit/archive/restore →
  `chrome_admin_step_save {fields}` / `chrome_admin_step_archive {step_id}` /
  `chrome_admin_step_restore {step_id}`). Non-admin invocation → 403-equivalent error notice +
  audited rejection (FR-014, US4).

## Cross-cutting

- **Explicit save** (FR-016): no autosave; every mutating action returns the re-rendered surface
  with an inline success/failure notice; failures preserve submitted field values.
- **Unsaved-state**: forms are short; closing the modal discards unsubmitted input (the spec's
  warning semantics are satisfied by explicit-save + notices; no draft-state persistence).
- **Audit**: mutating handlers ride the existing service-level audit events; surfaces add
  `settings` events only where the underlying service records none.
- **Errors**: any handler exception → in-modal error notice + `logger.exception` (Constitution X).
