# Contract: Onboarding Personalization

Extends the existing onboarding system (`backend/onboarding/`) rather than replacing it. Reuses `onboarding_state` (status/last_step) and `tutorial_step` (new `sdui` rows). Personalization steps render as **ParamPicker** primitives; submits round-trip through the existing `submit_message_template` → `ui_event:chat_message` path and are interpreted by the orchestrator, which calls the personalization/skill endpoints.

## Reused endpoints (no change)
- `GET /api/onboarding/state`, `PUT /api/onboarding/state`, `POST /api/onboarding/replay`, `GET /api/tutorial/steps` (existing signatures).

## New tutorial steps (seeded, `target_kind='sdui'`)
Seeded in `backend/onboarding/seeds/` with `ON CONFLICT (slug) DO NOTHING`, ordered after the existing `welcome`/`chat-with-agent` steps:

| slug | display_order | target_key (sdui) | purpose |
|---|---|---|---|
| `personalize-profession` | 22 | `personalize.profession` | ParamPicker: profession (text) + goals (text/checklist) → `PUT /api/personalization/profile` |
| `personalize-skills` | 24 | `personalize.skills` | ParamPicker checklist of recommended skills (tools) for the stated profession → enable via existing scope/tool-override path |
| `personalize-personality` | 26 | `personalize.personality` | ParamPicker: tone/directness/humor/verbosity (select) + notes (text) → `PUT /api/personalization/profile` |

## GET `/api/onboarding/personalize/{step}` → server-generated panel
Returns `_ui_components` (a ParamPicker) for the given step, with recommendations derived from current state.
- `personalize-skills` recommendations: ranked from the user's discoverable agents' tools (FR-007) filtered to scopes the user can be granted; each option shows skill name + agent + required scope; options the user is not authorized for are shown disabled with a reason (FR-011).

Example (skills step) response:
```json
{ "_ui_components": [ {
  "type": "param_picker",
  "title": "Turn on skills for a Clinical researcher",
  "description": "Pick the capabilities you want. You can change these anytime.",
  "fields": [ { "name": "skills", "kind": "checklist",
    "options": ["grants:search_grants (search)", "general:graph_patient_data (read)"],
    "default": ["grants:search_grants (search)"] } ],
  "submit_label": "Enable selected",
  "submit_message_template": "Enable these skills for me: {skills}"
} ] }
```

## Behavior / invariants
- **Non-blocking** (FR-005): the flow is dismissible/skippable; partial state persists in `onboarding_state` + whatever was already saved to `user_personalization`/scopes; resumable via `last_step_id`.
- **Run-once** (FR-006): served only while `status != 'completed'`; returning users are not re-onboarded automatically; `replay` re-enters.
- **No agents available** (edge case): the skills step renders an explanatory Alert + a path to request access, never a dead-end.
- **Audit**: completing steps reuses existing onboarding audit (`onboarding.*`); profile/skill mutations emit their own events.
- **Completion target** (SC-001/SC-002): profession+goals captured, ≥1 skill enabled or intentionally skipped, personality chosen → `status='completed'` in <5 min.
