---
name: "summarizer_techniques"
type: "technique"
agent: "summarizer-1"
created_at: "2026-06-11T00:00:00+00:00"
updated_at: "2026-06-11T00:00:00+00:00"
synthesis_count: 0
interaction_count: 0
confidence: 0.5
---

### Effective Patterns
*   **URL straight to summary**: for "summarize this link" requests, call
    `summarize_url` directly — it fetches, extracts readable text, and
    summarizes in one call. Do not pre-fetch with another agent's tools.
*   **Focused summaries**: pass `focus` to `summarize_text` when the user asks
    about a specific aspect ("what does it say about pricing?").
*   **Labeled comparisons**: pass `labels` to `compare_documents` so the
    side-by-side cards and differences table use the user's own names for the
    documents.

### Anti-Patterns
*   **Ignoring truncation**: inputs over 24,000 characters are cut at the cap
    and an explicit truncation notice is prepended — surface that notice
    rather than implying full coverage.
*   **Summarizing unreadable pages**: if a fetched page yields no readable
    text, the tool returns an error instead of inventing a summary; do not
    paraphrase from the URL alone.

### Error Recovery
*   **Error Pattern**: `LLM unavailable`.
    *   **Root Cause**: no per-session or operator LLM credentials resolved.
    *   **Recovery Strategy**: configure LLM settings (feature 006) and retry.
*   **Error Pattern**: `Fetch failed` / `Page too large` on `summarize_url`.
    *   **Recovery Strategy**: per-fetch bounds (1 MB / 15 s) and the SSRF
        gate are fixed; ask the user to paste the text and use
        `summarize_text` instead.

### Recommended Tool Sequences
*   **Single document**: `summarize_text` (or `summarize_url` for links).
*   **Two documents**: `compare_documents` — it internally summarizes both
    sides; no need to call `summarize_text` first.

### Statistics Summary

| Tool Name | Total Calls | Success Rate | Failure Rate |
| :--- | :--- | :--- | :--- |
| `summarize_text` | 0 | — | — |
| `summarize_url` | 0 | — | — |
| `compare_documents` | 0 | — | — |
