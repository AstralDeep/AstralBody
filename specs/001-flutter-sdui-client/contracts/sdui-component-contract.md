# SDUI Component Contract

**Version**: 1.0.0 | **Source of Truth**: `backend/shared/primitives.py`

## Overview

The backend produces SDUI component trees as JSON. The Flutter client renders them. This contract defines the JSON schema for every component type the client must support.

## Base Component Schema

Every component includes these fields:

```json
{
  "type": "string",        // Required. Component type identifier (snake_case).
  "id": "string|null",     // Optional. Unique identifier for targeting updates.
  "style": {}              // Optional. CSS-like style overrides (key-value string map).
}
```

## Component Types

### Layout Components

#### `container`
Vertical stack of child components.
```json
{
  "type": "container",
  "children": [/* Component[] */]
}
```

#### `grid`
Multi-column grid layout.
```json
{
  "type": "grid",
  "columns": 2,           // int, number of columns
  "gap": 20,              // int, gap between items in pixels
  "children": [/* Component[] */]
}
```
**Device adaptation**: ROTE caps `columns` to `max_grid_columns`. When capped to 1, collapses to `container`.

#### `tabs`
Tabbed container with labeled panels.
```json
{
  "type": "tabs",
  "variant": "default",
  "tabs": [
    {
      "label": "Tab Name",
      "value": "tab_id",         // optional
      "content": [/* Component[] */]
    }
  ]
}
```
**Watch/voice**: Falls back to first tab rendered as `card`.

#### `collapsible`
Expandable/collapsible section.
```json
{
  "type": "collapsible",
  "title": "Section Title",
  "default_open": false,
  "content": [/* Component[] */]
}
```

#### `divider`
Horizontal rule separator.
```json
{
  "type": "divider",
  "variant": "solid"      // "solid" (default)
}
```

### Text & Display Components

#### `text`
Static text with variant styling.
```json
{
  "type": "text",
  "content": "Hello world",
  "variant": "body"       // "h1", "h2", "h3", "body", "caption"
}
```
**Watch**: Truncated to 120 chars.

#### `code`
Code block with syntax highlighting.
```json
{
  "type": "code",
  "code": "print('hello')",
  "language": "python",
  "show_line_numbers": false
}
```
**Mobile**: Removed by ROTE. **Watch/voice**: Removed.

#### `image`
Remote or data URL image.
```json
{
  "type": "image",
  "url": "https://...",
  "alt": "Description",
  "width": "200px",       // optional
  "height": "150px"       // optional
}
```

### Data Display Components

#### `card`
Titled card container with child components.
```json
{
  "type": "card",
  "title": "Card Title",
  "variant": "default",
  "content": [/* Component[] */]
}
```

#### `table`
Data table with optional pagination.
```json
{
  "type": "table",
  "headers": ["Col1", "Col2", "Col3"],
  "rows": [
    ["val1", "val2", "val3"],
    ["val4", "val5", "val6"]
  ],
  "variant": "default",
  "total_rows": 100,          // optional, enables pagination
  "page_size": 10,            // optional
  "page_offset": 0,           // optional
  "page_sizes": [10, 25, 50], // optional
  "source_tool": "tool_name", // optional, for re-invocation
  "source_agent": "agent_id", // optional
  "source_params": {}         // optional, original tool params
}
```
**Watch**: Degraded to `list`. **Mobile**: Capped to 20 rows, 4 columns.

#### `list`
Ordered or unordered list.
```json
{
  "type": "list",
  "items": ["item1", "item2", {"nested": "object"}],
  "ordered": false,
  "variant": "default"
}
```

#### `alert`
Status message with severity.
```json
{
  "type": "alert",
  "message": "Operation completed",
  "variant": "info",      // "info", "success", "warning", "error"
  "title": "Status"       // optional
}
```

#### `progress`
Progress bar indicator.
```json
{
  "type": "progress",
  "value": 0.75,           // 0.0 to 1.0
  "label": "Loading...",   // optional
  "variant": "default",
  "show_percentage": true
}
```

#### `metric`
Key-value metric display.
```json
{
  "type": "metric",
  "title": "Revenue",
  "value": "$1.2M",
  "subtitle": "Q4 2025",  // optional
  "icon": "trending_up",  // optional Material icon name
  "variant": "default",
  "progress": 0.8          // optional, 0.0 to 1.0
}
```
**Watch**: Fully supported — primary glanceable component.

### Input Components

#### `button`
Clickable action trigger.
```json
{
  "type": "button",
  "label": "Submit",
  "action": "submit_form",
  "payload": {},           // sent to backend on click
  "variant": "primary"    // "primary", "secondary"
}
```
**TV**: Only primary buttons shown. **Voice**: Removed. **Watch**: Only primary.

#### `input`
Text input field.
```json
{
  "type": "input",
  "placeholder": "Enter text...",
  "name": "field_name",
  "value": ""              // pre-filled value
}
```

#### `color_picker`
Color selection input.
```json
{
  "type": "color_picker",
  "label": "Pick a color",
  "color_key": "bg_color",
  "value": "#000000"
}
```

#### `file_upload`
File selection and upload trigger.
```json
{
  "type": "file_upload",
  "label": "Upload File",
  "accept": "*/*",
  "action": "upload_handler"
}
```
**TV/watch/voice**: Removed by ROTE.

#### `file_download`
File download link.
```json
{
  "type": "file_download",
  "label": "Download Report",
  "url": "/api/files/report.pdf",
  "filename": "report.pdf" // optional
}
```
**TV/watch/voice**: Removed by ROTE.

### Chart Components

#### `bar_chart`
```json
{
  "type": "bar_chart",
  "title": "Monthly Sales",
  "labels": ["Jan", "Feb", "Mar"],
  "datasets": [
    {
      "label": "2025",
      "data": [100, 200, 150],
      "color": "#4285f4"
    }
  ]
}
```
**Watch/voice**: Degraded to `metric` with representative value.

#### `line_chart`
```json
{
  "type": "line_chart",
  "title": "Growth Trend",
  "labels": ["Q1", "Q2", "Q3", "Q4"],
  "datasets": [
    {
      "label": "Revenue",
      "data": [10, 25, 30, 45],
      "color": "#34a853"
    }
  ]
}
```

#### `pie_chart`
```json
{
  "type": "pie_chart",
  "title": "Market Share",
  "labels": ["A", "B", "C"],
  "data": [45, 30, 25],
  "colors": ["#4285f4", "#34a853", "#ea4335"]
}
```

#### `plotly_chart`
Full Plotly.js figure (rendered in WebView on capable devices).
```json
{
  "type": "plotly_chart",
  "title": "Complex Viz",
  "data": [/* Plotly trace objects */],
  "layout": {/* Plotly layout config */},
  "config": {/* Plotly config */}
}
```
**Watch/TV**: Degraded to `metric`. **Mobile/tablet**: Rendered in WebView.

## Unknown Component Handling

When the client receives a component with an unrecognized `type`:
1. Render a visually distinct placeholder (bordered box with type name)
2. Log a diagnostic warning with the unknown type
3. Do NOT crash or skip the component silently

## Device-Specific Component Support

| Component | Phone | Tablet | TV | Watch |
|-----------|-------|--------|-----|-------|
| container | Yes | Yes | Yes | Yes |
| text | Yes | Yes | Yes | Yes (120 char) |
| button | Yes | Yes | Primary only | Primary only |
| input | Yes | Yes | Yes | No |
| card | Yes | Yes | Yes | Yes |
| table | Yes (20r/4c) | Yes (6c) | Yes | No → list |
| list | Yes | Yes | Yes | Yes |
| alert | Yes | Yes | Yes | Yes |
| progress | Yes | Yes | Yes | Yes |
| metric | Yes | Yes | Yes | Yes |
| code | No | Yes | Yes | No |
| image | Yes | Yes | Yes | No |
| grid | 1 col | 3 col | 4 col | 1 col |
| tabs | Yes | Yes | Yes | No → card |
| divider | Yes | Yes | Yes | Yes |
| collapsible | Yes | Yes | Yes | No → card |
| Charts | Yes | Yes | Yes | No → metric |
| file_upload | Yes | Yes | No | No |
| file_download | Yes | Yes | No | No |
| color_picker | Yes | Yes | Yes | No |
| plotly_chart | WebView | WebView | No → metric | No → metric |
