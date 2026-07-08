"""Summarize perf_span log lines into per-span P50/P95 (feature 052, T003).

Reads log text from stdin or the files given as arguments, extracts lines of
the form ``perf <name> duration_ms=<int> ...``, and prints count/P50/P95/max
per span name. Used by the measurement protocol in
specs/052-perf-comment-hygiene/quickstart.md.
"""

import fileinput
import re
import sys
from collections import defaultdict

_LINE = re.compile(r"perf (\S+) duration_ms=(\d+)")


def percentile(sorted_values, fraction):
    """Nearest-rank percentile of an already-sorted list."""
    if not sorted_values:
        return 0
    rank = max(0, min(len(sorted_values) - 1, round(fraction * (len(sorted_values) - 1))))
    return sorted_values[rank]


def main():
    """Aggregate perf lines from stdin/args and print a per-span summary table."""
    spans = defaultdict(list)
    for line in fileinput.input():
        match = _LINE.search(line)
        if match:
            spans[match.group(1)].append(int(match.group(2)))
    if not spans:
        print("no perf lines found", file=sys.stderr)
        return 1
    width = max(len(name) for name in spans)
    print(f"{'span'.ljust(width)}  count  p50_ms  p95_ms  max_ms")
    for name in sorted(spans):
        values = sorted(spans[name])
        print(
            f"{name.ljust(width)}  {len(values):5d}  {percentile(values, 0.50):6d}"
            f"  {percentile(values, 0.95):6d}  {values[-1]:6d}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
