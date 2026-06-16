"""Deterministic scripted LLM (T011 / D2/D3).

Replaces the model's token output only — every tool the orchestrator dispatches
runs for real. The scripted policy implements the two-step chain:

  1. call the real reader for the file's category (real dispatch + audit + the
     permission gate run);
  2. on the next round, call the real ``generate_dynamic_chart`` with data read
     back from the uploaded file (so the component is a *product tool's* output
     whose data derives from the *actual file* — provenance + re-executability);
  3. a final no-tool turn closes the loop.

For non-tabular personas (no chart spec) the reader output is summarized into a
final-response component built from the real file content.
"""
from __future__ import annotations

import csv
import json
import types
from typing import Any, Callable, Dict, List, Optional

from verification.personas import Persona

# Category -> built-in reader tool (mirrors parser_registry.BUILTIN_CATEGORY_TOOL).
_READER_FOR = {
    "spreadsheet": "read_spreadsheet",
    "document": "read_document",
    "text": "read_text",
    "image": "read_image",
}


def _usage() -> Any:
    return types.SimpleNamespace(total_tokens=0, prompt_tokens=0, completion_tokens=0)


def _tool_call(name: str, args: Dict[str, Any]) -> Any:
    return types.SimpleNamespace(
        id=f"call_{name}",
        type="function",
        function=types.SimpleNamespace(name=name, arguments=json.dumps(args)),
    )


def _msg(content: Optional[str], tool_calls: Optional[List[Any]]) -> Any:
    return types.SimpleNamespace(
        content=content, tool_calls=tool_calls, reasoning_content=None
    )


def _csv_as_records(path: str) -> List[Dict[str, Any]]:
    """Read the uploaded CSV back into list-of-dict records (file-derived data)."""
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def _coerce_numeric(records: List[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
    out = []
    for r in records:
        r2 = dict(r)
        try:
            r2[key] = float(str(r.get(key, "")).replace(",", ""))
        except (TypeError, ValueError):
            pass
        out.append(r2)
    return out


def scripted_llm_for(
    persona: Persona, attachment_id: str, fixture_path: str
) -> Callable[..., Any]:
    """Build a deterministic ``_call_llm`` coroutine for one scenario.

    The returned coroutine matches the orchestrator's
    ``_call_llm(websocket, messages, tools_desc=None, temperature=None,
    feature="tool_dispatch")`` contract and returns ``(message, usage)``.
    """
    fixture = persona.fixture
    reader = _READER_FOR.get(fixture.category)
    chart = fixture.chart
    state: Dict[str, int] = {"tool_rounds": 0}

    async def _call_llm(websocket, messages, tools_desc=None, temperature=None,
                        feature: str = "tool_dispatch"):
        # The adaptive UI designer (029) also calls _call_llm; tell it to converge
        # immediately so component output is not rewritten and stays deterministic.
        if feature != "tool_dispatch":
            return _msg("DONE", None), _usage()

        state["tool_rounds"] += 1
        rnd = state["tool_rounds"]

        # Round 1: dispatch the real reader for this file's category.
        if rnd == 1 and reader is not None:
            return _msg(None, [_tool_call(reader, {"attachment_id": attachment_id})]), _usage()

        # Round 2: for tabular fixtures, render a real chart from file-derived data.
        if rnd == 2 and chart is not None:
            try:
                records = _csv_as_records(fixture_path)
                if chart.get("y_key"):
                    records = _coerce_numeric(records, chart["y_key"])
            except Exception:
                records = []
            if records:
                args = {
                    "data": records,
                    "x_key": chart["x_key"],
                    "title": f"{persona.display_name}: breakdown",
                }
                if chart.get("y_key"):
                    args["y_key"] = chart["y_key"]
                return _msg(None, [_tool_call("generate_dynamic_chart", args)]), _usage()

        # Final round: a short natural-language answer (no further tools).
        return _msg(
            f"Done — analyzed {fixture.filename} and produced the components above.",
            None,
        ), _usage()

    return _call_llm
