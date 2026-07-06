# Contract: Spoken Rendition (`speech` field on watch-bound frames)

**Additive, watch-profile sockets only.** When the registered device profile of the receiving
socket is `watch`, the orchestrator attaches a `speech` object to component-bearing delivery
frames. No other client receives the field; unknown-field tolerance means older/other clients
are unaffected. Frame/component *vocabulary* is unchanged — `ui_protocol.json` lists stay
as-is; this contract documents the field.

## Shape

```json
{
  "type": "ui_render",
  "components": [ …watch-adapted components… ],
  "speech": {
    "ssml": "<speak><s>Weather for Lexington.</s><break time=\"300ms\"/><s>72 degrees, clear.</s></speak>",
    "text": "Weather for Lexington. 72 degrees, clear."
  }
}
```

- Producer: the existing `webrender` `voice` render target (`render_voice`), fed the **same
  ROTE-adapted components** the frame carries — screen and speech never diverge.
- `text` is the tag-stripped fallback of `ssml`.
- Applies to `ui_render` and `ui_upsert` (per-op content collapsed into one utterance per
  delivery); absent (not empty) when the delivery has no speakable content.
- Bounds: the voice target's documented caps (list/table/timeline item limits, 300-char text
  behavior) are authoritative; the field is never larger than the visual payload's source.

## Client obligations (watch)

- Speak via `AVSpeechUtterance(ssmlRepresentation:)`, falling back to `text`.
- Honor system silent/DND state; stop on navigation; expose stop/replay; never auto-speak the
  same turn twice (track last-spoken turn id).
- Absence of `speech` ⇒ silent delivery (no client-side synthesis from components).
