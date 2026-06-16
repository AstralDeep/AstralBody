# Phase 1 Data Model: Agentic File-Upload SDUI & Delegated-Authority Verification

**Feature**: 032-attachment-sdui-verification | **Date**: 2026-06-16

These are **in-memory / file-backed** harness entities (Python dataclasses serialized to the JSON run record). They are NOT database tables — the feature adds no schema (FR-032). Field types are advisory; the contracts in `contracts/` are authoritative for serialized shapes.

## Entity overview & relationships

```text
RunRecord 1───* Verdict *───1 Check
    │                 │
    │                 *───1 CapturedEvidence
    *───* Scenario 1───1 Persona
              │
              1───1 DelegatedAuthorityAssertion   (authority scenarios only)
```

A **RunRecord** aggregates everything for one execution. Each **Scenario** (a Persona + file + query + expected properties + auth mode) is driven by the runner; each property is tested by one or more **Checks**, each producing a **Verdict** backed by **CapturedEvidence**. Authority scenarios additionally produce a **DelegatedAuthorityAssertion**.

## Persona

A named, realistic user profile. Extensible (FR-007): new personas register without redesign.

| Field | Type | Notes |
|---|---|---|
| `key` | str | stable id: `everyday` \| `researcher` \| `medical` \| `government` (+ future) |
| `display_name` | str | "Everyday person", etc. |
| `roles` | list[str] | realm roles granted to this persona's principal (default `["user"]`) |
| `default_scopes` | dict[str,bool] | scopes enabled for the persona's agent(s) at setup |
| `fixtures` | list[FixtureRef] | synthetic input files (category, path, known-content markers) |
| `query_catalogue` | list[str] | curated, deterministic queries (REQUIRED; LLM augmentation optional, FR-007) |
| `expected_component_types` | set[str] | component types this persona's scenarios warrant (subset of published vocabulary) |

**Validation**: `query_catalogue` non-empty; every `fixtures[].category` ∈ {`spreadsheet`,`document`,`text`,`image`,`<unsupported>`}; medical fixtures flagged `synthetic=True` and contain no real PHI (Assumption "synthetic, non-sensitive inputs").

**FixtureRef**: `{ category: str, path: str, filename: str, known_markers: list[str], synthetic: bool, expect_unsupported: bool }`. `known_markers` are literal values (e.g., a transaction amount, a column name) the harness searches for in delivered components to prove provenance (FR-011).

## Verification Scenario

The atomic unit the harness plans, drives, and verifies.

| Field | Type | Notes |
|---|---|---|
| `scenario_id` | str | `<persona.key>:<short-slug>` |
| `persona_key` | str | → Persona |
| `fixture` | FixtureRef | the file uploaded this scenario |
| `query` | str | the natural-language question |
| `auth_mode` | enum | `real_keycloak` \| `mock_inprocess` (run-level, echoed per scenario) |
| `warrants_ui` | bool | true → tangible-UI checks apply; false → prose acceptable (FR-015) |
| `expected_properties` | set[enum] | subset of {`tangible_ui`,`delegated_authority`,`backend_only_ui`} |
| `expected_component_types` | set[str] | what should appear (e.g., `{table, metric, bar_chart}`) |
| `principal` | Principal | the acting identity (namespaced) |

**Principal**: `{ user_id: str (namespaced __verif__…), roles: list[str], is_admin: bool }`.

**State transitions** (runner-driven, bounded — FR-005):
`planned → authenticated → uploaded → queried → captured → verified → {passed | failed | uncertain}`
Every scenario MUST reach a terminal state within the budget; `errored_observation` is a distinct terminal flagging "harness could not observe" vs "product wrong" (FR-033).

## Probe / Check

A single structured, replayable assertion with typed input and typed result, plus its adversarial counter-check.

| Field | Type | Notes |
|---|---|---|
| `check_id` | str | stable name, e.g. `us1.component_from_file`, `us2.cross_user_refused`, `us3.no_client_construction` |
| `property` | enum | `tangible_ui` \| `delegated_authority` \| `backend_only_ui` |
| `inputs` | dict (typed) | replay inputs (scenario_id, captured-evidence ref, expected markers, etc.) |
| `result` | CheckResult | `{ outcome: pass\|fail\|uncertain, observed: dict, reason: str }` |
| `counter_check_id` | str | the adversarial counter-check that must NOT refute a pass (FR-003) |
| `is_deterministic` | bool | always true for gate checks (D1) |

**Validation**: every positive (`pass`) check references a non-refuting counter-check result; a refuting counter-check forces the scenario verdict to `uncertain` (D13). Checks are pure over their `inputs` + `CapturedEvidence` so they replay identically (FR-002).

Representative checks:
- **US1**: `component_present` (≥1 interactive component when `warrants_ui`), `component_from_file` (known_markers found in component data — FR-011), `persisted_with_identity` (`workspace.live_components` shows the component with `wc_`/`au_` id tying agent|tool|params — FR-012), `survives_reload` (re-hydrate chat → component still present), `re_executable` (component_action re-runs source tool, morphs in place — FR-013), `vocabulary_ok` (types ∈ `allowed_primitive_types()` — FR-023).
- **US2**: `cross_user_refused` (FR-017), `scope_withheld` (FR-016), `disabled_tool_action_refused` (FR-013/US2-3), `admin_only_approval` (FR-018), `delegation_attribution` (actor≠principal — FR-019), `audit_chain_unbroken` (FR-020), `denials_audited` (FR-020).
- **US3**: `vocabulary_ok`, `server_markup_present` (FR-024), `client_has_no_construction_logic` + `client_has_no_framework` (FR-025), `device_diff_is_backend` (FR-026), `action_is_backend_intent` (FR-027).

## Captured Evidence

Concrete observations a scenario produced; retained so a verdict is justifiable and reproducible (and redaction-clean).

| Field | Type | Notes |
|---|---|---|
| `evidence_id` | str | |
| `scenario_id` | str | |
| `messages` | list[dict] | captured server→client messages (`ui_render`/`ui_upsert`/`chat_status`/…), secret-redacted |
| `components` | list[dict] | flattened delivered component dicts (type, data, component_id, `_source_*`) |
| `workspace_state` | list[dict] | `live_components(chat_id, user_id)` after the turn |
| `audit_rows` | list[dict] | audit events for the principal (action_type, actor_user_id, auth_principal, correlation_id, outcome) |
| `audit_chain_ok` | bool\|str | `True` or the first-broken `event_id` |
| `client_inspection` | dict | `{innerHTML:bool, data_component_id:bool, ui_event_forward:bool, framework_import:bool, type_switch:bool, markers:{…}}` |
| `device_diff` | dict | `{browser:[…], mobile:[…]}` adapted component summaries |
| `run_mode` | enum | `real_keycloak` \| `mock_inprocess` |

**Validation**: redaction pass runs before persistence; if any field would contain a credential-shaped value, it is masked and the run is flagged (FR-022/SC-011).

## Verdict

Machine-readable result for a check or a scenario.

| Field | Type | Notes |
|---|---|---|
| `verdict_id` | str | |
| `scope` | enum | `check` \| `scenario` \| `property` \| `run` |
| `outcome` | enum | `pass` \| `fail` \| `uncertain` |
| `confidence` | enum | `high` \| `medium` \| `low` (low when only one corroboration source) |
| `evidence_ref` | str | → CapturedEvidence |
| `refs` | dict | `{persona, scenario, check, counter_check}` |
| `run_mode` | enum | echoed for every verdict (SC-010) |
| `adversarial` | dict | `{deterministic: pass/fail, llm_judge: pass/fail/na, reconciled: outcome}` |

**Validation**: `outcome=pass` requires `adversarial.deterministic=pass` AND `adversarial.llm_judge ∈ {pass, na}`; any disagreement ⇒ `uncertain` (FR-003/D13).

## Run Record / Report

Durable, human-inspectable aggregate for one execution (the dual artifact — FR-008/028).

| Field | Type | Notes |
|---|---|---|
| `run_id` | str | namespaced; also the artifacts subdir name |
| `started_at` / `finished_at` | str | stamped by the caller after the run (scripts cannot read the clock) |
| `mode` | enum | `in_process` \| `external` |
| `auth_mode` | enum | `real_keycloak` \| `mock_inprocess` |
| `personas` | list[str] | exercised |
| `coverage` | dict | `{file_categories:[…], component_types:[…]}` — only what was actually observed (SC-003) |
| `verdicts` | list[Verdict] | all of them |
| `uncertain_ratio` | float | SC-009 |
| `differentiation` | list[str] | enumerated, evidence-backed capabilities a text-only assistant cannot provide (FR-029) |
| `flags` | list[str] | e.g., `credential_near_exposure`, `keycloak_unreachable_degraded` |

**Two serializations**: `verdicts.json` (this record, machine-readable, replayable) and `report.md` (generated from it, stakeholder-readable). They are derived from one source so they cannot disagree (FR-028).

## Delegated-authority assertion

The specific evidence that the agent acted as a scoped delegate of the user.

| Field | Type | Notes |
|---|---|---|
| `scenario_id` | str | |
| `acting_agent` | str | from `act.sub` (`agent:<id>`) |
| `on_behalf_of_user` | str | from `sub` |
| `authorizing_scope` | str | the scope/tool grant that permitted the action |
| `audit_link` | str | correlation_id / event_id tying the action into the chain |
| `mode` | enum | `real_keycloak` (real token exchange) \| `mock_inprocess` (delegation service mock) |

**Validation**: `acting_agent != on_behalf_of_user` (delegation, not identity assumption — FR-019); `audit_link` resolves to rows whose `actor_user_id == on_behalf_of_user` and `auth_principal == acting_agent` within an unbroken chain (FR-020).
