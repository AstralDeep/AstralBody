# MCP Tool Contract: `draft_program_officer_questions`

**Module**: `backend/agents/grants/mcp_tools.py`
**Registry**: `TOOL_REGISTRY["draft_program_officer_questions"]`

## Purpose

Produce a structured, ready-to-send list of questions the proposal team can email to the NSF program officer. Filters out questions whose answers are explicit in NSF 26-508. Implements FR-015 and US3 Acceptance Scenario 3 / SC-012.

## Input schema (JSON Schema)

```json
{
  "type": "object",
  "properties": {
    "topics": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Optional: subset of PROGRAM_OFFICER_QUESTION_TOPICS keys to focus on. If omitted, the tool emits questions across every unresolved topic."
    },
    "team_specific_context": {
      "type": "string",
      "description": "Optional: free-text context about the Kentucky team's specific situation (e.g., 'we are partnering with two community colleges that share a single CFO') that should shape the questions."
    },
    "max_questions": {
      "type": "integer",
      "default": 8,
      "minimum": 1,
      "maximum": 20,
      "description": "Cap on number of questions returned."
    }
  }
}
```

## Output

`_ui_components` payload:

- `Card(title="Questions for the NSF Program Officer")` containing:
  - A `Text` block with a brief preamble ("These questions are scoped to the Kentucky Coordination Hub proposal and avoid topics already addressed in NSF 26-508.").
  - A numbered `List_` of questions, one per topic, each refined with any `team_specific_context`.
- `Card(title="Topics filtered out")` listing topics where `solicitation_resolved=True` was the reason a question was suppressed (so the team can see what was deliberately excluded).

## Refusal paths

- If every requested topic has `solicitation_resolved=True` → `Alert(variant="error", message="The topics requested are already addressed in NSF 26-508; nothing to ask the program officer.")`.

## Post-processing invariants

1. Output contains zero questions whose topic key has `solicitation_resolved=True` in `PROGRAM_OFFICER_QUESTION_TOPICS`.
2. Output never exceeds `max_questions`.
3. Each question is a single sentence ending in `?`.
4. No question text contains a verbatim quote from NSF 26-508 (post-processor scans against a small set of canonical solicitation phrases — e.g., "rather than delivering training directly", "leverage existing resources").

## Test expectations

- Unit: a topic flagged `solicitation_resolved=True` is filtered out 100% of the time.
- Unit: `max_questions=3` is respected.
- Unit: empty topic intersection (all requested topics solicitation-resolved) → canonical refusal Alert.
- Integration: round-trip via `MCPServer.process_request` returns the expected two Cards.
