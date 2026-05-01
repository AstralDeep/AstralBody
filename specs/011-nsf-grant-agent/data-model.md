# Phase 1 Data Model: NSF TechAccess Grant Writing Agent

**Note**: This feature introduces **no database schema changes** (Constitution Principle IX is N/A here). The "data model" is the in-process Python data shape the new knowledge module exposes and the new MCP tools consume. Cross-session memory inherits the existing `grants` agent's posture per Clarifications Q3 — no new persistence, no new tables, no migrations.

## Overview

The new module [backend/agents/grants/nsf_techaccess_knowledge.py](../../backend/agents/grants/nsf_techaccess_knowledge.py) exposes module-level constants that the six new MCP tools read. These constants are versioned alongside the code; any change to them goes through the same PR review as code (Constitution VIII / X).

## Logical Entities → Python Constants

### `Solicitation`

Represents the overall NSF 26-508 / TechAccess: AI-Ready America program metadata.

| Field | Type | Validation / Notes |
|-------|------|-------------------|
| `id` | `str` | `"NSF 26-508"` (exact). |
| `name` | `str` | `"TechAccess: AI-Ready America"`. |
| `loi_due` | `str` (ISO date) | `"2026-06-16"`. |
| `full_proposal_due` | `str` (ISO date) | `"2026-07-16"`. |
| `internal_deadline` | `str` (ISO date) | `"2026-07-09"` (approximate). |
| `narrative_page_limit` | `int` | `15`. |
| `loi_synopsis_page_limit` | `int` | `1`. |
| `funders` | `list[str]` | NSF TIP, NSF CISE, NSF EDU, USDA-NIFA, DOL, SBA. |

Exposed as the constant `SOLICITATION_META` (a single dict).

### `OpportunityFamily`

The three opportunities the agent's TechAccess scope covers (per Clarifications Q4).

| Field | Type | Validation / Notes |
|-------|------|-------------------|
| `key` | `str` | One of `"hub"`, `"national_lead"`, `"catalyst"`. |
| `name` | `str` | Display name. |
| `mechanism` | `str` | e.g., `"Cooperative Agreement"`, `"Other Transaction Agreement"`, `"Award Competition"`. |
| `is_primary` | `bool` | True only for the Kentucky Coordination Hub. |
| `framing_notes` | `str` | Short note describing how rules differ — used by `techaccess_scope_check` when redirecting between siblings. |

Exposed as `OPPORTUNITY_FAMILY` — a list of three dicts. Used by `techaccess_scope_check` to classify requests as primary / sibling / out-of-scope.

### `ProposalSection`

One of the six writable units (LOI synopsis + Section 1–5). The LOI title is treated as a tiny seventh unit handled inside `draft_loi`.

| Field | Type | Validation / Notes |
|-------|------|-------------------|
| `key` | `str` | One of `"loi_synopsis"`, `"section_1"`, `"section_2"`, `"section_3"`, `"section_4"`, `"section_5"`. |
| `heading` | `str` | The exact required heading text (or `"LOI Synopsis"` for the LOI). Used verbatim in tool output. |
| `required_subelements` | `list[str]` | The required sub-element list from the spec FR-003 for that section. |
| `target_page_share` | `float` | Recommended share of the 15-page narrative budget (informational; tools surface this when the user asks for prioritization help per FR-016). Sums to ≤ 1.0 across Sections 1–5. |
| `applies_to_loi` | `bool` | True for `loi_synopsis`. |

Exposed as `SECTIONS` — list of six dicts in canonical order. The exact heading strings are also exposed separately as `SECTION_HEADINGS` for fast structural assertions in unit tests.

### `HubResponsibility`

One of the five non-negotiable Hub responsibility areas (FR-004).

| Field | Type | Validation / Notes |
|-------|------|-------------------|
| `key` | `str` | One of `"resource_navigator"`, `"strategic_plan"`, `"deployment_support"`, `"training_capacity"`, `"sector_coordination"`. |
| `name` | `str` | Full title from the solicitation. |
| `framing_constraint` | `str` | Per-responsibility framing rule (e.g., training_capacity → "backbone coordination, not direct delivery; align with DOL AI Literacy Framework, WIOA, Perkins V"). |
| `cross_section_relevance` | `list[str]` | Section keys where this responsibility must be addressed. Always includes `"section_1"`; most also appear in `"section_4"`. |

Exposed as `HUB_RESPONSIBILITIES` — list of five dicts. `draft_proposal_section` and `gap_check_section` iterate this list when the section's `cross_section_relevance` contains the section being processed.

### `PerformanceMetric`

Each NSF-required metric (FR-007) and each extended layer (FR-008).

| Field | Type | Validation / Notes |
|-------|------|-------------------|
| `key` | `str` | Stable identifier (e.g., `"individuals_trained_by_category"`). |
| `name` | `str` | Reviewer-facing name. |
| `category` | `str` | One of `"nsf_required"`, `"reach"`, `"depth"`, `"system_change"`. |
| `requires_baseline` | `bool` | True for all categories — the spec says baseline is mandatory before claiming progress (FR-008). |
| `notes` | `str` | Short hint, e.g., for `individuals_trained_by_category`: "report by educator / workforce / small-business-owner". |

Exposed as `NSF_REQUIRED_METRICS` (six entries, all `category="nsf_required"`) and `EXTENDED_METRIC_LAYERS` (entries with categories `reach`/`depth`/`system_change`). Combined as `ALL_METRICS` for ergonomic iteration.

State note: there is no metric "lifecycle" per se — Year 1 is "baseline established", Years 2–3 are "tracked against baseline". This is encoded in tool output text, not as a state machine.

### `KentuckyPartner`

A named institution or community organization in the likely partnership architecture (FR-009 / FR-010).

| Field | Type | Validation / Notes |
|-------|------|-------------------|
| `key` | `str` | Stable identifier (e.g., `"kctcs"`, `"cooperative_extension"`, `"cpe"`). |
| `name` | `str` | Display name (e.g., "Kentucky Community and Technical College System"). |
| `unique_contribution` | `str` | One-sentence rationale ("KCTCS reaches all 120 counties through 16 colleges, providing the workforce-training spine for the Hub"). |
| `trusted_messenger_for` | `list[str]` | Equity lens keys this partner is best positioned to serve (e.g., `["rural", "eastern_ky", "agricultural"]`). |
| `priority_sectors` | `list[str]` | Sector keys this partner is most relevant to. |

Exposed as `KY_PARTNERS` — list of dicts for **`uk_caai` (UK Center for Applied AI — the AI research lab providing technical credibility, evaluation, and research-to-practice translation; serves as the independent evaluation component referenced in FR-008)**, UK, KCTCS, CPE, COT, UK Cooperative Extension, KY Cabinet for Economic Development, KentuckianaWorks, KY SBDC, KDE. The `uk_caai` entry's `unique_contribution` MUST explicitly reference its independent-evaluation role so `gap_check_section` can detect when a Section 4 draft fails to cite an independent evaluator.

### `PrioritySector`

| Field | Type | Validation / Notes |
|-------|------|-------------------|
| `key` | `str` | One of `"healthcare"`, `"agriculture"`, `"advanced_manufacturing"`, `"energy"`, `"education"`. |
| `name` | `str` | Display name. |
| `notes` | `str` | One-sentence framing for that sector in the Kentucky context. |

Exposed as `KY_PRIORITY_SECTORS`.

### `EquityLens`

| Field | Type | Validation / Notes |
|-------|------|-------------------|
| `key` | `str` | One of `"rural_urban"`, `"eastern_ky"`, `"first_gen_adult"`, `"minority_owned_smb"`, `"underserved_districts"`, `"agricultural"`. |
| `name` | `str` | Display name. |
| `connected_partners` | `list[str]` | Partner keys whose trusted-messenger network reaches this lens. |

Exposed as `KY_EQUITY_LENSES`. The agent uses this to anchor equity claims to deliverable networks (FR-010).

### `AIReadinessLevel`

| Field | Type | Validation / Notes |
|-------|------|-------------------|
| `key` | `str` | One of `"literacy"`, `"proficiency"`, `"fluency"`. |
| `name` | `str` | Display name. |
| `definition` | `str` | The solicitation's definition (literacy = "Why AI? When AI?"; proficiency = "ability to apply"; fluency = "ability to create with"). |
| `audience_examples` | `list[str]` | Concrete audiences typical for that level (e.g., `["small business owners", "frontline workforce"]` for literacy). |

Exposed as `AI_LITERACY_LEVELS`. Tools post-process generated training language to ensure each training reference names both an audience and a level (FR-006 / SC-006).

### `SupplementalArtifactRule`

Allowed and prohibited supplemental document types.

| Field | Type | Validation / Notes |
|-------|------|-------------------|
| `key` | `str` | e.g., `"letter_of_collaboration"`, `"data_management_plan"`, `"mentoring_plan"`, `"letter_of_support"`. |
| `is_allowed` | `bool` | False for any prohibited artifact. |
| `condition` | `str \| None` | `"budget_includes_postdocs_or_grad_students"` for `mentoring_plan`; `None` for unconditional allows. |
| `format_rule` | `str \| None` | E.g., `"PAPPG format"` for LOC. |
| `refusal_message` | `str \| None` | Pre-canned refusal text used by `draft_supplemental_artifact` when `is_allowed=False`. |

Exposed as `SUPPLEMENTAL_RULES` — keyed by artifact type.

### `LOIRules`

| Field | Type | Validation / Notes |
|-------|------|-------------------|
| `title_prefix` | `str` | `"Kentucky Coordination Hub:"` (exact). |
| `title_forbids_acronyms` | `bool` | True. |
| `synopsis_page_limit` | `int` | 1. |
| `synopsis_must_cover` | `list[str]` | `["section_1_compressed", "section_2_compressed"]`. |

Exposed as `LOI_RULES`. `draft_loi` enforces these in its output post-processing.

### `FramingRule`

Cross-cutting drafting rules the agent applies to any output (FR-005, FR-017, FR-018).

| Field | Type | Validation / Notes |
|-------|------|-------------------|
| `key` | `str` | e.g., `"coordinator_not_builder"`, `"sustainability_year_4_plus"`, `"baseline_before_progress"`, `"common_instrument_across_partners"`, `"independent_evaluation_component"`, `"prose_over_bullets"`, `"no_overpromise_innovation_or_econ_dev"`. |
| `description` | `str` | One-sentence rule. |
| `applies_to` | `list[str]` | Section keys the rule applies to (most apply to all). |
| `violation_pattern_hints` | `list[str]` | Substrings or regex hints used by `gap_check_section` and `refine_section` to flag likely violations (e.g., "we will deliver training", "innovation will…"). |

Exposed as `FRAMING_RULES`.

### `AdministrationPriority`

| Field | Type | Validation / Notes |
|-------|------|-------------------|
| `key` | `str` | e.g., `"white_house_ai_action_plan"`, `"americas_talent_strategy"`, `"eo_ai_literacy"`, `"eo_remove_ai_barriers"`. |
| `name` | `str` | Display name. |
| `framing_phrase` | `str` | A short phrase the agent can lift into draft language when the user requests alignment (FR-019). The post-processor in `draft_proposal_section` uses substring-presence on this field to verify FR-019 compliance when alignment is requested. |

Exposed as `ADMINISTRATION_PRIORITIES`. `ADMINISTRATION_PRIORITY_PHRASES` is exposed as a flat `list[str]` of every `framing_phrase` for fast substring scanning.

### `ProgramOfficerQuestionTopic`

A pre-curated list of topics the team is likely to want to ask the program officer about. Used by `draft_program_officer_questions` (FR-015) to seed a structured question list and to drive the "answer-in-solicitation?" filter.

| Field | Type | Validation / Notes |
|-------|------|-------------------|
| `key` | `str` | e.g., `"hub_to_hub_coordination"`, `"deployment_corps_credentialing"`, `"shared_evaluation_instrument"`, `"sub_award_mechanics"`, `"matching_funds_treatment"`. |
| `name` | `str` | Short human-readable label. |
| `seed_question` | `str` | A starter question phrasing the agent may refine for the team. |
| `solicitation_resolved` | `bool` | True if the topic's answer is already explicit in NSF 26-508. The tool MUST NOT emit questions for `solicitation_resolved=True` topics. |

Exposed as `PROGRAM_OFFICER_QUESTION_TOPICS`.

### `PageBudget`

Used by `prioritize_page_budget` (FR-016) to surface current vs. target allocation under the 15-page limit and to drive a structured cut-list recommendation.

| Field | Type | Validation / Notes |
|-------|------|-------------------|
| `section_key` | `str` | One of `"section_1"`–`"section_5"`. |
| `target_share` | `float` | Recommended share of the 15-page narrative budget. Sum across Sections 1–5 ≤ 1.0. |
| `target_pages` | `float` | `15 * target_share`. Computed at module load. |
| `protected_subelement_keys` | `list[str]` | Sub-element keys (from `SECTION_REQUIREMENTS`) that MUST be preserved during any cut recommendation. |

Exposed as `PAGE_BUDGET` (mirrors `SECTIONS` ordering). The `prioritize_page_budget` tool consumes this plus user-supplied current page counts.

### `Deadline`

Used by `cite_deadlines` (FR-020) to deliver the standalone deadline-citation tool.

| Field | Type | Validation / Notes |
|-------|------|-------------------|
| `key` | `str` | One of `"loi"`, `"full_proposal"`, `"internal"`. |
| `date_iso` | `str` | `"2026-06-16"`, `"2026-07-16"`, `"2026-07-09"`. |
| `submission_path` | `str` | `"Research.gov"`, `"Research.gov or Grants.gov; AOR signature required"`, `"University of Kentucky Office of Sponsored Projects"`. |
| `display_label` | `str` | Reviewer-facing label. |

Exposed as `DEADLINES`.

## Relationships (in-process, not persisted)

```
Solicitation
  └─ has many ─ OpportunityFamily      (3: hub / national_lead / catalyst)
  └─ has many ─ ProposalSection        (6: loi_synopsis + section_1..5)
        └─ requires many ─ HubResponsibility   (via cross_section_relevance)
        └─ requires many ─ PerformanceMetric   (section_4 in particular)
HubResponsibility
  └─ framed by ─ FramingRule            (each responsibility has one or more)
KentuckyPartner
  └─ serves many ─ EquityLens
  └─ serves many ─ PrioritySector
SupplementalArtifactRule
  └─ standalone (allow/deny + format)
LOIRules / AIReadinessLevel / AdministrationPriority
  └─ standalone reference data
```

No foreign keys, no DB constraints — these are Python literal lookups.

## Validation rules enforced in tool code (not in a DB)

- `draft_proposal_section(section_key)` — `section_key` MUST be in `{loi_synopsis, section_1..section_5}`. Output MUST include the exact `heading` and reference every entry in `required_subelements`.
- `draft_loi(...)` — generated title MUST start with `LOI_RULES["title_prefix"]` and MUST NOT contain acronyms (string scan against a small acronym disallow-list — NSF, AI, UK, KCTCS, CPE, COT, etc., are all forbidden in the title; the agent uses long forms).
- `draft_supplemental_artifact(artifact_key)` — `artifact_key` MUST be in `SUPPLEMENTAL_RULES` AND `is_allowed=True`. If `condition` is set (e.g., Mentoring Plan), the tool requires the matching condition flag in the request and refuses otherwise. Prohibited artifacts return a tool-level `Alert(variant="error", message=refusal_message)`, which `MCPServer.process_request` already routes as a tool error.
- `gap_check_section(section_key, draft_text)` — output MUST list every `required_subelement` not detectably present in the draft, and MUST scan for `FRAMING_RULES.violation_pattern_hints`.
- `techaccess_scope_check(user_request)` — output MUST classify as one of `{primary_hub, sibling_national_lead, sibling_catalyst, out_of_family}` and provide a redirect message for `out_of_family`.

## State / Lifecycle

There is no persistent state. Each tool invocation is independent. The agent does not track "draft state" across calls. Per Clarifications Q3, the user is expected to paste prior context at session start.

## Migration impact

**None.** Constitution Principle IX is satisfied by N/A — no schema is changed, no migration script is required.
