/**
 * REST client for the agentic-soul-integration feature (025):
 * personalization profile + personality ("soul"), skills catalog,
 * durable memory, scheduled jobs, and dreaming/consolidation.
 *
 * All calls attach the caller's bearer token (mirrors api/llm.ts). The
 * server scopes everything to the JWT subject; PHI-bearing values are
 * rejected with HTTP 422 (see the PHI gate) and surfaced to the caller.
 */
import { API_URL } from "../config";

export interface Personality {
    tone?: string | null;
    directness?: string | null;
    humor?: string | null;
    verbosity?: string | null;
    notes?: string | null;
}

export interface Profile {
    profession: string | null;
    goals: string[];
    personality: Personality;
    dreaming_enabled: boolean;
}

export interface Skill {
    agent_id: string;
    tool_name: string;
    scope: string;
    enabled: boolean;
    authorized: boolean;
}

export interface MemoryItem {
    id: string;
    category: string;
    value: string;
    source: string;
    created_at: number;
}

export interface ScheduledJob {
    id: string;
    name: string;
    instruction: string;
    schedule_kind: string;
    schedule_expr: string;
    timezone: string;
    status: string;
    next_run_at: number | null;
    last_run_at: number | null;
    consented_scopes: string[];
}

export interface DreamingStatus {
    enabled: boolean;
    recent_sweeps: Array<{
        id: string;
        ran_at: number;
        candidates_considered: number;
        promoted_count: number;
        summary: string;
        trigger: string;
    }>;
}

/** Thrown when the server rejects a value as PHI (HTTP 422). */
export class PhiRejectedError extends Error {
    field: string;
    constructor(field: string, reason: string) {
        super(reason);
        this.name = "PhiRejectedError";
        this.field = field;
    }
}

function auth(token: string): HeadersInit {
    return { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
}

async function handle<T>(res: Response): Promise<T> {
    if (res.status === 422) {
        let body: { field?: string; reason?: string } = {};
        try { body = await res.json(); } catch { /* ignore */ }
        throw new PhiRejectedError(body.field ?? "value", body.reason ?? "value rejected");
    }
    if (!res.ok) {
        const text = await res.text();
        throw new Error(`Request failed (${res.status}): ${text}`);
    }
    if (res.status === 204) return undefined as unknown as T;
    return (await res.json()) as T;
}

// ── Profile / personality ──────────────────────────────────────────────────

export async function getProfile(token: string): Promise<Profile> {
    return handle(await fetch(`${API_URL}/api/personalization/profile`, { headers: auth(token) }));
}

export async function updateProfile(token: string, body: Partial<Profile>): Promise<Profile> {
    return handle(await fetch(`${API_URL}/api/personalization/profile`, {
        method: "PUT", headers: auth(token), body: JSON.stringify(body),
    }));
}

// ── Skills ───────────────────────────────────────────────────────────────--

export async function listSkills(token: string): Promise<Skill[]> {
    const r = await handle<{ skills: Skill[] }>(
        await fetch(`${API_URL}/api/skills`, { headers: auth(token) }));
    return r.skills;
}

export async function toggleSkill(
    token: string, agentId: string, toolName: string, enabled: boolean,
): Promise<void> {
    await handle(await fetch(`${API_URL}/api/skills`, {
        method: "PUT", headers: auth(token),
        body: JSON.stringify({ agent_id: agentId, tool_name: toolName, enabled }),
    }));
}

// ── Memory ───────────────────────────────────────────────────────────────--

export async function listMemory(token: string): Promise<MemoryItem[]> {
    const r = await handle<{ items: MemoryItem[] }>(
        await fetch(`${API_URL}/api/memory`, { headers: auth(token) }));
    return r.items;
}

export async function deleteMemory(token: string, id: string): Promise<void> {
    await handle(await fetch(`${API_URL}/api/memory/${encodeURIComponent(id)}`, {
        method: "DELETE", headers: auth(token),
    }));
}

// ── Dreaming ───────────────────────────────────────────────────────────────

export async function getDreaming(token: string): Promise<DreamingStatus> {
    return handle(await fetch(`${API_URL}/api/dreaming`, { headers: auth(token) }));
}

export async function setDreaming(token: string, enabled: boolean): Promise<void> {
    await handle(await fetch(`${API_URL}/api/dreaming/${enabled ? "enable" : "disable"}`, {
        method: "POST", headers: auth(token),
    }));
}

export async function triggerDreaming(token: string): Promise<DreamingStatus["recent_sweeps"][number]> {
    return handle(await fetch(`${API_URL}/api/dreaming/trigger`, { method: "POST", headers: auth(token) }));
}

// ── Schedule ───────────────────────────────────────────────────────────────

export async function listSchedules(token: string): Promise<ScheduledJob[]> {
    const r = await handle<{ jobs: ScheduledJob[] }>(
        await fetch(`${API_URL}/api/schedule`, { headers: auth(token) }));
    return r.jobs;
}

export interface CreateScheduleBody {
    name: string;
    instruction: string;
    schedule_kind: "one_shot" | "interval" | "cron";
    schedule_expr: string;
    timezone?: string;
    consented_scopes?: string[];
    consent: boolean;
    agent_id?: string | null;
}

export async function createSchedule(token: string, body: CreateScheduleBody): Promise<ScheduledJob> {
    const res = await fetch(`${API_URL}/api/schedule`, {
        method: "POST", headers: auth(token), body: JSON.stringify(body),
    });
    if (!res.ok && res.status !== 422) {
        // 400/403/409 carry a structured {error, detail} body — surface its message.
        let detail = `Request failed (${res.status})`;
        try { const b = await res.json(); detail = b.detail || b.error || detail; } catch { /* ignore */ }
        throw new Error(detail);
    }
    return handle(res);
}

export async function setScheduleStatus(
    token: string, id: string, action: "pause" | "resume",
): Promise<void> {
    await handle(await fetch(`${API_URL}/api/schedule/${encodeURIComponent(id)}/${action}`, {
        method: "POST", headers: auth(token),
    }));
}

export async function deleteSchedule(token: string, id: string): Promise<void> {
    await handle(await fetch(`${API_URL}/api/schedule/${encodeURIComponent(id)}`, {
        method: "DELETE", headers: auth(token),
    }));
}
