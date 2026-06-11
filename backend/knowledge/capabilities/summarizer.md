---
name: "summarizer_capabilities"
type: "capability"
agent: "summarizer-1"
updated_at: "2026-06-11T00:00:00+00:00"
---

# summarizer-1 Capabilities

Overall: 0 calls, no telemetry yet (seeded at feature 029 rollout)

## Tools

- **summarize_text**: summarize provided text into a structured TL;DR / key
  points / notable quotes tab set. Inputs over 24,000 characters are truncated
  with an explicit notice. Optional `focus` steers the summary.
- **summarize_url**: fetch a page through the egress-gated HTTP layer (1 MB
  cap, 15 s timeout), extract its readable text, then follow the
  `summarize_text` path.
- **compare_documents**: side-by-side summary cards for two documents plus a
  table of key differences by aspect. Optional `labels` names the documents.
