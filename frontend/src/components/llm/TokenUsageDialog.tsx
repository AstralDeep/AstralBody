/**
 * TokenUsageDialog — observed cumulative token-usage display
 * (feature 006-user-llm-config, US3 P2).
 *
 * Renders three counters (session / today / lifetime), an
 * "unknown calls" tally for upstream responses that omitted the
 * `usage` block, and a per-model breakdown table. A "Reset usage stats"
 * button zeroes all four counters and clears the per-model map; it
 * does NOT touch the user's saved API key / base URL / model.
 *
 * If the user has no personal LLM configuration, the dialog renders a
 * placeholder explaining that operator-default calls are NOT tracked
 * here (FR-016 — counters MUST NOT include calls served from the
 * operator's default credentials).
 *
 * Constitution VIII compliance: uses only existing styling primitives.
 */
import { RotateCcw, Sparkles } from "lucide-react";

import { useTokenUsage } from "../../hooks/useTokenUsage";

export interface TokenUsageDialogProps {
    hasPersonalConfig: boolean;
}

function formatNumber(n: number): string {
    return n.toLocaleString();
}

export default function TokenUsageDialog({ hasPersonalConfig }: TokenUsageDialogProps) {
    const { usage, reset } = useTokenUsage();

    if (!hasPersonalConfig) {
        return (
            <div className="rounded-xl border border-white/10 bg-white/5 p-4 text-xs text-astral-muted">
                <div className="flex items-center gap-2 text-astral-muted/80 font-medium mb-1">
                    <Sparkles size={12} />
                    Token usage
                </div>
                <p>
                    Not tracked while using the operator default. Save a personal
                    configuration above to start tracking your own token spend.
                </p>
            </div>
        );
    }

    const perModel = Object.entries(usage.perModel).sort((a, b) => b[1] - a[1]);

    return (
        <div className="rounded-xl border border-white/10 bg-white/5 p-4 space-y-3">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-astral-muted/90 text-xs font-medium">
                    <Sparkles size={12} />
                    Token usage
                </div>
                <button
                    type="button"
                    onClick={() => reset()}
                    className="flex items-center gap-1 text-[10px] px-2 py-1 rounded border border-white/10 text-astral-muted hover:bg-white/5 hover:text-white"
                    aria-label="Reset usage stats"
                >
                    <RotateCcw size={10} />
                    Reset
                </button>
            </div>

            <div className="grid grid-cols-3 gap-3">
                <Stat label="Session" value={formatNumber(usage.session)} />
                <Stat label="Today" value={formatNumber(usage.today)} />
                <Stat label="Lifetime" value={formatNumber(usage.lifetime)} />
            </div>

            {usage.unknownCalls > 0 && (
                <div className="text-[10px] text-astral-muted/80">
                    {usage.unknownCalls} call{usage.unknownCalls === 1 ? "" : "s"} returned no usage block (model didn't report tokens)
                </div>
            )}

            {perModel.length > 0 && (
                <div>
                    <div className="text-[10px] text-astral-muted/70 mb-1">Per model (lifetime)</div>
                    <div className="space-y-1">
                        {perModel.map(([m, n]) => (
                            <div
                                key={m}
                                className="flex items-center justify-between text-[11px] py-1 border-b border-white/5 last:border-0"
                            >
                                <span className="text-white/80 font-mono truncate">{m}</span>
                                <span className="text-astral-muted">{formatNumber(n)} tokens</span>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            <div className="text-[10px] text-astral-muted/60 leading-relaxed pt-1 border-t border-white/5">
                Counters are device-local. They are derived from each LLM
                response's <code className="text-astral-muted">usage.total_tokens</code>{" "}
                field and reset only when you click Reset.
            </div>
        </div>
    );
}

function Stat({ label, value }: { label: string; value: string }) {
    return (
        <div className="rounded-lg bg-astral-bg/50 border border-white/5 px-3 py-2">
            <div className="text-[10px] text-astral-muted/70">{label}</div>
            <div className="text-sm font-semibold text-white tabular-nums">{value}</div>
        </div>
    );
}
