#!/usr/bin/env python3
"""
MCP Tools for NocoDB Agent — CRUD operations on tables, records, links, and storage.
"""
import os
import sys
import json
import logging
from typing import Dict, Any, List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from shared.primitives import (
    Text, Card, Table, Container, MetricCard, ProgressBar,
    Alert, Grid, BarChart, LineChart, PieChart, PlotlyChart, List_,
    Collapsible, Divider, CodeBlock, Image, Tabs,
    FileDownload, FileUpload, Button, Input, ColorPicker,
    create_ui_response
)

try:
    import requests
except ImportError:
    print("ERROR: 'requests' package not installed. Please install with: pip install requests")
    requests = None

logger = logging.getLogger('NocodbAgentMCPTools')


# ---------------------------------------------------------------------------
# Shared API client
# ---------------------------------------------------------------------------

class NocoDBClient:
    """Reusable HTTP client for the NocoDB v2 API."""

    def __init__(self, credentials: Dict[str, str]):
        self.api_token = credentials.get("NOCODB_API_TOKEN", "")
        self.base_url = credentials.get("NOCODB_BASE_URL", "").rstrip("/")

    def validate(self) -> Optional[str]:
        """Return an error message if credentials are missing, else None."""
        if not self.api_token:
            return "NocoDB API Token is not configured. Please add it in agent settings."
        if not self.base_url:
            return "NocoDB Base URL is not configured. Please add it in agent settings."
        return None

    def _headers(self) -> Dict[str, str]:
        return {
            "xc-token": self.api_token,
            "xc-auth": self.api_token,
            "Content-Type": "application/json",
        }

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict] = None,
        json_body: Any = None,
        timeout: int = 30,
    ) -> Any:
        url = f"{self.base_url}{path}"
        resp = requests.request(
            method,
            url,
            headers=self._headers(),
            params=params,
            json=json_body,
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    def get(self, path: str, params: Optional[Dict] = None, **kw):
        return self._request("GET", path, params=params, **kw)

    def post(self, path: str, json_body: Any = None, **kw):
        return self._request("POST", path, json_body=json_body, **kw)

    def patch(self, path: str, json_body: Any = None, **kw):
        return self._request("PATCH", path, json_body=json_body, **kw)

    def delete(self, path: str, json_body: Any = None, **kw):
        return self._request("DELETE", path, json_body=json_body, **kw)

    def upload(self, path: str, file_path: str, storage_path: str, timeout: int = 60):
        """Upload a file via multipart form-data."""
        url = f"{self.base_url}{path}"
        headers = {"xc-token": self.api_token}
        with open(file_path, "rb") as f:
            resp = requests.post(
                url,
                headers=headers,
                params={"path": storage_path} if storage_path else None,
                files={"file": f},
                timeout=timeout,
            )
        resp.raise_for_status()
        return resp.json() if resp.content else {}


def _build_client(kwargs: Dict) -> NocoDBClient:
    """Extract credentials and return a validated client, or raise."""
    credentials = kwargs.get("_credentials", {})
    client = NocoDBClient(credentials)
    err = client.validate()
    if err:
        raise ValueError(err)
    return client


DEFAULT_PAGE_SIZES = [25, 50, 100, 200]
AGENT_ID = "nocodb-1"


def _records_to_table(
    records: List[Dict],
    page_info: Optional[Dict] = None,
    source_tool: Optional[str] = None,
    source_params: Optional[Dict] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
) -> Optional[Table]:
    """Convert a list of record dicts into a Table component with optional pagination."""
    if not records:
        return None
    headers = list(records[0].keys())
    rows = []
    for rec in records:
        row = []
        for h in headers:
            val = rec.get(h, "")
            if isinstance(val, (dict, list)):
                row.append(json.dumps(val, default=str)[:200])
            else:
                row.append(str(val) if val is not None else "")
        rows.append(row)

    tbl = Table(headers=headers, rows=rows)

    # Attach pagination metadata if we have page info
    if page_info and page_info.get("totalRows") is not None:
        tbl.total_rows = page_info.get("totalRows", 0)
        tbl.page_size = limit or page_info.get("pageSize", 25)
        tbl.page_offset = offset or 0
        tbl.page_sizes = DEFAULT_PAGE_SIZES
        if source_tool:
            tbl.source_tool = source_tool
            tbl.source_agent = AGENT_ID
            tbl.source_params = source_params or {}

    return tbl


def _page_info_metrics(page_info: Dict) -> List:
    """Build MetricCard list from NocoDB pageInfo."""
    metrics = []
    if "totalRows" in page_info:
        metrics.append(MetricCard(title="Total Rows", value=str(page_info["totalRows"])))
    if "page" in page_info:
        metrics.append(MetricCard(title="Page", value=str(page_info["page"])))
    if "pageSize" in page_info:
        metrics.append(MetricCard(title="Page Size", value=str(page_info["pageSize"])))
    return metrics


# ---------------------------------------------------------------------------
# Tool 1: check_connection
# ---------------------------------------------------------------------------

def check_connection(**kwargs) -> Dict[str, Any]:
    """Verify that NocoDB credentials are configured and the instance is reachable."""
    try:
        credentials = kwargs.get("_credentials", {})
        client = NocoDBClient(credentials)

        token_ok = bool(client.api_token)
        url_ok = bool(client.base_url)

        status_items = [
            MetricCard(title="API Token", value="Configured" if token_ok else "Missing"),
            MetricCard(title="Base URL", value=client.base_url if url_ok else "Missing"),
        ]

        if token_ok and url_ok:
            try:
                client.get("/api/v1/health")
                status_items.append(MetricCard(title="Connection", value="OK"))
            except Exception:
                # Health endpoint may not exist on all versions; try a lightweight call
                try:
                    client.get("/api/v1/version")
                    status_items.append(MetricCard(title="Connection", value="OK"))
                except Exception as inner:
                    status_items.append(MetricCard(title="Connection", value=f"Error: {inner}"))

        components = [
            Card(
                title="NocoDB Connection Status",
                content=[
                    Grid(columns=3, children=status_items),
                ]
            )
        ]

        return {
            "_ui_components": [c.to_json() for c in components],
            "_data": {"token_configured": token_ok, "url_configured": url_ok}
        }
    except Exception as e:
        return create_ui_response([Alert(message=f"Connection check failed: {e}", variant="error")])


# ---------------------------------------------------------------------------
# Tool 2: list_tables
# ---------------------------------------------------------------------------

def list_tables(base_id: str = "", **kwargs) -> Dict[str, Any]:
    """List all tables in a NocoDB base, returning their names and IDs.

    Use this to look up a table_id from a human-readable table name.
    If base_id is omitted, uses the NOCODB_BASE_ID credential.
    """
    try:
        client = _build_client(kwargs)
        credentials = kwargs.get("_credentials", {})

        # Use credential base_id as default if not provided
        if not base_id:
            base_id = credentials.get("NOCODB_BASE_ID", "")
        if not base_id:
            return create_ui_response([
                Alert(message="No base_id provided and NOCODB_BASE_ID credential is not configured.", variant="error")
            ])

        data = client.get(f"/api/v2/meta/bases/{base_id}/tables")

        tables = data.get("list", data) if isinstance(data, dict) else data
        if not isinstance(tables, list):
            tables = [tables] if tables else []

        rows = []
        table_map = {}
        for t in tables:
            tid = t.get("id", "")
            title = t.get("title", t.get("table_name", ""))
            ttype = t.get("type", "")
            rows.append([title, str(tid), ttype])
            table_map[title] = tid

        content = [
            MetricCard(title="Tables Found", value=str(len(rows))),
            Divider(),
        ]
        if rows:
            content.append(Table(headers=["Table Name", "Table ID", "Type"], rows=rows))
        else:
            content.append(Text(content="No tables found in this base.", variant="caption"))

        components = [Card(title=f"Tables in Base {base_id}", content=content)]
        return {
            "_ui_components": [c.to_json() for c in components],
            "_data": {"tables": tables, "table_map": table_map}
        }
    except Exception as e:
        return create_ui_response([Alert(message=f"Failed to list tables: {e}", variant="error")])


# ---------------------------------------------------------------------------
# Tool 3: list_records
# ---------------------------------------------------------------------------

def list_records(table_id: str, fields: str = "", sort: str = "",
                 view_id: str = "", limit: int = 100, offset: int = 0,
                 **kwargs) -> Dict[str, Any]:
    """List records from a NocoDB table with pagination, field selection, and sorting."""
    try:
        client = _build_client(kwargs)
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if fields:
            params["fields"] = fields
        if sort:
            params["sort"] = sort
        if view_id:
            params["viewId"] = view_id

        try:
            data = client.get(f"/api/v2/tables/{table_id}/records", params=params)
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code in (404, 422) and fields:
                params.pop("fields", None)
                data = client.get(f"/api/v2/tables/{table_id}/records", params=params)
            else:
                raise
        records = data.get("list", [])
        page_info = data.get("pageInfo", {})

        content = []
        metrics = _page_info_metrics(page_info)
        if metrics:
            content.append(Grid(columns=len(metrics), children=metrics))
            content.append(Divider())

        tool_params = {"table_id": table_id, "fields": fields, "sort": sort,
                       "view_id": view_id, "limit": limit, "offset": offset}
        tbl = _records_to_table(records, page_info, "list_records", tool_params, limit, offset)
        if tbl:
            content.append(tbl)
        else:
            content.append(Text(content="No records found.", variant="caption"))

        components = [Card(title=f"Records — {table_id}", content=content)]
        return {
            "_ui_components": [c.to_json() for c in components],
            "_data": {"records": records, "pageInfo": page_info}
        }
    except Exception as e:
        return create_ui_response([Alert(message=f"Failed to list records: {e}", variant="error")])


# ---------------------------------------------------------------------------
# Tool 3: get_record
# ---------------------------------------------------------------------------

def get_record(table_id: str, record_id: str, fields: str = "", **kwargs) -> Dict[str, Any]:
    """Get a single record by its ID."""
    try:
        client = _build_client(kwargs)
        params: Dict[str, Any] = {}
        if fields:
            params["fields"] = fields

        try:
            record = client.get(f"/api/v2/tables/{table_id}/records/{record_id}", params=params)
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code in (404, 422) and fields:
                params.pop("fields", None)
                record = client.get(f"/api/v2/tables/{table_id}/records/{record_id}", params=params)
            else:
                raise

        rows = []
        for key, val in record.items():
            display_val = json.dumps(val, default=str)[:200] if isinstance(val, (dict, list)) else str(val) if val is not None else ""
            rows.append([str(key), display_val])

        components = [
            Card(
                title=f"Record {record_id}",
                content=[
                    Table(headers=["Field", "Value"], rows=rows)
                ]
            )
        ]

        return {
            "_ui_components": [c.to_json() for c in components],
            "_data": {"record": record}
        }
    except Exception as e:
        return create_ui_response([Alert(message=f"Failed to get record: {e}", variant="error")])


# ---------------------------------------------------------------------------
# Tool 4: count_records
# ---------------------------------------------------------------------------

def count_records(table_id: str, where: str = "", view_id: str = "", **kwargs) -> Dict[str, Any]:
    """Count records in a table, optionally filtered."""
    try:
        client = _build_client(kwargs)
        params: Dict[str, Any] = {}
        if where:
            params["where"] = where
        if view_id:
            params["viewId"] = view_id

        data = client.get(f"/api/v2/tables/{table_id}/records/count", params=params)
        count = data.get("count", 0)

        content = [MetricCard(title="Record Count", value=str(count))]
        if where:
            content.append(Text(content=f"Filter: {where}", variant="caption"))

        components = [Card(title=f"Count — {table_id}", content=content)]
        return {
            "_ui_components": [c.to_json() for c in components],
            "_data": {"count": count}
        }
    except Exception as e:
        return create_ui_response([Alert(message=f"Failed to count records: {e}", variant="error")])


# ---------------------------------------------------------------------------
# Tool 5: search_records
# ---------------------------------------------------------------------------

def search_records(table_id: str, where: str, fields: str = "", sort: str = "",
                   limit: int = 100, offset: int = 0, **kwargs) -> Dict[str, Any]:
    """Search records using NocoDB filter syntax, e.g. (Status,eq,Active)~and(Priority,eq,High)."""
    try:
        client = _build_client(kwargs)
        params: Dict[str, Any] = {"where": where, "limit": limit, "offset": offset}
        if fields:
            params["fields"] = fields
        if sort:
            params["sort"] = sort

        try:
            data = client.get(f"/api/v2/tables/{table_id}/records", params=params)
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code in (404, 422) and fields:
                params.pop("fields", None)
                data = client.get(f"/api/v2/tables/{table_id}/records", params=params)
            else:
                raise
        records = data.get("list", [])
        page_info = data.get("pageInfo", {})

        content = [
            Alert(message=f"Filter: {where}", variant="info"),
        ]
        metrics = _page_info_metrics(page_info)
        if metrics:
            content.append(Grid(columns=len(metrics), children=metrics))
            content.append(Divider())

        tool_params = {"table_id": table_id, "where": where, "fields": fields,
                       "sort": sort, "limit": limit, "offset": offset}
        tbl = _records_to_table(records, page_info, "search_records", tool_params, limit, offset)
        if tbl:
            content.append(tbl)
        else:
            content.append(Text(content="No matching records.", variant="caption"))

        components = [Card(title=f"Search Results — {table_id}", content=content)]
        return {
            "_ui_components": [c.to_json() for c in components],
            "_data": {"records": records, "pageInfo": page_info}
        }
    except Exception as e:
        return create_ui_response([Alert(message=f"Search failed: {e}", variant="error")])


# ---------------------------------------------------------------------------
# Tool 6: search_records_simple
# ---------------------------------------------------------------------------

def search_records_simple(table_id: str, field_name: str, operator: str, value: str = "",
                          limit: int = 100, **kwargs) -> Dict[str, Any]:
    """Search records with a simplified interface: single field, operator, and value.

    Operators: eq, neq, like, nlike, gt, lt, gte, lte, is, isnot, null, notnull.
    For 'like'/'nlike', wraps value in % wildcards automatically.
    For 'null'/'notnull', value is ignored.
    """
    try:
        # Operators that take no value
        if operator in ("null", "notnull"):
            where = f"({field_name},{operator})"
        elif operator in ("like", "nlike"):
            # Auto-wrap in wildcards if not already present
            v = value if "%" in value else f"%{value}%"
            where = f"({field_name},{operator},{v})"
        else:
            where = f"({field_name},{operator},{value})"
        client = _build_client(kwargs)
        params: Dict[str, Any] = {"where": where, "limit": limit}

        data = client.get(f"/api/v2/tables/{table_id}/records", params=params)
        records = data.get("list", [])
        page_info = data.get("pageInfo", {})

        content = [
            Alert(message=f"{field_name} {operator} {value}", variant="info"),
            MetricCard(title="Matches", value=str(page_info.get("totalRows", len(records)))),
            Divider(),
        ]

        tool_params = {"table_id": table_id, "field_name": field_name,
                       "operator": operator, "value": value, "limit": limit}
        tbl = _records_to_table(records, page_info, "search_records_simple", tool_params, limit, 0)
        if tbl:
            content.append(tbl)
        else:
            content.append(Text(content="No matching records.", variant="caption"))

        components = [Card(title=f"Search — {table_id}", content=content)]
        return {
            "_ui_components": [c.to_json() for c in components],
            "_data": {"records": records, "pageInfo": page_info, "filter": where}
        }
    except Exception as e:
        return create_ui_response([Alert(message=f"Search failed: {e}", variant="error")])


# ---------------------------------------------------------------------------
# Tool 8: get_assigned_tasks
# ---------------------------------------------------------------------------

def get_assigned_tasks(table_id: str, assignee: str, status: str = "",
                       limit: int = 100, **kwargs) -> Dict[str, Any]:
    """Get tasks assigned to a specific person from a project tasks table.

    Searches the 'Assignee' field (case-sensitive) for the given name.
    Optionally filter by status as well.
    """
    try:
        client = _build_client(kwargs)

        # Try server-side filter first; fall back to client-side filtering
        # if the field type doesn't support 'like' (e.g. User fields → 422).
        where = f"(Assignee,like,%{assignee}%)"
        if status:
            where += f"~and(Status,eq,{status})"

        try:
            params: Dict[str, Any] = {"where": where, "limit": limit}
            data = client.get(f"/api/v2/tables/{table_id}/records", params=params)
        except requests.HTTPError as http_err:
            if http_err.response is not None and http_err.response.status_code == 422:
                # 'like' unsupported for this field type – fetch with status
                # filter only (if any) and match assignee client-side.
                fallback_where = f"(Status,eq,{status})" if status else ""
                fb_params: Dict[str, Any] = {"limit": limit}
                if fallback_where:
                    fb_params["where"] = fallback_where
                data = client.get(f"/api/v2/tables/{table_id}/records", params=fb_params)
                # Client-side assignee filtering
                assignee_lower = assignee.lower()
                filtered = []
                for rec in data.get("list", []):
                    raw = rec.get("Assignee", "")
                    # User fields can be a string, dict, or list of dicts
                    text = ""
                    if isinstance(raw, str):
                        text = raw
                    elif isinstance(raw, dict):
                        text = f"{raw.get('display_name', '')} {raw.get('email', '')}"
                    elif isinstance(raw, list):
                        parts = []
                        for u in raw:
                            if isinstance(u, dict):
                                parts.append(f"{u.get('display_name', '')} {u.get('email', '')}")
                            else:
                                parts.append(str(u))
                        text = " ".join(parts)
                    else:
                        text = str(raw)
                    if assignee_lower in text.lower():
                        filtered.append(rec)
                data["list"] = filtered
                if "pageInfo" in data:
                    data["pageInfo"]["totalRows"] = len(filtered)
            else:
                raise

        records = data.get("list", [])
        page_info = data.get("pageInfo", {})
        total = page_info.get("totalRows", len(records))

        content = [
            Grid(columns=2, children=[
                MetricCard(title="Assigned To", value=assignee),
                MetricCard(title="Tasks Found", value=str(total)),
            ]),
        ]
        if status:
            content.append(Alert(message=f"Filtered by status: {status}", variant="info"))
        content.append(Divider())

        tool_params = {"table_id": table_id, "assignee": assignee,
                       "status": status, "limit": limit}
        tbl = _records_to_table(records, page_info, "get_assigned_tasks", tool_params, limit, 0)
        if tbl:
            content.append(tbl)
        else:
            content.append(Text(content=f"No tasks found assigned to {assignee}.", variant="caption"))

        components = [Card(title=f"Tasks — {assignee}", content=content)]
        return {
            "_ui_components": [c.to_json() for c in components],
            "_data": {"records": records, "pageInfo": page_info, "assignee": assignee}
        }
    except Exception as e:
        return create_ui_response([Alert(message=f"Failed to get assigned tasks: {e}", variant="error")])


# ---------------------------------------------------------------------------
# Tool 9: create_record
# ---------------------------------------------------------------------------

def create_record(table_id: str, data: str, **kwargs) -> Dict[str, Any]:
    """Create a single record. `data` is a JSON string of field-value pairs."""
    try:
        client = _build_client(kwargs)
        record_data = json.loads(data) if isinstance(data, str) else data

        result = client.post(f"/api/v2/tables/{table_id}/records", json_body=record_data)

        new_id = result.get("Id", result.get("id", "unknown"))

        rows = []
        for key, val in record_data.items():
            rows.append([str(key), str(val)])

        components = [
            Card(
                title="Record Created",
                content=[
                    Alert(message=f"Successfully created record (ID: {new_id})", variant="success"),
                    MetricCard(title="New Record ID", value=str(new_id)),
                    Divider(),
                    Table(headers=["Field", "Value"], rows=rows),
                ]
            )
        ]
        return {
            "_ui_components": [c.to_json() for c in components],
            "_data": {"created": result}
        }
    except json.JSONDecodeError as e:
        return create_ui_response([Alert(message=f"Invalid JSON in data parameter: {e}", variant="error")])
    except Exception as e:
        return create_ui_response([Alert(message=f"Failed to create record: {e}", variant="error")])


# ---------------------------------------------------------------------------
# Tool 8: create_records_batch
# ---------------------------------------------------------------------------

def create_records_batch(table_id: str, records: str, **kwargs) -> Dict[str, Any]:
    """Create multiple records in one request. `records` is a JSON string of an array of objects."""
    try:
        client = _build_client(kwargs)
        records_data = json.loads(records) if isinstance(records, str) else records

        if not isinstance(records_data, list):
            return create_ui_response([Alert(message="records must be a JSON array of objects.", variant="error")])

        result = client.post(f"/api/v2/tables/{table_id}/records", json_body=records_data)

        created_ids = result if isinstance(result, list) else [result]
        rows = [[str(r.get("Id", r.get("id", "?")))] for r in created_ids]

        components = [
            Card(
                title="Batch Create Complete",
                content=[
                    Alert(message=f"Successfully created {len(created_ids)} record(s)", variant="success"),
                    MetricCard(title="Records Created", value=str(len(created_ids))),
                    Divider(),
                    Table(headers=["Created ID"], rows=rows),
                ]
            )
        ]
        return {
            "_ui_components": [c.to_json() for c in components],
            "_data": {"created": created_ids}
        }
    except json.JSONDecodeError as e:
        return create_ui_response([Alert(message=f"Invalid JSON in records parameter: {e}", variant="error")])
    except Exception as e:
        return create_ui_response([Alert(message=f"Failed to batch create records: {e}", variant="error")])


# ---------------------------------------------------------------------------
# Tool 9: update_record
# ---------------------------------------------------------------------------

def update_record(table_id: str, record_id: str, data: str, **kwargs) -> Dict[str, Any]:
    """Update fields of an existing record (partial update). `data` is a JSON string of fields to update."""
    try:
        client = _build_client(kwargs)
        update_data = json.loads(data) if isinstance(data, str) else data
        update_data["Id"] = int(record_id) if record_id.isdigit() else record_id

        result = client.patch(f"/api/v2/tables/{table_id}/records", json_body=update_data)

        rows = []
        for key, val in update_data.items():
            if key == "Id":
                continue
            rows.append([str(key), str(val)])

        components = [
            Card(
                title="Record Updated",
                content=[
                    Alert(message=f"Successfully updated record {record_id}", variant="success"),
                    MetricCard(title="Record ID", value=str(record_id)),
                    Divider(),
                    Table(headers=["Updated Field", "New Value"], rows=rows),
                ]
            )
        ]
        return {
            "_ui_components": [c.to_json() for c in components],
            "_data": {"updated": result}
        }
    except json.JSONDecodeError as e:
        return create_ui_response([Alert(message=f"Invalid JSON in data parameter: {e}", variant="error")])
    except Exception as e:
        return create_ui_response([Alert(message=f"Failed to update record: {e}", variant="error")])


# ---------------------------------------------------------------------------
# Tool 10: update_records_batch
# ---------------------------------------------------------------------------

def update_records_batch(table_id: str, records: str, **kwargs) -> Dict[str, Any]:
    """Batch update multiple records. `records` is a JSON array where each object must include an Id field."""
    try:
        client = _build_client(kwargs)
        records_data = json.loads(records) if isinstance(records, str) else records

        if not isinstance(records_data, list):
            return create_ui_response([Alert(message="records must be a JSON array of objects, each with an Id field.", variant="error")])

        missing_ids = [i for i, r in enumerate(records_data) if "Id" not in r and "id" not in r]
        if missing_ids:
            return create_ui_response([Alert(message=f"Records at indices {missing_ids} are missing the required Id field.", variant="error")])

        result = client.patch(f"/api/v2/tables/{table_id}/records", json_body=records_data)

        updated = result if isinstance(result, list) else [result]
        rows = [[str(r.get("Id", r.get("id", "?")))] for r in updated]

        components = [
            Card(
                title="Batch Update Complete",
                content=[
                    Alert(message=f"Successfully updated {len(updated)} record(s)", variant="success"),
                    MetricCard(title="Records Updated", value=str(len(updated))),
                    Divider(),
                    Table(headers=["Updated ID"], rows=rows),
                ]
            )
        ]
        return {
            "_ui_components": [c.to_json() for c in components],
            "_data": {"updated": updated}
        }
    except json.JSONDecodeError as e:
        return create_ui_response([Alert(message=f"Invalid JSON in records parameter: {e}", variant="error")])
    except Exception as e:
        return create_ui_response([Alert(message=f"Failed to batch update records: {e}", variant="error")])


# ---------------------------------------------------------------------------
# Tool 11: delete_records
# ---------------------------------------------------------------------------

def delete_records(table_id: str, record_ids: str, **kwargs) -> Dict[str, Any]:
    """Delete one or more records by ID. THIS IS IRREVERSIBLE.

    `record_ids` is a JSON array of record ID values, e.g. [1, 2, 3].
    """
    try:
        client = _build_client(kwargs)
        ids = json.loads(record_ids) if isinstance(record_ids, str) else record_ids

        if not isinstance(ids, list) or len(ids) == 0:
            return create_ui_response([Alert(message="record_ids must be a non-empty JSON array of IDs.", variant="error")])

        body = [{"Id": rid} for rid in ids]
        result = client.delete(f"/api/v2/tables/{table_id}/records", json_body=body)

        deleted = result if isinstance(result, list) else [result]
        rows = [[str(r.get("Id", r.get("id", "?")))] for r in deleted]

        components = [
            Card(
                title="Records Deleted",
                content=[
                    Alert(
                        message=f"Permanently deleted {len(deleted)} record(s). This action cannot be undone.",
                        variant="warning"
                    ),
                    MetricCard(title="Records Deleted", value=str(len(deleted))),
                    Divider(),
                    Table(headers=["Deleted ID"], rows=rows),
                ]
            )
        ]
        return {
            "_ui_components": [c.to_json() for c in components],
            "_data": {"deleted": deleted}
        }
    except json.JSONDecodeError as e:
        return create_ui_response([Alert(message=f"Invalid JSON in record_ids parameter: {e}", variant="error")])
    except Exception as e:
        return create_ui_response([Alert(message=f"Failed to delete records: {e}", variant="error")])


# ---------------------------------------------------------------------------
# Tool 12: list_linked_records
# ---------------------------------------------------------------------------

def list_linked_records(table_id: str, link_field_id: str, record_id: str,
                        limit: int = 100, offset: int = 0, **kwargs) -> Dict[str, Any]:
    """List records linked to a specific record via a link field."""
    try:
        client = _build_client(kwargs)
        params: Dict[str, Any] = {"limit": limit, "offset": offset}

        data = client.get(
            f"/api/v2/tables/{table_id}/links/{link_field_id}/records/{record_id}",
            params=params,
        )
        records = data.get("list", [])
        page_info = data.get("pageInfo", {})

        content = [
            MetricCard(title="Linked Records", value=str(page_info.get("totalRows", len(records)))),
            Divider(),
        ]

        tool_params = {"table_id": table_id, "link_field_id": link_field_id,
                       "record_id": record_id, "limit": limit, "offset": offset}
        tbl = _records_to_table(records, page_info, "list_linked_records", tool_params, limit, offset)
        if tbl:
            content.append(tbl)
        else:
            content.append(Text(content="No linked records found.", variant="caption"))

        components = [Card(title=f"Linked Records — {record_id}", content=content)]
        return {
            "_ui_components": [c.to_json() for c in components],
            "_data": {"records": records, "pageInfo": page_info}
        }
    except Exception as e:
        return create_ui_response([Alert(message=f"Failed to list linked records: {e}", variant="error")])


# ---------------------------------------------------------------------------
# Tool 13: link_records
# ---------------------------------------------------------------------------

def link_records(table_id: str, link_field_id: str, record_id: str,
                 linked_record_ids: str, **kwargs) -> Dict[str, Any]:
    """Create links between a record and other records via a link field.

    `linked_record_ids` is a JSON array of record IDs to link, e.g. [4, 5, 6].
    """
    try:
        client = _build_client(kwargs)
        ids = json.loads(linked_record_ids) if isinstance(linked_record_ids, str) else linked_record_ids

        if not isinstance(ids, list) or len(ids) == 0:
            return create_ui_response([Alert(message="linked_record_ids must be a non-empty JSON array of IDs.", variant="error")])

        body = [{"Id": rid} for rid in ids]
        client.post(
            f"/api/v2/tables/{table_id}/links/{link_field_id}/records/{record_id}",
            json_body=body,
        )

        components = [
            Card(
                title="Records Linked",
                content=[
                    Alert(
                        message=f"Successfully linked {len(ids)} record(s) to record {record_id}.",
                        variant="success"
                    ),
                    MetricCard(title="Links Created", value=str(len(ids))),
                ]
            )
        ]
        return {
            "_ui_components": [c.to_json() for c in components],
            "_data": {"linked": ids, "source_record": record_id}
        }
    except json.JSONDecodeError as e:
        return create_ui_response([Alert(message=f"Invalid JSON in linked_record_ids: {e}", variant="error")])
    except Exception as e:
        return create_ui_response([Alert(message=f"Failed to link records: {e}", variant="error")])


# ---------------------------------------------------------------------------
# Tool 14: unlink_records
# ---------------------------------------------------------------------------

def unlink_records(table_id: str, link_field_id: str, record_id: str,
                   linked_record_ids: str, **kwargs) -> Dict[str, Any]:
    """Remove links between a record and other records. This modifies relations.

    `linked_record_ids` is a JSON array of record IDs to unlink, e.g. [4, 5, 6].
    """
    try:
        client = _build_client(kwargs)
        ids = json.loads(linked_record_ids) if isinstance(linked_record_ids, str) else linked_record_ids

        if not isinstance(ids, list) or len(ids) == 0:
            return create_ui_response([Alert(message="linked_record_ids must be a non-empty JSON array of IDs.", variant="error")])

        body = [{"Id": rid} for rid in ids]
        client.delete(
            f"/api/v2/tables/{table_id}/links/{link_field_id}/records/{record_id}",
            json_body=body,
        )

        components = [
            Card(
                title="Records Unlinked",
                content=[
                    Alert(
                        message=f"Removed {len(ids)} link(s) from record {record_id}. This cannot be undone.",
                        variant="warning"
                    ),
                    MetricCard(title="Links Removed", value=str(len(ids))),
                ]
            )
        ]
        return {
            "_ui_components": [c.to_json() for c in components],
            "_data": {"unlinked": ids, "source_record": record_id}
        }
    except json.JSONDecodeError as e:
        return create_ui_response([Alert(message=f"Invalid JSON in linked_record_ids: {e}", variant="error")])
    except Exception as e:
        return create_ui_response([Alert(message=f"Failed to unlink records: {e}", variant="error")])


# ---------------------------------------------------------------------------
# Tool 15: upload_attachment
# ---------------------------------------------------------------------------

def upload_attachment(file_path: str, storage_path: str = "", **kwargs) -> Dict[str, Any]:
    """Upload a file attachment to NocoDB storage."""
    try:
        client = _build_client(kwargs)

        if not os.path.isfile(file_path):
            return create_ui_response([Alert(message=f"File not found: {file_path}", variant="error")])

        result = client.upload("/api/v2/storage/upload", file_path, storage_path)

        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)

        components = [
            Card(
                title="Attachment Uploaded",
                content=[
                    Alert(message=f"Successfully uploaded {file_name}", variant="success"),
                    Grid(columns=2, children=[
                        MetricCard(title="File Name", value=file_name),
                        MetricCard(title="File Size", value=f"{file_size:,} bytes"),
                    ]),
                ]
            )
        ]
        return {
            "_ui_components": [c.to_json() for c in components],
            "_data": {"upload_result": result}
        }
    except Exception as e:
        return create_ui_response([Alert(message=f"Upload failed: {e}", variant="error")])


# ---------------------------------------------------------------------------
# Tool Registry
# ---------------------------------------------------------------------------

TOOL_REGISTRY = {
    # --- Read (tools:read) ---
    "check_connection": {
        "function": check_connection,
        "description": "Verify NocoDB credentials are configured and the instance is reachable.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        },
        "scope": "tools:read"
    },
    "list_tables": {
        "function": list_tables,
        "description": "List all tables in a NocoDB base with their names and IDs. Use this to look up a table_id from a human-readable table name. If base_id is omitted, uses the configured NOCODB_BASE_ID credential.",
        "input_schema": {
            "type": "object",
            "properties": {
                "base_id": {"type": "string", "description": "The NocoDB base/project identifier. Optional if NOCODB_BASE_ID credential is set."}
            },
            "required": []
        },
        "scope": "tools:read"
    },
    "list_records": {
        "function": list_records,
        "description": "List records from a NocoDB table with pagination, field selection, sorting, and optional view filter.",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_id": {"type": "string", "description": "The NocoDB table identifier."},
                "fields": {"type": "string", "description": "Comma-separated field names to include (default: all)."},
                "sort": {"type": "string", "description": "Sort spec, e.g. 'field1,-field2' (- for descending)."},
                "view_id": {"type": "string", "description": "Optional view identifier to filter by."},
                "limit": {"type": "integer", "description": "Max records to return (default 100).", "default": 100},
                "offset": {"type": "integer", "description": "Number of records to skip (default 0).", "default": 0}
            },
            "required": ["table_id"]
        },
        "scope": "tools:read"
    },
    "get_record": {
        "function": get_record,
        "description": "Get a single record by its ID from a NocoDB table.",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_id": {"type": "string", "description": "The NocoDB table identifier."},
                "record_id": {"type": "string", "description": "The record ID to retrieve."},
                "fields": {"type": "string", "description": "Comma-separated field names to include (default: all)."}
            },
            "required": ["table_id", "record_id"]
        },
        "scope": "tools:read"
    },
    "count_records": {
        "function": count_records,
        "description": "Count total records in a NocoDB table, optionally with a filter expression.",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_id": {"type": "string", "description": "The NocoDB table identifier."},
                "where": {"type": "string", "description": "NocoDB filter syntax, e.g. (Status,eq,Active)."},
                "view_id": {"type": "string", "description": "Optional view identifier."}
            },
            "required": ["table_id"]
        },
        "scope": "tools:read"
    },
    "list_linked_records": {
        "function": list_linked_records,
        "description": "List records linked to a specific record via a link field relationship.",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_id": {"type": "string", "description": "The NocoDB table identifier."},
                "link_field_id": {"type": "string", "description": "The link field identifier for the relation."},
                "record_id": {"type": "string", "description": "The source record ID."},
                "limit": {"type": "integer", "description": "Max linked records to return (default 100).", "default": 100},
                "offset": {"type": "integer", "description": "Records to skip (default 0).", "default": 0}
            },
            "required": ["table_id", "link_field_id", "record_id"]
        },
        "scope": "tools:read"
    },

    # --- Search (tools:search) ---
    "get_assigned_tasks": {
        "function": get_assigned_tasks,
        "description": "Get tasks assigned to a specific person from a project tasks table. Searches the Assignee field and optionally filters by Status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_id": {"type": "string", "description": "The table ID of the Project Tasks table."},
                "assignee": {"type": "string", "description": "Full name of the person to find tasks for, e.g. 'Sam Armstrong'."},
                "status": {"type": "string", "description": "Optional status filter, e.g. 'In Progress', 'Todo', 'Done'."},
                "limit": {"type": "integer", "description": "Max records to return (default 100).", "default": 100}
            },
            "required": ["table_id", "assignee"]
        },
        "scope": "tools:search"
    },
    "search_records": {
        "function": search_records,
        "description": "Search records using NocoDB filter syntax. Example: (Status,eq,Active)~and(Priority,eq,High).",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_id": {"type": "string", "description": "The NocoDB table identifier."},
                "where": {"type": "string", "description": "NocoDB filter expression, e.g. (Status,eq,Active)~and(Priority,eq,High)."},
                "fields": {"type": "string", "description": "Comma-separated field names to include."},
                "sort": {"type": "string", "description": "Sort spec, e.g. 'field1,-field2'."},
                "limit": {"type": "integer", "description": "Max records to return (default 100).", "default": 100},
                "offset": {"type": "integer", "description": "Records to skip (default 0).", "default": 0}
            },
            "required": ["table_id", "where"]
        },
        "scope": "tools:search"
    },
    "search_records_simple": {
        "function": search_records_simple,
        "description": "Search records with a simplified interface: specify a field name, comparison operator, and value. Operators: eq, neq, like, nlike, gt, lt, gte, lte, is, isnot, null, notnull. For like/nlike, % wildcards are added automatically. For null/notnull, value is not needed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_id": {"type": "string", "description": "The NocoDB table identifier."},
                "field_name": {"type": "string", "description": "The field/column name to search on."},
                "operator": {"type": "string", "description": "Comparison operator (eq, neq, like, nlike, gt, lt, gte, lte, is, isnot, null, notnull)."},
                "value": {"type": "string", "description": "The value to compare against. Not needed for null/notnull operators."},
                "limit": {"type": "integer", "description": "Max records to return (default 100).", "default": 100}
            },
            "required": ["table_id", "field_name", "operator"]
        },
        "scope": "tools:search"
    },

    # --- Write (tools:write) ---
    "create_record": {
        "function": create_record,
        "description": "Create a single record in a NocoDB table. Provide field-value pairs as a JSON string.",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_id": {"type": "string", "description": "The NocoDB table identifier."},
                "data": {"type": "string", "description": "JSON string of field-value pairs, e.g. '{\"Name\": \"Task 1\", \"Status\": \"Todo\"}'."}
            },
            "required": ["table_id", "data"]
        },
        "scope": "tools:write"
    },
    "create_records_batch": {
        "function": create_records_batch,
        "description": "Create multiple records in one request. Provide a JSON array of objects.",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_id": {"type": "string", "description": "The NocoDB table identifier."},
                "records": {"type": "string", "description": "JSON array of record objects, e.g. '[{\"Name\": \"A\"}, {\"Name\": \"B\"}]'."}
            },
            "required": ["table_id", "records"]
        },
        "scope": "tools:write"
    },
    "update_record": {
        "function": update_record,
        "description": "Update fields of an existing record (partial update). Only specified fields are changed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_id": {"type": "string", "description": "The NocoDB table identifier."},
                "record_id": {"type": "string", "description": "The ID of the record to update."},
                "data": {"type": "string", "description": "JSON string of fields to update, e.g. '{\"Status\": \"Done\"}'."}
            },
            "required": ["table_id", "record_id", "data"]
        },
        "scope": "tools:write"
    },
    "update_records_batch": {
        "function": update_records_batch,
        "description": "Batch update multiple records. Each object in the array must include an Id field.",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_id": {"type": "string", "description": "The NocoDB table identifier."},
                "records": {"type": "string", "description": "JSON array of objects, each with Id and fields to update, e.g. '[{\"Id\": 1, \"Status\": \"Done\"}]'."}
            },
            "required": ["table_id", "records"]
        },
        "scope": "tools:write"
    },
    "delete_records": {
        "function": delete_records,
        "description": "IRREVERSIBLE: Delete one or more records by their IDs. This permanently removes data.",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_id": {"type": "string", "description": "The NocoDB table identifier."},
                "record_ids": {"type": "string", "description": "JSON array of record IDs to delete, e.g. [1, 2, 3]."}
            },
            "required": ["table_id", "record_ids"]
        },
        "scope": "tools:write"
    },
    "link_records": {
        "function": link_records,
        "description": "Create links between a source record and other records via a link field. Existing links are preserved.",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_id": {"type": "string", "description": "The NocoDB table identifier."},
                "link_field_id": {"type": "string", "description": "The link field identifier."},
                "record_id": {"type": "string", "description": "The source record ID to add links to."},
                "linked_record_ids": {"type": "string", "description": "JSON array of record IDs to link, e.g. [4, 5, 6]."}
            },
            "required": ["table_id", "link_field_id", "record_id", "linked_record_ids"]
        },
        "scope": "tools:write"
    },
    "unlink_records": {
        "function": unlink_records,
        "description": "Remove links between a source record and other records via a link field. This modifies relations and cannot be undone.",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_id": {"type": "string", "description": "The NocoDB table identifier."},
                "link_field_id": {"type": "string", "description": "The link field identifier."},
                "record_id": {"type": "string", "description": "The source record ID to remove links from."},
                "linked_record_ids": {"type": "string", "description": "JSON array of record IDs to unlink, e.g. [4, 5, 6]."}
            },
            "required": ["table_id", "link_field_id", "record_id", "linked_record_ids"]
        },
        "scope": "tools:write"
    },
    "upload_attachment": {
        "function": upload_attachment,
        "description": "Upload a file attachment to NocoDB storage.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Local file path to upload."},
                "storage_path": {"type": "string", "description": "Optional target storage path in NocoDB."}
            },
            "required": ["file_path"]
        },
        "scope": "tools:write"
    },
}
