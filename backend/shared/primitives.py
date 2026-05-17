"""
UI Primitives — server-side UI component library.

Each component is a dataclass that serializes to JSON for frontend rendering.
The frontend uses @json-render/react to map these to React components.
"""
import json
from dataclasses import dataclass, asdict, field
from typing import List, Optional, Dict, Any, Union


@dataclass
class Component:
    type: str
    id: Optional[str] = None
    style: Dict[str, str] = field(default_factory=dict)
    tooltip: Optional[str] = None

    def to_json(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_json(data: Dict[str, Any]) -> 'Component':
        comp_type = data.get('type', '')
        type_map = {
            'container': Container, 'text': Text, 'button': Button,
            'card': Card, 'table': Table, 'list': List_,
            'alert': Alert, 'progress': ProgressBar, 'metric': MetricCard,
            'code': CodeBlock, 'image': Image, 'grid': Grids,
            'tabs': Tabs, 'divider': Divider, 'input': Input,
            'bar_chart': BarChart, 'line_chart': LineChart, 'pie_chart': PieChart,
            'plotly_chart': PlotlyChart, 'collapsible': Collapsible,
            'color_picker': ColorPicker, 'theme_apply': ThemeApply,
            'file_upload': FileUpload, 'file_download': FileDownload,
            'audio': Audio,
        }
        cls = type_map.get(comp_type, Component)
        if cls == Component:
            return Component(**{k: v for k, v in data.items()})
        try:
            return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        except Exception:
            return Component(**{k: v for k, v in data.items() if k in Component.__dataclass_fields__})


@dataclass
class Container(Component):
    type: str = "container"
    children: List[Component] = field(default_factory=list)

    def to_json(self) -> Dict[str, Any]:
        d = asdict(self)
        d['children'] = [
            c.to_json() if hasattr(c, 'to_json') else c
            for c in self.children
        ]
        return d


@dataclass
class Text(Component):
    type: str = "text"
    content: str = ""
    variant: str = "body"  # h1, h2, h3, body, caption


@dataclass
class Button(Component):
    type: str = "button"
    label: str = ""
    action: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    variant: str = "primary"


@dataclass
class Input(Component):
    type: str = "input"
    placeholder: str = ""
    name: str = ""
    value: str = ""


@dataclass
class ParamPicker(Component):
    """Interactive parameter form rendered as a card with form fields.

    Each entry in ``fields`` is a dict of the shape::

        {"name": "models_to_train",
         "label": "Models to train",
         "kind": "boolean"|"number"|"text"|"checklist"|"select",
         "default": <starting value>,
         "options": [...]  # for checklist/select
         "help": "...",
         "step": 1  # optional, for number kind
        }

    On submit the frontend interpolates ``submit_message_template`` with the
    user's field values and sends the result as a chat message. Two
    placeholder forms are supported:

    * ``{field_name}`` — replaced with that field's value (JSON-encoded for
      lists/dicts/bools).
    * ``{__values_json__}`` — replaced with ``JSON.stringify`` of the entire
      form state.
    """
    type: str = "param_picker"
    title: str = ""
    description: str = ""
    fields: List[Dict[str, Any]] = field(default_factory=list)
    submit_label: str = "Submit"
    submit_message_template: str = ""


@dataclass
class Card(Component):
    type: str = "card"
    title: str = ""
    content: List[Component] = field(default_factory=list)
    variant: str = "default"

    def to_json(self) -> Dict[str, Any]:
        d = asdict(self)
        d['content'] = [
            c.to_json() if hasattr(c, 'to_json') else c
            for c in self.content
        ]
        return d


@dataclass
class Table(Component):
    type: str = "table"
    headers: List[str] = field(default_factory=list)
    rows: List[List[Any]] = field(default_factory=list)
    variant: str = "default"
    # Pagination (optional — when present, frontend renders controls)
    total_rows: Optional[int] = None
    page_size: Optional[int] = None
    page_offset: Optional[int] = None
    page_sizes: List[int] = field(default_factory=list)
    # Tool re-invocation context (enables frontend to request different pages)
    source_tool: Optional[str] = None
    source_agent: Optional[str] = None
    source_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class List_(Component):
    type: str = "list"
    items: List[Union[str, Dict[str, Any]]] = field(default_factory=list)
    ordered: bool = False
    variant: str = "default"


@dataclass
class Alert(Component):
    type: str = "alert"
    message: str = ""
    variant: str = "info"  # info, success, warning, error
    title: Optional[str] = None


@dataclass
class ProgressBar(Component):
    type: str = "progress"
    value: float = 0.0
    label: Optional[str] = None
    variant: str = "default"
    show_percentage: bool = True


@dataclass
class MetricCard(Component):
    type: str = "metric"
    title: str = ""
    value: str = ""
    subtitle: Optional[str] = None
    icon: Optional[str] = None
    variant: str = "default"
    progress: Optional[float] = None


@dataclass
class CodeBlock(Component):
    type: str = "code"
    code: str = ""
    language: str = "text"
    show_line_numbers: bool = False


@dataclass
class Image(Component):
    type: str = "image"
    url: str = ""
    alt: Optional[str] = None
    width: Optional[str] = None
    height: Optional[str] = None


@dataclass
class Grids(Component):
    type: str = "grid"
    columns: int = 2
    children: List[Component] = field(default_factory=list)
    gap: int = 20

    def to_json(self) -> Dict[str, Any]:
        d = asdict(self)
        d['children'] = [
            c.to_json() if hasattr(c, 'to_json') else c
            for c in self.children
        ]
        return d

Grid = Grids


@dataclass
class TabItem:
    label: str
    content: List[Component] = field(default_factory=list)
    value: Optional[str] = None

    def to_json(self) -> Dict[str, Any]:
        d = asdict(self)
        d['content'] = [
            c.to_json() if hasattr(c, 'to_json') else c
            for c in self.content
        ]
        return d


@dataclass
class Tabs(Component):
    type: str = "tabs"
    tabs: List[TabItem] = field(default_factory=list)
    variant: str = "default"

    def to_json(self) -> Dict[str, Any]:
        d = asdict(self)
        d['tabs'] = [t.to_json() if hasattr(t, 'to_json') else t for t in self.tabs]
        return d


@dataclass
class Collapsible(Component):
    type: str = "collapsible"
    title: str = ""
    content: List[Component] = field(default_factory=list)
    default_open: bool = False

    def to_json(self) -> Dict[str, Any]:
        d = asdict(self)
        d['content'] = [
            c.to_json() if hasattr(c, 'to_json') else c
            for c in self.content
        ]
        return d


@dataclass
class Divider(Component):
    type: str = "divider"
    variant: str = "solid"


# --- Chart Components ---

@dataclass
class ChartDataset:
    label: str
    data: List[float] = field(default_factory=list)
    color: Optional[str] = None

@dataclass
class BarChart(Component):
    type: str = "bar_chart"
    title: str = ""
    labels: List[str] = field(default_factory=list)
    datasets: List[Dict[str, Any]] = field(default_factory=list)

@dataclass
class LineChart(Component):
    type: str = "line_chart"
    title: str = ""
    labels: List[str] = field(default_factory=list)
    datasets: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class PieChart(Component):
    type: str = "pie_chart"
    title: str = ""
    labels: List[str] = field(default_factory=list)
    data: List[float] = field(default_factory=list)
    colors: List[str] = field(default_factory=list)

@dataclass
class PlotlyChart(Component):
    type: str = "plotly_chart"
    title: str = ""
    data: List[Dict[str, Any]] = field(default_factory=list)
    layout: Dict[str, Any] = field(default_factory=dict)
    config: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ColorPicker(Component):
    type: str = "color_picker"
    label: str = ""
    color_key: str = ""
    value: str = "#000000"


@dataclass
class ThemeApply(Component):
    type: str = "theme_apply"
    preset: Optional[str] = None
    colors: Optional[Dict[str, str]] = None
    color_key: Optional[str] = None
    color_value: Optional[str] = None
    message: str = ""


@dataclass
class FileUpload(Component):
    type: str = "file_upload"
    label: str = "Upload File"
    accept: str = "*/*"
    action: str = ""

@dataclass
class FileDownload(Component):
    type: str = "file_download"
    label: str = "Download File"
    url: str = ""
    filename: Optional[str] = None


@dataclass
class Audio(Component):
    """Audio player primitive for sound-enabled agents (US-21).

    Supports inline base64 data, URLs, generated speech, and MIDI.
    Agents (e.g. piano agent, TTS agent) emit this primitive to play
    sound in the SDUI canvas.
    """
    type: str = "audio"
    src: str = ""
    contentType: Optional[str] = None  # audio/mpeg, audio/wav, audio/midi, etc.
    autoplay: bool = False
    loop: bool = False
    label: Optional[str] = None         # optional title above the player
    showControls: bool = True
    description: Optional[str] = None   # optional caption/description


def create_ui_response(components: List[Component]) -> Dict[str, Any]:
    """Helper to create an MCP response with UI components."""
    serialized = []
    for c in components:
        if hasattr(c, 'to_json'):
            serialized.append(c.to_json())
        else:
            serialized.append(asdict(c))
    return {
        "_ui_components": serialized,
        "_data": None
    }
