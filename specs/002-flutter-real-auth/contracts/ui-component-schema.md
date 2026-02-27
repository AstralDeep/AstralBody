# UI Component Schema Contract

**Version**: 1.0.0
**Source**: Backend orchestrator component specification

## Overview

UI components are JSON objects that describe renderable UI elements. The Flutter frontend must render these components identically to how the React frontend renders them.

## Base Schema

All components share this base structure:

```json
{
  "type": "component_type",
  "id": "unique-id",
  "properties": {
    // Component-specific properties
  },
  "style": {
    // CSS-like styling properties
  },
  "metadata": {
    // Additional metadata
  }
}
```

## Component Types

### `text`
Display text content.

```json
{
  "type": "text",
  "properties": {
    "text": "Hello, world!",
    "variant": "body1",
    "align": "left"
  },
  "style": {
    "color": "#000000",
    "fontSize": 14,
    "fontWeight": 400,
    "lineHeight": 1.5
  }
}
```

**Variant values**: `h1`, `h2`, `h3`, `h4`, `h5`, `h6`, `subtitle1`, `subtitle2`, `body1`, `body2`, `caption`, `overline`

### `card`
Container with optional title and content.

```json
{
  "type": "card",
  "properties": {
    "title": "Dashboard",
    "subtitle": "Overview",
    "children": [
      { "type": "text", "properties": { "text": "Content" } }
    ]
  },
  "style": {
    "padding": "16px",
    "borderRadius": "8px",
    "backgroundColor": "#ffffff",
    "boxShadow": "0 2px 4px rgba(0,0,0,0.1)"
  }
}
```

### `table`
Data table with rows and columns.

```json
{
  "type": "table",
  "properties": {
    "columns": ["Name", "Age", "City"],
    "rows": [
      ["John", "30", "New York"],
      ["Jane", "25", "London"]
    ],
    "paginated": true,
    "pageSize": 10
  },
  "style": {
    "border": "1px solid #e0e0e0",
    "headerBackground": "#f5f5f5"
  }
}
```

### `metric`
Key metric display.

```json
{
  "type": "metric",
  "properties": {
    "value": 42,
    "label": "Active Users",
    "trend": "up",
    "change": 12.5
  },
  "style": {
    "valueColor": "#3b82f6",
    "valueSize": 24
  }
}
```

### `alert`
Alert/notification box.

```json
{
  "type": "alert",
  "properties": {
    "severity": "info",
    "title": "Note",
    "message": "This is an informational message."
  },
  "style": {
    "backgroundColor": "#e3f2fd",
    "borderColor": "#2196f3"
  }
}
```

**Severity values**: `info`, `success`, `warning`, `error`

### `progress`
Progress indicator.

```json
{
  "type": "progress",
  "properties": {
    "value": 65,
    "max": 100,
    "label": "Processing...",
    "variant": "linear"
  },
  "style": {
    "color": "#3b82f6",
    "height": "4px"
  }
}
```

**Variant values**: `linear`, `circular`, `indeterminate`

### `grid`
Grid layout container.

```json
{
  "type": "grid",
  "properties": {
    "columns": 3,
    "spacing": 16,
    "children": [
      { "type": "card", "properties": { "title": "Item 1" } },
      { "type": "card", "properties": { "title": "Item 2" } }
    ]
  }
}
```

### `list`
List of items.

```json
{
  "type": "list",
  "properties": {
    "items": [
      {
        "primary": "Item 1",
        "secondary": "Description 1",
        "icon": "check"
      },
      {
        "primary": "Item 2",
        "secondary": "Description 2"
      }
    ]
  }
}
```

### `code`
Code block with syntax highlighting.

```json
{
  "type": "code",
  "properties": {
    "code": "print('Hello, world!')",
    "language": "python",
    "showLineNumbers": true
  }
}
```

### `bar_chart`
Bar chart.

```json
{
  "type": "bar_chart",
  "properties": {
    "data": [
      { "label": "Jan", "value": 30 },
      { "label": "Feb", "value": 45 }
    ],
    "xAxisLabel": "Month",
    "yAxisLabel": "Sales"
  }
}
```

### `line_chart`
Line chart.

```json
{
  "type": "line_chart",
  "properties": {
    "series": [
      {
        "name": "Series 1",
        "data": [10, 20, 30, 40]
      }
    ],
    "xAxis": ["Q1", "Q2", "Q3", "Q4"]
  }
}
```

### `pie_chart`
Pie chart.

```json
{
  "type": "pie_chart",
  "properties": {
    "data": [
      { "label": "Category A", "value": 40 },
      { "label": "Category B", "value": 60 }
    ]
  }
}
```

### `plotly_chart`
Plotly.js chart (rendered in WebView).

```json
{
  "type": "plotly_chart",
  "properties": {
    "spec": {
      "data": [{
        "type": "scatter",
        "x": [1, 2, 3],
        "y": [2, 5, 3]
      }],
      "layout": {
        "title": "Plotly Chart"
      }
    },
    "config": {
      "responsive": true
    }
  }
}
```

### `divider`
Horizontal or vertical divider.

```json
{
  "type": "divider",
  "properties": {
    "orientation": "horizontal",
    "variant": "fullWidth"
  },
  "style": {
    "color": "#e0e0e0",
    "thickness": "1px"
  }
}
```

### `button`
Interactive button.

```json
{
  "type": "button",
  "properties": {
    "text": "Click me",
    "variant": "contained",
    "color": "primary",
    "onClick": {
      "action": "send_message",
      "payload": { "content": "Button clicked" }
    }
  }
}
```

**Variant values**: `text`, `outlined`, `contained`
**Color values**: `primary`, `secondary`, `success`, `error`, `warning`, `info`

### `collapsible`
Expandable/collapsible section.

```json
{
  "type": "collapsible",
  "properties": {
    "title": "Details",
    "expanded": false,
    "children": [
      { "type": "text", "properties": { "text": "Hidden content" } }
    ]
  }
}
```

### `file_upload`
File upload widget.

```json
{
  "type": "file_upload",
  "properties": {
    "accept": ".csv,.txt,.json",
    "multiple": false,
    "maxSize": 10485760
  }
}
```

### `file_download`
File download link.

```json
{
  "type": "file_download",
  "properties": {
    "filename": "report.pdf",
    "url": "/download/file-uuid",
    "size": 204800
  }
}
```

## Style Properties

Style properties use CSS-like syntax but are limited to supported properties:

### Layout
- `margin`: "16px" or "8px 16px"
- `padding`: "16px" or "8px 16px"
- `width`: "100%" or "200px"
- `height`: "auto" or "100px"
- `display`: "flex", "block", "inline"
- `flexDirection`: "row", "column"
- `justifyContent`: "flex-start", "center", "flex-end", "space-between"
- `alignItems`: "flex-start", "center", "flex-end", "stretch"

### Appearance
- `color`: "#3b82f6" or "rgb(59, 130, 246)"
- `backgroundColor`: "#ffffff"
- `border`: "1px solid #e0e0e0"
- `borderRadius`: "8px"
- `boxShadow`: "0 2px 4px rgba(0,0,0,0.1)"
- `opacity`: 0.8

### Typography
- `fontSize`: 14 (pixels)
- `fontWeight`: 400 (normal) or 700 (bold)
- `fontFamily`: "Inter, sans-serif"
- `lineHeight`: 1.5
- `textAlign`: "left", "center", "right", "justify"

## Event Handling

Components can include event handlers:

```json
{
  "onClick": {
    "action": "send_message",
    "payload": { "content": "Clicked" }
  },
  "onChange": {
    "action": "update_value",
    "payload": { "field": "name", "value": "new value" }
  }
}
```

**Supported actions**:
- `send_message`: Send chat message
- `update_value`: Update form value
- `navigate`: Change route
- `open_url`: Open external URL
- `download_file`: Trigger file download
- `save_component`: Save component to library

## Compatibility with React

This schema must produce identical rendering in Flutter as in React. Verify by:
1. Comparing rendered output for each component type
2. Testing with same backend-generated components
3. Ensuring style properties map correctly (CSS → Flutter)

## Implementation Notes for Flutter

### Mapping CSS to Flutter
- `margin: "16px"` → `EdgeInsets.all(16)`
- `padding: "8px 16px"` → `EdgeInsets.symmetric(horizontal: 16, vertical: 8)`
- `borderRadius: "8px"` → `BorderRadius.circular(8)`
- `boxShadow: "0 2px 4px rgba(0,0,0,0.1)"` → `BoxShadow(color: Color(0x1A000000), offset: Offset(0, 2), blurRadius: 4)`

### Component Rendering
Create a `DynamicRenderer` widget that:
1. Parses component JSON
2. Maps `type` to corresponding Flutter widget
3. Applies style properties
4. Attaches event handlers

### Performance
- Cache rendered components
- Use `ListView.builder` for large lists
- Lazy load images and charts

## Testing

### Contract Tests
1. Parse each component type successfully
2. Apply all style properties correctly
3. Handle events appropriately

### Visual Tests
1. Screenshot comparison with React rendering
2. Responsive design across screen sizes
3. Accessibility testing

---

*This contract defines the UI component schema that must be rendered identically in Flutter and React. Any deviation will break visual parity.*