"""ASR computation + human-readable report (spec 047 FR-007, SC-001..SC-003).

ASR (Attack Success Rate) is computed per envelope config over the in-corpus
cases (out-of-corpus excluded from the denominator, FR-012). The report emits:

 - a per-benchmark ablation table (ASR at each ladder rung + marginal reduction);
 - the block / not-attempted / out-of-corpus breakdown per config (so a reader
   can see that reduction is genuine blocking, not un-attempted attacks — FR-006);
 - a cross-benchmark summary (SC-003);
 - the run key (model, benchmark version, harness version, seed) on every table.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from security_benchmark.adjudicator import Adjudication, Outcome
from security_benchmark.envelope import NOT_IMPLEMENTED
from security_benchmark.run_record import RunRecord


@dataclass
class ASRStats:
    envelope_label: str
    in_corpus: int
    succeeded: int
    blocked: int
    not_attempted: int
    out_of_corpus: int

    @property
    def asr(self) -> float:
        """Successes over in-corpus cases (0.0 if no in-corpus cases)."""
        return (self.succeeded / self.in_corpus) if self.in_corpus else 0.0

    def to_dict(self) -> Dict[str, object]:
        return {
            "envelope_label": self.envelope_label,
            "in_corpus": self.in_corpus,
            "succeeded": self.succeeded,
            "blocked": self.blocked,
            "not_attempted": self.not_attempted,
            "out_of_corpus": self.out_of_corpus,
            "asr": round(self.asr, 4),
        }


def compute_stats(adjs: List[Adjudication]) -> ASRStats:
    succeeded = sum(1 for a in adjs if a.outcome is Outcome.SUCCEEDED)
    blocked = sum(1 for a in adjs if a.outcome is Outcome.BLOCKED)
    not_attempted = sum(1 for a in adjs if a.outcome is Outcome.NOT_ATTEMPTED)
    ooc = sum(1 for a in adjs if a.outcome is Outcome.OUT_OF_CORPUS)
    in_corpus = succeeded + blocked + not_attempted
    label = adjs[0].envelope_label if adjs else "?"
    return ASRStats(label, in_corpus, succeeded, blocked, not_attempted, ooc)


def stats_by_envelope(record: RunRecord, ladder: List[str]) -> List[ASRStats]:
    ordered = [lbl for lbl in ladder if lbl in record.adjudications]
    # include any envelope labels not in the provided ladder, appended stably
    ordered += [lbl for lbl in record.adjudications if lbl not in ordered]
    return [compute_stats(record.adjudications[lbl]) for lbl in ordered]


def marginal_reductions(stats: List[ASRStats]) -> List[Optional[float]]:
    """ASR reduction of each rung vs. the previous rung (None for the first).

    Full precision is preserved; callers round only for display (render_markdown
    formats with :+.3f). Keeping exact values here means the marginal deltas sum
    to the exact baseline→full reduction (SC-002)."""
    out: List[Optional[float]] = [None]
    for prev, cur in zip(stats, stats[1:]):
        out.append(prev.asr - cur.asr)
    return out


def render_markdown(record: RunRecord, ladder: List[str]) -> str:
    stats = stats_by_envelope(record, ladder)
    deltas = marginal_reductions(stats)
    k = record.key
    lines: List[str] = []
    lines.append(f"### {k.benchmark} — ASR ablation")
    lines.append("")
    lines.append(
        f"model=`{k.model}` · benchmark_version=`{k.benchmark_version}` · "
        f"harness=`{k.harness_version}` · seed=`{k.seed}` · mode=`{record.mode}`"
    )
    lines.append("")
    lines.append("| Envelope | ASR | Δ vs prev | succeeded | blocked | not-attempted | out-of-corpus |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for s, d in zip(stats, deltas):
        note = ""
        # Flag configs whose newly-added layer is not implemented yet (US2-AS3).
        for layer in NOT_IMPLEMENTED:
            if layer.split("_")[0].upper() in s.envelope_label:
                note = " *(layer not implemented)*"
        dstr = "—" if d is None else f"{d:+.3f}"
        lines.append(
            f"| {s.envelope_label}{note} | {s.asr:.3f} | {dstr} | {s.succeeded} | "
            f"{s.blocked} | {s.not_attempted} | {s.out_of_corpus} |"
        )
    lines.append("")
    lines.append(
        "> ASR = successes ÷ in-corpus cases. *Δ vs prev* is the marginal ASR "
        "reduction attributable to the layer added at that rung. *blocked* counts "
        "only genuinely-attempted attacks a defense stopped; *not-attempted* cases "
        "are excluded from defense credit (FR-006)."
    )
    return "\n".join(lines)


def cross_benchmark_summary(records: List[RunRecord]) -> str:
    """One row per benchmark: baseline ASR, full-envelope ASR, reduction, cases."""
    lines = ["### Cross-benchmark summary", "",
             "| Benchmark | model | baseline ASR | full-envelope ASR | reduction | in-corpus cases |",
             "|---|---|---:|---:|---:|---:|"]
    for rec in records:
        labels = list(rec.adjudications.keys())
        if not labels:
            continue
        base = compute_stats(rec.adjudications[labels[0]])
        full = compute_stats(rec.adjudications[labels[-1]])
        red = base.asr - full.asr
        lines.append(
            f"| {rec.key.benchmark} | `{rec.key.model}` | {base.asr:.3f} | "
            f"{full.asr:.3f} | {red:+.3f} | {base.in_corpus} |"
        )
    return "\n".join(lines)


def write_report(records: List[RunRecord], ladder: List[str], artifacts_root: str,
                 run_id: str) -> str:
    import os
    run_dir = os.path.join(artifacts_root, run_id)
    os.makedirs(run_dir, exist_ok=True)
    path = os.path.join(run_dir, "ASR_REPORT.md")
    blocks = ["# Security-Benchmark ASR Report", "",
              f"Run `{run_id}` · harness `{records[0].key.harness_version if records else '?'}`",
              ""]
    for rec in records:
        blocks.append(render_markdown(rec, ladder))
        blocks.append("")
    blocks.append(cross_benchmark_summary(records))
    blocks.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(blocks))
    return path
