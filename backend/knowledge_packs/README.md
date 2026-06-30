# Authored skill packs (feature 040, US4)

Human-authored, **version-controlled** capability/technique guidance that the
chat model loads **on demand by relevance** — only for the agents whose tools
are in play on a given turn (progressive disclosure, à la Claude Code's
`SKILL.md`).

## Why this directory exists

The auto-synthesized knowledge under `backend/knowledge/` is git-ignored,
telemetry-derived, and **rewritten** by the "Dreamer" (`knowledge_synthesis.py`)
on every cycle — so hand-curated guidance placed there gets clobbered. Packs
here are:

- **Committed** (reproducible across container rebuilds), and
- **Never written by the synthesizer** — `get_techniques_for_agent` reads this
  directory *first* and only falls back to the synthesized file when no authored
  pack exists (`AUTHORED_KNOWLEDGE_DIR` in `knowledge_synthesis.py`).

## Format

`techniques/<agent-slug>.md`, where the slug is the agent id with the trailing
`-N` removed and hyphens → underscores (e.g. `web-research-1` → `web_research`,
`summarizer-1` → `summarizer`). YAML frontmatter + a short body:

```markdown
---
name: "<human name>"
type: technique
agent: "<agent-id>"
authored: true        # protected marker — the synthesizer must never write here
relevance: [keyword, ...]
updated_at: "<ISO date>"
---

## Effective Patterns
...
## Anti-Patterns
...
## Recommended Tool Sequences
...
```

Loading is bounded (`orchestrator/skill_packs.py`: at most a few packs, capped
total size) and fail-open: a missing or malformed pack simply contributes
nothing and the turn proceeds normally.
