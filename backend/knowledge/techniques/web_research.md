---
name: "web_research_techniques"
type: "technique"
agent: "web-research-1"
created_at: "2026-06-11T00:00:00+00:00"
updated_at: "2026-06-11T00:00:00+00:00"
synthesis_count: 0
interaction_count: 0
confidence: 0.5
---

### Effective Patterns
*   **Search before fetch**: `web_search` first to find candidate URLs, then
    `fetch_page` only on the most relevant results — fetches are bounded
    (1 MB / 15 s each) so choose targets deliberately.
*   **One-shot briefs**: for "research X and summarize" requests, call
    `research_brief` directly instead of orchestrating search + fetch + an
    ad-hoc summary; it produces a cited brief, a sources table, and per-section
    tabs in a single tool call.

### Anti-Patterns
*   **Fabricating sources**: never present URLs that were not returned by
    `web_search` or fetched by `fetch_page`. The brief refuses to cite
    anything it did not fetch; mirror that behavior in conversation.
*   **Fetching private/internal hosts**: all egress is SSRF-gated; URLs that
    resolve into private address space are refused by design — do not retry
    them.

### Error Recovery
*   **Error Pattern**: `Search failed: DuckDuckGo HTML search could not complete…`
    *   **Root Cause**: the keyless endpoint is unreachable or rate-limited.
    *   **Recovery Strategy**: suggest saving the optional `SEARCH_API_URL` +
        `SEARCH_API_KEY` credentials (Tavily-compatible endpoint) in the
        agent's settings; the provider path is preferred automatically.
*   **Error Pattern**: `Page too large` / `Fetch failed`.
    *   **Recovery Strategy**: pick a different result from the search list;
        per-fetch bounds are fixed (1 MB / 15 s) and are not configurable.

### Recommended Tool Sequences
*   **Quick lookup**: `web_search` → answer from snippets (cite URLs).
*   **Deep dive**: `web_search` → `fetch_page` (top 1-2 URLs) → answer.
*   **Briefing**: `research_brief` (depth `shallow` for speed, `standard` for
    coverage).

### Statistics Summary

| Tool Name | Total Calls | Success Rate | Failure Rate |
| :--- | :--- | :--- | :--- |
| `web_search` | 0 | — | — |
| `fetch_page` | 0 | — | — |
| `research_brief` | 0 | — | — |
