/**
 * CreateAgentModal — Multi-step modal for creating user-defined agents.
 *
 * Steps:
 * 1. Define Agent (name, description, tags, packages)
 * 2. Define Tools (optional tool specifications)
 * 3. Review & Generate (triggers code generation)
 * 4. Test & Refine (test chat + refinement chat, expanded to ~90% screen)
 */
import React, { useState, useRef, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import {
    X, ChevronRight, ChevronLeft, Plus, Trash2, Zap,
    Play, Square, CheckCircle2, AlertTriangle, Shield,
    Loader2, Send, Bot, Tag, Package, Wrench, Info,
    XCircle, MessageSquare, KeyRound
} from "lucide-react";
import { API_URL, WS_URL } from "../config";
import DynamicRenderer from "./DynamicRenderer";

// ─── Types ──────────────────────────────────────────────────────────────

interface ToolSpec {
    name: string;
    description: string;
    scope: string;
    params: { name: string; type: string; description: string; required: boolean }[];
}

interface RequiredCredential {
    key: string;
    label: string;
    description?: string;
    required: boolean;
    type?: string; // api_key, oauth_client_id, oauth_client_secret, token, password, username
}

interface DraftAgent {
    id: string;
    user_id: string;
    agent_name: string;
    agent_slug: string;
    description: string;
    tools_spec?: ToolSpec[] | null;
    skill_tags?: string[] | null;
    packages?: string[] | null;
    status: string;
    generation_log?: { message: string; timestamp: number }[] | null;
    security_report?: SecurityReport | null;
    validation_report?: ValidationReport | null;
    error_message?: string | null;
    port?: number | null;
    refinement_history?: { role: string; content: string; timestamp: number }[] | null;
    required_credentials?: RequiredCredential[] | null;
    created_at?: number;
    updated_at?: number;
}

interface SecurityReport {
    passed: boolean;
    findings: { severity: string; category: string; message: string; line?: number; code_snippet?: string }[];
    max_severity?: string;
    recommendation?: string;
}

interface ValidationReport {
    passed: boolean;
    tools_tested: number;
    tools_passed: number;
    findings: { severity: string; category: string; message: string; tool_name?: string }[];
    tools?: { name: string; description: string; scope: string; parameters: { name: string; type: string; description: string; required: boolean }[] }[];
}

interface ProgressMessage {
    draft_id: string;
    step: string;
    message: string;
    status: string;
    detail?: SecurityReport | { security?: SecurityReport; validation?: ValidationReport };
}

interface TestChatMessage {
    role: "user" | "assistant" | "status";
    content: unknown;
}

interface CreateAgentModalProps {
    isOpen: boolean;
    onClose: () => void;
    accessToken?: string;
    onAgentCreated?: () => void;
    resumeDraftId?: string | null;
}

// ─── Helpers ────────────────────────────────────────────────────────────

const SCOPES = [
    { value: "tools:read", label: "Read", color: "text-green-400" },
    { value: "tools:write", label: "Write", color: "text-amber-400" },
    { value: "tools:search", label: "Search", color: "text-blue-400" },
    { value: "tools:system", label: "System", color: "text-purple-400" },
];

const SEVERITY_COLORS: Record<string, string> = {
    critical: "text-red-400 bg-red-400/10 border-red-400/20",
    high: "text-orange-400 bg-orange-400/10 border-orange-400/20",
    medium: "text-yellow-400 bg-yellow-400/10 border-yellow-400/20",
    low: "text-blue-400 bg-blue-400/10 border-blue-400/20",
};

const STATUS_LABELS: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
    pending: { label: "Pending", color: "text-astral-muted", icon: <Info size={14} /> },
    generating: { label: "Generating...", color: "text-blue-400", icon: <Loader2 size={14} className="animate-spin" /> },
    validating: { label: "Validating...", color: "text-cyan-400", icon: <Loader2 size={14} className="animate-spin" /> },
    generated: { label: "Ready to Test", color: "text-green-400", icon: <CheckCircle2 size={14} /> },
    testing: { label: "Testing", color: "text-amber-400", icon: <Play size={14} /> },
    analyzing: { label: "Analyzing...", color: "text-blue-400", icon: <Loader2 size={14} className="animate-spin" /> },
    approved: { label: "Approved", color: "text-green-400", icon: <CheckCircle2 size={14} /> },
    pending_review: { label: "Awaiting Admin Review", color: "text-amber-400", icon: <Shield size={14} /> },
    rejected: { label: "Rejected", color: "text-red-400", icon: <XCircle size={14} /> },
    live: { label: "Live", color: "text-green-400", icon: <Zap size={14} /> },
    error: { label: "Error", color: "text-red-400", icon: <AlertTriangle size={14} /> },
};

// ─── Component ──────────────────────────────────────────────────────────

export default function CreateAgentModal({ isOpen, onClose, accessToken, onAgentCreated, resumeDraftId }: CreateAgentModalProps) {
    const [step, setStep] = useState(1);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Step 1: Agent Info
    const [agentName, setAgentName] = useState("");
    const [description, setDescription] = useState("");
    const [tagInput, setTagInput] = useState("");
    const [tags, setTags] = useState<string[]>([]);
    const [pkgInput, setPkgInput] = useState("");
    const [packages, setPackages] = useState<string[]>([]);

    // Step 2: Tools
    const [tools, setTools] = useState<ToolSpec[]>([]);

    // Step 3-4: Draft state
    const [draft, setDraft] = useState<DraftAgent | null>(null);
    const [progress, setProgress] = useState<ProgressMessage[]>([]);

    // Step 4: Refinement chat
    const [chatInput, setChatInput] = useState("");
    const [refining, setRefining] = useState(false);
    const refineChatEndRef = useRef<HTMLDivElement>(null);

    // Step 4: Test chat (own WebSocket)
    const [testMessages, setTestMessages] = useState<TestChatMessage[]>([]);
    const [testInput, setTestInput] = useState("");
    const [testChatId, setTestChatId] = useState<string>(() => `draft-test-${Date.now()}`);
    const [testStatus, setTestStatus] = useState<string>("idle");
    const [testStatusMsg, setTestStatusMsg] = useState<string>("");
    const testWsRef = useRef<WebSocket | null>(null);
    const testChatEndRef = useRef<HTMLDivElement>(null);

    // Credentials
    const [credentialValues, setCredentialValues] = useState<Record<string, string>>({});
    const [storedCredentialKeys, setStoredCredentialKeys] = useState<string[]>([]);
    const [credentialsSaving, setCredentialsSaving] = useState(false);

    // Scroll chats to bottom
    useEffect(() => {
        refineChatEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [draft?.refinement_history, refining]);

    useEffect(() => {
        testChatEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [testMessages, testStatus]);

    // ─── Test Chat WebSocket ───────────────────────────────────────

    const connectTestWs = useCallback(() => {
        if (testWsRef.current && testWsRef.current.readyState === WebSocket.OPEN) return;

        const ws = new WebSocket(WS_URL);
        testWsRef.current = ws;

        ws.onopen = () => {
            // Register as UI client
            ws.send(JSON.stringify({
                type: "register_ui",
                token: accessToken || "dev-token",
                capabilities: ["render", "stream"],
                session_id: `draft-test-${Date.now()}`,
            }));
        };

        ws.onmessage = (ev) => {
            try {
                const data = JSON.parse(ev.data);

                if (data.type === "ui_render") {
                    setTestMessages(prev => [
                        ...prev,
                        { role: "assistant", content: data.components || [] }
                    ]);
                } else if (data.type === "ui_update" || data.type === "ui_append") {
                    setTestMessages(prev => [
                        ...prev,
                        { role: "assistant", content: data.components || [] }
                    ]);
                } else if (data.type === "chat_status") {
                    const status = data.status || "idle";
                    if (status === "done") {
                        setTestStatus("idle");
                    } else {
                        setTestStatus(status);
                        if (data.message) setTestStatusMsg(data.message);
                    }
                } else if (data.type === "chat_response") {
                    // Text response from the LLM (no UI components)
                    const text = data.response || data.message || data.content || "";
                    if (text) {
                        setTestMessages(prev => [
                            ...prev,
                            { role: "assistant", content: text }
                        ]);
                    }
                    setTestStatus("idle");
                } else if (data.type === "error") {
                    const errMsg = data.message || data.error || "An error occurred";
                    setTestMessages(prev => [
                        ...prev,
                        { role: "status", content: `Error: ${errMsg}` }
                    ]);
                    setTestStatus("idle");
                }
            } catch {
                // ignore parse errors
            }
        };

        ws.onclose = () => {
            testWsRef.current = null;
        };
    }, [accessToken]);

    const disconnectTestWs = useCallback(() => {
        if (testWsRef.current) {
            testWsRef.current.close();
            testWsRef.current = null;
        }
    }, []);

    // Connect WS when entering step 4 with the draft in any post-generation
    // status that supports testing. Previously this gated on "testing" only,
    // but generation completes at "generated" and nothing ever flipped the
    // status — the user landed on Step 4 with no socket and silently dropped
    // messages (feature 012-fix-agent-flows Story 1). Accepting both states
    // here, plus the explicit /test POST below, closes the loop.
    useEffect(() => {
        if (step === 4 && (draft?.status === "generated" || draft?.status === "testing" || draft?.status === "live")) {
            connectTestWs();
        }
        return () => {
            // Don't disconnect on every render, only on unmount
        };
    }, [step, draft?.status, connectTestWs]);

    // Start the draft subprocess when the user lands on Step 4 with a
    // freshly generated draft. The /test endpoint is idempotent —
    // start_draft_agent stops any existing subprocess before re-spawning,
    // and the orchestrator deduplicates the agent_id on discovery — so
    // calling it whenever we enter Step 4 in "generated" state is safe.
    // Failures land in draft.status="error" and are rendered by the
    // error-state branch on Step 4.
    const ensuredStartedRef = useRef<string | null>(null);
    useEffect(() => {
        if (step !== 4 || !draft?.id) return;
        if (draft.status !== "generated") return;
        if (ensuredStartedRef.current === draft.id) return;
        ensuredStartedRef.current = draft.id;
        (async () => {
            try {
                const resp = await fetch(`${API_URL}/api/agents/drafts/${draft.id}/test`, {
                    method: "POST",
                    headers: headers(),
                });
                if (resp.ok) {
                    const updated: DraftAgent = await resp.json();
                    setDraft(updated);
                } else {
                    const errBody = await resp.json().catch(() => ({}));
                    setDraft(prev => prev ? {
                        ...prev,
                        status: "error",
                        error_message: errBody.detail || `Failed to start draft (HTTP ${resp.status})`,
                    } : prev);
                }
            } catch (e) {
                setDraft(prev => prev ? {
                    ...prev,
                    status: "error",
                    error_message: e instanceof Error ? e.message : String(e),
                } : prev);
            }
        })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [step, draft?.id, draft?.status]);

    // Cleanup on close
    useEffect(() => {
        if (!isOpen) {
            disconnectTestWs();
        }
    }, [isOpen, disconnectTestWs]);

    // Resume a draft agent (e.g., from agent manager "Drafts" tab)
    useEffect(() => {
        if (!isOpen || !resumeDraftId) return;
        const loadDraft = async () => {
            try {
                const resp = await fetch(`${API_URL}/api/agents/drafts/${resumeDraftId}`, { headers: headers() });
                if (!resp.ok) return;
                const d: DraftAgent = await resp.json();
                setDraft(d);
                setAgentName(d.agent_name);
                setDescription(d.description);
                setTags(d.skill_tags || []);
                setPackages(d.packages || []);
                // Jump to step 4 if code has been generated
                if (["generated", "testing", "analyzing", "approved", "pending_review", "live", "error"].includes(d.status)) {
                    setStep(4);
                } else {
                    setStep(3);
                }
            } catch {
                // ignore — will show empty modal
            }
        };
        loadDraft();
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isOpen, resumeDraftId]);

    const sendTestMessage = useCallback(() => {
        if (!testInput.trim() || !testWsRef.current || testWsRef.current.readyState !== WebSocket.OPEN) return;

        const msg = testInput.trim();
        setTestInput("");
        setTestMessages(prev => [...prev, { role: "user", content: msg }]);
        setTestStatus("thinking");
        setTestStatusMsg("");

        // Include draft_agent_id so the backend only exposes this agent's tools
        const draftAgentId = draft?.agent_slug
            ? draft.agent_slug.replace(/_/g, "-") + "-1"
            : undefined;

        testWsRef.current.send(JSON.stringify({
            type: "ui_event",
            action: "chat_message",
            session_id: testChatId || undefined,
            payload: {
                message: msg,
                chat_id: testChatId,
                draft_agent_id: draftAgentId,
            }
        }));
    }, [testInput, testChatId, draft?.agent_slug]);

    // Reset state on close
    const handleClose = () => {
        setStep(1);
        setAgentName("");
        setDescription("");
        setTags([]);
        setPackages([]);
        setTools([]);
        setDraft(null);
        setProgress([]);
        setError(null);
        setLoading(false);
        setTestMessages([]);
        setTestInput("");
        setTestChatId(`draft-test-${Date.now()}`);
        setTestStatus("idle");
        setTestStatusMsg("");
        disconnectTestWs();
        onClose();
    };

    const headers = (): Record<string, string> => {
        const h: Record<string, string> = { "Content-Type": "application/json" };
        if (accessToken) h["Authorization"] = `Bearer ${accessToken}`;
        return h;
    };

    // ─── Credential helpers ─────────────────────────────────────────

    const fetchCredentialStatus = useCallback(async (draftId: string) => {
        try {
            const resp = await fetch(`${API_URL}/api/agents/drafts/${draftId}/credentials`, {
                headers: headers(),
            });
            if (resp.ok) {
                const data = await resp.json();
                setStoredCredentialKeys(data.stored_credential_keys || []);
            }
        } catch (e) {
            console.error("Failed to fetch credential status", e);
        }
    }, [accessToken]);

    const saveCredentials = async () => {
        if (!draft) return;
        setCredentialsSaving(true);
        try {
            const creds: Record<string, string> = {};
            for (const [k, v] of Object.entries(credentialValues)) {
                if (v.trim()) creds[k] = v.trim();
            }
            if (Object.keys(creds).length === 0) return;
            const resp = await fetch(`${API_URL}/api/agents/drafts/${draft.id}/credentials`, {
                method: "PUT",
                headers: headers(),
                body: JSON.stringify({ credentials: creds }),
            });
            if (resp.ok) {
                const data = await resp.json();
                setStoredCredentialKeys(data.stored_credential_keys || []);
                setCredentialValues({});
            }
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        } finally {
            setCredentialsSaving(false);
        }
    };

    // Fetch credential status when draft enters generated/testing state
    useEffect(() => {
        if (draft?.id && draft.required_credentials?.length && step === 4) {
            fetchCredentialStatus(draft.id);
        }
    }, [draft?.id, draft?.required_credentials, step, fetchCredentialStatus]);

    // ─── API Calls ──────────────────────────────────────────────────

    const createAndGenerate = async () => {
        setLoading(true);
        setError(null);
        setProgress([]);

        try {
            // Create draft
            const createResp = await fetch(`${API_URL}/api/agents/drafts`, {
                method: "POST",
                headers: headers(),
                body: JSON.stringify({
                    agent_name: agentName,
                    description,
                    tools: tools.length > 0 ? tools.map(t => ({
                        name: t.name,
                        description: t.description,
                        scope: t.scope,
                        input_schema: t.params.length > 0 ? {
                            type: "object",
                            properties: Object.fromEntries(
                                t.params.map(p => [p.name, { type: p.type, description: p.description }])
                            ),
                            required: t.params.filter(p => p.required).map(p => p.name),
                        } : undefined,
                    })) : undefined,
                    skill_tags: tags.length > 0 ? tags : undefined,
                    packages: packages.length > 0 ? packages : undefined,
                }),
            });

            if (!createResp.ok) {
                const err = await createResp.json();
                throw new Error(err.detail || "Failed to create draft");
            }

            const created: DraftAgent = await createResp.json();
            setDraft(created);
            setProgress(prev => [...prev, { draft_id: created.id, step: "created", message: "Draft created. Starting code generation...", status: "pending" }]);

            // Generate code
            const genResp = await fetch(`${API_URL}/api/agents/drafts/${created.id}/generate`, {
                method: "POST",
                headers: headers(),
            });

            if (!genResp.ok) {
                const err = await genResp.json();
                throw new Error(err.detail || "Code generation failed");
            }

            const generated: DraftAgent = await genResp.json();
            setDraft(generated);
            setProgress(prev => [...prev, {
                draft_id: generated.id,
                step: "complete",
                message: generated.status === "error"
                    ? `Generation failed: ${generated.error_message}`
                    : "Code generated successfully!",
                status: generated.status,
                detail: generated.security_report as SecurityReport | undefined,
            }]);

            if (generated.status === "generated") {
                setStep(4);
            }
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : String(e));
        } finally {
            setLoading(false);
        }
    };

    const startTesting = async () => {
        if (!draft) return;
        setLoading(true);
        setError(null);
        try {
            const resp = await fetch(`${API_URL}/api/agents/drafts/${draft.id}/test`, {
                method: "POST",
                headers: headers(),
            });
            if (!resp.ok) {
                const err = await resp.json();
                throw new Error(err.detail || "Failed to start agent");
            }
            const updated: DraftAgent = await resp.json();
            setDraft(updated);
            // Reset test chat for fresh testing session
            setTestMessages([]);
            setTestChatId(`draft-test-${Date.now()}`);
            setTestStatus("idle");
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : String(e));
        } finally {
            setLoading(false);
        }
    };

    const stopTesting = async () => {
        if (!draft) return;
        setLoading(true);
        try {
            const resp = await fetch(`${API_URL}/api/agents/drafts/${draft.id}/stop`, {
                method: "POST",
                headers: headers(),
            });
            if (resp.ok) {
                const updated: DraftAgent = await resp.json();
                setDraft(updated);
            }
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : String(e));
        } finally {
            setLoading(false);
        }
    };

    const refineAgent = async () => {
        if (!draft || !chatInput.trim()) return;
        const msg = chatInput.trim();
        setChatInput("");
        setRefining(true);
        setError(null);
        try {
            const resp = await fetch(`${API_URL}/api/agents/drafts/${draft.id}/refine`, {
                method: "POST",
                headers: headers(),
                body: JSON.stringify({ message: msg }),
            });
            if (!resp.ok) {
                const err = await resp.json();
                throw new Error(err.detail || "Refinement failed");
            }
            const updated: DraftAgent = await resp.json();
            setDraft(updated);
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : String(e));
        } finally {
            setRefining(false);
        }
    };

    const approveAgent = async () => {
        if (!draft) return;
        setLoading(true);
        setError(null);
        try {
            const resp = await fetch(`${API_URL}/api/agents/drafts/${draft.id}/approve`, {
                method: "POST",
                headers: headers(),
            });
            if (!resp.ok) {
                const err = await resp.json();
                throw new Error(err.detail || "Approval failed");
            }
            const updated: DraftAgent = await resp.json();
            setDraft(updated);
            if (updated.status === "live") {
                onAgentCreated?.();
            }
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : String(e));
        } finally {
            setLoading(false);
        }
    };

    // ─── Tool Management ────────────────────────────────────────────

    const addTool = () => {
        setTools([...tools, { name: "", description: "", scope: "tools:read", params: [] }]);
    };

    const updateTool = (index: number, field: keyof ToolSpec, value: unknown) => {
        const updated = [...tools];
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (updated[index] as any)[field] = value;
        setTools(updated);
    };

    const removeTool = (index: number) => {
        setTools(tools.filter((_, i) => i !== index));
    };

    const addParam = (toolIndex: number) => {
        const updated = [...tools];
        updated[toolIndex].params.push({ name: "", type: "string", description: "", required: false });
        setTools(updated);
    };

    const updateParam = (toolIndex: number, paramIndex: number, field: string, value: unknown) => {
        const updated = [...tools];
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (updated[toolIndex].params[paramIndex] as any)[field] = value;
        setTools(updated);
    };

    const removeParam = (toolIndex: number, paramIndex: number) => {
        const updated = [...tools];
        updated[toolIndex].params = updated[toolIndex].params.filter((_, i) => i !== paramIndex);
        setTools(updated);
    };

    // ─── Tag / Package Helpers ──────────────────────────────────────

    const addTag = (e: React.KeyboardEvent) => {
        if (e.key === "Enter" && tagInput.trim()) {
            e.preventDefault();
            if (!tags.includes(tagInput.trim())) {
                setTags([...tags, tagInput.trim()]);
            }
            setTagInput("");
        }
    };

    const addPackage = (e: React.KeyboardEvent) => {
        if (e.key === "Enter" && pkgInput.trim()) {
            e.preventDefault();
            if (!packages.includes(pkgInput.trim())) {
                setPackages([...packages, pkgInput.trim()]);
            }
            setPkgInput("");
        }
    };

    // ─── Validation ─────────────────────────────────────────────────

    const canProceedStep1 = agentName.trim().length >= 2 && description.trim().length >= 10;
    const canProceedStep2 = true; // Tools are optional
    const isStep4 = step === 4;

    if (!isOpen) return null;

    // ─── Render ─────────────────────────────────────────────────────

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
            onClick={handleClose}
        >
            <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
                transition={{ duration: 0.15 }}
                className={`bg-astral-surface border border-white/10 rounded-xl shadow-2xl mx-4 flex flex-col transition-all duration-300 ${
                    isStep4
                        ? "w-[95vw] max-w-[1600px] h-[90vh]"
                        : "max-w-2xl w-full max-h-[85vh]"
                }`}
                onClick={(e) => e.stopPropagation()}
            >
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-white/5 flex-shrink-0">
                    <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-astral-accent/20 flex items-center justify-center">
                            <Zap size={16} className="text-astral-accent" />
                        </div>
                        <div>
                            <h2 className="text-base font-semibold text-white">
                                {isStep4 && draft ? draft.agent_name : "Create Agent"}
                            </h2>
                            <p className="text-xs text-astral-muted">
                                Step {step} of 4 &mdash; {
                                    step === 1 ? "Define Agent" :
                                    step === 2 ? "Define Tools" :
                                    step === 3 ? "Review & Generate" :
                                    "Test & Refine"
                                }
                            </p>
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        {isStep4 && draft && (
                            <span className={`flex items-center gap-1 text-xs px-2 py-1 rounded-md border border-white/5 ${STATUS_LABELS[draft.status]?.color || "text-astral-muted"}`}>
                                {STATUS_LABELS[draft.status]?.icon}
                                {STATUS_LABELS[draft.status]?.label || draft.status}
                                {draft.port && <span className="text-astral-muted ml-1">:{draft.port}</span>}
                            </span>
                        )}
                        <button onClick={handleClose} className="p-1.5 rounded-lg hover:bg-white/10 transition-colors">
                            <X size={16} className="text-astral-muted" />
                        </button>
                    </div>
                </div>

                {/* Step indicator */}
                <div className="flex items-center gap-1 px-6 pt-3 flex-shrink-0">
                    {[1, 2, 3, 4].map(s => (
                        <div key={s} className={`h-1 flex-1 rounded-full transition-colors ${
                            s <= step ? "bg-astral-accent" : "bg-white/10"
                        }`} />
                    ))}
                </div>

                {/* Content */}
                <div className={`flex-1 overflow-hidden ${isStep4 ? "" : "overflow-y-auto p-6"}`}>
                    {/* Step 1: Define Agent */}
                    {step === 1 && (
                        <div className="space-y-4 p-6">
                            <div>
                                <label className="block text-xs font-medium text-astral-muted mb-1.5">Agent Name *</label>
                                <input
                                    type="text"
                                    value={agentName}
                                    onChange={e => setAgentName(e.target.value)}
                                    placeholder="e.g., Stock Tracker"
                                    maxLength={100}
                                    className="w-full px-3 py-2 text-sm bg-white/5 border border-white/10 rounded-lg
                                               text-white placeholder-astral-muted/50 focus:outline-none focus:border-astral-accent/40"
                                />
                            </div>
                            <div>
                                <label className="block text-xs font-medium text-astral-muted mb-1.5">Description *</label>
                                <textarea
                                    value={description}
                                    onChange={e => setDescription(e.target.value)}
                                    placeholder="Describe what this agent does, what data it works with, and its capabilities..."
                                    rows={3}
                                    className="w-full px-3 py-2 text-sm bg-white/5 border border-white/10 rounded-lg
                                               text-white placeholder-astral-muted/50 focus:outline-none focus:border-astral-accent/40 resize-none"
                                />
                                <p className="text-[10px] text-astral-muted mt-1">{description.length}/10 min characters</p>
                            </div>
                            <div>
                                <label className="flex items-center gap-1.5 text-xs font-medium text-astral-muted mb-1.5">
                                    <Tag size={12} /> Skill Tags <span className="opacity-50">(optional)</span>
                                </label>
                                <div className="flex flex-wrap gap-1.5 mb-2">
                                    {tags.map(tag => (
                                        <span key={tag} className="flex items-center gap-1 px-2 py-0.5 text-xs bg-astral-primary/15 text-astral-primary rounded-full border border-astral-primary/20">
                                            {tag}
                                            <button onClick={() => setTags(tags.filter(t => t !== tag))} className="hover:text-white">
                                                <X size={10} />
                                            </button>
                                        </span>
                                    ))}
                                </div>
                                <input
                                    type="text"
                                    value={tagInput}
                                    onChange={e => setTagInput(e.target.value)}
                                    onKeyDown={addTag}
                                    placeholder="Type a tag and press Enter"
                                    className="w-full px-3 py-1.5 text-xs bg-white/5 border border-white/10 rounded-lg
                                               text-white placeholder-astral-muted/50 focus:outline-none focus:border-astral-accent/40"
                                />
                            </div>
                            <div>
                                <label className="flex items-center gap-1.5 text-xs font-medium text-astral-muted mb-1.5">
                                    <Package size={12} /> Python Packages <span className="opacity-50">(optional)</span>
                                </label>
                                <div className="flex flex-wrap gap-1.5 mb-2">
                                    {packages.map(pkg => (
                                        <span key={pkg} className="flex items-center gap-1 px-2 py-0.5 text-xs bg-astral-secondary/15 text-astral-secondary rounded-full border border-astral-secondary/20">
                                            {pkg}
                                            <button onClick={() => setPackages(packages.filter(p => p !== pkg))} className="hover:text-white">
                                                <X size={10} />
                                            </button>
                                        </span>
                                    ))}
                                </div>
                                <input
                                    type="text"
                                    value={pkgInput}
                                    onChange={e => setPkgInput(e.target.value)}
                                    onKeyDown={addPackage}
                                    placeholder="e.g., requests, pandas (press Enter)"
                                    className="w-full px-3 py-1.5 text-xs bg-white/5 border border-white/10 rounded-lg
                                               text-white placeholder-astral-muted/50 focus:outline-none focus:border-astral-accent/40"
                                />
                            </div>
                        </div>
                    )}

                    {/* Step 2: Define Tools */}
                    {step === 2 && (
                        <div className="space-y-4 p-6">
                            <p className="text-xs text-astral-muted">
                                Define specific tools for your agent, or skip this step and let AI generate tools based on your description.
                            </p>
                            {tools.map((tool, ti) => (
                                <div key={ti} className="border border-white/10 rounded-lg p-4 space-y-3 bg-white/[0.02]">
                                    <div className="flex items-center justify-between">
                                        <span className="text-xs font-medium text-astral-accent flex items-center gap-1.5">
                                            <Wrench size={12} /> Tool {ti + 1}
                                        </span>
                                        <button onClick={() => removeTool(ti)} className="p-1 rounded hover:bg-red-500/10 text-astral-muted hover:text-red-400">
                                            <Trash2 size={12} />
                                        </button>
                                    </div>
                                    <input
                                        type="text"
                                        value={tool.name}
                                        onChange={e => updateTool(ti, "name", e.target.value)}
                                        placeholder="function_name"
                                        className="w-full px-2.5 py-1.5 text-xs bg-white/5 border border-white/10 rounded-lg text-white placeholder-astral-muted/50 focus:outline-none focus:border-astral-accent/40"
                                    />
                                    {/* Feature 013 / US3 (T029): replace the legacy scope
                                        dropdown with a per-permission selector cluster so
                                        the author sees every permission kind at a glance
                                        and the choice is visually explicit. The data
                                        model is unchanged (one required scope per tool);
                                        each pill is keyboard-reachable. */}
                                    <div>
                                        <span className="text-[10px] text-astral-muted uppercase tracking-wider block mb-1.5">
                                            Required permission
                                        </span>
                                        <div
                                            role="radiogroup"
                                            aria-label={`Permission for tool ${ti + 1}`}
                                            data-testid={`tool-${ti}-permission-cluster`}
                                            className="flex flex-wrap gap-1.5"
                                        >
                                            {SCOPES.map(s => {
                                                const selected = tool.scope === s.value;
                                                return (
                                                    <button
                                                        key={s.value}
                                                        type="button"
                                                        role="radio"
                                                        aria-checked={selected}
                                                        data-testid={`tool-${ti}-permission-${s.value}`}
                                                        onClick={() => updateTool(ti, "scope", s.value)}
                                                        title={`${s.label} — required for this tool`}
                                                        className={`px-2.5 py-1 text-[11px] font-medium rounded-md border transition-colors ${
                                                            selected
                                                                ? `${s.color} bg-white/[0.06] border-white/20`
                                                                : "text-astral-muted bg-white/[0.02] border-white/5 hover:bg-white/5 hover:border-white/10"
                                                        }`}
                                                    >
                                                        {s.label}
                                                    </button>
                                                );
                                            })}
                                        </div>
                                    </div>
                                    <textarea
                                        value={tool.description}
                                        onChange={e => updateTool(ti, "description", e.target.value)}
                                        placeholder="What does this tool do?"
                                        rows={2}
                                        className="w-full px-2.5 py-1.5 text-xs bg-white/5 border border-white/10 rounded-lg text-white placeholder-astral-muted/50 focus:outline-none focus:border-astral-accent/40 resize-none"
                                    />
                                    {/* Parameters */}
                                    {tool.params.length > 0 && (
                                        <div className="space-y-2">
                                            <span className="text-[10px] text-astral-muted uppercase tracking-wider">Parameters</span>
                                            {tool.params.map((p, pi) => (
                                                <div key={pi} className="flex items-center gap-2">
                                                    <input
                                                        type="text"
                                                        value={p.name}
                                                        onChange={e => updateParam(ti, pi, "name", e.target.value)}
                                                        placeholder="param_name"
                                                        className="flex-1 px-2 py-1 text-[11px] bg-white/5 border border-white/10 rounded text-white placeholder-astral-muted/50 focus:outline-none focus:border-astral-accent/40"
                                                    />
                                                    <select
                                                        value={p.type}
                                                        onChange={e => updateParam(ti, pi, "type", e.target.value)}
                                                        className="px-2 py-1 text-[11px] bg-white/5 border border-white/10 rounded text-white focus:outline-none"
                                                    >
                                                        <option value="string">string</option>
                                                        <option value="number">number</option>
                                                        <option value="integer">integer</option>
                                                        <option value="boolean">boolean</option>
                                                        <option value="array">array</option>
                                                        <option value="object">object</option>
                                                    </select>
                                                    <label className="flex items-center gap-1 text-[10px] text-astral-muted">
                                                        <input
                                                            type="checkbox"
                                                            checked={p.required}
                                                            onChange={e => updateParam(ti, pi, "required", e.target.checked)}
                                                            className="rounded border-white/20"
                                                        />
                                                        Req
                                                    </label>
                                                    <button onClick={() => removeParam(ti, pi)} className="p-0.5 text-astral-muted hover:text-red-400">
                                                        <X size={10} />
                                                    </button>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                    <button
                                        onClick={() => addParam(ti)}
                                        className="text-[10px] text-astral-accent hover:text-astral-accent/80 flex items-center gap-1"
                                    >
                                        <Plus size={10} /> Add parameter
                                    </button>
                                </div>
                            ))}
                            <button
                                onClick={addTool}
                                className="w-full py-2.5 text-xs font-medium rounded-lg border border-dashed border-white/10
                                           text-astral-muted hover:text-astral-accent hover:border-astral-accent/30 transition-colors
                                           flex items-center justify-center gap-1.5"
                            >
                                <Plus size={14} /> Add Tool
                            </button>
                        </div>
                    )}

                    {/* Step 3: Review & Generate */}
                    {step === 3 && (
                        <div className="space-y-4 p-6">
                            {/* Summary */}
                            <div className="border border-white/10 rounded-lg p-4 space-y-2 bg-white/[0.02]">
                                <h3 className="text-sm font-medium text-white">{agentName}</h3>
                                <p className="text-xs text-astral-muted">{description}</p>
                                {tags.length > 0 && (
                                    <div className="flex flex-wrap gap-1">
                                        {tags.map(t => (
                                            <span key={t} className="px-2 py-0.5 text-[10px] bg-astral-primary/15 text-astral-primary rounded-full">{t}</span>
                                        ))}
                                    </div>
                                )}
                                {packages.length > 0 && (
                                    <div className="flex flex-wrap gap-1">
                                        {packages.map(p => (
                                            <span key={p} className="px-2 py-0.5 text-[10px] bg-astral-secondary/15 text-astral-secondary rounded-full">{p}</span>
                                        ))}
                                    </div>
                                )}
                                {tools.length > 0 && (
                                    <div className="text-xs text-astral-muted mt-2">
                                        {tools.length} tool{tools.length !== 1 ? "s" : ""} defined
                                    </div>
                                )}
                            </div>

                            {/* Progress */}
                            {progress.length > 0 && (
                                <div className="space-y-2">
                                    {progress.map((p, i) => (
                                        <div key={i} className="flex items-start gap-2 text-xs">
                                            {p.status === "error" || p.status === "rejected"
                                                ? <XCircle size={14} className="text-red-400 mt-0.5 flex-shrink-0" />
                                                : p.step === "complete"
                                                ? <CheckCircle2 size={14} className="text-green-400 mt-0.5 flex-shrink-0" />
                                                : <Loader2 size={14} className="text-blue-400 mt-0.5 flex-shrink-0 animate-spin" />}
                                            <span className={p.status === "error" ? "text-red-400" : "text-astral-muted"}>{p.message}</span>
                                        </div>
                                    ))}
                                </div>
                            )}

                            {/* Security Report */}
                            {draft?.security_report && draft.security_report.findings?.length > 0 && (
                                <div className="border border-white/10 rounded-lg p-3 space-y-2 bg-white/[0.02]">
                                    <h4 className="text-xs font-medium text-astral-muted flex items-center gap-1.5">
                                        <Shield size={12} /> Security Report
                                    </h4>
                                    {draft.security_report.findings.map((f, i) => (
                                        <div key={i} className={`flex items-start gap-2 text-[11px] px-2 py-1 rounded border ${SEVERITY_COLORS[f.severity] || "text-astral-muted"}`}>
                                            <span className="font-medium uppercase text-[9px] mt-0.5">{f.severity}</span>
                                            <span>{f.message}{f.line ? ` (line ${f.line})` : ""}</span>
                                        </div>
                                    ))}
                                </div>
                            )}

                            {/* Validation Report */}
                            {draft?.validation_report && (
                                <div className={`border rounded-lg p-3 space-y-2 ${
                                    draft.validation_report.passed
                                        ? "border-green-500/20 bg-green-500/5"
                                        : "border-amber-500/20 bg-amber-500/5"
                                }`}>
                                    <h4 className="text-xs font-medium flex items-center gap-1.5">
                                        <CheckCircle2 size={12} className={draft.validation_report.passed ? "text-green-400" : "text-amber-400"} />
                                        <span className={draft.validation_report.passed ? "text-green-400" : "text-amber-400"}>
                                            Spec Validation — {draft.validation_report.tools_passed}/{draft.validation_report.tools_tested} tools passed
                                        </span>
                                    </h4>
                                    {(draft.validation_report.tools?.length ?? 0) > 0 ? (
                                        <>
                                            {draft.validation_report.tools!.map((tool, i) => {
                                                const toolFindings = draft.validation_report!.findings.filter(f => f.tool_name === tool.name);
                                                const hasError = toolFindings.some(f => f.severity === "error");
                                                return (
                                                    <div key={i} className={`rounded border px-2.5 py-2 ${
                                                        hasError ? "border-red-500/20 bg-red-500/5" : "border-green-500/20 bg-green-500/5"
                                                    }`}>
                                                        <div className="flex items-center gap-2">
                                                            <span className={`font-mono text-xs font-medium ${hasError ? "text-red-400" : "text-green-400"}`}>
                                                                {tool.name}
                                                            </span>
                                                            <span className="text-[9px] px-1.5 py-0.5 rounded bg-white/5 text-astral-muted font-mono">{tool.scope}</span>
                                                        </div>
                                                        {tool.description && (
                                                            <p className="text-[11px] text-white/60 mt-0.5">{tool.description}</p>
                                                        )}
                                                        {tool.parameters?.length > 0 && (
                                                            <div className="mt-1.5 space-y-0.5">
                                                                {tool.parameters.map((p, j) => (
                                                                    <div key={j} className="flex items-baseline gap-1.5 text-[10px]">
                                                                        <span className="font-mono text-white/80">{p.name}</span>
                                                                        <span className="text-astral-muted font-mono">{p.type}</span>
                                                                        {p.required && <span className="text-amber-400/70 text-[8px]">required</span>}
                                                                        {p.description && <span className="text-white/40">— {p.description}</span>}
                                                                    </div>
                                                                ))}
                                                            </div>
                                                        )}
                                                        {toolFindings.filter(f => f.severity !== "info").map((f, fi) => (
                                                            <div key={fi} className={`mt-1 text-[10px] px-1.5 py-0.5 rounded ${
                                                                f.severity === "error" ? "text-red-400 bg-red-400/10" : "text-amber-400 bg-amber-400/10"
                                                            }`}>
                                                                {f.message}
                                                            </div>
                                                        ))}
                                                    </div>
                                                );
                                            })}
                                            {draft.validation_report.findings
                                                .filter(f => !f.tool_name && f.severity !== "info")
                                                .map((f, i) => (
                                                <div key={`g-${i}`} className={`text-[11px] px-2 py-1 rounded border ${
                                                    f.severity === "error"
                                                        ? "text-red-400 bg-red-400/10 border-red-400/20"
                                                        : "text-amber-400 bg-amber-400/10 border-amber-400/20"
                                                }`}>
                                                    {f.message}
                                                </div>
                                            ))}
                                        </>
                                    ) : (
                                        /* Fallback for reports without tools metadata */
                                        draft.validation_report.findings.map((f, i) => (
                                            <div key={i} className={`text-[11px] px-2 py-1 rounded border ${
                                                f.severity === "error"
                                                    ? "text-red-400 bg-red-400/10 border-red-400/20"
                                                    : f.severity === "warning"
                                                    ? "text-amber-400 bg-amber-400/10 border-amber-400/20"
                                                    : "text-green-400 bg-green-400/10 border-green-400/20"
                                            }`}>
                                                <span className="font-medium uppercase text-[9px]">{f.severity}</span>
                                                {f.tool_name && <span className="font-mono text-white/60 ml-1">[{f.tool_name}]</span>}
                                                {" "}{f.message}
                                            </div>
                                        ))
                                    )}
                                </div>
                            )}

                            {/* Error */}
                            {error && (
                                <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/20 text-xs text-red-400">
                                    <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" />
                                    {error}
                                </div>
                            )}
                        </div>
                    )}

                    {/* Step 4: Test & Refine — Expanded side-by-side layout */}
                    {step === 4 && draft && (
                        <div className="flex h-full">
                            {/* Left: Test Chat */}
                            <div className="flex-1 flex flex-col border-r border-white/5 min-w-0">
                                {/* Test chat header */}
                                <div className="flex items-center justify-between px-4 py-2.5 border-b border-white/5 flex-shrink-0">
                                    <div className="flex items-center gap-2">
                                        <MessageSquare size={14} className="text-astral-accent" />
                                        <span className="text-xs font-medium text-white">Test Chat</span>
                                        {testStatus !== "idle" && testStatus !== "done" && (
                                            <span className={`flex items-center gap-1 text-[10px] ${
                                                testStatus === "fixing" ? "text-cyan-400" :
                                                testStatus === "executing" ? "text-amber-400" :
                                                testStatus === "retrying" ? "text-orange-400" :
                                                "text-blue-400"
                                            }`}>
                                                <Loader2 size={10} className="animate-spin" />
                                                {testStatusMsg || (
                                                    testStatus === "fixing" ? "Auto-fixing..." :
                                                    testStatus === "executing" ? "Executing..." :
                                                    testStatus === "retrying" ? "Retrying..." :
                                                    "Processing..."
                                                )}
                                            </span>
                                        )}
                                    </div>
                                    {draft.status !== "testing" && (
                                        <span className="text-[10px] text-astral-muted">Start testing to chat</span>
                                    )}
                                </div>

                                {/* Test chat messages */}
                                <div className="flex-1 overflow-y-auto p-4 space-y-4">
                                    {/* Feature 012-fix-agent-flows Story 1+2: explicit
                                        error state with Retry / Edit Definition / Close
                                        actions when generation or subprocess startup
                                        failed. Without this banner the user lands on a
                                        frozen empty chat and has no recovery path. */}
                                    {draft.status === "error" && (
                                        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4">
                                            <div className="flex items-start gap-2 mb-2">
                                                <AlertTriangle size={16} className="text-red-400 mt-0.5 flex-shrink-0" />
                                                <div className="min-w-0">
                                                    <p className="text-sm font-medium text-red-400">Draft agent could not start</p>
                                                    <p className="text-xs text-red-300/80 mt-1 break-words">
                                                        {draft.error_message || "An unknown error occurred."}
                                                    </p>
                                                </div>
                                            </div>
                                            <div className="flex items-center gap-2 mt-3">
                                                <button
                                                    type="button"
                                                    onClick={async () => {
                                                        if (!draft?.id) return;
                                                        ensuredStartedRef.current = null;
                                                        try {
                                                            const resp = await fetch(`${API_URL}/api/agents/drafts/${draft.id}/test`, {
                                                                method: "POST",
                                                                headers: headers(),
                                                            });
                                                            if (resp.ok) {
                                                                const updated: DraftAgent = await resp.json();
                                                                setDraft(updated);
                                                            }
                                                        } catch {
                                                            // surfaced via the next status update
                                                        }
                                                    }}
                                                    className="px-3 py-1.5 text-xs rounded-lg bg-red-500/20 text-red-300 border border-red-500/30 hover:bg-red-500/30 transition-colors"
                                                >
                                                    Retry
                                                </button>
                                                <button
                                                    type="button"
                                                    onClick={() => setStep(3)}
                                                    className="px-3 py-1.5 text-xs rounded-lg bg-white/5 text-white border border-white/10 hover:bg-white/10 transition-colors"
                                                >
                                                    Edit Definition
                                                </button>
                                                <button
                                                    type="button"
                                                    onClick={handleClose}
                                                    className="px-3 py-1.5 text-xs rounded-lg text-astral-muted hover:text-white hover:bg-white/5 transition-colors ml-auto"
                                                >
                                                    Close
                                                </button>
                                            </div>
                                        </div>
                                    )}
                                    {testMessages.length === 0 && draft.status === "testing" && (
                                        <div className="flex flex-col items-center justify-center h-full text-center opacity-50">
                                            <Bot size={32} className="text-astral-muted mb-2" />
                                            <p className="text-xs text-astral-muted">Send a message to test your agent</p>
                                            <p className="text-[10px] text-astral-muted mt-1">
                                                Try asking it to use its tools
                                            </p>
                                        </div>
                                    )}
                                    {testMessages.length === 0 && draft.status === "generated" && (
                                        <div className="flex flex-col items-center justify-center h-full text-center opacity-60">
                                            <Loader2 size={32} className="text-astral-muted mb-2 animate-spin" />
                                            <p className="text-xs text-astral-muted">Starting your agent...</p>
                                            <p className="text-[10px] text-astral-muted mt-1">
                                                This usually takes a few seconds.
                                            </p>
                                        </div>
                                    )}
                                    {testMessages.length === 0 && draft.status !== "testing" && draft.status !== "generated" && draft.status !== "error" && (
                                        <div className="flex flex-col items-center justify-center h-full text-center opacity-50">
                                            <Play size={32} className="text-astral-muted mb-2" />
                                            <p className="text-xs text-astral-muted">Start testing to begin chatting with your agent</p>
                                        </div>
                                    )}
                                    {testMessages.map((msg, i) => (
                                        <div key={i} className={`${msg.role === "user" ? "flex justify-end" : ""}`}>
                                            {msg.role === "user" ? (
                                                <div className="max-w-[80%] px-3 py-2 rounded-xl bg-astral-accent/15 border border-astral-accent/20 text-sm text-white">
                                                    {String(msg.content)}
                                                </div>
                                            ) : msg.role === "status" ? (
                                                <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/20 text-xs text-red-400">
                                                    <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" />
                                                    {String(msg.content)}
                                                </div>
                                            ) : typeof msg.content === "string" ? (
                                                <div className="px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-sm text-white whitespace-pre-wrap">
                                                    {msg.content}
                                                </div>
                                            ) : (
                                                <div className="space-y-2">
                                                    <DynamicRenderer components={msg.content} />
                                                </div>
                                            )}
                                        </div>
                                    ))}
                                    {testStatus !== "idle" && testStatus !== "done" && (
                                        <div className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs ${
                                            testStatus === "fixing"
                                                ? "bg-cyan-500/10 border border-cyan-500/20 text-cyan-400"
                                                : testStatus === "executing"
                                                ? "bg-amber-500/10 border border-amber-500/20 text-amber-400"
                                                : testStatus === "retrying"
                                                ? "bg-orange-500/10 border border-orange-500/20 text-orange-400"
                                                : "bg-blue-500/10 border border-blue-500/20 text-blue-400"
                                        }`}>
                                            <Loader2 size={14} className="animate-spin flex-shrink-0" />
                                            <span>{testStatusMsg || (
                                                testStatus === "fixing" ? "Tool error detected — auto-fixing and restarting agent..." :
                                                testStatus === "executing" ? "Executing tools..." :
                                                testStatus === "retrying" ? "Retrying after fix..." :
                                                "Processing your message..."
                                            )}</span>
                                        </div>
                                    )}
                                    <div ref={testChatEndRef} />
                                </div>

                                {/* Test chat input — feature 012-fix-agent-flows:
                                    deliberately NOT a <form>. A native form
                                    submit (Enter key, button type=submit) was
                                    causing the entire modal to remount on every
                                    response because the form's default submit
                                    behavior was firing alongside our handler.
                                    Now uses an onKeyDown handler on the input
                                    and a type="button" send button. There is
                                    no form-submit path that React or the
                                    browser can take. */}
                                <div className="flex items-center gap-2 px-4 py-3 border-t border-white/5 flex-shrink-0">
                                    <input
                                        type="text"
                                        value={testInput}
                                        onChange={e => setTestInput(e.target.value)}
                                        onKeyDown={(e) => {
                                            if (e.key === "Enter" && !e.shiftKey) {
                                                e.preventDefault();
                                                e.stopPropagation();
                                                sendTestMessage();
                                            }
                                        }}
                                        placeholder={draft.status === "testing" ? "Ask your agent something..." : "Start testing first..."}
                                        disabled={draft.status !== "testing" || testStatus === "thinking" || testStatus === "executing" || testStatus === "fixing"}
                                        className="flex-1 px-3 py-2 text-sm bg-white/5 border border-white/10 rounded-lg
                                                   text-white placeholder-astral-muted/50 focus:outline-none focus:border-astral-accent/40
                                                   disabled:opacity-40"
                                    />
                                    <button
                                        type="button"
                                        onClick={(e) => { e.preventDefault(); e.stopPropagation(); sendTestMessage(); }}
                                        disabled={draft.status !== "testing" || !testInput.trim() || testStatus === "thinking" || testStatus === "executing"}
                                        className="p-2 rounded-lg bg-astral-accent/15 text-astral-accent border border-astral-accent/20
                                                   hover:bg-astral-accent/25 disabled:opacity-30 transition-colors"
                                    >
                                        <Send size={14} />
                                    </button>
                                </div>
                            </div>

                            {/* Right: Controls + Refinement Chat */}
                            <div className="w-[360px] flex-shrink-0 flex flex-col overflow-hidden">
                                {/* Controls section */}
                                <div className="p-4 space-y-3 border-b border-white/5 flex-shrink-0 overflow-y-auto max-h-[50%]">

                                    {/* Credential entry form */}
                                    {draft.required_credentials && draft.required_credentials.length > 0 && (
                                        <div className="p-3 rounded-lg border border-amber-500/20 bg-amber-500/5 space-y-2.5">
                                            <div className="flex items-center gap-2 text-amber-400 text-xs font-medium">
                                                <KeyRound size={14} />
                                                Required Credentials
                                            </div>
                                            {draft.required_credentials.map((cred) => {
                                                const isStored = storedCredentialKeys.includes(cred.key);
                                                return (
                                                    <div key={cred.key} className="space-y-1">
                                                        <label className="flex items-center gap-1.5 text-xs text-white/70">
                                                            {cred.label}
                                                            {cred.required && <span className="text-red-400 text-[10px]">*</span>}
                                                            {isStored && <CheckCircle2 size={11} className="text-green-400" />}
                                                        </label>
                                                        {cred.description && (
                                                            <p className="text-[10px] text-white/40 leading-tight">{cred.description}</p>
                                                        )}
                                                        <input
                                                            type={cred.type === "password" || cred.type === "oauth_client_secret" ? "password" : "text"}
                                                            placeholder={isStored ? "\u2022\u2022\u2022\u2022\u2022\u2022\u2022 (saved)" : `Enter ${cred.label}`}
                                                            value={credentialValues[cred.key] || ""}
                                                            onChange={(e) => setCredentialValues(prev => ({
                                                                ...prev, [cred.key]: e.target.value,
                                                            }))}
                                                            className="w-full px-2 py-1.5 text-xs bg-white/5 border border-white/10 rounded
                                                                       text-white placeholder-white/30 focus:outline-none focus:border-amber-500/40"
                                                        />
                                                    </div>
                                                );
                                            })}
                                            <button
                                                onClick={saveCredentials}
                                                disabled={credentialsSaving || Object.values(credentialValues).every(v => !v.trim())}
                                                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg w-full justify-center
                                                           bg-amber-500/15 text-amber-400 border border-amber-500/20 hover:bg-amber-500/25
                                                           disabled:opacity-50 transition-colors"
                                            >
                                                {credentialsSaving ? <Loader2 size={12} className="animate-spin" /> : <KeyRound size={12} />}
                                                {credentialsSaving ? "Saving..." : "Save Credentials"}
                                            </button>
                                        </div>
                                    )}

                                    {/* Action buttons */}
                                    <div className="flex flex-wrap items-center gap-2">
                                        {(draft.status === "generated" || draft.status === "error") && (() => {
                                            const requiredCreds = draft.required_credentials?.filter(c => c.required) || [];
                                            const allRequiredStored = requiredCreds.every(c => storedCredentialKeys.includes(c.key));
                                            const needsCreds = requiredCreds.length > 0 && !allRequiredStored;
                                            return (
                                                <div className="flex flex-col gap-1">
                                                    <button
                                                        onClick={startTesting}
                                                        disabled={loading || needsCreds}
                                                        className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg
                                                                   bg-green-500/15 text-green-400 border border-green-500/20 hover:bg-green-500/25
                                                                   disabled:opacity-50 transition-colors"
                                                    >
                                                        {loading ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />}
                                                        Start Testing
                                                    </button>
                                                    {needsCreds && (
                                                        <span className="text-[10px] text-amber-400/70">
                                                            Provide required credentials first
                                                        </span>
                                                    )}
                                                </div>
                                            );
                                        })()}
                                        {draft.status === "testing" && (
                                            <>
                                                <button
                                                    onClick={stopTesting}
                                                    disabled={loading}
                                                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg
                                                               bg-red-500/15 text-red-400 border border-red-500/20 hover:bg-red-500/25
                                                               disabled:opacity-50 transition-colors"
                                                >
                                                    <Square size={12} /> Stop
                                                </button>
                                                <button
                                                    onClick={approveAgent}
                                                    disabled={loading}
                                                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg
                                                               bg-astral-accent/15 text-astral-accent border border-astral-accent/20 hover:bg-astral-accent/25
                                                               disabled:opacity-50 transition-colors"
                                                >
                                                    {loading ? <Loader2 size={12} className="animate-spin" /> : <Shield size={12} />}
                                                    Approve Agent
                                                </button>
                                            </>
                                        )}
                                        {draft.status === "live" && (
                                            <div className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-green-400 bg-green-500/10 rounded-lg border border-green-500/20">
                                                <Zap size={12} /> Agent is live!
                                            </div>
                                        )}
                                        {draft.status === "pending_review" && (
                                            <div className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-amber-400 bg-amber-500/10 rounded-lg border border-amber-500/20">
                                                <Shield size={12} /> Awaiting admin approval
                                            </div>
                                        )}
                                        {draft.status === "rejected" && (
                                            <div className="flex items-start gap-1.5 px-3 py-1.5 text-xs text-red-400 bg-red-500/10 rounded-lg border border-red-500/20">
                                                <XCircle size={12} className="mt-0.5 flex-shrink-0" />
                                                <span>Rejected: {draft.error_message || "See security report"}</span>
                                            </div>
                                        )}
                                    </div>

                                    {/* Security findings (collapsed) */}
                                    {draft.security_report && draft.security_report.findings?.length > 0 && (
                                        <details className="border border-white/10 rounded-lg bg-white/[0.02]">
                                            <summary className="px-3 py-2 text-xs font-medium text-astral-muted flex items-center gap-1.5 cursor-pointer hover:text-white">
                                                <Shield size={12} /> {draft.security_report.findings.length} Security Finding{draft.security_report.findings.length !== 1 ? "s" : ""}
                                            </summary>
                                            <div className="px-3 pb-2 space-y-1">
                                                {draft.security_report.findings.map((f, i) => (
                                                    <div key={i} className={`text-[11px] px-2 py-1 rounded border ${SEVERITY_COLORS[f.severity] || "text-astral-muted"}`}>
                                                        <span className="font-medium uppercase text-[9px]">{f.severity}</span> {f.message}
                                                    </div>
                                                ))}
                                            </div>
                                        </details>
                                    )}

                                    {/* Validation report (collapsed) */}
                                    {draft.validation_report && (
                                        <details className={`border rounded-lg ${
                                            draft.validation_report.passed
                                                ? "border-green-500/20 bg-green-500/5"
                                                : "border-amber-500/20 bg-amber-500/5"
                                        }`}>
                                            <summary className={`px-3 py-2 text-xs font-medium flex items-center gap-1.5 cursor-pointer hover:text-white ${
                                                draft.validation_report.passed ? "text-green-400" : "text-amber-400"
                                            }`}>
                                                <CheckCircle2 size={12} />
                                                Spec Validation — {draft.validation_report.tools_passed}/{draft.validation_report.tools_tested} tools passed
                                            </summary>
                                            <div className="px-3 pb-2 space-y-1.5">
                                                {(draft.validation_report.tools?.length ?? 0) > 0 ? (
                                                    <>
                                                        {draft.validation_report.tools!.map((tool, i) => {
                                                            const toolFindings = draft.validation_report!.findings.filter(f => f.tool_name === tool.name);
                                                            const hasError = toolFindings.some(f => f.severity === "error");
                                                            return (
                                                                <div key={i} className={`rounded border px-2.5 py-1.5 ${
                                                                    hasError ? "border-red-500/20 bg-red-500/5" : "border-green-500/20 bg-green-500/5"
                                                                }`}>
                                                                    <div className="flex items-center gap-2">
                                                                        <span className={`font-mono text-[11px] font-medium ${hasError ? "text-red-400" : "text-green-400"}`}>
                                                                            {tool.name}
                                                                        </span>
                                                                        <span className="text-[8px] px-1 py-0.5 rounded bg-white/5 text-astral-muted font-mono">{tool.scope}</span>
                                                                    </div>
                                                                    {tool.description && (
                                                                        <p className="text-[10px] text-white/60 mt-0.5">{tool.description}</p>
                                                                    )}
                                                                    {tool.parameters?.length > 0 && (
                                                                        <div className="mt-1 space-y-0.5">
                                                                            {tool.parameters.map((p, j) => (
                                                                                <div key={j} className="flex items-baseline gap-1.5 text-[10px]">
                                                                                    <span className="font-mono text-white/80">{p.name}</span>
                                                                                    <span className="text-astral-muted font-mono">{p.type}</span>
                                                                                    {p.required && <span className="text-amber-400/70 text-[8px]">required</span>}
                                                                                    {p.description && <span className="text-white/40">— {p.description}</span>}
                                                                                </div>
                                                                            ))}
                                                                        </div>
                                                                    )}
                                                                    {toolFindings.filter(f => f.severity !== "info").map((f, fi) => (
                                                                        <div key={fi} className={`mt-1 text-[10px] px-1.5 py-0.5 rounded ${
                                                                            f.severity === "error" ? "text-red-400 bg-red-400/10" : "text-amber-400 bg-amber-400/10"
                                                                        }`}>
                                                                            {f.message}
                                                                        </div>
                                                                    ))}
                                                                </div>
                                                            );
                                                        })}
                                                        {draft.validation_report.findings
                                                            .filter(f => !f.tool_name && f.severity !== "info")
                                                            .map((f, i) => (
                                                            <div key={`g-${i}`} className={`text-[11px] px-2 py-1 rounded border ${
                                                                f.severity === "error"
                                                                    ? "text-red-400 bg-red-400/10 border-red-400/20"
                                                                    : "text-amber-400 bg-amber-400/10 border-amber-400/20"
                                                            }`}>
                                                                {f.message}
                                                            </div>
                                                        ))}
                                                    </>
                                                ) : (
                                                    /* Fallback for reports without tools metadata */
                                                    draft.validation_report.findings.map((f, i) => (
                                                        <div key={i} className={`text-[11px] px-2 py-1 rounded border ${
                                                            f.severity === "error"
                                                                ? "text-red-400 bg-red-400/10 border-red-400/20"
                                                                : f.severity === "warning"
                                                                ? "text-amber-400 bg-amber-400/10 border-amber-400/20"
                                                                : "text-green-400 bg-green-400/10 border-green-400/20"
                                                        }`}>
                                                            <span className="font-medium uppercase text-[9px]">{f.severity}</span>
                                                            {f.tool_name && <span className="font-mono text-white/50 ml-1">[{f.tool_name}]</span>}
                                                            {" "}{f.message}
                                                        </div>
                                                    ))
                                                )}
                                            </div>
                                        </details>
                                    )}

                                    {/* Error */}
                                    {error && (
                                        <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/20 text-xs text-red-400">
                                            <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" />
                                            {error}
                                        </div>
                                    )}
                                </div>

                                {/* Refinement Chat */}
                                <div className="flex-1 flex flex-col overflow-hidden">
                                    <div className="px-4 py-2.5 border-b border-white/5 flex-shrink-0">
                                        <div className="flex items-center gap-2">
                                            <Wrench size={14} className="text-astral-primary" />
                                            <span className="text-xs font-medium text-white">Refinement Chat</span>
                                        </div>
                                        <p className="text-[10px] text-astral-muted mt-0.5">Describe changes to your agent&apos;s tools</p>
                                    </div>
                                    <div className="flex-1 overflow-y-auto p-3 space-y-2">
                                        {(draft.refinement_history || []).length === 0 && (
                                            <div className="flex flex-col items-center justify-center h-full text-center opacity-40">
                                                <p className="text-[11px] text-astral-muted">
                                                    Tell the system what to change about your agent&apos;s tools
                                                </p>
                                            </div>
                                        )}
                                        {(draft.refinement_history || []).map((msg, i) => (
                                            <div key={i} className={`text-xs ${msg.role === "user" ? "text-white" : "text-astral-muted"}`}>
                                                <span className={`text-[10px] font-medium ${msg.role === "user" ? "text-astral-accent" : "text-astral-primary"}`}>
                                                    {msg.role === "user" ? "You" : "System"}:
                                                </span>{" "}
                                                {msg.content}
                                            </div>
                                        ))}
                                        {refining && (
                                            <div className="flex items-center gap-1.5 text-xs text-astral-muted">
                                                <Loader2 size={12} className="animate-spin" /> Refining...
                                            </div>
                                        )}
                                        <div ref={refineChatEndRef} />
                                    </div>
                                    <form
                                        onSubmit={(e) => { e.preventDefault(); refineAgent(); }}
                                        className="flex items-center gap-2 px-3 py-2.5 border-t border-white/5 flex-shrink-0"
                                    >
                                        <input
                                            type="text"
                                            value={chatInput}
                                            onChange={e => setChatInput(e.target.value)}
                                            placeholder="Describe changes..."
                                            disabled={refining || draft.status === "live"}
                                            className="flex-1 px-2.5 py-1.5 text-xs bg-white/5 border border-white/10 rounded-lg
                                                       text-white placeholder-astral-muted/50 focus:outline-none focus:border-astral-accent/40
                                                       disabled:opacity-50"
                                        />
                                        <button
                                            type="submit"
                                            disabled={refining || !chatInput.trim() || draft.status === "live"}
                                            className="p-1.5 rounded-lg bg-astral-accent/15 text-astral-accent border border-astral-accent/20
                                                       hover:bg-astral-accent/25 disabled:opacity-30 transition-colors"
                                        >
                                            <Send size={12} />
                                        </button>
                                    </form>
                                </div>
                            </div>
                        </div>
                    )}
                </div>

                {/* Footer (hidden on step 4 — controls are inline) */}
                {!isStep4 && (
                    <div className="flex items-center justify-between px-6 py-4 border-t border-white/5 flex-shrink-0">
                        <div>
                            {step > 1 && step < 4 && !loading && (
                                <button
                                    onClick={() => setStep(step - 1)}
                                    className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-astral-muted
                                               hover:text-white rounded-lg hover:bg-white/5 transition-colors"
                                >
                                    <ChevronLeft size={14} /> Back
                                </button>
                            )}
                        </div>
                        <div className="flex items-center gap-2">
                            {step === 1 && (
                                <button
                                    onClick={() => setStep(2)}
                                    disabled={!canProceedStep1}
                                    className="flex items-center gap-1 px-4 py-1.5 text-xs font-medium rounded-lg
                                               bg-astral-accent/15 text-astral-accent border border-astral-accent/20
                                               hover:bg-astral-accent/25 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                                >
                                    Next <ChevronRight size={14} />
                                </button>
                            )}
                            {step === 2 && (
                                <button
                                    onClick={() => setStep(3)}
                                    disabled={!canProceedStep2}
                                    className="flex items-center gap-1 px-4 py-1.5 text-xs font-medium rounded-lg
                                               bg-astral-accent/15 text-astral-accent border border-astral-accent/20
                                               hover:bg-astral-accent/25 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                                >
                                    Review <ChevronRight size={14} />
                                </button>
                            )}
                            {step === 3 && !draft && (
                                <button
                                    onClick={createAndGenerate}
                                    disabled={loading}
                                    className="flex items-center gap-1.5 px-4 py-1.5 text-xs font-medium rounded-lg
                                               bg-astral-accent text-white hover:bg-astral-accent/90
                                               disabled:opacity-50 transition-colors"
                                >
                                    {loading ? <Loader2 size={14} className="animate-spin" /> : <Zap size={14} />}
                                    Generate Agent
                                </button>
                            )}
                        </div>
                    </div>
                )}

                {/* Step 4 footer — just a Done button when applicable */}
                {isStep4 && (draft?.status === "live" || draft?.status === "pending_review") && (
                    <div className="flex items-center justify-end px-6 py-3 border-t border-white/5 flex-shrink-0">
                        <button
                            onClick={handleClose}
                            className="flex items-center gap-1 px-4 py-1.5 text-xs font-medium rounded-lg
                                       bg-astral-primary/15 text-astral-primary border border-astral-primary/20
                                       hover:bg-astral-primary/25 transition-colors"
                        >
                            Done
                        </button>
                    </div>
                )}
            </motion.div>
        </div>
    );
}
