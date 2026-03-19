/**
 * A2UIRenderer — Renders A2UI surfaces (flat adjacency-list components)
 * by converting them to the nested format DynamicRenderer expects.
 *
 * This bridges A2UI's flat component model with the existing rendering
 * pipeline, reusing all DynamicRenderer component functions.
 */
import { useMemo } from "react";
import DynamicRenderer from "./DynamicRenderer";
import type { A2UISurface } from "../hooks/useWebSocket";

// ---------------------------------------------------------------------------
// A2UI type → legacy type mapping (reverse of backend LEGACY_TYPE_MAP)
// ---------------------------------------------------------------------------

const A2UI_TO_LEGACY_TYPE: Record<string, string> = {
    Column: "container",
    Row: "grid",
    Card: "card",
    Text: "text",
    Button: "button",
    TextField: "input",
    Image: "image",
    Divider: "divider",
    Tabs: "tabs",
    List: "list",
    Modal: "modal",
    Icon: "text",
    CheckBox: "checkbox",
    ChoicePicker: "choice_picker",
    Slider: "slider",
    DateTimeInput: "datetime_input",
    Video: "video",
    AudioPlayer: "audio_player",
    "x-astral-table": "table",
    "x-astral-metric-card": "metric",
    "x-astral-code": "code",
    "x-astral-alert": "alert",
    "x-astral-progress-bar": "progress",
    "x-astral-bar-chart": "bar_chart",
    "x-astral-line-chart": "line_chart",
    "x-astral-pie-chart": "pie_chart",
    "x-astral-plotly-chart": "plotly_chart",
    "x-astral-color-picker": "color_picker",
    "x-astral-file-upload": "file_upload",
    "x-astral-file-download": "file_download",
};

// ---------------------------------------------------------------------------
// Property mapping: A2UI properties → legacy component props
// ---------------------------------------------------------------------------

function mapProperties(
    a2uiType: string,
    _legacyType: string,
    properties: Record<string, unknown>,
): Record<string, unknown> {
    const props: Record<string, unknown> = {};

    switch (a2uiType) {
        case "Text":
            props.content = properties.text ?? "";
            props.variant = properties.textStyle ?? "body";
            if (properties.markdown) props.variant = "markdown";
            break;

        case "Button": {
            props.label = properties.text ?? "";
            props.variant = properties.variant ?? "primary";
            const action = properties.action as Record<string, unknown> | undefined;
            if (action?.event) {
                const event = action.event as Record<string, unknown>;
                props.action = event.name ?? "";
                props.payload = event.context ?? {};
            }
            break;
        }

        case "TextField":
            props.placeholder = properties.placeholder ?? "";
            props.name = properties.name ?? "";
            props.value = properties.value ?? "";
            break;

        case "Card":
            props.title = properties.title ?? "";
            if (properties.isCollapsible) {
                // Render as collapsible instead
                return {
                    ...props,
                    title: properties.title ?? "",
                    default_open: properties.defaultOpen ?? false,
                    _renderAsCollapsible: true,
                };
            }
            break;

        case "Row":
            props.columns = properties.columns ?? 2;
            props.gap = properties.gap ?? 16;
            break;

        case "Column":
            break; // container needs no special props

        case "Image":
            props.url = properties.url ?? "";
            props.alt = properties.alt ?? "";
            if (properties.width) props.width = properties.width;
            if (properties.height) props.height = properties.height;
            break;

        case "Divider":
            props.variant = properties.variant ?? "solid";
            break;

        case "Tabs":
            // Will be handled specially during tree reconstruction
            props._tabsData = properties.tabs;
            break;

        case "List":
            props.items = properties.items ?? [];
            props.ordered = properties.ordered ?? false;
            break;

        // Custom extensions — pass properties through directly
        case "x-astral-table":
            props.headers = properties.headers ?? [];
            props.rows = properties.rows ?? [];
            if (properties.totalRows != null) props.total_rows = properties.totalRows;
            if (properties.pageSize != null) props.page_size = properties.pageSize;
            if (properties.pageOffset != null) props.page_offset = properties.pageOffset;
            if (properties.pageSizes) props.page_sizes = properties.pageSizes;
            if (properties.sourceTool) props.source_tool = properties.sourceTool;
            if (properties.sourceAgent) props.source_agent = properties.sourceAgent;
            if (properties.sourceParams) props.source_params = properties.sourceParams;
            break;

        case "x-astral-metric-card":
            props.title = properties.title ?? "";
            props.value = properties.value ?? "";
            if (properties.subtitle) props.subtitle = properties.subtitle;
            if (properties.icon) props.icon = properties.icon;
            if (properties.progress != null) props.progress = properties.progress;
            break;

        case "x-astral-code":
            props.code = properties.code ?? "";
            props.language = properties.language ?? "text";
            props.show_line_numbers = properties.showLineNumbers ?? false;
            break;

        case "x-astral-alert":
            props.message = properties.message ?? "";
            props.variant = properties.variant ?? "info";
            if (properties.title) props.title = properties.title;
            break;

        case "x-astral-progress-bar":
            props.value = properties.value ?? 0;
            if (properties.label) props.label = properties.label;
            props.show_percentage = properties.showPercentage ?? true;
            break;

        case "x-astral-bar-chart":
        case "x-astral-line-chart":
        case "x-astral-pie-chart":
            props.title = properties.title ?? "";
            props.labels = properties.labels ?? [];
            props.datasets = properties.datasets;
            props.data = properties.data;
            if (properties.colors) props.colors = properties.colors;
            break;

        case "x-astral-plotly-chart":
            props.title = properties.title ?? "";
            props.data = properties.data ?? [];
            if (properties.layout) props.layout = properties.layout;
            if (properties.config) props.config = properties.config;
            break;

        case "x-astral-color-picker":
            props.label = properties.label ?? "";
            props.color_key = properties.colorKey ?? "";
            props.value = properties.value ?? "#000000";
            break;

        case "x-astral-file-upload":
            props.label = properties.label ?? "Upload File";
            props.accept = properties.accept ?? "*/*";
            props.action = properties.action ?? "";
            break;

        case "x-astral-file-download":
            props.label = properties.label ?? "Download File";
            props.url = properties.url ?? "";
            if (properties.filename) props.filename = properties.filename;
            break;

        case "Slider":
            props.min = properties.min ?? 0;
            props.max = properties.max ?? 100;
            props.value = properties.value ?? 50;
            props.step = properties.step ?? 1;
            if (properties.name) props.name = properties.name;
            if (properties.label) props.label = properties.label;
            break;

        case "ChoicePicker":
            props.options = properties.options ?? [];
            props.maxSelections = properties.maxSelections ?? 1;
            if (properties.selected) props.selected = properties.selected;
            if (properties.name) props.name = properties.name;
            if (properties.label) props.label = properties.label;
            break;

        case "DateTimeInput":
            props.mode = properties.mode ?? "date";
            props.value = properties.value ?? "";
            if (properties.name) props.name = properties.name;
            if (properties.label) props.label = properties.label;
            break;

        case "CheckBox":
            props.label = properties.label ?? "";
            props.checked = properties.checked ?? false;
            if (properties.name) props.name = properties.name;
            break;

        case "Modal":
            props.title = properties.title ?? "";
            break;

        case "Video":
            props.url = properties.url ?? "";
            props.autoplay = properties.autoplay ?? false;
            break;

        case "AudioPlayer":
            props.url = properties.url ?? "";
            if (properties.description) props.description = properties.description;
            break;

        default:
            // Pass all properties through for unknown types
            Object.assign(props, properties);
    }

    return props;
}

// ---------------------------------------------------------------------------
// Convert flat adjacency list → nested tree for DynamicRenderer
// ---------------------------------------------------------------------------

interface FlatComponent {
    id: string;
    type: string;
    properties?: Record<string, unknown>;
    children?: string[];
    accessibility?: Record<string, string>;
    dataBinding?: Record<string, string>;
}

function flatToNested(
    components: FlatComponent[],
    rootId: string,
): Record<string, unknown>[] {
    const lookup = new Map<string, FlatComponent>();
    for (const comp of components) {
        lookup.set(comp.id, comp);
    }

    function buildNested(compId: string): Record<string, unknown> | null {
        const comp = lookup.get(compId);
        if (!comp) return null;

        const a2uiType = comp.type;
        const legacyType = A2UI_TO_LEGACY_TYPE[a2uiType] ?? a2uiType;
        const properties = comp.properties ?? {};
        const mapped = mapProperties(a2uiType, legacyType, properties);

        // Determine actual legacy type (Card with isCollapsible → collapsible)
        let finalType = legacyType;
        if (mapped._renderAsCollapsible) {
            finalType = "collapsible";
            delete mapped._renderAsCollapsible;
        }

        const result: Record<string, unknown> = {
            type: finalType,
            id: comp.id,
            ...mapped,
        };

        // Recurse into children
        const childIds = comp.children ?? [];
        if (childIds.length > 0) {
            if (a2uiType === "Tabs") {
                // Tabs: reconstruct tab items with nested content
                const tabsData = (properties.tabs as Array<{ label: string; children: string[] }>) ?? [];
                result.tabs = tabsData.map((tab) => ({
                    label: tab.label,
                    content: (tab.children ?? [])
                        .map((cid: string) => buildNested(cid))
                        .filter(Boolean),
                }));
                delete result._tabsData;
            } else if (finalType === "card" || finalType === "collapsible") {
                result.content = childIds
                    .map((cid) => buildNested(cid))
                    .filter(Boolean);
            } else {
                result.children = childIds
                    .map((cid) => buildNested(cid))
                    .filter(Boolean);
            }
        }

        return result;
    }

    const root = buildNested(rootId);
    if (!root) return [];

    // If root is a container/column, return its children directly
    // to match the DynamicRenderer's expected top-level array
    if (root.type === "container" && Array.isArray(root.children)) {
        return root.children as Record<string, unknown>[];
    }

    return [root];
}

// ---------------------------------------------------------------------------
// A2UIRenderer component
// ---------------------------------------------------------------------------

interface A2UIRendererProps {
    surface: A2UISurface;
    onSaveComponent?: (
        componentData: Record<string, unknown>,
        componentType: string,
        title?: string,
    ) => Promise<boolean>;
    onSendMessage?: (message: string) => void;
    onTablePaginate?: (event: {
        source_tool: string;
        source_agent: string;
        source_params: Record<string, unknown>;
        limit: number;
        offset: number;
    }) => void;
}

export default function A2UIRenderer({
    surface,
    onSaveComponent,
    onSendMessage,
    onTablePaginate,
}: A2UIRendererProps) {
    const nestedComponents = useMemo(
        () =>
            flatToNested(
                surface.components as unknown as FlatComponent[],
                surface.rootComponentId,
            ),
        [surface.components, surface.rootComponentId],
    );

    if (nestedComponents.length === 0) return null;

    return (
        <DynamicRenderer
            components={nestedComponents}
            onSaveComponent={onSaveComponent}
            onSendMessage={onSendMessage}
            onTablePaginate={onTablePaginate}
        />
    );
}
