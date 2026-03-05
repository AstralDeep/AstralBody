"""
Agent Constitution — single source of truth for generated agent specifications.

Auto-derives the primitives spec from shared/primitives.py dataclass fields
so it never drifts out of sync. Provides the LLM prompt section used by
both generate_tools_file() and refine_tools_file().
"""
import dataclasses
import os
import sys
from typing import Dict, Any, Set

# Ensure shared is importable
_backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from shared.primitives import (
    Text, Card, Table, List_, Alert, ProgressBar, MetricCard,
    CodeBlock, Image, Grids, Tabs, Collapsible, Divider,
    BarChart, LineChart, PieChart, PlotlyChart, Container,
    ColorPicker, FileUpload, FileDownload, Button, Input,
)

# ─── Auto-derived component registry ────────────────────────────────────

COMPONENT_CLASSES = [
    Text, Card, Table, List_, Alert, ProgressBar, MetricCard,
    CodeBlock, Image, Grids, Tabs, Collapsible, Divider,
    BarChart, LineChart, PieChart, PlotlyChart, Container,
    ColorPicker, FileUpload, FileDownload, Button, Input,
]


def _build_primitives_spec() -> Dict[str, Dict[str, Any]]:
    """Inspect dataclass fields to build the canonical component spec."""
    spec = {}
    for cls in COMPONENT_CLASSES:
        fields = dataclasses.fields(cls)
        field_info = {}
        type_value = None
        for f in fields:
            has_default = f.default is not dataclasses.MISSING
            has_factory = f.default_factory is not dataclasses.MISSING
            default = f.default if has_default else (
                "[]" if has_factory else None
            )
            field_info[f.name] = {
                "type": str(f.type),
                "default": default,
            }
            if f.name == "type" and has_default:
                type_value = f.default

        if type_value:
            spec[type_value] = {
                "class_name": cls.__name__,
                "fields": field_info,
            }
    return spec


PRIMITIVES_SPEC: Dict[str, Dict[str, Any]] = _build_primitives_spec()

VALID_COMPONENT_TYPES: Set[str] = set(PRIMITIVES_SPEC.keys())

# ─── Required imports block ─────────────────────────────────────────────

REQUIRED_IMPORTS_BLOCK = """import os
import sys
from typing import Dict, Any, List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from shared.primitives import (
    Text, Card, Table, Container, MetricCard, ProgressBar,
    Alert, Grid, BarChart, LineChart, PieChart, PlotlyChart, List_,
    Collapsible, Divider, CodeBlock, Image, Tabs,
    FileDownload, FileUpload, Button, Input, ColorPicker,
    create_ui_response
)"""

# ─── Working example ────────────────────────────────────────────────────

WORKING_EXAMPLE = '''def get_stock_summary(ticker: str, **kwargs) -> Dict[str, Any]:
    """Get a summary for a stock ticker with UI visualization."""
    try:
        # ... fetch data from API ...
        price = 150.25
        change = 2.50
        change_pct = 1.69

        components = [
            Card(
                title=f"Stock Summary: {ticker.upper()}",
                content=[
                    Grid(
                        columns=3,
                        children=[
                            MetricCard(title="Price", value=f"${price:.2f}"),
                            MetricCard(title="Change", value=f"${change:+.2f}", subtitle=f"{change_pct:+.2f}%"),
                            MetricCard(title="Status", value="Active"),
                        ]
                    ),
                    Table(
                        headers=["Metric", "Value"],
                        rows=[
                            ["Open", "$148.00"],
                            ["High", "$151.20"],
                            ["Low", "$147.50"],
                            ["Volume", "12.3M"],
                        ]
                    ),
                    Text(content="Data provided by example API.", variant="caption"),
                ]
            ),
        ]

        return {
            "_ui_components": [c.to_json() for c in components],
            "_data": {
                "ticker": ticker,
                "price": price,
                "change": change,
                "change_percent": change_pct,
            }
        }
    except Exception as e:
        return create_ui_response([
            Alert(message=f"Failed to fetch data for {ticker}: {str(e)}", variant="error")
        ])'''

# ─── Component reference (human-readable) ───────────────────────────────

def _build_component_reference() -> str:
    """Build a concise reference of all components with their fields."""
    lines = []
    for type_val, info in sorted(PRIMITIVES_SPEC.items()):
        cls_name = info["class_name"]
        fields = info["fields"]
        # Skip the 'type' field and common base fields
        relevant = {k: v for k, v in fields.items()
                    if k not in ("type", "id", "style")}
        params = []
        for fname, finfo in relevant.items():
            default = finfo["default"]
            if default is None:
                params.append(f"{fname}")
            else:
                params.append(f"{fname}={default!r}")
        lines.append(f"  - {cls_name}({', '.join(params)})  # type=\"{type_val}\"")
    return "\n".join(lines)


COMPONENT_REFERENCE = _build_component_reference()

# ─── LLM prompt section generator ───────────────────────────────────────

def generate_llm_prompt_section() -> str:
    """Generate the complete UI component specification for LLM prompts.

    Used by both generate_tools_file() and refine_tools_file() to ensure
    the LLM always has correct, up-to-date component information.
    """
    return f"""## UI COMPONENT SYSTEM — YOU MUST FOLLOW THIS EXACTLY

### Required Imports
Your file MUST start with these imports (after any package imports):
```python
{REQUIRED_IMPORTS_BLOCK}
```

### Available UI Components
These are the ONLY components you can use. Note the exact class names and field names:
{COMPONENT_REFERENCE}

### CRITICAL RULES
1. **Use the primitive classes**, NOT raw dicts. Create component objects and call `.to_json()`.
2. **Card uses `content`** (a list of child components), NOT `children`.
3. **Grid uses `children`** (a list of child components).
4. **Types are lowercase** in the JSON output (handled by `.to_json()` automatically).
5. **Every tool MUST return** a dict with BOTH keys:
   - `"_ui_components"`: `[c.to_json() for c in components]` — a list of serialized component dicts
   - `"_data"`: a dict of raw data for the LLM to reference in its response
6. **Error handling**: Wrap tool body in try/except and return `create_ui_response([Alert(message=str(e), variant="error")])` on failure.
7. **Never return an empty `_ui_components` list** — always include at least one component (even if just a Text or Alert).
8. **MetricCard** is the class name, but its type is `"metric"`. Use `MetricCard(title="...", value="...")`.
9. **List_** (with underscore) is the list component. Use `List_(items=["item1", "item2"])`.

### Complete Working Example
```python
{WORKING_EXAMPLE}
```

### TOOL_REGISTRY Format
Each tool must be registered in TOOL_REGISTRY:
```python
TOOL_REGISTRY = {{
    "tool_name": {{
        "function": tool_function,
        "description": "What this tool does",
        "input_schema": {{
            "type": "object",
            "properties": {{
                "param_name": {{"type": "string", "description": "..."}}
            }},
            "required": ["param_name"]
        }},
        "scope": "tools:read"
    }}
}}
```"""
