# Contract: Authored Skill Packs (progressive disclosure)

## Pack format

Committed markdown under `backend/knowledge_packs/techniques/<agent>.md` (and optionally `capabilities/`). YAML frontmatter + body:

```markdown
---
name: <human name>
type: technique            # technique | capability
agent: <agent_id>          # the agent/capability this pack guides
authored: true             # marks it human-authored — synthesizer must never overwrite
relevance: [keywords, ...] # cues used for on-demand selection
updated_at: <ISO date>
---

## Effective Patterns
...
## Anti-Patterns
...
## Recommended Tool Sequences
...
```

`authored: true` is the protected marker. The auto-synthesizer (`knowledge_synthesis.py`) MUST NOT write into `backend/knowledge_packs/`; it continues to own the gitignored `backend/knowledge/` only.

## Loading (orchestrator/skill_packs.py + knowledge_synthesis.KnowledgeIndex)

- `KnowledgeIndex` is extended to read `backend/knowledge_packs/` with an `authored` provenance flag. Authored content takes precedence over a synthesized pack for the same agent.
- `get_techniques_for_agent(agent_id)` (currently defined but never called) is wired into per-turn system-prompt assembly (orchestrator.py ~3281-3357).
- For a turn, the loader selects packs only for agents whose tools are in play / enabled this turn, scores by `relevance` against the request, and injects a **bounded digest** (capped length, a small number of packs) — progressive disclosure, not a full dump.
- `RETIRED_KNOWLEDGE_STEMS` / `RETIRED_AGENT_IDS` still exclude retired agents (incl. `etf-tracker-1-1`).

## Behavior invariants (MUST hold)

- Gated by `FF_SKILL_PACKS`. Off → today's behavior (only the existing aggregate routing hints, if any).
- Fail-open: any error in loading/selection → the turn proceeds with no pack injected, logged (`skill_packs.fallback{reason}`).
- A request unrelated to any pack injects nothing; baseline per-turn context size is unchanged.
- Selection is bounded so token budget / KV-cache prefix stability is not regressed.
- Authored packs are reproducible across container rebuilds (committed) and never clobbered by synthesis.
