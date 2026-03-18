"""Category: Parallel Multi-Agent Dispatch Benchmark.

Validates that the Orchestrator's parallel dispatch strategy
(asyncio.gather) reduces total latency compared to sequential
execution when invoking tools on multiple specialist agents.

Uses REAL MCP tool calls against the Weather, General, and Medical
specialist agents — no simulated delays.

Test cases:
  PD-B01: Sequential vs parallel latency comparison
  PD-B02: Parallel dispatch correctness (all results returned)
  PD-B03: Parallel speedup factor measurement
"""

import asyncio
import json
import os
import tempfile
import time
from typing import List, Tuple

import pytest

from shared.protocol import MCPRequest, MCPResponse

# Sidecar file for benchmark results (read by latex_export for console summary)
_BENCHMARK_FILE = os.path.join(tempfile.gettempdir(), "astral_parallel_dispatch_bench.json")


def _write_benchmark(key: str, data: dict):
    """Append benchmark data to the sidecar JSON file."""
    existing = {}
    if os.path.exists(_BENCHMARK_FILE):
        with open(_BENCHMARK_FILE, "r") as f:
            try:
                existing = json.load(f)
            except json.JSONDecodeError:
                pass
    existing[key] = data
    with open(_BENCHMARK_FILE, "w") as f:
        json.dump(existing, f, indent=2)

# ---------------------------------------------------------------------------
# Real agent MCP servers
# ---------------------------------------------------------------------------

from agents.weather.mcp_server import MCPServer as WeatherMCPServer
from agents.general.mcp_server import MCPServer as GeneralMCPServer
from agents.medical.mcp_server import MCPServer as MedicalMCPServer


def _build_request(tool_name: str, arguments: dict, request_id: str = "bench") -> MCPRequest:
    return MCPRequest(
        request_id=request_id,
        method="tools/call",
        params={"name": tool_name, "arguments": arguments},
    )


# Each entry: (server_instance, tool_name, arguments, label)
AGENT_CALLS: List[Tuple] = [
    (WeatherMCPServer(), "get_current_weather", {"city": "New York"}, "weather_agent"),
    (GeneralMCPServer(), "get_system_status", {}, "general_agent"),
    (MedicalMCPServer(), "search_patients", {"min_age": 30, "max_age": 60, "condition": "diabetes"}, "medical_agent"),
]


def _invoke_tool(server, tool_name: str, arguments: dict) -> MCPResponse:
    """Synchronously invoke a tool on an MCP server."""
    request = _build_request(tool_name, arguments, request_id=f"bench_{tool_name}")
    return server.process_request(request)


async def _invoke_tool_async(server, tool_name: str, arguments: dict) -> MCPResponse:
    """Run a synchronous MCP tool call in a thread (mirrors Orchestrator dispatch)."""
    return await asyncio.to_thread(_invoke_tool, server, tool_name, arguments)


# ---------------------------------------------------------------------------
# Test Suite
# ---------------------------------------------------------------------------

class TestParallelDispatch:
    """Benchmark sequential vs parallel multi-agent tool dispatch using real agents."""

    @pytest.mark.asyncio
    async def test_sequential_vs_parallel_latency(self):
        """PD-B01: Parallel dispatch is faster than sequential dispatch.

        Dispatches real MCP tool calls to the Weather, General, and Medical
        agents first sequentially (awaiting each in order) then in parallel
        (via asyncio.gather), and asserts that the parallel wall-clock time
        is lower.
        """
        # --- Sequential execution ---
        sequential_start = time.perf_counter()
        sequential_results = []
        for server, tool, args, _label in AGENT_CALLS:
            result = await _invoke_tool_async(server, tool, args)
            sequential_results.append(result)
        sequential_ms = (time.perf_counter() - sequential_start) * 1000

        # --- Parallel execution (mirrors Orchestrator's asyncio.gather pattern) ---
        parallel_start = time.perf_counter()
        parallel_results = await asyncio.gather(
            *[_invoke_tool_async(server, tool, args) for server, tool, args, _label in AGENT_CALLS]
        )
        parallel_ms = (time.perf_counter() - parallel_start) * 1000

        speedup = sequential_ms / parallel_ms
        _write_benchmark("latency", {
            "sequential_ms": round(sequential_ms, 1),
            "parallel_ms": round(parallel_ms, 1),
            "speedup": round(speedup, 2),
            "agent_count": len(AGENT_CALLS),
        })

        # Parallel must be faster than sequential
        assert parallel_ms < sequential_ms, (
            f"Parallel ({parallel_ms:.1f}ms) should be faster than "
            f"sequential ({sequential_ms:.1f}ms)"
        )

        # Both should return the same number of results
        assert len(sequential_results) == len(list(parallel_results))

    @pytest.mark.asyncio
    async def test_parallel_dispatch_correctness(self):
        """PD-B02: All parallel results are returned without errors.

        Verifies that asyncio.gather preserves result ordering and that
        every dispatched tool call produces a successful MCP response
        from the real agent.
        """
        results = await asyncio.gather(
            *[_invoke_tool_async(server, tool, args) for server, tool, args, _label in AGENT_CALLS]
        )

        assert len(results) == len(AGENT_CALLS)

        for i, ((_server, _tool, _args, label), response) in enumerate(zip(AGENT_CALLS, results)):
            assert isinstance(response, MCPResponse), (
                f"Result {i} ({label}) is not an MCPResponse"
            )
            assert response.error is None, (
                f"Result {i} ({label}) returned error: {response.error}"
            )
            assert response.result is not None or response.ui_components is not None, (
                f"Result {i} ({label}) has no result data"
            )

    @pytest.mark.asyncio
    async def test_parallel_speedup_factor(self):
        """PD-B03: Parallel speedup is consistent across multiple trials.

        Runs N trials of sequential vs parallel dispatch against real agents
        and verifies the average speedup exceeds 1.0x (i.e., parallel is
        consistently faster than sequential).
        """
        n_trials = 3
        speedups = []

        for _ in range(n_trials):
            # Sequential
            seq_start = time.perf_counter()
            for server, tool, args, _label in AGENT_CALLS:
                await _invoke_tool_async(server, tool, args)
            seq_ms = (time.perf_counter() - seq_start) * 1000

            # Parallel
            par_start = time.perf_counter()
            await asyncio.gather(
                *[_invoke_tool_async(s, t, a) for s, t, a, _ in AGENT_CALLS]
            )
            par_ms = (time.perf_counter() - par_start) * 1000

            speedups.append(seq_ms / par_ms)

        avg_speedup = sum(speedups) / len(speedups)
        _write_benchmark("speedup_trials", {
            "n_trials": n_trials,
            "avg_speedup": round(avg_speedup, 2),
            "individual": [round(s, 2) for s in speedups],
        })

        # Observed speedup should consistently exceed 1.0x
        assert avg_speedup > 1.0, (
            f"Average speedup {avg_speedup:.2f}x should exceed 1.0x"
        )
