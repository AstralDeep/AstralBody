"""
MCP Tools — tool functions that return UI Primitives.

Includes:
- Patient tools (mock): search_patients, graph_patient_data
- System tools: get_system_status, get_cpu_info, get_memory_info, get_disk_info
- Search tools: search_wikipedia
"""
import os
import sys
from typing import List, Dict, Any
import arxiv
from openai import OpenAI
from typing import Dict, Any, List, Optional
from collections import Counter
import json
import csv
import io
import time


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from shared.primitives import (
    Text, Card, Table, Container, MetricCard, ProgressBar,
    Alert, Grid, BarChart, LineChart, PieChart, PlotlyChart, List_,
    FileDownload, create_ui_response
)


def generate_dynamic_chart(
    data: List[Dict[str, Any]] | str, 
    x_key: str, 
    y_key: Optional[str] = None, 
    chart_type: str = "auto",
    title: str = "Data Visualization"
) -> Dict[str, Any]:
    """Generate a chart dynamically based on generic input data.

    Args:
        data: List of dictionaries representing the dataset (e.g., [{"date": "2023", "sales": 10}, ...]).
        x_key: The dictionary key to use for the X-axis (labels/categories).
        y_key: The dictionary key for the Y-axis. If None, it plots the frequency count of x_key.
        chart_type: 'auto', 'bar', 'line', 'pie', or 'scatter' (default: 'auto').
        title: Title of the chart.

    Returns:
        Dict with _ui_components and _data keys.
    """
    
    # 1. Parse stringified JSON if necessary
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            return {
                "_ui_components": [Alert(message="Invalid data format provided. Expected JSON array.", variant="error").to_json()],
                "_data": {}
            }

    if not data:
        return {
            "_ui_components": [Alert(message="No data provided to graph.", variant="warning").to_json()],
            "_data": {}
        }

    # --- THE FIX ---
    # Normalize y_key (LLMs sometimes pass the string "null", "None", or "")
    if str(y_key).strip().lower() in ("null", "none", "", "undefined"):
        y_key = None

    # 2. Extract Data Safely
    labels = []
    values = []

    if y_key is None:
        # Frequency count mode (Now triggered correctly!)
        raw_labels = [str(row.get(x_key, "Unknown")) for row in data]
        counts = Counter(raw_labels)
        labels = list(counts.keys())
        values = list(counts.values())
        y_key = "count" 
    else:
        # Explicit X vs Y mode
        labels = [str(row.get(x_key, "")) for row in data]
        
        for row in data:
            try:
                values.append(float(row.get(y_key, 0)))
            except (ValueError, TypeError):
                values.append(0)

    # 3. Auto-determine Chart Type
    if chart_type == "auto":
        unique_labels = len(set(labels))
        is_date_like = len(labels) > 0 and any(char in labels[0] for char in ['-', '/']) and any(char.isdigit() for char in labels[0])
        
        if is_date_like:
            chart_type = "line" 
        elif y_key == "count" and unique_labels <= 10:
            chart_type = "pie"  
        else:
            chart_type = "bar" 

    # 4. Build Plotly Configuration
    chart_data = []
    layout_update = {}
    color_palette = ["#6366F1", "#8B5CF6", "#06B6D4", "#10B981", "#F59E0B", "#EF4444", "#EC4899", "#3B82F6"]

    if chart_type == "pie":
        chart_data = [{
            "labels": labels,
            "values": values,
            "type": "pie",
            "marker": {"colors": color_palette},
            "textinfo": "label+percent",
            "hole": 0.4 
        }]
    else:
        trace = {
            "x": labels,
            "y": values,
            "type": "bar" if chart_type == "bar" else "scatter",
            "marker": {"color": color_palette[0]}
        }
        
        if chart_type == "line":
            trace["mode"] = "lines+markers"
            trace["line"] = {"color": color_palette[0], "width": 3}
        elif chart_type == "scatter":
            trace["mode"] = "markers"
            
        chart_data.append(trace)

        # Plotly layout fixes for categories
        if chart_type == "bar":
            layout_update["xaxis"] = {
                "type": "category",
                "tickangle": -45,
                "categoryorder": "category ascending" # This forces the X-axis to sort neatly!
            }

    # 5. Build UI Primitives
    chart = PlotlyChart(
        title=title,
        data=chart_data,
        layout=layout_update,
        id="dynamic-chart"
    )

    components = [
        Card(
            title=title,
            id="chart-card",
            content=[chart]
        )
    ]

    return {
        "_ui_components": [c.to_json() for c in components],
        "_data": {
            "labels": labels, 
            "values": values, 
            "x_key": x_key, 
            "y_key": y_key, 
            "rendered_chart_type": chart_type
        }
    }



def modify_data(
    csv_data: Optional[str] = None, 
    modifications: List[Dict[str, Any]] = None, 
    filename: Optional[str] = None,
    file_path: Optional[str] = None
) -> Dict[str, Any]:
    """Apply modifications to a CSV dataset and provide a download link.

    Args:
        csv_data: Raw CSV string data (optional if file_path is provided).
        modifications: List of modifications to apply. Example: [{"action": "add_column", "name": "metadata", "value": "Banana"}]
        filename: Optional filename for the modified file (default: modified_data_<timestamp>.csv).
        file_path: Optional absolute path to a CSV file to modify.
    """
    if modifications is None:
        modifications = []

    rows = []
    fieldnames = []

    try:
        if file_path:
            if not os.path.exists(file_path):
                return create_ui_response([Alert(message=f"File not found: {file_path}", variant="error")])
            with open(file_path, mode='r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                fieldnames = list(reader.fieldnames) if reader.fieldnames else []
                rows = list(reader)
        elif csv_data:
            # Strip markdown code fences
            csv_data = csv_data.strip()
            if csv_data.startswith("```csv"):
                csv_data = csv_data[6:].strip()
            elif csv_data.startswith("```"):
                csv_data = csv_data[3:].strip()
            if csv_data.endswith("```"):
                csv_data = csv_data[:-3].strip()

            reader = csv.DictReader(io.StringIO(csv_data))
            fieldnames = list(reader.fieldnames) if reader.fieldnames else []
            rows = list(reader)
        else:
            return create_ui_response([Alert(message="Neither csv_data nor file_path provided.", variant="error")])

        # Apply modifications (to ALL rows)
        for mod in modifications:
            action = mod.get("action")
            name = mod.get("name")
            value = mod.get("value")

            if action == "add_column" and name:
                if name not in fieldnames:
                    fieldnames.append(name)
                for row in rows:
                    row[name] = value
            elif action == "update_column" and name:
                for row in rows:
                    row[name] = value

        # Save to downloads directory
        timestamp = int(time.time())
        if not filename:
            filename = f"modified_data_{timestamp}.csv"
        
        backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        download_dir = os.path.join(backend_dir, "data", "downloads")
        os.makedirs(download_dir, exist_ok=True)
        out_file_path = os.path.join(download_dir, filename)

        with open(out_file_path, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        # The BFF URL
        bff_port = int(os.getenv("AUTH_PORT", 8002))
        bff_url = f"http://localhost:{bff_port}"
        download_url = f"{bff_url}/api/download/{filename}"

        components = [
            Card(
                title="Data Modified Successfully",
                id="modify-data-card",
                content=[
                    Alert(message=f"Applied {len(modifications)} modifications to the full dataset ({len(rows)} rows).", variant="success"),
                    FileDownload(
                        label=f"Download {filename}",
                        url=download_url,
                        filename=filename
                    ),
                    Table(
                        headers=fieldnames[:5], 
                        rows=[[str(r.get(f, "")) for f in fieldnames[:5]] for r in rows[:5]],
                        id="modify-data-preview"
                    )
                ]
            )
        ]

        return {
            "_ui_components": [c.to_json() for c in components],
            "_data": {"filename": filename, "file_path": out_file_path, "rows_count": len(rows)}
        }

    except Exception as e:
        return create_ui_response([Alert(message=f"Failed to modify data: {e}", variant="error")])


# =============================================================================
# SYSTEM TOOLS
# =============================================================================
import psutil
import platform


def get_system_status() -> Dict[str, Any]:
    """Get comprehensive system status information."""
    cpu_percent = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage('/')

    def get_variant(percent):
        if percent > 90: return "error"
        if percent > 70: return "warning"
        return "default"

    components = [
        Card(
            title="System Status",
            id="system-status-card",
            content=[
                Grid(
                    columns=3,
                    children=[
                        MetricCard(
                            title="CPU Usage",
                            value=f"{cpu_percent}%",
                            progress=cpu_percent / 100,
                            variant=get_variant(cpu_percent),
                            id="cpu-metric"
                        ),
                        MetricCard(
                            title="Memory Usage",
                            value=f"{mem.percent}%",
                            subtitle=f"{mem.used // (1024**3):.1f} / {mem.total // (1024**3):.1f} GB",
                            progress=mem.percent / 100,
                            variant=get_variant(mem.percent),
                            id="mem-metric"
                        ),
                        MetricCard(
                            title="Disk Usage",
                            value=f"{disk.percent}%",
                            subtitle=f"{disk.used // (1024**3):.1f} / {disk.total // (1024**3):.1f} GB",
                            progress=disk.percent / 100,
                            variant=get_variant(disk.percent),
                            id="disk-metric"
                        ),
                    ]
                ),
                Text(content=f"Platform: {platform.system()} {platform.release()}", variant="caption"),
                Text(content=f"Hostname: {platform.node()}", variant="caption"),
            ]
        )
    ]

    return {
        "_ui_components": [c.to_json() for c in components],
        "_data": {
            "cpu_percent": cpu_percent,
            "memory_percent": mem.percent,
            "disk_percent": disk.percent,
            "platform": platform.system(),
        }
    }


def get_cpu_info() -> Dict[str, Any]:
    """Get detailed CPU information."""
    cpu_freq = psutil.cpu_freq()
    cpu_count = psutil.cpu_count()
    cpu_percent_per_core = psutil.cpu_percent(interval=0.5, percpu=True)

    headers = ["Core", "Usage %"]
    rows = [[f"Core {i}", f"{p}%"] for i, p in enumerate(cpu_percent_per_core)]

    components = [
        Card(
            title="CPU Information",
            id="cpu-info-card",
            content=[
                Grid(columns=2, children=[
                    MetricCard(title="Total Cores", value=str(cpu_count), id="cpu-cores"),
                    MetricCard(
                        title="Frequency",
                        value=f"{cpu_freq.current:.0f} MHz" if cpu_freq else "N/A",
                        id="cpu-freq"
                    ),
                ]),
                Table(headers=headers, rows=rows, id="cpu-table"),
            ]
        )
    ]

    return {
        "_ui_components": [c.to_json() for c in components],
        "_data": {"cores": cpu_count, "frequency": cpu_freq.current if cpu_freq else 0}
    }


def get_memory_info() -> Dict[str, Any]:
    """Get detailed memory information."""
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()

    components = [
        Card(
            title="Memory Information",
            id="memory-info-card",
            content=[
                Grid(columns=2, children=[
                    MetricCard(
                        title="RAM Usage",
                        value=f"{mem.percent}%",
                        subtitle=f"{mem.used // (1024**3):.1f} / {mem.total // (1024**3):.1f} GB",
                        progress=mem.percent / 100,
                        id="ram-metric"
                    ),
                    MetricCard(
                        title="Swap Usage",
                        value=f"{swap.percent}%",
                        subtitle=f"{swap.used // (1024**3):.1f} / {swap.total // (1024**3):.1f} GB",
                        progress=swap.percent / 100,
                        id="swap-metric"
                    ),
                ]),
            ]
        )
    ]

    return {
        "_ui_components": [c.to_json() for c in components],
        "_data": {"ram_percent": mem.percent, "swap_percent": swap.percent}
    }


def get_disk_info() -> Dict[str, Any]:
    """Get disk partition information."""
    partitions = psutil.disk_partitions()
    headers = ["Device", "Mount", "FS Type", "Total GB", "Used GB", "Free GB", "Usage %"]
    rows = []

    for p in partitions:
        try:
            usage = psutil.disk_usage(p.mountpoint)
            rows.append([
                p.device,
                p.mountpoint,
                p.fstype,
                f"{usage.total // (1024**3):.1f}",
                f"{usage.used // (1024**3):.1f}",
                f"{usage.free // (1024**3):.1f}",
                f"{usage.percent}%"
            ])
        except PermissionError:
            rows.append([p.device, p.mountpoint, p.fstype, "N/A", "N/A", "N/A", "N/A"])

    components = [
        Card(
            title="Disk Information",
            id="disk-info-card",
            content=[
                Table(headers=headers, rows=rows, id="disk-table"),
            ]
        )
    ]

    return {
        "_ui_components": [c.to_json() for c in components],
        "_data": {"partitions": len(rows)}
    }


# =============================================================================
# SEARCH TOOLS
# =============================================================================
import requests


def search_wikipedia(query: str, language: str = "en") -> Dict[str, Any]:
    """Search Wikipedia for articles and summaries.

    Args:
        query: The search query
        language: Wikipedia language code (default: 'en')

    Returns:
        Dict with _ui_components and _data keys.
    """
    try:
        search_url = f"https://{language}.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "format": "json",
            "srlimit": 5,
            "srprop": "snippet|titlesnippet"
        }
        headers = {
            "User-Agent": "AstralDeep/1.0 (internal research project)"
        }
        resp = requests.get(search_url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("query", {}).get("search", [])

        if not results:
            return create_ui_response([
                Alert(message=f"No Wikipedia results for '{query}'", variant="info")
            ])

        items = []
        for r in results:
            # Clean HTML from snippet
            snippet = r.get("snippet", "").replace("<span class=\"searchmatch\">", "").replace("</span>", "")
            items.append(f"**{r['title']}** — {snippet}")

        components = [
            Card(
                title=f"Wikipedia: {query}",
                id="wiki-results",
                content=[
                    List_(items=items, id="wiki-list"),
                ]
            )
        ]

        return {
            "_ui_components": [c.to_json() for c in components],
            "_data": {"results": [{"title": r["title"], "pageid": r["pageid"]} for r in results]}
        }

    except Exception as e:
        return create_ui_response([
            Alert(message=f"Wikipedia search failed: {str(e)}", variant="error", title="Error")
        ])


# =============================================================================
# ACADEMIC SEARCH TOOLS
# =============================================================================

def extract_search_terms(query: str) -> str:
    """Extract relevant search terms from a natural language query using LLM."""
    print(f"DEBUG: Extracting search terms for: {query}")
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    model = os.getenv("LLM_MODEL", "gpt-4o")
    
    if not api_key:
        print("Warning: OPENAI_API_KEY not found, using raw query")
        return query.strip()
        
    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        print("DEBUG: Calling LLM for search terms...")
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a search query optimizer. Extract the core subject/keywords from the user's request for an academic paper search. Return ONLY the keywords, nothing else. Example: 'write a paper about deep learning' -> 'deep learning'"},
                {"role": "user", "content": query}
            ],
            max_tokens=50,
            timeout=10 # Add timeout
        )
        terms = response.choices[0].message.content.strip()
        print(f"DEBUG: extracted terms: {terms}")
        return terms
    except Exception as e:
        print(f"Error extracting search terms: {e}")
        return query.strip()

def search_arxiv(query: str, max_results: int = 10) -> Dict[str, Any]:
    """Search arXiv for papers related to the query.
    
    Args:
        query: The search query
        max_results: Maximum number of results (default: 10)
    """
    print(f"DEBUG: search_arxiv called with query: {query}")
    # Use LLM to extract clean search terms
    clean_query = extract_search_terms(query)
    print(f"Original query: '{query}' -> Cleaned query: '{clean_query}'")
    
    try:
        print("DEBUG: Executing arxiv search...")
        search = arxiv.Search(
            query=clean_query,
            max_results=int(max_results),
            sort_by=arxiv.SortCriterion.Relevance
        )
        
        results = []
        for paper in search.results():
            results.append({
                "title": paper.title,
                "authors": [author.name for author in paper.authors],
                "summary": paper.summary,
                "published": paper.published.strftime("%Y-%m-%d"),
                "url": paper.entry_id,
                "pdf_url": paper.pdf_url
            })
        print(f"DEBUG: Found {len(results)} papers")
        
        # Create UI components
        if not results:
            components = [
                Alert(
                    title="No Results",
                    message=f"No papers found for '{query}' on arXiv.",
                    variant="warning"
                )
            ]
        else:
            # Calculate metrics
            total_papers = len(results)
            latest_date = max(r["published"] for r in results) if results else "N/A"
            # Find most common author
            all_authors = [a for r in results for a in r["authors"]]
            top_author = max(set(all_authors), key=all_authors.count) if all_authors else "N/A"

            # Create list items with paper details
            list_items = []
            for paper in results:
                authors_str = ", ".join(paper["authors"][:2])
                if len(paper["authors"]) > 2:
                    authors_str += f" +{len(paper['authors'])-2}"
                
                list_items.append({
                    "title": paper["title"],
                    "subtitle": f"{authors_str} • {paper['published']}",
                    "description": paper["summary"][:200] + "..." if len(paper['summary']) > 200 else paper['summary'],
                    "url": paper["url"]
                })
            
            # Cohesive UI: Card with Metrics + List
            components = [
                Card(
                    title=f"ArXiv Research: {clean_query}",
                    id="arxiv-results-card",
                    content=[
                        Grid(
                            columns=3,
                            children=[
                                MetricCard(
                                    title="Total Papers",
                                    value=str(total_papers),
                                    id="metric-total"
                                ),
                                MetricCard(
                                    title="Latest Paper",
                                    value=latest_date,
                                    id="metric-date"
                                ),
                                MetricCard(
                                    title="Top Author",
                                    value=top_author,
                                    id="metric-author"
                                ),
                            ]
                        ),
                        Text(content="Most relevant papers found:", variant="body"),
                        List_(
                            items=list_items,
                            variant="detailed",
                            id="arxiv-list"
                        )
                    ]
                )
            ]
        
        return {
            "_ui_components": [c.to_json() if hasattr(c, 'to_json') else c for c in components],
            "_data": results
        }
    except Exception as e:
        print(f"Error searching arXiv: {e}")
        components = [
            Alert(
                title="Search Error",
                message=f"Error searching arXiv: {str(e)}",
                variant="error"
            )
        ]
        return create_ui_response(components)


# =============================================================================
# TOOL REGISTRY
# =============================================================================

TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {
   "generate_dynamic_chart": {
        "function": generate_dynamic_chart,
        "description": "Create a dynamic chart/graph visualization from generic tabular data. Automatically selects the best chart type ('bar', 'line', 'pie', 'scatter') based on data heuristics, or accepts a specific chart type. Supports plotting specific X and Y axes, or frequency counts if no Y axis is provided.",
        "input_schema": {
            "type": "object",
            "properties": {
                "data": {
                    "type": "array",
                    "items": {
                        "type": "object"
                    },
                    "description": "The dataset to visualize, formatted as a list of dictionaries (e.g., [{'category': 'A', 'value': 10}, ...])."
                },
                "x_key": {
                    "type": "string",
                    "description": "The dictionary key in the data to use for the X-axis (labels/categories)."
                },
                "y_key": {
                    "type": "string",
                    "description": "The dictionary key in the data for the Y-axis values. If omitted or null, the tool will plot the frequency count of the x_key categories."
                },
                "chart_type": {
                    "type": "string",
                    "description": "The type of chart to render. Options: 'auto', 'bar', 'line', 'pie', or 'scatter'.",
                    "default": "auto"
                },
                "title": {
                    "type": "string",
                    "description": "The display title of the generated chart.",
                    "default": "Data Visualization"
                }
            },
            "required": ["data", "x_key"]
        }
    },
    "get_system_status": {
        "function": get_system_status,
        "description": "Get comprehensive system status including CPU, memory, and disk usage with visual metrics.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    "get_cpu_info": {
        "function": get_cpu_info,
        "description": "Get detailed CPU information including per-core usage.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    "get_memory_info": {
        "function": get_memory_info,
        "description": "Get detailed memory (RAM + swap) information.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    "get_disk_info": {
        "function": get_disk_info,
        "description": "Get disk partition and usage information.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    "search_wikipedia": {
        "function": search_wikipedia,
        "description": "Search Wikipedia for articles and summaries on any topic.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "language": {"type": "string", "description": "Wikipedia language code", "default": "en"}
            },
            "required": ["query"]
        }
    },
    "search_arxiv": {
        "function": search_arxiv,
        "description": "Search arXiv for academic papers and research.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {"type": "integer", "description": "Maximum number of results", "default": 10}
            },
            "required": ["query"]
        }
    },
    "modify_data": {
        "function": modify_data,
        "description": "Modify CSV data (add or update columns) and provide a downloadable file link. Use this for ANY data modification request. IMPORTANT: If a 'file_path' is available in the chat context, you MUST use it instead of 'csv_data' to ensure the entire file is processed and not just a truncated preview.",
        "input_schema": {
            "type": "object",
            "properties": {
                "csv_data": {"type": "string", "description": "Raw CSV string data (use only for small/pasted data)"},
                "file_path": {"type": "string", "description": "Absolute path to the CSV file on disk (MANDATORY for uploaded files)"},
                "modifications": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "description": "Action to perform: 'add_column' or 'update_column'"},
                            "name": {"type": "string", "description": "Column name"},
                            "value": {"type": "string", "description": "Value to fill (string)"}
                        },
                        "required": ["action", "name", "value"]
                    }
                },
                "filename": {"type": "string", "description": "Optional name for the result file"}
            },
            "required": ["modifications"]
        }
    },
}
