# Data Model — Fix Page Flash

**Feature**: 010-fix-page-flash
**Date**: 2026-05-01

This feature has **no persisted data and no schema changes**. Everything described here is in-memory, scoped to a single browser tab/session.

## In-memory entities

### `BackgroundFetchCache`

Module-scoped (singleton per browser tab) deduplication store used by the helper that wraps in-scope background fetches.

| Field | Type | Notes |
|---|---|---|
| `entries` | `Map<string, Promise<unknown>>` | Key is `${endpoint}?${sortedQueryString}`. Value is the in-flight or resolved promise of the fetch. |
| `getOrFetch` | `(key, fetcher, opts?: { refresh?: boolean }) => Promise<T>` | Returns the cached promise if present and `refresh` is falsy; otherwise invokes `fetcher`, stores the promise, and returns it. |
| `invalidate` | `(key) => void` | Removes a single entry (used after explicit user actions that mutate the underlying data). |

**Lifecycle**: Created when the bundle loads; destroyed only when the tab closes. There is no eviction by time — eviction is by explicit `invalidate` or by tab close.

### `MountState` (per animating list region)

Local component state, not shared.

| Field | Type | Notes |
|---|---|---|
| `mountedRef` | `MutableRefObject<boolean>` | `false` until the mount-only `useEffect` runs once, then `true` for the lifetime of the component instance. |
| `initialIdsRef` | `MutableRefObject<Set<string>>` | Captures the IDs (or count, for ordered streams without IDs) of items present at first paint. Read by render to decide whether each `<motion.*>` receives `initial={false}` or the fade-in object. |

**Lifecycle**: Created on component mount, persists across re-renders, destroyed on unmount.

### `SessionAuthSnapshot` (audit reference, not new code)

Existing in-memory state already exposed via the auth provider. Reads `accessToken` and `isAdmin`. The audit verifies that no globally mounted region calls `useEffect(() => fetch(...), [accessToken])` — token identity changes during silent OIDC refresh must not retrigger any in-scope background fetch. No structural changes to this entity; documented here so the audit checklist can reference it.

## What this feature does NOT change

- Database schema (no migration needed; Constitution IX not triggered).
- Backend models or DTOs.
- The shape of any existing API response (`FlaggedToolsResponse`, agent listings, chat history payloads, etc.).
- LocalStorage keys or IndexedDB stores. The existing `astral-theme` key in localStorage is read by the new inline bootstrap script in `index.html`, but no new keys are introduced and no existing key's shape changes.

## Validation rules

None — this feature does not introduce any user input or persisted state requiring validation.

## State transitions

None — the in-memory entities described above hold either "uncached → cached" (`BackgroundFetchCache`) or "pre-mount → mounted" (`MountState`) transitions, both of which are mechanical and have no business-rule semantics.
