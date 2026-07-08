# Contract: Narrative Token Streaming (existing frames only)

**Wire delta: NONE.** `backend/shared/ui_protocol.json` is not modified. Narrative
streaming reuses the already-manifested streaming frame category (`ui_stream_data` et
al.) that web (`client.js` `case "ui_stream_data"`), Windows (`streaming.py`), and
Android (`Streaming.kt::streamFrameToOps`) already render. Drift guards in all three
stacks must remain green — that is the proof of protocol neutrality.

## Behavior

1. Applies to the chat loop's final (tool-free) LLM iteration only, behind
   `FF_LLM_STREAMING` (default on).
2. `_call_llm` streaming mode: the sync OpenAI-compatible client is invoked with
   `stream=True` inside the existing worker thread; deltas are marshaled to the event
   loop via `loop.call_soon_threadsafe`.
3. Discrimination: chunks buffer until the first meaningful delta —
   - `delta.tool_calls` ⇒ this iteration is a tool round: abort streaming mode, fall
     through to today's non-streamed handling (no frames were emitted).
   - `delta.content` ⇒ open a narrative stream and emit incremental `ui_stream_data`
     frames targeting the chat narrative slot.
4. Completion: the existing final `ui_render` (authoritative canvas/chat replace via the
   existing morph path) always lands and supersedes the streamed text. Stream frames are
   presentation-progressive only; transcript persistence is unchanged (the full final
   text is what is stored).
5. Fallback ladder (each step silent, logged via `perf`/warning):
   provider rejects `stream=True` or errors mid-stream ⇒ retry that call non-streaming;
   flag off ⇒ today's behavior byte-for-byte; non-streaming provider ⇒ SC-007 is
   conditional and does not fail.

## Invariants

- Same authenticated socket, same permission and PHI gates, same audit rows as the
  non-streamed path (streaming changes delivery pacing, not content or policy).
- A client that ignores the stream frames still receives the final `ui_render` — no
  client can end a turn with partial-only text.
- No new frame type, field, or enum value may be introduced by this work. If
  implementation discovers that reuse is impossible without a manifest change, STOP and
  re-plan (that would trigger Constitution XII / 044 drift-guard review).
