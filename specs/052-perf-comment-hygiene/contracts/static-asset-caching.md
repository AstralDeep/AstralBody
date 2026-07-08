# Contract: Versioned-Immutable Static Asset Delivery

Governs `GET /static/*` on the orchestrator (`:8001`). Replaces the blanket
`Cache-Control: no-cache` behavior of `_NoCacheStaticFiles`.

## URL contract

- Every asset referenced by the shell or client code carries a per-file version query:
  `/static/<path>?v=<sha1[:12] of file bytes>`.
- The server maintains a process-lifetime version map (built at boot, memoized). A deploy
  produces a new process ⇒ new hashes ⇒ new URLs; old URLs simply stop being referenced.
- The shell (`GET /`) remains `Cache-Control: no-store` and is the sole source of current
  asset URLs — this is what makes immutable caching safe.

## Response headers

| Request | Cache-Control |
|---|---|
| `?v=` present AND matches current hash | `public, max-age=31536000, immutable` |
| `?v=` absent or mismatched | `no-cache` (today's behavior; ETag/Last-Modified 304 flow preserved) |

## Invariants

1. No external-origin request is required before first paint (fonts self-hosted under
   `/static/fonts/`, preloaded from the shell; the googleapis `@import` is gone).
2. `plotly.min.js` is NOT referenced from the shell `<head>`; it is injected on first
   chart need (and idle-prefetched). Charts rendered before the library finishes loading
   are re-initialized on its `load` event — never permanently blank.
3. `tailwind.js` remains in the shell `<head>` (load-bearing, render-blocking by design)
   but is served under this versioned-immutable contract.
4. Repeat visit with no deploy: total `/static/*` transfer <100KB (SC-004) — everything
   heavy is a 304-free cache hit.
5. Content changes without a URL change are impossible by construction (hash-derived).

## Verification

- Unit: version map correctness (hash changes ⇒ URL changes); header matrix above.
- CI asset-budget check: parse the shell, assert no external origins and no plotly tag;
  assert versioned URLs on all referenced assets.
- Manual (quickstart): browser network panel on second visit — transfer <100KB.
