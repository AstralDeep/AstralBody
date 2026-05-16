# US-21: Sound-Playing UI Components

## User Story

> As a user, I want UI components that can play sounds so that agents
> can produce audio output (speech, music, tones) directly in the canvas.

Use Vaiden's piano agent to test the implementation.

## Scope

- Add an `Audio` primitive to the SDUI component catalog
- Render `<audio>` elements in the frontend DynamicRenderer
- Agents (piano, TTS, etc.) emit `Audio` components through the existing
  `create_ui_response` helper

## Backend: Audio Primitive

### Fields

| Field         | Type           | Default     | Description                              |
|---------------|----------------|-------------|------------------------------------------|
| type          | `"audio"`      | —           | Discriminator                            |
| src           | `string`       | `""`        | URL or base64 data URI                   |
| contentType   | `string?`      | `null`      | MIME type (audio/mpeg, audio/wav, etc.)  |
| autoplay      | `boolean`      | `false`     | Auto-play on render                      |
| loop          | `boolean`      | `false`     | Loop playback                            |
| label         | `string?`      | `null`      | Title above the player                   |
| showControls  | `boolean`      | `true`      | Show browser-native controls             |
| description   | `string?`      | `null`      | Caption below the player                 |

### Agent Usage

```python
from shared.primitives import Audio, create_ui_response

# TTS agent returning speech
audio = Audio(
    src="data:audio/mpeg;base64,//uQx...",
    contentType="audio/mpeg",
    autoplay=True,
    label="Generated Speech",
)

# Piano agent returning a MIDI or WAV
piano = Audio(
    src="https://example.com/generated-melody.wav",
    contentType="audio/wav",
    label="Piano Melody",
    description="C major arpeggio",
)

return create_ui_response([audio])
```

## Frontend: RenderAudio

- `<audio>` element with `<source>` child
- Respects `autoplay`, `loop`, `showControls` booleans
- Shows `label` above and `description` below
- Graceful fallback when `src` is empty
- Browser security: autoplay is gated by browser policy (user gesture required
  on first interaction) — this is expected and acceptable

### Browser Audio Security Note

Modern browsers block autoplay without a prior user gesture. The first audio
component will require the user to click play. Subsequent autoplay works once
the user has interacted with the page. This is a browser-level restriction,
not a framework limitation. The `autoplay` flag serves as a hint — agents
should design their UX accordingly.

## Test Plan

- [x] Primitive serialization (to_json)
- [ ] Audio primitive rendered in DynamicRenderer
- [ ] Empty src shows fallback message
- [ ] Controls shown/hidden by showControls prop
- [ ] Label and description rendered when present

## Constitution Compliance

- ✅ No new third-party libraries (native `<audio>` element)
- ✅ Primitive extends existing `Component` base class
- ✅ Rendered through existing `DynamicRenderer` pattern
- ✅ No database changes required
- ✅ Agents use existing `create_ui_response` helper