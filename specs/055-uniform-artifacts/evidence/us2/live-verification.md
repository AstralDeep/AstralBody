# US2 — live verification (server + wire), 2026-07-13

**Setup**: `astraldeep` container serving branch code (post-466e689 + the
unsubscribe-persist follow-up), `USE_MOCK_AUTH=true` (mock user `test_user`),
raw-WS driver on the host (`websockets`), real in-process `general` agent.

## Stream → keyed frames → terminal persist → reload (quickstart §US2 1+3)

Driving `stream_subscribe {tool_name: live_system_metrics, params:{interval_s:1}}`
against a fresh chat:

1. **Blocking bug found first**: push-stream dispatch predated feature 040 and
   knew only WS-connected agents — every built-in streaming tool failed with
   `agent 'general-1' is not connected`. Fixed via the LoopbackSocket branch
   in `_dispatch_stream_request`/`_cancel_stream_request` (regression suite
   `tests/test_stream_inprocess.py`).
2. `stream_subscribed` ack carries the bridged identity:
   `component_id: wc_1e5db16cf19c4fc1`.
3. Every `ui_stream_data` frame carries the same identity; seq monotonic 1–4
   with real card content; terminal frame seq 5 (above the high-water — the
   seq-continuation fix observable).
4. On `stream_unsubscribe` (the indefinite stream's success-terminal), the
   retained last chunk persisted:
   `saved_components` row `('wc_1e5db16cf19c4fc1', 'card', 'Live System Metrics')`.
5. Fresh socket + `load_chat` on that chat: the workspace-hydration
   `ui_render` carries `wc_1e5db16cf19c4fc1` with the Live System Metrics
   card — reload-visible under the same identity.

## Covered by pinned tests rather than live drive

- Narrative markdown boundary (§US2 4): `tests/test_narrative_markdown_boundary.py`
  (16 tests incl. the recorded `You rolled **` defect + property test).
- Leak stripping (§US2 5): `tests/test_toolcall_leak_stripping.py` (18 tests
  incl. the reconstructed `update_component<arg_key>…` fixture and the
  `john@true.example.com` false-positive regression).
- Kill-mid-stream honest failure (§US2 6): `tests/test_stream_persist.py::
  test_abandoned_stream_persists_failed_alert` + terminal-hook coverage in
  `tests/test_stream_bridge.py` (retry exhaustion, TTL eviction,
  resume-dispatch failure).
- Client keying rules: web (live-driven above at the wire level; visual morph
  code-reviewed), Windows (`test_streaming_bridge.py`, 10), Android
  (`StreamingTest`/`WireTest`, CI), Apple (`StreamKeyingTests`, 9).

**Pending operator step**: simultaneous web + native visual watch of one
stream (§US2 1) needs a signed-in simulator (real PKCE only on Apple targets)
and an LLM-configured user for chat-driven dispatch — staged, see us1 notes.
