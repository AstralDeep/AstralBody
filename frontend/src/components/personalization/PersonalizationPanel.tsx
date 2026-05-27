/**
 * PersonalizationPanel — full-screen overlay to edit the agentic-soul
 * params (feature 025) without hand-crafting web requests:
 *   • Profile & Soul — profession, goals, personality (tone/directness/verbosity/notes)
 *   • Skills — toggle agent tools you're authorized for
 *   • Schedule — list / create / pause / resume / delete scheduled jobs
 *   • Memory & Dreaming — dreaming toggle + manual sweep + delete memories
 *
 * Mirrors the LlmSettingsPanel pattern (feature 006): no router, full-screen
 * modal, Escape to close, existing Tailwind primitives only (Constitution VIII).
 * All writes go through the REST endpoints in api/personalization.ts; PHI is
 * rejected server-side and surfaced inline.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Sparkles, X, AlertTriangle, Trash2, Play, Pause, ChevronDown } from "lucide-react";

import * as api from "../../api/personalization";

export interface PersonalizationPanelProps {
    open: boolean;
    accessToken: string | undefined;
    onClose: () => void;
}

type Tab = "profile" | "schedule" | "memory";

const TABS: Array<{ id: Tab; label: string }> = [
    { id: "profile", label: "Profile & Soul" },
    { id: "schedule", label: "Schedule" },
    { id: "memory", label: "Memory & Dreaming" },
];

const inputClass =
    "w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder:text-astral-muted focus:outline-none focus:border-astral-primary";
interface SelectOption { value: string; label: string; }

/**
 * Fully-themed dropdown — replaces the native <select>, whose popup chrome
 * (frame, selected-row highlight) can't be dark-styled cross-browser. No new
 * dependency: a button + an absolutely-positioned list, React + Tailwind only.
 */
function DarkSelect({ value, options, onChange }: {
    value: string;
    options: SelectOption[];
    onChange: (v: string) => void;
}) {
    const [open, setOpen] = useState(false);
    const ref = useRef<HTMLDivElement | null>(null);
    useEffect(() => {
        if (!open) return;
        const onDoc = (e: MouseEvent) => {
            if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
        };
        const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
        document.addEventListener("mousedown", onDoc);
        document.addEventListener("keydown", onKey);
        return () => {
            document.removeEventListener("mousedown", onDoc);
            document.removeEventListener("keydown", onKey);
        };
    }, [open]);
    const current = options.find((o) => o.value === value);
    return (
        <div className="relative" ref={ref}>
            <button type="button" onClick={() => setOpen((o) => !o)}
                className={`${inputClass} flex items-center justify-between`}>
                <span className="truncate">{current?.label ?? options[0]?.label}</span>
                <ChevronDown size={14} className="text-astral-muted flex-shrink-0 ml-2" />
            </button>
            {open && (
                <div className="absolute z-20 mt-1 w-full rounded-lg border border-white/10 bg-astral-surface shadow-2xl max-h-56 overflow-y-auto py-1">
                    {options.map((o) => (
                        <button key={o.value} type="button"
                            onClick={() => { onChange(o.value); setOpen(false); }}
                            className={`w-full text-left px-3 py-1.5 text-sm text-white hover:bg-white/10 ${o.value === value ? "bg-white/5" : ""}`}>
                            {o.label}
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
}

function toOptions(values: string[], withDefault = true): SelectOption[] {
    const opts = values.map((v) => ({ value: v, label: v }));
    return withDefault ? [{ value: "", label: "default" }, ...opts] : opts;
}
const labelClass = "block text-[11px] font-semibold uppercase tracking-wide text-astral-muted mb-1";
const btnPrimary =
    "px-4 py-2 rounded-lg text-sm font-medium bg-astral-primary hover:bg-astral-primary/80 text-white disabled:opacity-50";

function fmtTime(ms: number | null): string {
    if (!ms) return "—";
    return new Date(ms).toLocaleString();
}

// ── Profile & Soul ─────────────────────────────────────────────────────────

function ProfileTab({ token }: { token: string }) {
    const [profession, setProfession] = useState("");
    const [goals, setGoals] = useState("");
    const [tone, setTone] = useState("");
    const [directness, setDirectness] = useState("");
    const [verbosity, setVerbosity] = useState("");
    const [notes, setNotes] = useState("");
    const [status, setStatus] = useState<"loading" | "idle" | "saving" | "saved">("loading");
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        let cancel = false;
        api.getProfile(token).then((p) => {
            if (cancel) return;
            setProfession(p.profession ?? "");
            setGoals((p.goals ?? []).join("\n"));
            setTone(p.personality?.tone ?? "");
            setDirectness(p.personality?.directness ?? "");
            setVerbosity(p.personality?.verbosity ?? "");
            setNotes(p.personality?.notes ?? "");
            setStatus("idle");
        }).catch((e) => { if (!cancel) { setError(String(e.message ?? e)); setStatus("idle"); } });
        return () => { cancel = true; };
    }, [token]);

    const save = useCallback(async () => {
        setStatus("saving");
        setError(null);
        try {
            await api.updateProfile(token, {
                profession: profession.trim() || null,
                goals: goals.split("\n").map((g) => g.trim()).filter(Boolean),
                personality: {
                    tone: tone || null, directness: directness || null,
                    verbosity: verbosity || null, notes: notes.trim() || null,
                },
            });
            setStatus("saved");
            setTimeout(() => setStatus("idle"), 1500);
        } catch (e) {
            if (e instanceof api.PhiRejectedError) {
                setError(`"${e.field}" looks like protected health information and was not saved. Memory holds personalization only — never PHI.`);
            } else {
                setError(String((e as Error).message ?? e));
            }
            setStatus("idle");
        }
    }, [token, profession, goals, tone, directness, verbosity, notes]);

    if (status === "loading") return <p className="text-sm text-astral-muted">Loading…</p>;

    return (
        <div className="space-y-4">
            <div>
                <label className={labelClass}>Profession / role</label>
                <input className={inputClass} value={profession} onChange={(e) => setProfession(e.target.value)}
                    placeholder="e.g. Clinical research coordinator" />
            </div>
            <div>
                <label className={labelClass}>Goals (one per line)</label>
                <textarea className={`${inputClass} h-20 resize-y`} value={goals}
                    onChange={(e) => setGoals(e.target.value)} placeholder={"Track grant deadlines\nSummarize cohorts"} />
            </div>
            <div className="grid grid-cols-3 gap-3">
                <div>
                    <label className={labelClass}>Tone</label>
                    <DarkSelect value={tone} onChange={setTone} options={toOptions(["concise", "warm", "formal", "playful", "blunt"])} />
                </div>
                <div>
                    <label className={labelClass}>Directness</label>
                    <DarkSelect value={directness} onChange={setDirectness} options={toOptions(["high", "balanced", "gentle"])} />
                </div>
                <div>
                    <label className={labelClass}>Verbosity</label>
                    <DarkSelect value={verbosity} onChange={setVerbosity} options={toOptions(["low", "medium", "high"])} />
                </div>
            </div>
            <div>
                <label className={labelClass}>Personality notes (style only — never overrides safety/compliance)</label>
                <textarea className={`${inputClass} h-16 resize-y`} value={notes}
                    onChange={(e) => setNotes(e.target.value)} placeholder="No corporate filler. Bullet points." />
            </div>
            {error && (
                <div className="flex items-start gap-2 text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg p-2">
                    <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" /><span>{error}</span>
                </div>
            )}
            <div className="flex items-center gap-3">
                <button type="button" className={btnPrimary} onClick={save} disabled={status === "saving"}>
                    {status === "saving" ? "Saving…" : "Save"}
                </button>
                {status === "saved" && <span className="text-xs text-green-400">Saved</span>}
            </div>
        </div>
    );
}

// ── Schedule ───────────────────────────────────────────────────────────────

function ScheduleTab({ token }: { token: string }) {
    const [jobs, setJobs] = useState<api.ScheduledJob[] | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [name, setName] = useState("");
    const [instruction, setInstruction] = useState("");
    const [kind, setKind] = useState<"interval" | "cron" | "one_shot">("cron");
    const [expr, setExpr] = useState("0 7 * * 1-5");
    const [consent, setConsent] = useState(false);

    const load = useCallback(() => {
        api.listSchedules(token).then(setJobs).catch((e) => setError(String(e.message ?? e)));
    }, [token]);
    useEffect(() => { load(); }, [load]);

    const create = async () => {
        setError(null);
        try {
            await api.createSchedule(token, {
                name: name.trim(), instruction: instruction.trim(),
                schedule_kind: kind, schedule_expr: expr.trim(), consent,
            });
            setName(""); setInstruction(""); setConsent(false);
            load();
        } catch (e) { setError(String((e as Error).message ?? e)); }
    };

    const act = async (fn: () => Promise<void>) => {
        setError(null);
        try { await fn(); load(); } catch (e) { setError(String((e as Error).message ?? e)); }
    };

    return (
        <div className="space-y-4">
            {jobs && jobs.length > 0 && (
                <div className="space-y-1">
                    {jobs.map((j) => (
                        <div key={j.id} className="flex items-center justify-between px-3 py-2 rounded-lg bg-white/5">
                            <div className="min-w-0">
                                <div className="text-sm text-white truncate">{j.name} <span className="text-[10px] text-astral-muted">({j.status})</span></div>
                                <div className="text-[11px] text-astral-muted truncate">
                                    {j.schedule_kind} · {j.schedule_expr} · next {fmtTime(j.next_run_at)}
                                </div>
                            </div>
                            <div className="flex items-center gap-1 flex-shrink-0">
                                {j.status === "active" ? (
                                    <button title="Pause" className="p-1.5 rounded hover:bg-white/10"
                                        onClick={() => act(() =>api.setScheduleStatus(token, j.id, "pause"))}>
                                        <Pause size={14} className="text-astral-muted" /></button>
                                ) : (
                                    <button title="Resume" className="p-1.5 rounded hover:bg-white/10"
                                        onClick={() => act(() =>api.setScheduleStatus(token, j.id, "resume"))}>
                                        <Play size={14} className="text-astral-muted" /></button>
                                )}
                                <button title="Delete" className="p-1.5 rounded hover:bg-white/10"
                                    onClick={() => act(() =>api.deleteSchedule(token, j.id))}>
                                    <Trash2 size={14} className="text-red-400" /></button>
                            </div>
                        </div>
                    ))}
                </div>
            )}

            <div className="border-t border-white/5 pt-4 space-y-3">
                <div className="text-[11px] font-semibold uppercase tracking-wide text-astral-muted">New scheduled job</div>
                <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} placeholder="Name (e.g. Morning brief)" />
                <textarea className={`${inputClass} h-16 resize-y`} value={instruction}
                    onChange={(e) => setInstruction(e.target.value)} placeholder="What should the assistant do?" />
                <div className="grid grid-cols-3 gap-3">
                    <DarkSelect value={kind} onChange={(v) => setKind(v as typeof kind)}
                        options={[{ value: "cron", label: "cron" }, { value: "interval", label: "interval" }, { value: "one_shot", label: "one-shot" }]} />
                    <input className={`${inputClass} col-span-2`} value={expr} onChange={(e) => setExpr(e.target.value)}
                        placeholder={kind === "cron" ? "0 7 * * 1-5" : kind === "interval" ? "15m" : "2026-06-01T09:00:00Z"} />
                </div>
                <label className="flex items-center gap-2 text-xs text-astral-muted cursor-pointer">
                    <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} className="accent-astral-primary" />
                    I consent to this job running on my behalf, within my own permissions.
                </label>
                {error && <p className="text-xs text-red-400">{error}</p>}
                <button type="button" className={btnPrimary} disabled={!name || !instruction || !consent} onClick={create}>
                    Create job
                </button>
                <p className="text-[10px] text-astral-muted">
                    Note: jobs are saved but unattended execution is disabled until the security review of the offline-grant store is complete.
                </p>
            </div>
        </div>
    );
}

// ── Memory & Dreaming ──────────────────────────────────────────────────────

function MemoryTab({ token }: { token: string }) {
    const [items, setItems] = useState<api.MemoryItem[] | null>(null);
    const [dreaming, setDreaming] = useState<api.DreamingStatus | null>(null);
    const [error, setError] = useState<string | null>(null);

    const load = useCallback(() => {
        api.listMemory(token).then(setItems).catch((e) => setError(String(e.message ?? e)));
        api.getDreaming(token).then(setDreaming).catch((e) => setError(String(e.message ?? e)));
    }, [token]);
    useEffect(() => { load(); }, [load]);

    const wrap = async (fn: () => Promise<unknown>) => {
        setError(null);
        try { await fn(); load(); } catch (e) { setError(String((e as Error).message ?? e)); }
    };

    return (
        <div className="space-y-5">
            <div>
                <div className="flex items-center justify-between">
                    <span className="text-sm text-white">Background consolidation ("dreaming")</span>
                    <label className="flex items-center gap-2 text-xs text-astral-muted cursor-pointer">
                        <input type="checkbox" checked={dreaming?.enabled ?? true} className="accent-astral-primary"
                            onChange={(e) => wrap(() => api.setDreaming(token, e.target.checked))} />
                        {dreaming?.enabled ?? true ? "On" : "Off"}
                    </label>
                </div>
                <button type="button" className="mt-2 text-xs text-astral-primary hover:underline"
                    onClick={() => wrap(() => api.triggerDreaming(token))}>
                    Run a sweep now
                </button>
                {dreaming && dreaming.recent_sweeps.length > 0 && (
                    <ul className="mt-2 space-y-1">
                        {dreaming.recent_sweeps.slice(0, 5).map((s) => (
                            <li key={s.id} className="text-[11px] text-astral-muted">
                                {fmtTime(s.ran_at)} — {s.summary}
                            </li>
                        ))}
                    </ul>
                )}
            </div>

            <div className="border-t border-white/5 pt-4">
                <div className="text-[11px] font-semibold uppercase tracking-wide text-astral-muted mb-2">
                    What the assistant remembers (non-PHI)
                </div>
                {error && <p className="text-xs text-red-400 mb-2">{error}</p>}
                {!items ? <p className="text-sm text-astral-muted">Loading…</p> :
                    items.length === 0 ? <p className="text-sm text-astral-muted">Nothing remembered yet.</p> : (
                        <div className="space-y-1">
                            {items.map((m) => (
                                <div key={m.id} className="flex items-center justify-between px-3 py-2 rounded-lg hover:bg-white/5">
                                    <div className="min-w-0">
                                        <div className="text-sm text-white truncate">{m.value}</div>
                                        <div className="text-[11px] text-astral-muted">{m.category} · {m.source}</div>
                                    </div>
                                    <button title="Forget" className="p-1.5 rounded hover:bg-white/10 flex-shrink-0"
                                        onClick={() => wrap(() => api.deleteMemory(token, m.id))}>
                                        <Trash2 size={14} className="text-red-400" />
                                    </button>
                                </div>
                            ))}
                        </div>
                    )}
            </div>
        </div>
    );
}

// ── Panel ──────────────────────────────────────────────────────────────────

export default function PersonalizationPanel({ open, accessToken, onClose }: PersonalizationPanelProps) {
    const [tab, setTab] = useState<Tab>("profile");

    useEffect(() => {
        if (!open) return;
        const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, [open, onClose]);

    if (!open) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
            <div className="bg-astral-surface border border-white/10 rounded-xl shadow-2xl w-full max-w-2xl mx-4 max-h-[90vh] flex flex-col"
                onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label="Personalization">
                <div className="flex items-center justify-between px-6 py-4 border-b border-white/5">
                    <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-astral-primary/20 flex items-center justify-center">
                            <Sparkles size={16} className="text-astral-primary" />
                        </div>
                        <div>
                            <h2 className="text-sm font-semibold text-white">Personalization</h2>
                            <p className="text-[11px] text-astral-muted">Shape your assistant — profile, skills, schedule, memory.</p>
                        </div>
                    </div>
                    <button type="button" onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/10" aria-label="Close">
                        <X size={14} className="text-astral-muted" />
                    </button>
                </div>

                <div className="flex gap-1 px-4 pt-3 border-b border-white/5">
                    {TABS.map((t) => (
                        <button key={t.id} type="button" onClick={() => setTab(t.id)}
                            className={`px-3 py-2 text-xs font-medium rounded-t-lg ${tab === t.id ? "text-white border-b-2 border-astral-primary" : "text-astral-muted hover:text-white"}`}>
                            {t.label}
                        </button>
                    ))}
                </div>

                <div className="flex-1 overflow-y-auto px-6 py-5">
                    {!accessToken ? (
                        <p className="text-sm text-astral-muted">Sign in to manage personalization.</p>
                    ) : tab === "profile" ? <ProfileTab token={accessToken} />
                        : tab === "schedule" ? <ScheduleTab token={accessToken} />
                        : <MemoryTab token={accessToken} />}
                </div>
            </div>
        </div>
    );
}
