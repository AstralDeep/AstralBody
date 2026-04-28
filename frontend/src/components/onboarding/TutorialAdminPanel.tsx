/**
 * TutorialAdminPanel — admin overlay for editing tutorial step copy.
 *
 * Mirrors `FeedbackAdminPanel`. Loads every step (including archived
 * ones) from `GET /api/admin/tutorial/steps`, renders an editable list,
 * and writes through the admin endpoints. All write paths emit a
 * `tutorial_step_edited` audit event server-side; we don't need to
 * surface that in the UI.
 *
 * Defense-in-depth: the panel itself checks `open` and renders nothing
 * if the caller is not admin. The server still rejects non-admin
 * requests with 403, but a misclick from a non-admin path should at
 * least not flash content.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Archive, Plus, RefreshCw, RotateCcw, Save, X } from "lucide-react";

import { API_URL } from "../../config";
import type { AdminTutorialStep, StepAudience, TargetKind } from "./types";

export interface TutorialAdminPanelProps {
    open: boolean;
    accessToken: string | null;
    onClose: () => void;
}

const AUDIENCES: StepAudience[] = ["user", "admin"];
const TARGET_KINDS: TargetKind[] = ["static", "sdui", "none"];

interface FormState {
    slug: string;
    audience: StepAudience;
    display_order: number;
    target_kind: TargetKind;
    target_key: string;
    title: string;
    body: string;
}

function blankForm(): FormState {
    return {
        slug: "",
        audience: "user",
        display_order: 0,
        target_kind: "none",
        target_key: "",
        title: "",
        body: "",
    };
}

function fromStep(s: AdminTutorialStep): FormState {
    return {
        slug: s.slug,
        audience: s.audience,
        display_order: s.display_order,
        target_kind: s.target_kind,
        target_key: s.target_key ?? "",
        title: s.title,
        body: s.body,
    };
}

export function TutorialAdminPanel({ open, accessToken, onClose }: TutorialAdminPanelProps) {
    const [steps, setSteps] = useState<AdminTutorialStep[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [editingId, setEditingId] = useState<number | "new" | null>(null);
    const [form, setForm] = useState<FormState>(blankForm());
    const [saving, setSaving] = useState(false);

    const headers = useMemo<Record<string, string>>(() => {
        const h: Record<string, string> = { "Content-Type": "application/json" };
        if (accessToken) h["Authorization"] = `Bearer ${accessToken}`;
        return h;
    }, [accessToken]);

    const refresh = useCallback(async () => {
        if (!accessToken) return;
        setLoading(true);
        setError(null);
        try {
            const r = await fetch(
                `${API_URL}/api/admin/tutorial/steps?include_archived=true`,
                { headers },
            );
            if (r.status === 403) {
                setError("Admin role required.");
                setSteps([]);
                return;
            }
            if (!r.ok) {
                throw new Error(`tutorial admin list ${r.status}`);
            }
            const body = (await r.json()) as { steps: AdminTutorialStep[] };
            setSteps(Array.isArray(body.steps) ? body.steps : []);
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        } finally {
            setLoading(false);
        }
    }, [accessToken, headers]);

    useEffect(() => {
        if (open) void refresh();
    }, [open, refresh]);

    const startNew = () => {
        setEditingId("new");
        setForm(blankForm());
    };

    const startEdit = (s: AdminTutorialStep) => {
        setEditingId(s.id);
        setForm(fromStep(s));
    };

    const cancelEdit = () => {
        setEditingId(null);
        setForm(blankForm());
    };

    const save = async () => {
        if (!accessToken) return;
        setSaving(true);
        setError(null);
        try {
            const payload: Record<string, unknown> = {
                audience: form.audience,
                display_order: form.display_order,
                target_kind: form.target_kind,
                target_key: form.target_kind === "none" ? null : form.target_key.trim(),
                title: form.title,
                body: form.body,
            };
            if (editingId === "new") {
                payload["slug"] = form.slug.trim();
                const r = await fetch(`${API_URL}/api/admin/tutorial/steps`, {
                    method: "POST",
                    headers,
                    body: JSON.stringify(payload),
                });
                if (!r.ok) {
                    const detail = await r.text();
                    throw new Error(`create failed (${r.status}): ${detail}`);
                }
            } else if (typeof editingId === "number") {
                const r = await fetch(`${API_URL}/api/admin/tutorial/steps/${editingId}`, {
                    method: "PUT",
                    headers,
                    body: JSON.stringify(payload),
                });
                if (!r.ok) {
                    const detail = await r.text();
                    throw new Error(`update failed (${r.status}): ${detail}`);
                }
            }
            cancelEdit();
            await refresh();
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        } finally {
            setSaving(false);
        }
    };

    const archive = async (id: number) => {
        if (!accessToken) return;
        try {
            await fetch(`${API_URL}/api/admin/tutorial/steps/${id}/archive`, {
                method: "POST",
                headers,
            });
            await refresh();
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        }
    };

    const restore = async (id: number) => {
        if (!accessToken) return;
        try {
            await fetch(`${API_URL}/api/admin/tutorial/steps/${id}/restore`, {
                method: "POST",
                headers,
            });
            await refresh();
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        }
    };

    if (!open) return null;

    return (
        <div
            role="dialog"
            aria-label="Tutorial admin"
            className="fixed inset-0 z-[10002] bg-black/70 flex items-center justify-center p-4"
        >
            <div className="bg-astral-bg border border-white/10 rounded-xl shadow-2xl
                            w-full max-w-4xl max-h-[90vh] flex flex-col">
                <div className="flex items-center justify-between px-5 py-3 border-b border-white/10">
                    <div className="flex items-center gap-2 text-white">
                        <strong>Tutorial admin</strong>
                        <span className="text-xs text-astral-muted">
                            ({steps.length} steps)
                        </span>
                    </div>
                    <div className="flex items-center gap-2">
                        <button
                            type="button"
                            onClick={() => void refresh()}
                            className="text-astral-muted hover:text-white p-1.5 rounded-md hover:bg-white/5"
                            aria-label="Refresh"
                        >
                            <RefreshCw size={14} />
                        </button>
                        <button
                            type="button"
                            onClick={startNew}
                            className="flex items-center gap-1 text-xs text-white bg-astral-primary
                                       hover:bg-astral-primary/90 px-3 py-1.5 rounded-lg"
                            data-tutorial-target="admin.tutorial.new-step"
                        >
                            <Plus size={14} /> New step
                        </button>
                        <button
                            type="button"
                            onClick={onClose}
                            aria-label="Close"
                            className="text-astral-muted hover:text-white p-1.5 rounded-md hover:bg-white/5"
                        >
                            <X size={16} />
                        </button>
                    </div>
                </div>

                {error && (
                    <div className="px-5 py-2 bg-red-500/10 border-b border-red-500/20 text-xs text-red-300">
                        {error}
                    </div>
                )}

                <div className="flex-1 overflow-y-auto p-5 space-y-3">
                    {loading && (
                        <div className="text-center text-xs text-astral-muted py-4">
                            Loading…
                        </div>
                    )}

                    {editingId === "new" && (
                        <StepEditForm
                            heading="New step"
                            form={form}
                            setForm={setForm}
                            saving={saving}
                            onSave={() => void save()}
                            onCancel={cancelEdit}
                        />
                    )}

                    {steps.map((s) => (
                        <div
                            key={s.id}
                            className={`border border-white/10 rounded-lg p-4 ${
                                s.archived_at ? "opacity-60" : ""
                            }`}
                        >
                            {editingId === s.id ? (
                                <StepEditForm
                                    heading={`Edit ${s.slug}`}
                                    form={form}
                                    setForm={setForm}
                                    saving={saving}
                                    onSave={() => void save()}
                                    onCancel={cancelEdit}
                                />
                            ) : (
                                <div>
                                    <div className="flex items-start justify-between gap-3 mb-2">
                                        <div className="flex-1">
                                            <div className="flex items-center gap-2 flex-wrap">
                                                <span className="text-xs font-semibold text-white">
                                                    {s.title}
                                                </span>
                                                <span className="text-[10px] text-astral-muted">
                                                    {s.slug}
                                                </span>
                                                <span className="text-[10px] uppercase tracking-wide bg-white/5 px-1.5 py-0.5 rounded">
                                                    {s.audience}
                                                </span>
                                                <span className="text-[10px] text-astral-muted">
                                                    order {s.display_order}
                                                </span>
                                                {s.archived_at && (
                                                    <span className="text-[10px] uppercase tracking-wide bg-amber-500/20 text-amber-300 px-1.5 py-0.5 rounded">
                                                        archived
                                                    </span>
                                                )}
                                            </div>
                                            <p className="text-xs text-astral-muted mt-1 line-clamp-2">
                                                {s.body}
                                            </p>
                                            {s.target_key && (
                                                <p className="text-[10px] text-astral-muted/70 mt-1">
                                                    target: {s.target_kind}={s.target_key}
                                                </p>
                                            )}
                                        </div>
                                        <div className="flex items-center gap-1.5">
                                            <button
                                                type="button"
                                                onClick={() => startEdit(s)}
                                                className="text-xs text-astral-muted hover:text-white
                                                           px-2 py-1 rounded hover:bg-white/5"
                                            >
                                                Edit
                                            </button>
                                            {s.archived_at ? (
                                                <button
                                                    type="button"
                                                    onClick={() => void restore(s.id)}
                                                    aria-label="Restore"
                                                    data-tutorial-target="admin.tutorial.restore"
                                                    className="text-xs text-astral-muted hover:text-white
                                                               p-1.5 rounded hover:bg-white/5"
                                                >
                                                    <RotateCcw size={12} />
                                                </button>
                                            ) : (
                                                <button
                                                    type="button"
                                                    onClick={() => void archive(s.id)}
                                                    aria-label="Archive"
                                                    data-tutorial-target="admin.tutorial.archive"
                                                    className="text-xs text-astral-muted hover:text-amber-300
                                                               p-1.5 rounded hover:bg-white/5"
                                                >
                                                    <Archive size={12} />
                                                </button>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>
                    ))}

                    {!loading && steps.length === 0 && editingId !== "new" && (
                        <div className="text-center text-xs text-astral-muted py-8">
                            No tutorial steps yet. Click <em>New step</em> to add one.
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

interface StepEditFormProps {
    heading: string;
    form: FormState;
    setForm: (f: FormState) => void;
    saving: boolean;
    onSave: () => void;
    onCancel: () => void;
}

function StepEditForm({ heading, form, setForm, saving, onSave, onCancel }: StepEditFormProps) {
    const isCreate = !form.slug || /^new-step/.test(form.slug);
    return (
        <div>
            <div className="flex items-center justify-between mb-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-astral-muted">
                    {heading}
                </p>
            </div>
            <div className="grid grid-cols-2 gap-3 mb-3">
                {isCreate && (
                    <label className="block col-span-2">
                        <span className="text-[10px] text-astral-muted">slug</span>
                        <input
                            type="text"
                            value={form.slug}
                            onChange={(e) => setForm({ ...form, slug: e.target.value })}
                            className="w-full bg-white/5 border border-white/10 rounded-md px-2 py-1
                                       text-xs text-white"
                            placeholder="e.g. open-audit-log"
                        />
                    </label>
                )}
                <label className="block">
                    <span className="text-[10px] text-astral-muted">audience</span>
                    <select
                        value={form.audience}
                        onChange={(e) =>
                            setForm({ ...form, audience: e.target.value as StepAudience })
                        }
                        className="w-full bg-white/5 border border-white/10 rounded-md px-2 py-1
                                   text-xs text-white"
                    >
                        {AUDIENCES.map((a) => (
                            <option key={a} value={a}>
                                {a}
                            </option>
                        ))}
                    </select>
                </label>
                <label className="block">
                    <span className="text-[10px] text-astral-muted">display_order</span>
                    <input
                        type="number"
                        value={form.display_order}
                        onChange={(e) =>
                            setForm({ ...form, display_order: Number(e.target.value) })
                        }
                        className="w-full bg-white/5 border border-white/10 rounded-md px-2 py-1
                                   text-xs text-white"
                    />
                </label>
                <label className="block">
                    <span className="text-[10px] text-astral-muted">target_kind</span>
                    <select
                        value={form.target_kind}
                        onChange={(e) =>
                            setForm({ ...form, target_kind: e.target.value as TargetKind })
                        }
                        className="w-full bg-white/5 border border-white/10 rounded-md px-2 py-1
                                   text-xs text-white"
                    >
                        {TARGET_KINDS.map((k) => (
                            <option key={k} value={k}>
                                {k}
                            </option>
                        ))}
                    </select>
                </label>
                <label className="block">
                    <span className="text-[10px] text-astral-muted">
                        target_key {form.target_kind === "none" ? "(must be empty)" : ""}
                    </span>
                    <input
                        type="text"
                        value={form.target_key}
                        disabled={form.target_kind === "none"}
                        onChange={(e) => setForm({ ...form, target_key: e.target.value })}
                        className="w-full bg-white/5 border border-white/10 rounded-md px-2 py-1
                                   text-xs text-white disabled:opacity-40"
                        placeholder={form.target_kind === "none" ? "" : "e.g. sidebar.audit"}
                    />
                </label>
            </div>
            <label className="block mb-3">
                <span className="text-[10px] text-astral-muted">title</span>
                <input
                    type="text"
                    value={form.title}
                    maxLength={120}
                    onChange={(e) => setForm({ ...form, title: e.target.value })}
                    className="w-full bg-white/5 border border-white/10 rounded-md px-2 py-1
                               text-xs text-white"
                />
            </label>
            <label className="block mb-3">
                <span className="text-[10px] text-astral-muted">body</span>
                <textarea
                    value={form.body}
                    maxLength={1000}
                    rows={4}
                    onChange={(e) => setForm({ ...form, body: e.target.value })}
                    className="w-full bg-white/5 border border-white/10 rounded-md px-2 py-1
                               text-xs text-white"
                />
            </label>
            <div className="flex items-center justify-end gap-2">
                <button
                    type="button"
                    onClick={onCancel}
                    disabled={saving}
                    className="text-xs text-astral-muted hover:text-white px-3 py-1.5 rounded-md
                               hover:bg-white/5"
                >
                    Cancel
                </button>
                <button
                    type="button"
                    onClick={onSave}
                    disabled={saving}
                    className="flex items-center gap-1 text-xs text-white bg-astral-primary
                               hover:bg-astral-primary/90 px-3 py-1.5 rounded-md disabled:opacity-50"
                >
                    <Save size={12} />
                    {saving ? "Saving…" : "Save"}
                </button>
            </div>
        </div>
    );
}
