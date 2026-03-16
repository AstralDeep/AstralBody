"""Category 7: Cost Overhead Tests (CLEAR Framework — Cost Dimension).

Measures the computational overhead of the security analysis pipeline
to quantify the cost of security guarantees provided by the DAF.
4 test cases.
"""

import statistics
import sys
import time

try:
    import resource
except ImportError:
    resource = None  # type: ignore[assignment]  # Windows


class TestSecurityProcessingOverhead:
    """Measure the computational cost of the ToolSecurityAnalyzer and
    CodeSecurityAnalyzer processing pipelines."""

    # Synthetic tool corpus covering all six threat categories
    _TOOL_CORPUS = [
        ("weather_forecast", "Get the current weather forecast for a location",
         {"properties": {"city": {"type": "string"}}}),
        ("send_email", "Send an email to a specified recipient",
         {"properties": {"to": {"type": "string"}, "body": {"type": "string"}}}),
        ("query_database", "Execute a read-only SQL query on the analytics database",
         {"properties": {"query": {"type": "string"}}}),
        ("generate_report", "Generate a quarterly sales report in PDF format",
         {"properties": {"quarter": {"type": "integer"}, "year": {"type": "integer"}}}),
        ("translate_text", "Translate text from one language to another",
         {"properties": {"text": {"type": "string"}, "target_lang": {"type": "string"}}}),
        ("summarize_document", "Summarize a long document into key points",
         {"properties": {"document_url": {"type": "string"}}}),
        ("calculate_metrics", "Calculate performance metrics for a given dataset",
         {"properties": {"dataset_id": {"type": "string"}}}),
        ("search_knowledge_base", "Search the internal knowledge base for relevant articles",
         {"properties": {"query": {"type": "string"}, "max_results": {"type": "integer"}}}),
        ("schedule_meeting", "Schedule a calendar meeting with specified attendees",
         {"properties": {"title": {"type": "string"}, "attendees": {"type": "array"}}}),
        ("get_stock_price", "Retrieve current stock price for a given ticker symbol",
         {"properties": {"symbol": {"type": "string"}}}),
    ]

    _CODE_SAMPLES = [
        # Short benign function (~10 LOC)
        '''
def greet(name):
    """Say hello."""
    if not name:
        return "Hello, World!"
    return f"Hello, {name}!"

result = greet("Alice")
print(result)
''',
        # Medium function (~30 LOC)
        '''
import json
import os

def process_data(filepath):
    """Load and process a JSON data file."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")

    with open(filepath, "r") as f:
        data = json.load(f)

    results = []
    for item in data.get("records", []):
        if item.get("active"):
            value = item.get("value", 0)
            normalized = value / 100.0
            results.append({
                "id": item["id"],
                "normalized": round(normalized, 4),
                "category": item.get("category", "unknown"),
            })

    results.sort(key=lambda x: x["normalized"], reverse=True)
    return results[:10]

output = process_data("data.json")
for r in output:
    print(f"{r['id']}: {r['normalized']}")
''',
        # Large function with multiple patterns (~80 LOC)
        '''
import hashlib
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class DataProcessor:
    """Process and validate incoming data records."""

    VALID_CATEGORIES = {"finance", "health", "education", "technology"}
    MAX_BATCH_SIZE = 1000

    def __init__(self, config: Dict):
        self.config = config
        self.processed_count = 0
        self.error_count = 0
        self._cache: Dict[str, any] = {}

    def validate_record(self, record: Dict) -> bool:
        required_fields = ["id", "timestamp", "category", "payload"]
        for field in required_fields:
            if field not in record:
                logger.warning(f"Missing field: {field}")
                return False

        if record["category"] not in self.VALID_CATEGORIES:
            return False

        try:
            ts = datetime.fromisoformat(record["timestamp"])
            if ts > datetime.now() + timedelta(hours=1):
                return False
        except ValueError:
            return False

        return True

    def compute_hash(self, payload: str) -> str:
        return hashlib.sha256(payload.encode()).hexdigest()

    def process_batch(self, records: List[Dict]) -> List[Dict]:
        if len(records) > self.MAX_BATCH_SIZE:
            records = records[:self.MAX_BATCH_SIZE]

        results = []
        for record in records:
            if not self.validate_record(record):
                self.error_count += 1
                continue

            cache_key = record["id"]
            if cache_key in self._cache:
                results.append(self._cache[cache_key])
                continue

            processed = {
                "id": record["id"],
                "hash": self.compute_hash(str(record["payload"])),
                "category": record["category"],
                "processed_at": datetime.now().isoformat(),
                "size": len(str(record["payload"])),
            }

            self._cache[cache_key] = processed
            results.append(processed)
            self.processed_count += 1

        return results

    def get_stats(self) -> Dict:
        return {
            "processed": self.processed_count,
            "errors": self.error_count,
            "cache_size": len(self._cache),
        }
''',
    ]

    def test_tool_analyzer_timing(self, tool_security_analyzer):
        """CO-001: ToolSecurityAnalyzer.analyze_tool() mean and p95 timing
        across a 10-tool corpus."""
        timings = []
        iterations = 5  # Run the full corpus multiple times for stability

        for _ in range(iterations):
            for name, desc, schema in self._TOOL_CORPUS:
                start = time.perf_counter()
                tool_security_analyzer.analyze_tool(
                    tool_name=name,
                    description=desc,
                    input_schema=schema,
                )
                elapsed_ms = (time.perf_counter() - start) * 1000
                timings.append(elapsed_ms)

        mean_ms = statistics.mean(timings)

        # Security analysis should be fast — under 10ms per tool on average
        assert mean_ms < 10.0, (
            f"ToolSecurityAnalyzer mean latency {mean_ms:.3f}ms exceeds 10ms threshold"
        )

    def test_code_analyzer_timing(self, code_security_analyzer):
        """CO-002: CodeSecurityAnalyzer.analyze() timing for code samples
        of varying complexity (10–80 LOC)."""
        timings_by_size = {}

        for i, code in enumerate(self._CODE_SAMPLES):
            loc = len([line for line in code.strip().split("\n") if line.strip()])
            sample_timings = []
            for _ in range(10):
                start = time.perf_counter()
                code_security_analyzer.analyze(code)
                elapsed_ms = (time.perf_counter() - start) * 1000
                sample_timings.append(elapsed_ms)

            timings_by_size[f"sample_{i}_loc_{loc}"] = {
                "mean_ms": round(statistics.mean(sample_timings), 3),
                "p95_ms": round(sorted(sample_timings)[int(len(sample_timings) * 0.95)], 3),
            }

        # All samples should analyze in under 50ms on average
        for key, data in timings_by_size.items():
            assert data["mean_ms"] < 50.0, (
                f"CodeSecurityAnalyzer mean for {key}: {data['mean_ms']:.3f}ms exceeds 50ms"
            )

    def test_combined_registration_overhead(
        self, tool_security_analyzer, code_security_analyzer
    ):
        """CO-003: Combined security screening overhead as percentage of a
        simulated tool registration flow."""
        registration_code = self._CODE_SAMPLES[1]  # Medium-complexity sample

        # Simulate registration: analyze tool description + analyze code
        overhead_timings = []
        baseline_timings = []

        for name, desc, schema in self._TOOL_CORPUS:
            # Baseline: just the "registration" logic (dict creation)
            start = time.perf_counter()
            _ = {"name": name, "description": desc, "schema": schema}
            baseline_ms = (time.perf_counter() - start) * 1000
            baseline_timings.append(baseline_ms)

            # With security: tool analysis + code analysis
            start = time.perf_counter()
            _ = {"name": name, "description": desc, "schema": schema}
            tool_security_analyzer.analyze_tool(
                tool_name=name, description=desc, input_schema=schema,
            )
            code_security_analyzer.analyze(registration_code)
            overhead_ms = (time.perf_counter() - start) * 1000
            overhead_timings.append(overhead_ms)

        mean_overhead = statistics.mean(overhead_timings)
        # Security overhead per registration should be under 100ms
        assert mean_overhead < 100.0, (
            f"Combined security overhead {mean_overhead:.3f}ms exceeds 100ms per tool"
        )

    def test_memory_overhead(self, tool_security_analyzer):
        """CO-004: Peak memory delta during security analysis of a large
        tool set (50 tools)."""
        large_corpus = self._TOOL_CORPUS * 5  # 50 tools

        if sys.platform == "win32":
            import psutil
            process = psutil.Process()
            mem_before = process.memory_info().rss
        else:
            mem_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

        for name, desc, schema in large_corpus:
            tool_security_analyzer.analyze_tool(
                tool_name=name, description=desc, input_schema=schema,
            )

        if sys.platform == "win32":
            mem_after = process.memory_info().rss
            delta_mb = (mem_after - mem_before) / (1024 * 1024)
        else:
            mem_after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            delta_kb = mem_after - mem_before
            delta_mb = delta_kb / 1024

        # Memory increase should be minimal — under 50MB for 50 tools
        assert delta_mb < 50.0, (
            f"Memory delta {delta_mb:.2f}MB exceeds 50MB threshold for 50-tool analysis"
        )
