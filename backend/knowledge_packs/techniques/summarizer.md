---
name: "summarizer_techniques"
type: technique
agent: "summarizer-1"
authored: true
relevance: [summarize, summary, tldr, condense, digest, url, article]
updated_at: "2026-06-24"
---

# Summarizer — effective use

## Effective Patterns
- For a web page, prefer `summarize_url` (it fetches via the egress-gated
  client and follows redirects) over asking the user to paste text.
- For text the user already supplied, use `summarize_text` directly — do not
  re-fetch.
- Use `compare_documents` when the user wants the differences or a synthesis
  across two or more sources, not separate per-document summaries.

## Anti-Patterns
- Do not fabricate a summary when a fetch fails — surface the failure and offer
  to retry or accept pasted text.
- Do not exceed the input cap silently; if content is truncated, say so.

## Recommended Tool Sequences
- "summarize this link" → `summarize_url`.
- "what's different between these two" → `compare_documents`.
