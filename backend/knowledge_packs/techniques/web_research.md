---
name: "web_research_techniques"
type: technique
agent: "web-research-1"
authored: true
relevance: [research, search, web, sources, cite, brief, investigate]
updated_at: "2026-06-24"
---

# Web Research — effective use

## Effective Patterns
- Start with `web_search` to find candidate sources, then `fetch_page` on the
  most promising results before drawing conclusions — snippets are often too
  thin to answer well.
- Use `research_brief` when the user wants a synthesized, cited write-up; it
  composes multiple sources and never fabricates citations.

## Anti-Patterns
- Never invent a source or a URL. If a claim cannot be grounded in a fetched
  page, say it is unverified.
- Do not rely on a single source for a contested or fast-changing fact.

## Recommended Tool Sequences
- "research X and write me a brief" → `web_search` → `fetch_page` (top hits) →
  `research_brief`.
- "find the latest on X" → `web_search` (then fetch to confirm).
