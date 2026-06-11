---
name: "web_research_capabilities"
type: "capability"
agent: "web-research-1"
updated_at: "2026-06-11T00:00:00+00:00"
---

# web-research-1 Capabilities

Overall: 0 calls, no telemetry yet (seeded at feature 029 rollout)

## Tools

- **web_search**: search the web for a query. Prefers the optional configured
  Tavily-compatible provider (`SEARCH_API_URL` + `SEARCH_API_KEY`); falls back
  to the keyless DuckDuckGo HTML endpoint. Returns titles, URLs, and snippets
  — results are never fabricated.
- **fetch_page**: fetch a single page through the egress-gated HTTP layer
  (1 MB cap, 15 s timeout) and extract readable text as markdown (headings
  kept; scripts/styles/navigation stripped; truncation is announced).
- **research_brief**: search, fetch the top sources (shallow=2, standard=5),
  and synthesize one cited markdown brief. Citations `[1]..[n]` refer only to
  sources that were actually fetched; a sources table lists every cited URL.
