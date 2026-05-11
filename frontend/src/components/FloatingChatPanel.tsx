/**
 * FloatingChatPanel — Collapsible floating text-only chat panel.
 *
 * Handles user query input and displays text-only LLM responses (summaries).
 * UI components are routed to the SDUICanvas instead.
 *
 * Features:
 * - Collapse/expand toggle
 * - Text-only message rendering (no SDUI components)
 * - File upload, voice input/output
 * - Mobile bottom sheet layout
 * - Chat status indicator
 */
import React, { useState, useRef, useEffect, useLayoutEffect, useCallback, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
    Send, Bot, User, MessageSquare, Loader2,
    Paperclip, X, FileMinus, FileText, Square, Mic, Volume2, VolumeX, Minus, UploadCloud, Wrench,
} from "lucide-react";
import ToolPicker from "./ToolPicker";
import { toast } from "sonner";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { normalizeLlmMarkdown } from "../utils/normalizeLlmMarkdown";
import { BFF_URL } from "../config";
import { ACCEPT_ATTRIBUTE } from "../lib/attachmentTypes";
import { useAttachments, formatAttachmentRefs } from "../hooks/useAttachments";
import { RotateCcw } from "lucide-react";
import type { Agent, ChatStatus, DeviceCapabilityFlags } from "../hooks/useWebSocket";
import type { ChatStepMap } from "../types/chatSteps";
import { CosmicProgressIndicator } from "./chat/CosmicProgressIndicator";
import { ChatStepEntry } from "./chat/ChatStepEntry";
import TextOnlyBanner from "./TextOnlyBanner";
import { setUserAgentEnabled } from "../api/toolSelection";
import { API_URL } from "../config";

interface FloatingChatPanelProps {
    messages: { role: string; content: unknown; _target?: string; id?: number }[];
    chatStatus: ChatStatus;
    /**
     * Feature 014 — persistent step entries for the active chat (US2).
     * Map of step id → step. Rendering sorts by ``started_at`` and shows
     * each entry inline below the latest exchange.
     */
    chatSteps?: ChatStepMap;
    onSendMessage: (message: string, displayMessage?: string, explicitChatId?: string) => void;
    onCancelTask: () => void;
    isConnected: boolean;
    activeChatId: string | null;
    accessToken?: string;
    deviceCapabilities?: DeviceCapabilityFlags;
    /**
     * Feature 008-llm-text-only-chat (FR-007a): false ⇒ render the
     * persistent text-only banner because the next chat turn would
     * dispatch with no agents/tools.
     */
    toolsAvailableForUser?: boolean;
    /** Feature 008: opens the existing Agents modal in DashboardLayout. */
    onOpenAgentSettings?: () => void;
    /**
     * Feature 013 / Story 2 / FR-006, FR-007: the agent currently bound
     * to the active chat. Resolved by the parent from `chat.agent_id`
     * plus the agents list.
     *
     * - `null` ⇒ the chat is not bound to any agent (legacy chat or
     *   multi-agent free-mode); the header renders a neutral state.
     * - `{ id, name, available: true }` ⇒ the agent is reachable; the
     *   header shows its name and assistant bubbles attribute replies
     *   to it.
     * - `{ id, name, available: false }` ⇒ the agent has been deleted,
     *   deprecated, or had a critical permission revoked; FR-009
     *   requires the unavailable banner + send-block.
     */
    activeAgent?: { id: string; name: string; available: boolean } | null;
    /** Feature 013 / FR-009: invoked when the user clicks "Start a new chat" in the unavailable banner. */
    onStartNewChat?: () => void;
    /**
     * Feature 013 / Story 4 / FR-016, FR-017: tools the active agent is
     * permitted to use right now. If omitted, the picker derives its
     * tool list from `agents` instead (preferred — the picker shows
     * tools for every enabled agent, not just one bound agent).
     */
    permittedTools?: ToolPickerToolEntry[];
    /**
     * Feature 013 follow-up: the full agents list. When provided, the
     * tool picker shows agent on/off toggles and a tool list across
     * all enabled agents — same UX as the agent manager modal but
     * inside the chat composer. Drafts are filtered out by the picker.
     */
    agents?: Agent[];
    /**
     * Feature 013 / FR-024: the user's saved tool selection. `null` ≡
     * no narrowing. Optional — when omitted, the picker manages its
     * own selection in local state for this chat session only.
     */
    selectedTools?: string[] | null;
    /** Fired when the user toggles a tool checkbox in the picker (FR-018). */
    onToolSelectionChange?: (next: string[] | null) => void;
    /** Fired when the user clicks "Reset to default" in the picker (FR-025). */
    onToolSelectionReset?: () => void;
}

interface ToolPickerToolEntry {
    name: string;
    description?: string;
    agentId?: string;
    agentName?: string;
}

export default function FloatingChatPanel({
    messages,
    chatStatus,
    chatSteps,
    onSendMessage,
    onCancelTask,
    isConnected,
    activeChatId,
    accessToken,
    deviceCapabilities = { hasMicrophone: false, hasGeolocation: false, speechServerAvailable: false },
    toolsAvailableForUser = true,
    onOpenAgentSettings,
    activeAgent = null,
    onStartNewChat,
    permittedTools,
    agents,
    selectedTools: selectedToolsProp,
    onToolSelectionChange,
    onToolSelectionReset,
}: FloatingChatPanelProps) {
    // Feature 013 / FR-009: when the chat is bound to an agent that is no
    // longer reachable, send is disabled and a banner explains what to do.
    // `null` activeAgent means the chat is unbound (legacy / fresh) — that
    // is NOT the same as unavailable; the user can still send.
    const isAgentUnavailable = activeAgent !== null && activeAgent.available === false;
    // Feature 013 / Story 4: ToolPicker open state lives here so the
    // popover anchors correctly to the trigger button below.
    const [toolPickerOpen, setToolPickerOpen] = useState(false);

    // Feature 013 follow-up: per-user agent on/off state for the picker.
    // Hydrate from /api/agents on mount so the toggles persist across
    // reload. Same canonical state as the agent manager modal.
    const [agentDisabled, setAgentDisabled] = useState<Record<string, boolean>>({});
    const [agentDisabledHydrated, setAgentDisabledHydrated] = useState(false);
    useEffect(() => {
        if (!accessToken) return;
        let cancelled = false;
        (async () => {
            try {
                const resp = await fetch(`${API_URL}/api/agents`, {
                    headers: { Authorization: `Bearer ${accessToken}` },
                });
                if (!resp.ok) return;
                const data = await resp.json();
                if (cancelled) return;
                const next: Record<string, boolean> = {};
                for (const a of (data.agents || []) as Array<{ id: string; disabled?: boolean }>) {
                    if (a.disabled) next[a.id] = true;
                }
                setAgentDisabled(next);
                setAgentDisabledHydrated(true);
            } catch {
                /* non-fatal — picker still works against optimistic local state */
            }
        })();
        return () => { cancelled = true; };
    }, [accessToken]);

    const handleAgentToggle = useCallback(async (agentId: string, enabled: boolean) => {
        if (!accessToken) return;
        const before = agentDisabled[agentId];
        // Optimistic update.
        setAgentDisabled(prev => ({ ...prev, [agentId]: !enabled }));
        try {
            await setUserAgentEnabled(accessToken, agentId, enabled);
        } catch (err) {
            // Roll back on failure.
            setAgentDisabled(prev => {
                const next = { ...prev };
                if (typeof before === "boolean") next[agentId] = before;
                else delete next[agentId];
                return next;
            });
            console.error("Failed to toggle agent enabled state:", err);
        }
    }, [accessToken, agentDisabled]);

    // Build the agents list shown in the picker. Drafts are excluded —
    // they have their own test surface and don't get a per-user toggle.
    const pickerAgents = useMemo(() => {
        if (!agents || agents.length === 0) return [];
        return agents
            .filter(a => !a.id.startsWith("draft:"))
            .map(a => ({
                id: a.id,
                name: a.name,
                disabled: Boolean(agentDisabled[a.id]),
            }));
    }, [agents, agentDisabled]);

    // Build the tools list shown in the picker. When the parent passed
    // `permittedTools` directly, use it. Otherwise derive from `agents`
    // — taking only tools whose agent is enabled AND whose
    // `permissions[tool] !== false` (i.e., scope/per-tool permissions
    // allow it).
    const pickerTools = useMemo<ToolPickerToolEntry[]>(() => {
        if (Array.isArray(permittedTools)) return permittedTools;
        if (!agents) return [];
        const out: ToolPickerToolEntry[] = [];
        for (const agent of agents) {
            if (agent.id.startsWith("draft:")) continue;
            if (agentDisabled[agent.id]) continue;
            const perms = agent.permissions || {};
            const descs = agent.tool_descriptions || {};
            for (const toolName of agent.tools) {
                if (perms[toolName] === false) continue;
                out.push({
                    name: toolName,
                    description: descs[toolName],
                    agentId: agent.id,
                    agentName: agent.name,
                });
            }
        }
        return out;
    }, [permittedTools, agents, agentDisabled]);

    // Local fallback selection state when the parent doesn't manage it.
    // FR-024 persistence is the parent's responsibility; the chat
    // session-scoped state here keeps the picker functional regardless.
    const [localSelectedTools, setLocalSelectedTools] = useState<string[] | null>(null);
    const selectedTools = selectedToolsProp !== undefined ? selectedToolsProp : localSelectedTools;
    const handleSelectionChange = useCallback((next: string[] | null) => {
        if (onToolSelectionChange) onToolSelectionChange(next);
        else setLocalSelectedTools(next);
    }, [onToolSelectionChange]);
    const handleSelectionReset = useCallback(() => {
        if (onToolSelectionReset) onToolSelectionReset();
        else setLocalSelectedTools(null);
    }, [onToolSelectionReset]);

    // Show the picker whenever there is at least one connected agent
    // (or the parent supplied a tool list directly). Even if every
    // agent is currently disabled, the user needs the popover to
    // re-enable one of them.
    const showToolPicker = !isAgentUnavailable && (
        pickerAgents.length > 0
        || pickerTools.length > 0
    );
    // FR-021: explicit empty selection (length 0, not null) ⇒ block send.
    const hasZeroSelection = selectedTools !== null && selectedTools !== undefined && selectedTools.length === 0;
    // FR-018 / picker badge: show a count when the user has narrowed.
    const isNarrowed = selectedTools !== null && selectedTools !== undefined
        && pickerTools.length > 0
        && selectedTools.length < pickerTools.length;
    // Reference to silence the unused-variable warning when hydration
    // state isn't read in render — the effect drives setAgentDisabled.
    void agentDisabledHydrated;
    const canUseVoiceInput = deviceCapabilities.hasMicrophone && deviceCapabilities.speechServerAvailable;
    const canUseVoiceOutput = deviceCapabilities.speechServerAvailable;
    const canUseGeolocation = deviceCapabilities.hasGeolocation;

    const [isOpen, setIsOpen] = useState(true);
    const [input, setInput] = useState(() => {
        try { return localStorage.getItem("astral-draft") || ""; } catch { return ""; }
    });
    const [isDragging, setIsDragging] = useState(false);
    const [previewFile, setPreviewFile] = useState<{ name: string; content: string } | null>(null);

    // Attachment state — feature 002-file-uploads. Replaces the legacy
    // single-file FileReader path so binary uploads (PDFs, images, Office
    // formats) are not corrupted by treating them as text.
    const attachments = useAttachments({ accessToken });
    const isProcessingFile = attachments.pending.some((p) => p.status === "uploading");
    const readyAttachments = attachments.pending.filter((p) => p.status === "ready");

    const bottomRef = useRef<HTMLDivElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const inputRef = useRef<HTMLTextAreaElement>(null);
    const prevChatIdRef = useRef(activeChatId);

    // Feature 010-fix-page-flash. Capture the message count at FIRST
    // RENDER so we can skip the entry animation for messages that are
    // already present (e.g., restored from a historical chat).
    // `useState` with a lazy initializer runs ONCE on the first render
    // — messages at indices below `initialMsgCount` skip their entry
    // animation, indices at or above it animate in normally. `mounted`
    // is flipped after first commit so the panel container's own
    // first-paint can also be silent.
    const [initialMsgCount] = useState<number>(() => messages.length);
    const [mounted, setMounted] = useState(false);
    useEffect(() => {
        // Standard "did mount" flag — first paint renders the panel
        // with `initial={false}`, later state changes (collapse/expand
        // toggles) animate normally. Framer-motion only honors
        // `initial` on first element mount.
        setMounted(true);
    }, []);

    // Voice Input (STT)
    const [isRecording, setIsRecording] = useState(false);
    const [isTranscribing, setIsTranscribing] = useState(false);
    const [streamingTranscript, setStreamingTranscript] = useState("");
    const mediaRecorderRef = useRef<MediaRecorder | null>(null);
    const voiceWsRef = useRef<WebSocket | null>(null);
    const mediaStreamRef = useRef<MediaStream | null>(null);
    const audioContextRef = useRef<AudioContext | null>(null);
    const audioChunksRef = useRef<Blob[]>([]);

    // Voice Output (TTS)
    const [ttsEnabled, setTtsEnabled] = useState(false);
    const [isSpeaking, setIsSpeaking] = useState(false);
    const audioRef = useRef<HTMLAudioElement | null>(null);
    const lastSpokenMsgIdx = useRef<number>(-1);

    // Geolocation
    const [userLocation, setUserLocation] = useState<{ latitude: number; longitude: number } | null>(null);

    useEffect(() => {
        if (!canUseGeolocation || userLocation) return;
        navigator.geolocation.getCurrentPosition(
            (pos) => setUserLocation({
                latitude: parseFloat(pos.coords.latitude.toFixed(4)),
                longitude: parseFloat(pos.coords.longitude.toFixed(4)),
            }),
            (err) => console.debug("Geolocation unavailable:", err.message),
            { timeout: 8000, maximumAge: 300_000 }
        );
    }, [canUseGeolocation, userLocation]);

    const enrichWithLocation = useCallback((text: string): string => {
        if (!userLocation) return text;
        return `${text}\n\n[User location: ${userLocation.latitude}, ${userLocation.longitude}]`;
    }, [userLocation]);

    // Auto-focus input when panel opens
    useEffect(() => {
        if (isOpen) {
            setTimeout(() => inputRef.current?.focus(), 100);
        }
    }, [isOpen]);

    // Auto-focus input on new chat or chat switch
    useEffect(() => {
        if (activeChatId && activeChatId !== prevChatIdRef.current) {
            setTimeout(() => inputRef.current?.focus(), 100);
        }
        prevChatIdRef.current = activeChatId;
    }, [activeChatId]);

    // Auto-grow the chat textarea to fit its content; CSS max-h caps it.
    useLayoutEffect(() => {
        const el = inputRef.current;
        if (!el) return;
        el.style.height = "auto";
        el.style.height = `${el.scrollHeight}px`;
    }, [input, streamingTranscript, isRecording, isTranscribing]);

    // Filter messages to only show chat-targeted messages (text summaries) and user messages
    const chatMessages = messages.filter(msg => {
        if (msg.role === "user") return true;
        // Show assistant messages that are targeted to "chat" or have no target (legacy/loaded history)
        const target = msg._target;
        return target === "chat" || target === undefined;
    });

    // Feature 014 — group step entries by their originating user-message id
    // so each turn's "Calling 'tool-name'" lines render directly under that
    // turn instead of clustering at the bottom of the chat. Steps whose
    // turn_message_id has not yet been stamped onto a local user message
    // (the in-flight turn before user_message_acked arrives) render in a
    // tail group right before the loading indicator.
    type ChatStepLike = NonNullable<typeof chatSteps>[string];
    const allChatStepsList: ChatStepLike[] = chatSteps
        ? Object.values(chatSteps).sort((a, b) => a.started_at - b.started_at)
        : [];
    const stepsByTurnId: Record<number, ChatStepLike[]> = {};
    const unmatchedSteps: ChatStepLike[] = [];
    if (allChatStepsList.length > 0) {
        const stampedIds = new Set<number>();
        for (const m of chatMessages) {
            if (m.role === "user" && typeof m.id === "number") stampedIds.add(m.id);
        }
        for (const s of allChatStepsList) {
            const tid = s.turn_message_id;
            if (typeof tid === "number" && stampedIds.has(tid)) {
                if (!stepsByTurnId[tid]) stepsByTurnId[tid] = [];
                stepsByTurnId[tid].push(s);
            } else {
                unmatchedSteps.push(s);
            }
        }
    }

    // Unread count when panel is collapsed
    const [lastSeenCount, setLastSeenCount] = useState(0);
    const unreadCount = isOpen ? 0 : Math.max(0, chatMessages.length - lastSeenCount);

    useEffect(() => {
        if (isOpen) setLastSeenCount(chatMessages.length);
    }, [isOpen, chatMessages.length]);

    // Auto-scroll
    useEffect(() => {
        if (!isOpen) return;
        const frameId = requestAnimationFrame(() => {
            bottomRef.current?.scrollIntoView({ behavior: "smooth" });
        });
        return () => cancelAnimationFrame(frameId);
    }, [chatMessages, chatStatus, isOpen]);

    // Draft auto-save
    useEffect(() => {
        const timer = setTimeout(() => {
            try {
                if (input) localStorage.setItem("astral-draft", input);
                else localStorage.removeItem("astral-draft");
            } catch { /* ignore */ }
        }, 300);
        return () => clearTimeout(timer);
    }, [input]);

    const clearAttachment = () => {
        attachments.clear();
        if (fileInputRef.current) fileInputRef.current.value = '';
    };

    // Extract text content from assistant component arrays. Recurses
    // into card / list children and pulls through alert/heading/paragraph
    // payloads so greeting-style replies (which often arrive as a single
    // alert or paragraph component, not a top-level "text" entry) render
    // their words instead of the "Processing complete." fallback.
    const extractTextFromComponents = (content: unknown): string => {
        if (typeof content === "string") return content;
        if (!Array.isArray(content)) {
            // Some assistant payloads are a single component object.
            if (content && typeof content === "object") {
                return extractTextFromComponents([content as Record<string, unknown>]);
            }
            return "";
        }
        const TEXT_BEARING_TYPES = new Set([
            "text", "paragraph", "heading", "alert", "note", "markdown", "code",
        ]);
        const pieces: string[] = [];
        const walk = (node: unknown): void => {
            if (typeof node === "string") {
                if (node.trim()) pieces.push(node);
                return;
            }
            if (Array.isArray(node)) {
                for (const child of node) walk(child);
                return;
            }
            if (!node || typeof node !== "object") return;
            const obj = node as Record<string, unknown>;
            const type = typeof obj.type === "string" ? obj.type : undefined;
            // Pull explicit text-bearing fields when the type matches.
            if (type && TEXT_BEARING_TYPES.has(type)) {
                if (typeof obj.content === "string" && obj.content.trim()) {
                    pieces.push(obj.content);
                } else if (typeof obj.message === "string" && obj.message.trim()) {
                    pieces.push(obj.message);
                } else if (typeof obj.text === "string" && obj.text.trim()) {
                    pieces.push(obj.text);
                } else if (typeof obj.title === "string" && obj.title.trim()) {
                    pieces.push(obj.title);
                }
            }
            // Recurse into common container payloads regardless of type.
            if (Array.isArray(obj.content)) walk(obj.content);
            if (Array.isArray(obj.children)) walk(obj.children);
            if (Array.isArray(obj.items)) walk(obj.items);
        };
        walk(content);
        const out = pieces.join("\n\n").trim();
        return out || "(No text content in this response.)";
    };

    // Voice helpers (simplified from ChatInterface)
    const float32ToPcm16 = useCallback((float32: Float32Array): ArrayBuffer => {
        const buf = new ArrayBuffer(float32.length * 2);
        const view = new DataView(buf);
        for (let i = 0; i < float32.length; i++) {
            const s = Math.max(-1, Math.min(1, float32[i]));
            view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
        }
        return buf;
    }, []);

    const sendAudioForTranscription = useCallback(async (audioBlob: Blob) => {
        setIsTranscribing(true);
        try {
            const formData = new FormData();
            formData.append("file", audioBlob, "recording.webm");
            const headers: HeadersInit = {};
            if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;
            const res = await fetch(`${BFF_URL}/api/voice/transcribe`, {
                method: "POST", headers, body: formData,
            });
            if (!res.ok) throw new Error("Transcription failed");
            const data = await res.json();
            const text = data.text?.trim();
            if (text) onSendMessage(enrichWithLocation(text), text);
            else toast.error("No speech detected");
        } catch (err) {
            console.error("Transcription error:", err);
            toast.error("Failed to transcribe audio");
        } finally {
            setIsTranscribing(false);
        }
    }, [accessToken, onSendMessage, enrichWithLocation]);

    const startRecording = useCallback(async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({
                audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
            });
            mediaStreamRef.current = stream;

            const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
                ? "audio/webm;codecs=opus"
                : MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "audio/mp4";
            const mediaRecorder = new MediaRecorder(stream, { mimeType });
            mediaRecorderRef.current = mediaRecorder;
            audioChunksRef.current = [];
            mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) audioChunksRef.current.push(e.data); };
            mediaRecorder.start(250);

            const audioCtx = new AudioContext();
            audioContextRef.current = audioCtx;
            const nativeSR = audioCtx.sampleRate;
            const targetSR = 24000;
            const source = audioCtx.createMediaStreamSource(stream);
            const processor = audioCtx.createScriptProcessor(4096, 1, 1);
            let streamingActive = false;
            let gotTranscription = false;

            const wsScheme = window.location.protocol === "https:" ? "wss" : "ws";
            const voiceWsUrl = `${wsScheme}://${window.location.host}/api/voice/stream`;
            const voiceWs = new WebSocket(voiceWsUrl);
            voiceWsRef.current = voiceWs;

            voiceWs.onopen = () => { streamingActive = true; };

            processor.onaudioprocess = (e) => {
                if (streamingActive && voiceWs.readyState === WebSocket.OPEN) {
                    let samples = e.inputBuffer.getChannelData(0);
                    if (nativeSR !== targetSR) {
                        const ratio = nativeSR / targetSR;
                        const newLen = Math.floor(samples.length / ratio);
                        const resampled = new Float32Array(newLen);
                        for (let i = 0; i < newLen; i++) resampled[i] = samples[Math.floor(i * ratio)];
                        samples = resampled;
                    }
                    voiceWs.send(float32ToPcm16(samples));
                }
            };
            source.connect(processor);
            processor.connect(audioCtx.destination);

            voiceWs.onmessage = (event) => {
                try {
                    const msg = JSON.parse(event.data);
                    if (msg.type === "transcription.delta") {
                        setStreamingTranscript((prev) => prev + msg.text);
                    } else if (msg.type === "transcription.done") {
                        gotTranscription = true;
                        const finalText = msg.text?.trim();
                        setStreamingTranscript("");
                        setIsRecording(false);
                        setIsTranscribing(false);
                        processor.disconnect(); source.disconnect(); audioCtx.close();
                        audioContextRef.current = null;
                        stream.getTracks().forEach((t) => t.stop());
                        mediaStreamRef.current = null;
                        if (mediaRecorderRef.current?.state === "recording") mediaRecorderRef.current.stop();
                        voiceWs.close(); voiceWsRef.current = null;
                        if (finalText) onSendMessage(enrichWithLocation(finalText), finalText);
                        else toast.error("No speech detected");
                    } else if (msg.type === "error") {
                        streamingActive = false; voiceWs.close();
                    }
                } catch { /* ignore */ }
            };

            voiceWs.onerror = () => { streamingActive = false; };
            voiceWs.onclose = () => {
                voiceWsRef.current = null;
                try { processor.disconnect(); } catch { /* */ }
                try { source.disconnect(); } catch { /* */ }
                try { audioCtx.close(); } catch { /* */ }
                audioContextRef.current = null;
                if (!gotTranscription) {
                    if (mediaRecorderRef.current?.state === "recording") mediaRecorderRef.current.stop();
                    stream.getTracks().forEach((t) => t.stop());
                    mediaStreamRef.current = null;
                    setIsRecording(false);
                    if (audioChunksRef.current.length > 0) {
                        const audioBlob = new Blob(audioChunksRef.current, { type: mimeType });
                        sendAudioForTranscription(audioBlob);
                    } else { setIsTranscribing(false); setStreamingTranscript(""); }
                }
            };

            setIsRecording(true);
            setStreamingTranscript("");
        } catch (err) {
            const msg = err instanceof DOMException && err.name === "NotAllowedError"
                ? "Microphone access denied"
                : `Microphone error: ${err instanceof Error ? err.message : String(err)}`;
            toast.error(msg);
        }
    }, [onSendMessage, enrichWithLocation, sendAudioForTranscription, float32ToPcm16]);

    const stopRecording = useCallback(() => {
        if (voiceWsRef.current?.readyState === WebSocket.OPEN) {
            voiceWsRef.current.send(JSON.stringify({ type: "stop" }));
            setIsTranscribing(true);
        } else {
            if (mediaRecorderRef.current?.state === "recording") mediaRecorderRef.current.stop();
            if (mediaStreamRef.current) { mediaStreamRef.current.getTracks().forEach((t) => t.stop()); mediaStreamRef.current = null; }
            if (audioContextRef.current) { audioContextRef.current.close(); audioContextRef.current = null; }
            setIsRecording(false);
            if (audioChunksRef.current.length > 0) {
                const mimeType = mediaRecorderRef.current?.mimeType || "audio/webm";
                sendAudioForTranscription(new Blob(audioChunksRef.current, { type: mimeType }));
            }
        }
    }, [sendAudioForTranscription]);

    // TTS
    const speakAnalysis = useCallback(async (text: string) => {
        setIsSpeaking(true);
        try {
            const headers: HeadersInit = { "Content-Type": "application/json" };
            if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;
            const res = await fetch(`${BFF_URL}/api/voice/speak`, {
                method: "POST", headers, body: JSON.stringify({ text }),
            });
            if (!res.ok) throw new Error("TTS failed");
            const audioBlob = await res.blob();
            const audioUrl = URL.createObjectURL(audioBlob);
            const audio = new Audio(audioUrl);
            audioRef.current = audio;
            audio.onended = () => { setIsSpeaking(false); URL.revokeObjectURL(audioUrl); audioRef.current = null; };
            audio.play();
        } catch { setIsSpeaking(false); }
    }, [accessToken]);

    useEffect(() => {
        if (!ttsEnabled || chatMessages.length === 0) return;
        if (lastSpokenMsgIdx.current >= chatMessages.length - 1) return;
        const lastMsg = chatMessages[chatMessages.length - 1];
        if (lastMsg.role !== "assistant") return;
        const plainText = extractTextFromComponents(lastMsg.content);
        if (!plainText) return;
        lastSpokenMsgIdx.current = chatMessages.length - 1;
        speakAnalysis(plainText);
    }, [ttsEnabled, chatMessages, speakAnalysis]);

    // Stage one or more files via the shared attachments hook (multi-file
    // safe, validates extension + 30 MB cap, uploads via /api/upload).
    const stageFiles = useCallback(async (files: FileList | File[]) => {
        if (!isConnected) return;
        await attachments.upload(files);
    }, [isConnected, attachments]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        const hasText = input.trim().length > 0;
        const hasReadyAttachments = readyAttachments.length > 0;
        if ((!hasText && !hasReadyAttachments) || !isConnected) return;
        if (isProcessingFile) {
            toast.message("Waiting for uploads to finish…");
            return;
        }

        const targetChatId = activeChatId || crypto.randomUUID();
        const refs = formatAttachmentRefs(attachments.pending);
        const filenames = readyAttachments.map((p) => p.attachment?.filename).filter(Boolean).join(", ");
        const promptPrefix = hasText ? `${input.trim()}\n\n` : "";
        const fullMsg = hasReadyAttachments
            ? `${promptPrefix}${refs}\n\nThe user has attached the file(s) above. Use the appropriate file-reading tool (read_document / read_spreadsheet / read_presentation / read_text / read_image) with the given attachment_id(s) to read the contents before answering.`
            : input.trim();
        const displayMsg = hasReadyAttachments
            ? `${promptPrefix}[Attached: ${filenames}]`
            : input.trim();

        onSendMessage(enrichWithLocation(fullMsg), displayMsg, targetChatId);

        setInput("");
        try { localStorage.removeItem("astral-draft"); } catch { /* ignore */ }
        clearAttachment();
    };

    const extractFileContentFromMsg = (content: string) => {
        const match = /```[\w]*\s*([\s\S]*?)```/g.exec(content);
        return match ? match[1].trim() : "Preview not available.";
    };

    const renderUserMessage = (content: string) => {
        const cleanContent = content
            .replace(/I have uploaded .* to the backend at: `.*`/g, "")
            .replace(/Here is a preview \(first 50 lines\):/g, "")
            .replace(/Please use the `analyze_csv_file` tool .*/g, "")
            .replace(/Here is my data from .*\. Please run various data analyses .*/g, "")
            .replace(/I've attached a file named .*\. Here are the contents:/g, "")
            .replace(/```[\w]*\s*([\s\S]*?)```/g, "")
            .trim();

        const fileRegex = /\[Attached File: (.*?)\]/g;
        const parts: React.ReactNode[] = [];
        let lastIndex = 0;
        let match;

        while ((match = fileRegex.exec(cleanContent)) !== null) {
            if (match.index > lastIndex) {
                const textBefore = cleanContent.substring(lastIndex, match.index).trim();
                if (textBefore) parts.push(<p key={`t-${lastIndex}`} className="text-xs text-white whitespace-pre-wrap">{textBefore}</p>);
            }
            const fileName = match[1];
            parts.push(
                <button key={`f-${match.index}`} type="button"
                    onClick={() => setPreviewFile({ name: fileName, content: extractFileContentFromMsg(content) })}
                    className="flex items-center gap-1.5 px-2 py-1 bg-white/10 border border-white/10 rounded-lg text-left hover:bg-white/15 transition-all text-xs"
                >
                    <FileText size={12} className="text-astral-primary" />
                    <span className="text-white truncate max-w-[140px]">{fileName}</span>
                </button>
            );
            lastIndex = match.index + match[0].length;
        }

        if (lastIndex < cleanContent.length) {
            const remaining = cleanContent.substring(lastIndex).trim();
            if (remaining) parts.push(<p key={`t-${lastIndex}`} className="text-xs text-white whitespace-pre-wrap">{remaining}</p>);
        }

        return parts.length > 0 ? parts : <p className="text-xs text-white">{cleanContent || content.split('[Attached File:')[0].trim()}</p>;
    };

    // File drag-and-drop
    const handleFileDragOver = useCallback((e: React.DragEvent) => {
        if (!e.dataTransfer.types.includes("Files")) return;
        e.preventDefault(); e.stopPropagation();
        if (!isDragging) setIsDragging(true);
    }, [isDragging]);

    const handleFileDragLeave = useCallback((e: React.DragEvent) => {
        if (!e.dataTransfer.types.includes("Files")) return;
        e.preventDefault(); e.stopPropagation();
        if (e.currentTarget === e.target) setIsDragging(false);
    }, []);

    const handleFileDrop = useCallback((e: React.DragEvent) => {
        if (!e.dataTransfer.types.includes("Files")) return;
        e.preventDefault(); e.stopPropagation();
        setIsDragging(false);
        if (e.dataTransfer.files?.length) void stageFiles(e.dataTransfer.files);
    }, [stageFiles]);

    // Collapsed state — just a floating button
    if (!isOpen) {
        return (
            <motion.button
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                onClick={() => setIsOpen(true)}
                className="fixed bottom-4 right-4 z-40 w-14 h-14 rounded-full bg-gradient-to-br from-astral-primary to-astral-secondary shadow-2xl flex items-center justify-center hover:scale-105 transition-transform"
            >
                <MessageSquare size={22} className="text-white" />
                {unreadCount > 0 && (
                    <span className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center">
                        {unreadCount > 9 ? "9+" : unreadCount}
                    </span>
                )}
            </motion.button>
        );
    }

    return (
        <>
            {/* File Preview Modal */}
            <AnimatePresence>
                {previewFile && (
                    <motion.div
                        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                        className="fixed inset-0 z-[60] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4"
                        onClick={() => setPreviewFile(null)}
                    >
                        <motion.div
                            initial={{ scale: 0.9 }} animate={{ scale: 1 }} exit={{ scale: 0.9 }}
                            className="bg-astral-bg border border-white/10 rounded-xl max-w-lg w-full max-h-[60vh] overflow-auto p-4"
                            onClick={(e) => e.stopPropagation()}
                        >
                            <div className="flex justify-between items-center mb-3">
                                <h3 className="text-sm font-medium text-white">{previewFile.name}</h3>
                                <button onClick={() => setPreviewFile(null)} className="p-1 hover:bg-white/10 rounded"><X size={14} className="text-astral-muted" /></button>
                            </div>
                            <pre className="text-xs text-astral-muted whitespace-pre-wrap font-mono">{previewFile.content}</pre>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Floating Panel */}
            <motion.div
                initial={mounted ? { opacity: 0, y: 20, scale: 0.95 } : false}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: 20, scale: 0.95 }}
                className="fixed bottom-4 right-4 z-40 w-[380px] sm:w-[420px] max-h-[70vh] max-sm:left-4 max-sm:w-auto
                           bg-astral-bg/95 backdrop-blur-xl border border-white/10 rounded-2xl shadow-2xl
                           flex flex-col overflow-hidden"
                onDragOver={handleFileDragOver}
                onDragLeave={handleFileDragLeave}
                onDrop={handleFileDrop}
            >
                {/* File drag overlay */}
                <AnimatePresence>
                    {isDragging && (
                        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                            className="absolute inset-0 z-50 bg-astral-bg/80 backdrop-blur-sm border-2 border-dashed border-astral-primary/50 rounded-2xl flex flex-col items-center justify-center"
                        >
                            <UploadCloud size={32} className="text-astral-primary mb-2" />
                            <p className="text-sm text-astral-muted">Drop file here</p>
                        </motion.div>
                    )}
                </AnimatePresence>

                {/* Header — shows active agent so the user always knows
                    who's running this chat (Feature 013 / FR-006). */}
                <div
                    className="flex items-center justify-between px-4 py-3 border-b border-white/10 flex-shrink-0"
                    data-testid="chat-header"
                >
                    <div className="flex items-center gap-2 min-w-0">
                        <div className={`w-6 h-6 rounded-lg flex items-center justify-center flex-shrink-0 ${
                            isAgentUnavailable
                                ? "bg-white/5 border border-amber-400/30"
                                : "bg-gradient-to-br from-astral-primary to-astral-secondary"
                        }`}>
                            {activeAgent
                                ? <Bot size={12} className={isAgentUnavailable ? "text-amber-300" : "text-white"} />
                                : <MessageSquare size={12} className="text-white" />}
                        </div>
                        <div className="flex flex-col min-w-0">
                            {activeAgent ? (
                                <span
                                    className={`text-sm font-medium truncate ${
                                        isAgentUnavailable ? "text-amber-300" : "text-white"
                                    }`}
                                    data-testid="active-agent-name"
                                    title={activeAgent.name}
                                >
                                    {activeAgent.name}
                                </span>
                            ) : (
                                <span className="text-sm font-medium text-white">Chat</span>
                            )}
                            {isAgentUnavailable && (
                                <span className="text-[10px] text-amber-300/80" data-testid="active-agent-unavailable-tag">
                                    Unavailable
                                </span>
                            )}
                        </div>
                        {chatStatus.status !== "idle" && chatStatus.status !== "done" && !isAgentUnavailable && (
                            <span className="text-[10px] text-astral-primary animate-pulse ml-1 flex-shrink-0">
                                {chatStatus.status === "thinking" ? "Thinking..." : "Executing..."}
                            </span>
                        )}
                    </div>
                    <button
                        onClick={() => setIsOpen(false)}
                        className="p-1 rounded-lg hover:bg-white/10 text-astral-muted hover:text-white transition-colors flex-shrink-0"
                        title="Minimize chat"
                    >
                        <Minus size={16} />
                    </button>
                </div>

                {/* Messages */}
                <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3 min-h-0">
                    <TextOnlyBanner
                        toolsAvailableForUser={toolsAvailableForUser}
                        onOpenAgentSettings={onOpenAgentSettings ?? (() => { /* noop */ })}
                    />
                    {/* Feature 013 / FR-009: agent-unavailable banner.
                        Visible only when the chat is bound to an agent that
                        is no longer reachable. Send is also blocked below. */}
                    {isAgentUnavailable && activeAgent && (
                        <div
                            data-testid="agent-unavailable-banner"
                            className="rounded-lg border border-amber-400/40 bg-amber-400/10 px-3 py-2 text-[11px] text-amber-200"
                        >
                            <p className="font-medium">
                                "{activeAgent.name}" is no longer available.
                            </p>
                            <p className="mt-0.5 text-amber-200/80">
                                The chat history is preserved. Pick another agent or start a new chat to continue.
                            </p>
                            <div className="mt-2 flex flex-wrap gap-1.5">
                                {onStartNewChat && (
                                    <button
                                        type="button"
                                        onClick={onStartNewChat}
                                        data-testid="agent-unavailable-new-chat"
                                        className="px-2 py-1 text-[11px] font-medium rounded-md bg-amber-400/15 text-amber-200 hover:bg-amber-400/25 transition-colors"
                                    >
                                        Start a new chat
                                    </button>
                                )}
                                {onOpenAgentSettings && (
                                    <button
                                        type="button"
                                        onClick={onOpenAgentSettings}
                                        data-testid="agent-unavailable-pick-agent"
                                        className="px-2 py-1 text-[11px] font-medium rounded-md bg-white/5 text-white/80 hover:bg-white/10 transition-colors"
                                    >
                                        Pick another agent
                                    </button>
                                )}
                            </div>
                        </div>
                    )}
                    {chatMessages.length === 0 && (
                        <div className="flex flex-col items-center justify-center h-full text-center py-8">
                            <Bot size={24} className="text-astral-muted/30 mb-2" />
                            <p className="text-xs text-astral-muted">Send a message to get started</p>
                        </div>
                    )}

                    {chatMessages.map((msg, i) => {
                        const turnSteps = msg.role === "user" && typeof msg.id === "number"
                            ? stepsByTurnId[msg.id]
                            : undefined;
                        return (
                        <React.Fragment key={i}>
                        <motion.div
                            initial={i < initialMsgCount ? false : { opacity: 0, y: 6 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ duration: 0.15 }}
                            className={`flex gap-2 ${msg.role === "user" ? "justify-end" : ""}`}
                        >
                            {msg.role === "assistant" && (
                                <div className="w-6 h-6 rounded-md bg-gradient-to-br from-astral-primary to-astral-secondary flex items-center justify-center flex-shrink-0 mt-0.5">
                                    <Bot size={12} className="text-white" />
                                </div>
                            )}
                            <div className={msg.role === "user"
                                ? "max-w-[80%] bg-astral-primary/20 border border-astral-primary/30 rounded-xl rounded-tr-sm px-3 py-2"
                                : "flex-1 max-w-[calc(100%-2rem)] min-w-0 bg-white/5 border border-white/10 rounded-xl rounded-tl-sm px-3 py-2"
                            }>
                                {msg.role === "user" ? (
                                    <div className="space-y-1">
                                        {renderUserMessage(msg.content as string)}
                                    </div>
                                ) : (
                                    <>
                                        {/* Feature 013 / FR-007: attribute every assistant
                                            reply in this chat to the bound agent so the
                                            user can see who produced the response. */}
                                        {activeAgent && (
                                            <div
                                                data-testid="assistant-agent-attribution"
                                                className="text-[10px] text-astral-muted/70 mb-1 truncate"
                                                title={activeAgent.name}
                                            >
                                                {activeAgent.name}
                                            </div>
                                        )}
                                        <div className="text-xs text-astral-text prose prose-invert prose-xs max-w-none [&_p]:text-xs [&_li]:text-xs [&_h1]:text-sm [&_h2]:text-xs [&_h3]:text-xs">
                                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                                {normalizeLlmMarkdown(extractTextFromComponents(msg.content))}
                                            </ReactMarkdown>
                                        </div>
                                    </>
                                )}
                            </div>
                            {msg.role === "user" && (
                                <div className="w-6 h-6 rounded-md bg-white/10 flex items-center justify-center flex-shrink-0 mt-0.5">
                                    <User size={12} className="text-astral-muted" />
                                </div>
                            )}
                        </motion.div>
                        {turnSteps && turnSteps.length > 0 && (
                            <div
                                data-testid="chat-step-trail-turn"
                                data-turn-message-id={msg.id}
                                className="ml-8 space-y-1"
                            >
                                {turnSteps.map((step) => (
                                    <ChatStepEntry key={step.id} step={step} />
                                ))}
                            </div>
                        )}
                        </React.Fragment>
                    );
                    })}

                    {/* Feature 014 — persistent step trail (tail group).
                        Steps from earlier turns render inline next to their
                        originating user message above; this tail only
                        renders steps for the in-flight turn before
                        user_message_acked stamps the local message id. */}
                    {unmatchedSteps.length > 0 && (
                        <div data-testid="chat-step-trail" className="ml-8 space-y-1">
                            {unmatchedSteps.map((step) => (
                                <ChatStepEntry key={step.id} step={step} />
                            ))}
                        </div>
                    )}

                    {/* Loading state */}
                    <AnimatePresence>
                        {chatStatus.status !== "idle" && chatStatus.status !== "done" && (
                            <motion.div
                                initial={{ opacity: 0, y: 6 }}
                                animate={{ opacity: 1, y: 0 }}
                                exit={{ opacity: 0 }}
                                className="flex gap-2"
                            >
                                <div className="w-6 h-6 rounded-md bg-gradient-to-br from-astral-primary to-astral-secondary flex items-center justify-center flex-shrink-0 pulse-glow">
                                    <Bot size={12} className="text-white" />
                                </div>
                                <div className="glass-card px-3 py-2 flex items-center gap-2">
                                    <Loader2 size={12} className="text-astral-primary animate-spin" />
                                    <CosmicProgressIndicator chatStatus={chatStatus} />
                                    <button
                                        onClick={onCancelTask}
                                        className="p-1 rounded-md bg-white/5 hover:bg-red-500/20 text-astral-muted hover:text-red-400 transition-colors"
                                        title="Stop"
                                    >
                                        <Square size={10} />
                                    </button>
                                </div>
                            </motion.div>
                        )}
                    </AnimatePresence>

                    <div ref={bottomRef} />
                </div>

                {/* Input Area */}
                <div className="px-3 py-2 border-t border-white/10 flex-shrink-0">
                    <form onSubmit={handleSubmit} className="flex flex-col gap-1.5">
                        {/* Recording Indicator */}
                        <AnimatePresence>
                            {isRecording && (
                                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                                    className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-red-500/15 border border-red-500/30 text-red-400 text-[10px] font-medium self-start"
                                >
                                    <span className="w-1.5 h-1.5 rounded-full bg-red-400 animate-pulse" />
                                    Recording...
                                </motion.div>
                            )}
                        </AnimatePresence>

                        {/* Staged attachment chips — feature 002-file-uploads */}
                        {attachments.pending.length > 0 && (
                            <div className="flex flex-wrap gap-1 self-start">
                                {attachments.pending.map((p) => {
                                    const isError = p.status === "error";
                                    const isUploading = p.status === "uploading";
                                    return (
                                        <div
                                            key={p.localId}
                                            className={`flex items-center gap-1.5 px-2 py-1 rounded-md border text-[11px] font-medium ${
                                                isError
                                                    ? "bg-red-500/10 border-red-500/30 text-red-400"
                                                    : "bg-astral-primary/10 border-astral-primary/30 text-astral-primary"
                                            }`}
                                        >
                                            {isUploading
                                                ? <Loader2 size={12} className="animate-spin" />
                                                : <FileMinus size={12} className={isError ? "text-red-400" : "text-astral-primary"} />}
                                            <span className="truncate max-w-[120px]" title={p.filename}>{p.filename}</span>
                                            {isError && p.source && (
                                                <button type="button" onClick={(e) => { e.stopPropagation(); void attachments.retry(p.localId); }} className="p-0.5 rounded hover:bg-white/10" title="Retry"><RotateCcw size={10} /></button>
                                            )}
                                            <button type="button" onClick={(e) => { e.stopPropagation(); attachments.remove(p.localId); }} className="p-0.5 rounded hover:bg-white/10" title="Remove"><X size={10} /></button>
                                            {isError && p.error && <span className="ml-0.5 opacity-90">{p.error.message}</span>}
                                        </div>
                                    );
                                })}
                            </div>
                        )}

                        <div className="flex gap-1.5">
                            <div className="flex-1 relative flex items-center gap-1 bg-astral-surface/60 border border-white/10 rounded-xl px-1.5 transition-all focus-within:border-astral-primary/50 focus-within:ring-1 focus-within:ring-astral-primary/20">
                                <button type="button" onClick={() => fileInputRef.current?.click()}
                                    disabled={!isConnected || isProcessingFile}
                                    className="p-1.5 text-astral-muted hover:text-white rounded-md hover:bg-white/10 transition-colors disabled:opacity-50 flex-shrink-0"
                                    title="Attach File"
                                >
                                    {isProcessingFile ? <Loader2 size={16} className="animate-spin text-astral-primary" /> : <Paperclip size={16} />}
                                </button>
                                <input type="file" className="hidden" ref={fileInputRef}
                                    onChange={(e) => { const fs = e.target.files; if (fs && fs.length) void stageFiles(fs); if (fileInputRef.current) fileInputRef.current.value = ''; }}
                                    accept={ACCEPT_ATTRIBUTE}
                                    multiple />

                                <textarea
                                    ref={inputRef}
                                    rows={1}
                                    value={isRecording || isTranscribing ? streamingTranscript || "" : input}
                                    onChange={(e) => { if (!isRecording && !isTranscribing) setInput(e.target.value); }}
                                    onKeyDown={(e) => {
                                        // Skip while IME composition is active so Enter commits the candidate
                                        // instead of submitting the message.
                                        if (e.nativeEvent.isComposing || e.keyCode === 229) return;
                                        if (e.key === "Enter" && !e.shiftKey) {
                                            e.preventDefault();
                                            e.currentTarget.form?.requestSubmit();
                                        }
                                    }}
                                    placeholder={
                                        isAgentUnavailable
                                            ? "This agent is no longer available."
                                            : isRecording
                                            ? "Listening..."
                                            : isTranscribing
                                            ? "Transcribing..."
                                            : isConnected
                                            ? "Ask anything..."
                                            : "Connecting..."
                                    }
                                    disabled={
                                        !isConnected
                                        || isRecording
                                        || isTranscribing
                                        || (chatStatus.status !== "idle" && chatStatus.status !== "done")
                                        || isAgentUnavailable
                                    }
                                    data-tutorial-target="chat.input"
                                    className="w-full py-2 bg-transparent text-xs text-white placeholder:text-astral-muted/50 focus:outline-none disabled:opacity-50 resize-none overflow-y-auto max-h-[8rem] leading-5"
                                />

                                {canUseVoiceInput && (
                                    <button type="button" onClick={isRecording ? stopRecording : startRecording}
                                        disabled={!isConnected || isTranscribing || (chatStatus.status !== "idle" && chatStatus.status !== "done")}
                                        className={`p-1.5 rounded-md transition-colors flex-shrink-0 ${isRecording ? "text-red-400 bg-red-500/20" : "text-astral-muted hover:text-white hover:bg-white/10"} disabled:opacity-50`}
                                    >
                                        {isTranscribing ? <Loader2 size={14} className="animate-spin" /> : isRecording ? <Square size={12} /> : <Mic size={16} />}
                                    </button>
                                )}

                                {canUseVoiceOutput && (
                                    <button type="button"
                                        onClick={() => { setTtsEnabled(prev => !prev); if (ttsEnabled && audioRef.current) { audioRef.current.pause(); audioRef.current = null; setIsSpeaking(false); } }}
                                        className={`p-1.5 rounded-md transition-colors flex-shrink-0 ${ttsEnabled ? "text-astral-primary bg-astral-primary/20" : "text-astral-muted hover:text-white hover:bg-white/10"}`}
                                    >
                                        {isSpeaking ? <Volume2 size={14} className="animate-pulse" /> : ttsEnabled ? <Volume2 size={14} /> : <VolumeX size={14} />}
                                    </button>
                                )}

                                {/* Feature 013 / FR-016 (+ follow-up): in-chat
                                    Tools & Agents picker. Renders whenever there's
                                    at least one connected agent so users can flip
                                    agents on/off and narrow tools per query without
                                    leaving the chat. */}
                                {showToolPicker && (
                                    <div className="relative flex-shrink-0">
                                        <button
                                            type="button"
                                            onClick={() => setToolPickerOpen(prev => !prev)}
                                            disabled={!isConnected || isAgentUnavailable}
                                            data-testid="tool-picker-trigger"
                                            title={isNarrowed
                                                ? `Tool selection narrowed (${selectedTools?.length}/${pickerTools.length})`
                                                : "Pick which agents and tools to use for this chat"}
                                            className={`p-1.5 rounded-md transition-colors flex items-center gap-0.5 ${
                                                isNarrowed
                                                    ? "text-astral-primary bg-astral-primary/20"
                                                    : "text-astral-muted hover:text-white hover:bg-white/10"
                                            } disabled:opacity-50`}
                                        >
                                            <Wrench size={14} />
                                            {isNarrowed && selectedTools && (
                                                <span className="text-[9px] font-medium" data-testid="tool-picker-badge">
                                                    {selectedTools.length}
                                                </span>
                                            )}
                                        </button>
                                        <ToolPicker
                                            agents={pickerAgents}
                                            onAgentToggle={handleAgentToggle}
                                            permittedTools={pickerTools}
                                            selectedTools={selectedTools ?? null}
                                            onChange={handleSelectionChange}
                                            onReset={() => {
                                                // Reset = re-enable every disabled agent AND
                                                // clear the tool narrowing. The popover stays
                                                // open so the user can keep tweaking from the
                                                // freshly-default state.
                                                for (const agent of pickerAgents) {
                                                    if (agent.disabled) {
                                                        void handleAgentToggle(agent.id, true);
                                                    }
                                                }
                                                handleSelectionReset();
                                            }}
                                            open={toolPickerOpen}
                                            onClose={() => setToolPickerOpen(false)}
                                        />
                                    </div>
                                )}
                            </div>
                            <button type="submit"
                                disabled={
                                    (!input.trim() && readyAttachments.length === 0)
                                    || !isConnected
                                    || isProcessingFile
                                    || (chatStatus.status !== "idle" && chatStatus.status !== "done")
                                    || isAgentUnavailable
                                    || hasZeroSelection
                                }
                                title={
                                    isAgentUnavailable
                                        ? "This agent is no longer available — start a new chat or pick another agent."
                                        : hasZeroSelection
                                        ? "No tools selected — pick at least one or click Reset in the tool picker."
                                        : undefined
                                }
                                data-testid="chat-send-button"
                                className="px-3 py-2 rounded-xl bg-astral-primary hover:bg-astral-primary/80 disabled:opacity-30 disabled:cursor-not-allowed transition-colors flex items-center flex-shrink-0"
                            >
                                <Send size={14} className="text-white" />
                            </button>
                        </div>
                    </form>
                </div>
            </motion.div>
        </>
    );
}
