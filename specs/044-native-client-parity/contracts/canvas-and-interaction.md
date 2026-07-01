# Contract — Canvas Convergence, Pagination, Progress, Markdown (044)

**Satisfies**: FR-006, FR-007, FR-011, FR-012, FR-013, US1.5, US2.4–2.6 | **Research**: R11–R14

## 1. Canonical canvas semantics (from the web baseline + verified send sites)

| Instruction | Semantics every client MUST implement |
|---|---|
| `ui_upsert {chat_id, ops[]}` | authoritative keyed mutation: `{op:"upsert", component_id, component}` merges/replaces that identity in place; `{op:"remove", component_id}` deletes it. Foreign-`chat_id` frames dropped (logged). |
| `ui_render {target:"canvas", components[]}` | **full-canvas state, reconciled by identity**: the resulting canvas contains exactly the delivered components; components whose `component_id`/`id` matches an existing one are morphed in place (no flicker/state loss), new ids append, absent ids are removed. Never a blind widget-tree rebuild, never a merge that resurrects components the server dropped. |
| `ui_render {target:"chat"}` | transcript append (text flatten per client idiom). |
| `ui_render {target:"history"}` | historical view render — Windows stops silently dropping it (routes to its history view). |
| `ui_stream_data` / `stream_data` | keyed frame update with **sequence protection**: out-of-order or duplicate frames for a stream id are discarded (Android's `seqState` pattern; Windows `streaming.py` gains the same guard if absent). Socket drop mid-stream resolves the stream visually (interrupted badge), never a frozen "live" state. |
| `chat_status {status:"done"}` | turn commit (buffered in-turn canvas state swaps in — Android's commit-on-done lifecycle is the shared model). |

**Server guarantee (full-stack)**: a backend regression test asserts canvas-target
`ui_render`s always carry the complete materialized canvas (the 029 designer contract). If
live verification finds a send site delivering partial canvases, the fix lands **server-side**
— clients never guess at missing components. The known Android clobber sequence
(keyed upsert → out-of-turn full render) becomes a scripted convergence scenario asserted on
all three clients; rapid designer re-render racing keyed upserts (spec edge case) is part of
it.

## 2. Table pagination (existing contract, now implemented natively)

A table component with `total_rows` + `page_size` (+ `component_id`) gets a native pager:

```
component fields: headers, rows, total_rows, page_size, page_offset (default 0),
                  page_sizes (optional, default [25,50,100,200]), component_id
pager UI:        ‹ Prev · "rows X–Y of Z" · Next ›  (+ optional page-size selector)
request:         ui_event {action:"table_paginate",
                           payload:{component_id, chat_id,
                                    params:{page_offset:<new>, page_size:<n>}}}
response:        ui_upsert op keyed to the same component_id (existing client apply path)
```

Provenance (`source_tool/agent/params`) is resolved server-side from the persisted workspace
row — natives MUST NOT echo it (028 path only). Tables without pagination metadata render as
today. A table far exceeding the screen stays responsive (page bounds the row count).

## 3. Progress-signal duty (FR-006)

| Frame | Windows | Android | Web (baseline) |
|---|---|---|---|
| `user_message_acked` | **add**: pending→acked mark | has | has |
| `chat_status` (full vocab incl. `processing_async`) | extend | extend | has |
| `chat_step` | **add**: step trail line | **add** | has |
| `tool_progress` | **add**: transient progress line | **add** | has |
| `task_started` / `task_completed` | **add**: async hand-off notice + completion toast | **add** | has |
| `notification` | **add**: toast | **add**: toast | classify (log) |
| `heartbeat`, `stream_list`, component-verb acks, `llm_usage_report`, `audit_append`, `agent_creation_progress`, `rote_config`, `system_config` | classified `ignored` (logged) unless already surfaced | same | has/uses |

Invariant: every turn reaches a visible terminal state (done / failed / interrupted) under
the failure-injection suite (SC-006) — error frames, in-band Alerts, and disconnects all
resolve the turn.

## 4. Markdown construct set (FR-012)

Minimum equivalent set on all three clients: headings, bold/italic, inline + fenced code,
ordered/unordered lists, **links**. Android adds link rendering (`inlineMarkdown` →
`LinkAnnotation.Url` via `withLink`; Compose BOM already ≥1.7); Windows (QLabel rich text)
and web already comply. The same assistant text MUST NOT render as raw markup on one client
and formatted on another — asserted by a shared fixture rendered in each client's test suite.
