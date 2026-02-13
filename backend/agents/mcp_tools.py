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


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from shared.primitives import (
    Text, Card, Table, Container, MetricCard, ProgressBar,
    Alert, Grid, BarChart, LineChart, PieChart, PlotlyChart, List_,
    create_ui_response
)

# =============================================================================
# MOCK PATIENT TOOLS
# =============================================================================

MOCK_PATIENTS = [
    {"id": "P-1024", "name": "Sarah Connor", "age": 45, "condition": "Degenerative Disc Disease - L4/L5", "status": "Severe", "blood_pressure": "142/88", "heart_rate": 78},
    {"id": "P-1092", "name": "John Smith", "age": 38, "condition": "Degenerative Disc Disease - C5/C6", "status": "Moderate", "blood_pressure": "128/82", "heart_rate": 72},
    {"id": "P-1123", "name": "Emily Davis", "age": 52, "condition": "Degenerative Disc Disease - L5/S1", "status": "Critical", "blood_pressure": "156/94", "heart_rate": 88},
    {"id": "P-1245", "name": "Michael Brown", "age": 34, "condition": "Degenerative Disc Disease - L3/L4", "status": "Mild", "blood_pressure": "118/76", "heart_rate": 68},
    {"id": "P-1301", "name": "Lisa Wilson", "age": 41, "condition": "Osteoarthritis - Knee", "status": "Moderate", "blood_pressure": "132/84", "heart_rate": 74},
    {"id": "P-1388", "name": "Robert Taylor", "age": 55, "condition": "Chronic Back Pain", "status": "Severe", "blood_pressure": "148/90", "heart_rate": 82},
    {"id": "P-1402", "name": "Jennifer Lee", "age": 29, "condition": "Scoliosis", "status": "Mild", "blood_pressure": "112/72", "heart_rate": 66},
    {"id": "P-1455", "name": "David Martinez", "age": 47, "condition": "Spinal Stenosis", "status": "Moderate", "blood_pressure": "138/86", "heart_rate": 76},
    {"id": "P-1500", "name": "Amanda Clark", "age": 36, "condition": "Herniated Disc - L4/L5", "status": "Moderate", "blood_pressure": "124/78", "heart_rate": 70},
    {"id": "P-1567", "name": "James Anderson", "age": 62, "condition": "Degenerative Disc Disease - Multiple", "status": "Critical", "blood_pressure": "162/96", "heart_rate": 92},
]


def search_patients(min_age: int = 0, max_age: int = 200, condition: str = "") -> Dict[str, Any]:
    """Search patients by age range and/or condition.

    Args:
        min_age: Minimum age filter (default: 0)
        max_age: Maximum age filter (default: 200)
        condition: Condition keyword to filter by (case-insensitive, partial match)

    Returns:
        Dict with _ui_components and _data keys.
    """
    # Ensure ages are integers (LLM might pass strings)
    try:
        min_age = int(min_age)
        max_age = int(max_age)
    except ValueError:
        pass  # If casting fails, we'll likely get a TypeError later, or maybe we should default? For now, let's trust best effort.

    results = []
    for p in MOCK_PATIENTS:
        if p["age"] < min_age or p["age"] > max_age:
            continue
        if condition and condition.lower() not in p["condition"].lower():
            continue
        results.append(p)

    if not results:
        return create_ui_response([
            Alert(message="No patients found matching your criteria.", variant="info", title="Search Results")
        ])

    # Build a table component
    headers = ["ID", "Name", "Age", "Condition", "Status"]
    rows = [[p["id"], p["name"], str(p["age"]), p["condition"], p["status"]] for p in results]

    status_summary = {}
    for p in results:
        status_summary[p["status"]] = status_summary.get(p["status"], 0) + 1

    components = [
        Card(
            title=f"Patient Search Results ({len(results)} found)",
            id="patient-results-card",
            content=[
                Text(content=f"Showing patients aged {min_age}+" +
                     (f" with condition matching '{condition}'" if condition else ""),
                     variant="caption"),
                Table(headers=headers, rows=rows, id="patient-table"),
            ]
        ),
        Grid(
            columns=len(status_summary),
            id="patient-metrics",
            children=[
                MetricCard(
                    title=status,
                    value=str(count),
                    subtitle="patients",
                    variant="warning" if status == "Severe" else "error" if status == "Critical" else "default",
                    id=f"metric-{status.lower()}"
                )
                for status, count in status_summary.items()
            ]
        )
    ]

    return {
        "_ui_components": [c.to_json() for c in components],
        "_data": {"patients": results, "total": len(results)}
    }

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
    "search_patients": {
        "function": search_patients,
        "description": "Search patients by age range and/or condition. Returns a table of matching patients with status metrics.",
        "input_schema": {
            "type": "object",
            "properties": {
                "min_age": {"type": "integer", "description": "Minimum patient age", "default": 0},
                "max_age": {"type": "integer", "description": "Maximum patient age", "default": 200},
                "condition": {"type": "string", "description": "Condition keyword to filter by (partial match)", "default": ""}
            }
        }
    },
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
}
