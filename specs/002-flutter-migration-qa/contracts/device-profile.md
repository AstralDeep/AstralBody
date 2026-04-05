# Contract: Device Profile Registration

**Version**: 1.0 | **Date**: 2026-04-03

## Overview

When the Flutter client connects via WebSocket, it sends a device profile as part of the `register_ui` message. The backend ROTE (Response Output Translation Engine) uses this profile to adapt SDUI component trees for the device's capabilities and constraints.

---

## Device Profile Schema

```json
{
  "device_type": "mobile | tablet | tv | watch | browser",
  "screen_width": 1170,
  "screen_height": 2532,
  "viewport_width": 390,
  "viewport_height": 844,
  "pixel_ratio": 3.0,
  "has_touch": true,
  "has_geolocation": true,
  "has_microphone": true,
  "has_camera": true,
  "has_file_system": true,
  "connection_type": "wifi",
  "user_agent": "AstralBody-Flutter/1.0"
}
```

---

## Device Type Detection Rules

### Flutter Client-Side Detection

| Condition | Device Type |
|-----------|-------------|
| `viewportWidth ≤ 480` AND (iOS \| Android) | `mobile` |
| `481 ≤ viewportWidth ≤ 1024` AND (iOS \| Android) | `tablet` |
| `viewportWidth > 1024` AND (iOS \| Android) | `tv` |
| watchOS platform (future) | `watch` |

### Backend ROTE Detection (fallback)

| Condition | Device Type |
|-----------|-------------|
| `viewport_width < 200` | `watch` |
| `200 ≤ viewport_width < 480` | `mobile` |
| `480 ≤ viewport_width < 1024` | `tablet` |
| `viewport_width ≥ 1024` | `browser` |

---

## Capability Matrix

| Capability | Mobile | Tablet | TV | Watch |
|-----------|--------|--------|-----|-------|
| `has_touch` | true | true | **false** | true |
| `has_geolocation` | true | true | **false** | true |
| `has_microphone` | true | true | **false** | **false** |
| `has_camera` | true | true | **false** | **false** |
| `has_file_system` | true | true | **false** | **false** |

---

## ROTE Adaptation Rules

The backend applies these constraints based on `device_type`:

### Component Support by Device

| Component Type | Mobile | Tablet | TV | Watch |
|----------------|--------|--------|-----|-------|
| container | ✓ | ✓ | ✓ | ✓ |
| text | ✓ | ✓ | ✓ | ✓ (120 char max) |
| button | ✓ | ✓ | ✓ | ✓ |
| input | ✓ | ✓ | ✓ | ✗ |
| card | ✓ | ✓ | ✓ | ✓ |
| table | ✓ (20 rows, 4 cols) | ✓ (6 cols) | ✓ | ✗ → list |
| list | ✓ | ✓ | ✓ | ✓ (3 rows, 2 cols) |
| alert | ✓ | ✓ | ✓ | ✓ |
| progress | ✓ | ✓ | ✓ | ✓ |
| metric | ✓ | ✓ | ✓ | ✓ |
| code | ✗ (hidden) | ✓ | ✓ | ✗ |
| image | ✓ | ✓ | ✓ | ✗ |
| grid | ✓ (1 col) | ✓ (3 cols) | ✓ (4 cols) | ✓ (1 col) |
| tabs | ✓ | ✓ | ✓ | ✗ |
| divider | ✓ | ✓ | ✓ | ✓ |
| collapsible | ✓ | ✓ | ✓ | ✗ |
| bar_chart | ✓ | ✓ | ✓ | ✗ → metric |
| line_chart | ✓ | ✓ | ✓ | ✗ → metric |
| pie_chart | ✓ | ✓ | ✓ | ✗ → metric |
| plotly_chart | ✓ | ✓ | ✓ | ✗ → metric |
| color_picker | ✓ | ✓ | ✓ | ✗ |
| file_upload | ✓ | ✓ | ✗ | ✗ |
| file_download | ✓ | ✓ | ✗ | ✗ |

### Watch Degradation (Client-Side — WatchRenderer)

Since the backend ROTE may not fully handle all watch cases, the Flutter `WatchRenderer` also degrades:

| Unsupported Type | Degrades To |
|-----------------|-------------|
| `bar_chart`, `line_chart`, `pie_chart`, `plotly_chart` | `metric` (title + first value) |
| `table` | `list` (first column) |
| All others not in supported set | Silently skipped |

**Watch-Supported Set**: `text`, `metric`, `alert`, `card`, `button`, `list`, `progress`, `divider`, `container`

---

## Input Modality

| Device Type | Input Modality | UI Implications |
|-------------|---------------|-----------------|
| `mobile` | `touch` | Standard touch targets (48px min) |
| `tablet` | `touch` | Standard touch targets |
| `tv` | `dpad` | Focus-based navigation, large targets, focus indicators |
| `watch` | `crown` | Minimal interaction, scroll-based |

### TV Focus Requirements
- All interactive elements must be focusable
- Focus indicator: 3px amber (#FFD600) border
- D-pad arrow keys map to directional focus movement
- Select/Enter activates focused element
- Any destination reachable within 5 D-pad presses from home

### TV Theme Adjustments
- Text scale: 1.5x baseline
- Content padding: 32px
- Button padding: 48px horizontal, 24px vertical
- Visual density: comfortable (4.0)

---

## Test Scenarios

| Scenario | Expected Behavior |
|----------|-------------------|
| Phone registers as `mobile` | ROTE sends phone-optimized tree (1-col grid, no code blocks) |
| Tablet registers as `tablet` | ROTE sends tablet tree (3-col grid max, 6-col tables) |
| TV registers as `tv` | ROTE sends TV tree (4-col grid, no file I/O) |
| Watch viewport (< 200px) | ROTE sends minimal tree (text, metric, alert only) |
| Device rotated | Client re-sends device profile with new dimensions |
| Capability mismatch | Backend trusts reported capabilities for feature gating |
