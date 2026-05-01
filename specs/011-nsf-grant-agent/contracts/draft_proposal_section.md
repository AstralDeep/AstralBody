# MCP Tool Contract: `draft_proposal_section`

**Module**: `backend/agents/grants/mcp_tools.py`
**Registry**: `TOOL_REGISTRY["draft_proposal_section"]`

## Purpose

Draft any of the five required full-proposal sections (or, on request, the LOI synopsis when called with `section_key="loi_synopsis"`) using the exact required heading text and addressing every required sub-element. Implements FR-002, FR-003, FR-004, FR-005, FR-009, FR-017, FR-018.

## Input schema (JSON Schema)

```json
{
  "type": "object",
  "properties": {
    "section_key": {
      "type": "string",
      "enum": ["loi_synopsis", "section_1", "section_2", "section_3", "section_4", "section_5"],
      "description": "Which section to draft. The exact required heading is injected by the tool."
    },
    "opportunity": {
      "type": "string",
      "enum": ["hub", "national_lead", "catalyst"],
      "default": "hub",
      "description": "Which TechAccess opportunity the draft is for. Defaults to the Kentucky Coordination Hub. National Lead and Catalyst trigger framing-note alerts."
    },
    "existing_draft": {
      "type": "string",
      "description": "Optional: prior text the agent should treat as a starting point rather than drafting from scratch."
    },
    "partner_roster_override": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Optional: partner keys (matching KY_PARTNERS) to scope the draft to. If omitted, the full likely partnership architecture is used as a working assumption and that assumption is named explicitly in the draft."
    },
    "extra_context": {
      "type": "string",
      "description": "Optional: any extra context (PI roster, prior decisions, page-budget constraint) the team wants the draft to honor."
    },
    "request_administration_priority_alignment": {
      "type": "boolean",
      "default": false,
      "description": "When true, the draft post-processor enforces FR-019 by verifying that the output contains at least one phrase from ADMINISTRATION_PRIORITY_PHRASES. If absent, the post-processor injects an alignment paragraph that lifts at least one phrase verbatim."
    }
  },
  "required": ["section_key"]
}
```

## Output

A `_ui_components` payload built via `create_ui_response(...)` containing:

- A `Card` with `title` set to the exact heading from `SECTION_HEADINGS[section_key]`.
- One or more `Text` blocks rendering the drafted prose (clear prose, not bullet-heavy, per FR-017).
- A `List_` summarizing every required sub-element addressed in the draft (one bullet per `required_subelement` in `SECTION_REQUIREMENTS[section_key]`), so reviewers can verify SC-001 by inspection.
- For `section_4`: an explicit sub-Card listing each NSF-required metric by name (six entries from `NSF_REQUIRED_METRICS`) plus reach / depth / system-change layers (FR-008, SC-002).
- An `Alert(variant="info")` when `opportunity != "hub"` reminding the user that National Lead / Catalyst rules differ.

## Refusal paths

- If `section_key` is missing or unknown → `Alert(variant="error", message=...)`. Routed by `MCPServer.process_request` as a tool error.
- If the user request (free-text) is not actually about NSF TechAccess (detected via `techaccess_scope_check`) → refuse with redirect.

## Post-processing invariants the tool MUST enforce on its own output

1. The drafted text contains the exact `heading` string (not a paraphrase).
2. Every entry in `SECTION_REQUIREMENTS[section_key]` is referenced (case-insensitive substring scan on a normalized variant).
3. For Section 1: all five Hub responsibilities by name; coordinator-not-builder framing.
4. For Section 4: all six NSF-required metric names + at least one of each extended layer + a Year 1 baseline statement + an independent evaluation component.
5. For LOI synopsis: ≤ ~600 words and contains both Section-1-equivalent and Section-2-equivalent content.
6. No language matching `FRAMING_RULES.violation_pattern_hints` for "direct delivery" or "innovation overpromise".
7. Every training / capacity-building reference is paired with a literacy/proficiency/fluency level and an audience (FR-006 / SC-006).
8. When `request_administration_priority_alignment=true`, the draft contains at least one substring drawn from `ADMINISTRATION_PRIORITY_PHRASES` (FR-019). If the LLM omits all phrases, the post-processor appends an alignment paragraph and re-scans.

If any post-processing invariant fails, the tool MUST patch its own output by appending a "Required-coverage gap" section listing the missing invariants, rather than silently returning incomplete work.

## Test expectations

- Unit: deterministic post-processing path (LLM mocked) — every invariant tested for each `section_key`.
- Unit: refusal path on bad `section_key`.
- Integration: `MCPServer.process_request({method: "tools/call", name: "draft_proposal_section", arguments: ...})` returns a `MCPResponse` whose `ui_components` contains the expected `Card.title`.
