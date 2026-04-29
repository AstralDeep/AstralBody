/**
 * WebSocket hook for real-time communication with the orchestrator.
 */
import { useState, useEffect, useRef, useCallback } from "react";
import { toast } from "sonner";
import { API_URL } from "../config";
import { mergeStreamChunk } from "../utils/streamMerge";
import type {
    UIStreamDataMessage,
    StreamSubscribedMessage,
    StreamSubscriptionRecord,
} from "../types/streaming";

export interface SecurityFlag {
    tool_name: string;
    category: string;  // DATA_EGRESS | CODE_EXECUTION | CREDENTIAL_ACCESS | DESTRUCTIVE | PRIVILEGE_ESCALATION | NETWORK_MANIPULATION
    reason: string;
    blocked: boolean;
}

export interface RequiredCredential {
    key: string;
    label: string;
    required: boolean;
}

export interface AgentMetadata {
    required_credentials?: RequiredCredential[];
    [key: string]: unknown;
}

export interface Agent {
    id: string;
    name: string;
    description?: string;
    tools: string[];
    tool_descriptions?: Record<string, string>;
    scopes?: Record<string, boolean>;
    tool_scope_map?: Record<string, string>;
    permissions?: Record<string, boolean>;
    security_flags?: Record<string, SecurityFlag>;
    metadata?: AgentMetadata;
    status: string;
    owner_email?: string;
    is_public?: boolean;
}

export interface ChatSession {
    id: string;
    title: string;
    updated_at: number;
    preview: string;
    has_saved_components?: boolean;
}

export interface SavedComponent {
    id: string;
    chat_id: string;
    component_data: Record<string, unknown>;
    component_type: string;
    title: string;
    created_at: number;
}

export interface ChatStatus {
    status: "idle" | "thinking" | "executing" | "done";
    message: string;
}

export interface AgentPermissionsData {
    agent_id: string;
    agent_name: string;
    scopes: Record<string, boolean>;
    tool_scope_map: Record<string, string>;
    permissions: Record<string, boolean>;
    tool_overrides?: Record<string, boolean>;
    tool_descriptions: Record<string, string>;
    security_flags?: Record<string, SecurityFlag>;
}

export interface WSMessage {
    type: string;
    [key: string]: unknown;
}

export interface DeviceCapabilityFlags {
    hasMicrophone: boolean;
    hasGeolocation: boolean;
    speechServerAvailable: boolean;
}

// ---------------------------------------------------------------------------
// ROTE: Device capability detection
// ---------------------------------------------------------------------------

function detectDeviceType(): string {
    const ua = navigator.userAgent.toLowerCase();
    const vw = window.innerWidth;

    if (/watch|watchos/.test(ua)) return "watch";
    if (/smart-?tv|hbbtv|netcast|viera|nettv|roku|web0s/.test(ua)) return "tv";
    if (vw <= 200) return "watch";
    if (/ipad|tablet|playbook|silk/.test(ua) || (vw > 480 && vw <= 1024 && /android/.test(ua))) return "tablet";
    if (/android|iphone|ipod|blackberry|iemobile|opera mini/.test(ua) || vw <= 480) return "mobile";
    if (vw <= 1024) return "tablet";
    return "browser";
}

function detectDeviceCapabilities(): Record<string, unknown> {
    const nav = navigator as Navigator & {
        connection?: { effectiveType?: string };
        maxTouchPoints?: number;
    };
    return {
        device_type: detectDeviceType(),
        screen_width: window.screen.width,
        screen_height: window.screen.height,
        viewport_width: window.innerWidth,
        viewport_height: window.innerHeight,
        pixel_ratio: window.devicePixelRatio ?? 1,
        has_touch: (nav.maxTouchPoints ?? 0) > 0,
        has_geolocation: "geolocation" in navigator,
        has_microphone: !!navigator.mediaDevices,
        has_camera: !!navigator.mediaDevices,
        has_file_system: true,
        connection_type: nav.connection?.effectiveType ?? "unknown",
        user_agent: navigator.userAgent,
    };
}

// ---------------------------------------------------------------------------

/**
 * 001-tool-stream-ui: send a `stream_subscribe` message in the correct wire
 * format for the tool's `kind`. Push-streaming tools require `session_id` at
 * the message level and omit `interval_seconds`; poll tools use the legacy
 * interval-driven shape. Centralising this prevents the three auto-subscribe
 * call sites (ui_render, saved_components_list, chat_loaded) from drifting.
 */
export function sendStreamSubscribe(
    ws: WebSocket,
    toolName: string,
    cfg: { default_interval: number; kind?: string },
    params: Record<string, unknown>,
    chatId: string | null,
): void {
    if (cfg.kind === "push") {
        ws.send(JSON.stringify({
            type: "ui_event",
            action: "stream_subscribe",
            session_id: chatId,
            payload: { tool_name: toolName, params },
        }));
    } else {
        ws.send(JSON.stringify({
            type: "ui_event",
            action: "stream_subscribe",
            payload: { tool_name: toolName, interval_seconds: cfg.default_interval, params },
        }));
    }
}

export type ConnectionState = "disconnected" | "connecting" | "connected" | "reconnecting";

const MAX_RECONNECT_ATTEMPTS = 10;

export function useWebSocket(url: string = `ws://localhost:${import.meta.env.ORCHESTRATOR_PORT}`, token?: string) {
    const [isConnected, setIsConnected] = useState(false);
    const [connectionState, setConnectionState] = useState<ConnectionState>("disconnected");
    const reconnectAttemptsRef = useRef(0);
    const [agents, setAgents] = useState<Agent[]>([]);
    const [chatStatus, setChatStatus] = useState<ChatStatus>({ status: "idle", message: "" });
    const [uiComponents, setUiComponents] = useState<Record<string, unknown>[]>([]);
    const [messages, setMessages] = useState<{ role: string; content: unknown; _target?: string }[]>([]);
    const [chatHistory, setChatHistory] = useState<ChatSession[]>([]);
    const [activeChatIdState, setActiveChatIdState] = useState<string | null>(null);
    const activeChatIdRef = useRef<string | null>(null);
    const [userId, setUserId] = useState<string | null>(null);
    const tokenRef = useRef<string | undefined>(token);

    useEffect(() => {
        tokenRef.current = token;
    }, [token]);

    // Decode token to extract user_id
    useEffect(() => {
        if (!token) {
            setUserId(null);
            return;
        }
        const decodeToken = (token: string): string | null => {
            if (token === "dev-token") {
                return "dev-user-id";
            }
            try {
                const base64Url = token.split('.')[1];
                const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
                const jsonPayload = decodeURIComponent(atob(base64).split('').map(function (c) {
                    return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
                }).join(''));
                const payload = JSON.parse(jsonPayload);
                // console.log("Decoded JWT payload:", payload);
                return payload.sub || null;
            } catch (e) {
                console.error("Failed to decode JWT", e);
                return null;
            }
        };
        const id = decodeToken(token);
        setUserId(id);
    }, [token]);

    const setActiveChatId = useCallback((id: string | null, replace = false) => {
        const oldId = activeChatIdRef.current;
        activeChatIdRef.current = id;
        setActiveChatIdState(id);

        // 001-tool-stream-ui (US2 T046): when the active chat changes, drop
        // any push-stream client-side records for the OLD chat. The server
        // already moves them to dormant via load_chat → pause_chat (T042),
        // so we just clean up the local refs to keep activeSubscriptionsRef
        // honest.
        if (oldId && oldId !== id) {
            const stale: string[] = [];
            pushStreamsRef.current.forEach((rec, sid) => {
                if (rec.chat_id === oldId) stale.push(sid);
            });
            stale.forEach((sid) => {
                pushStreamsRef.current.delete(sid);
                streamSeqRef.current.delete(sid);
            });
        }

        // Sync chat ID to URL
        const params = new URLSearchParams(window.location.search);
        if (id) {
            params.set("chat", id);
        } else {
            params.delete("chat");
        }
        const newUrl = params.toString() ? `${window.location.pathname}?${params.toString()}` : window.location.pathname;
        if (replace) {
            window.history.replaceState({}, "", newUrl);
        } else {
            window.history.pushState({}, "", newUrl);
        }
    }, []);

    const activeChatId = activeChatIdState;
    const [savedComponents, setSavedComponents] = useState<SavedComponent[]>([]);
    const [canvasComponents, setCanvasComponents] = useState<SavedComponent[]>([]);
    const [isCombining, setIsCombining] = useState(false);
    const [combineError, setCombineError] = useState<string | null>(null);
    const condenseTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const [agentPermissions, setAgentPermissions] = useState<AgentPermissionsData | null>(null);
    // Live streaming state
    const [streamData, setStreamData] = useState<Record<string, {
        components: Record<string, unknown>[];
        data: Record<string, unknown>;
        timestamp: number;
    }>>({});
    const activeSubscriptionsRef = useRef<Map<string, { interval: number; params: Record<string, unknown> }>>(new Map());
    const chatSubscriptionsMapRef = useRef<Map<string, Map<string, { interval: number; params: Record<string, unknown> }>>>(new Map());
    const streamableToolsRef = useRef<Record<string, { agent_id: string; default_interval: number; kind?: string }>>({});

    // 001-tool-stream-ui: per-stream client-side state for the new push path.
    // - pushStreamsRef: stream_id → subscription record (so a manual retry
    //   button can re-issue stream_subscribe with the original args).
    // - streamSeqRef: stream_id → highest seq seen (so we drop out-of-order
    //   chunks per contracts/frontend-events.md §1).
    const pushStreamsRef = useRef<Map<string, StreamSubscriptionRecord>>(new Map());
    const streamSeqRef = useRef<Map<string, number>>(new Map());

    const [deviceCapabilities, setDeviceCapabilities] = useState<DeviceCapabilityFlags>({
        hasMicrophone: false,
        hasGeolocation: false,
        speechServerAvailable: false,
    });
    const wsRef = useRef<WebSocket | null>(null);
    const reconnectTimer = useRef<number | null>(null);
    const pendingSaveResolveRef = useRef<((value: boolean) => void) | null>(null);
    const pendingSaveRejectRef = useRef<((error: unknown) => void) | null>(null);

    const handleMessage = useCallback((data: WSMessage) => {
        switch (data.type) {
            case "system_config": {
                const config = data.config as Record<string, unknown>;
                if (config?.agents) {
                    setAgents(config.agents as Agent[]);
                }
                if (config?.streamable_tools) {
                    streamableToolsRef.current = config.streamable_tools as Record<string, { agent_id: string; default_interval: number }>;
                }
                break;
            }

            case "agent_registered":
                setAgents(prev => {
                    const existing = prev.find(a => a.id === data.agent_id);
                    if (existing) return prev;
                    return [...prev, {
                        id: data.agent_id as string,
                        name: data.name as string,
                        description: (data.description as string) || undefined,
                        tools: (data.tools as string[]) || [],
                        tool_descriptions: (data.tool_descriptions as Record<string, string>) || undefined,
                        scopes: (data.scopes as Record<string, boolean>) || undefined,
                        tool_scope_map: (data.tool_scope_map as Record<string, string>) || undefined,
                        permissions: (data.permissions as Record<string, boolean>) || undefined,
                        security_flags: (data.security_flags as Record<string, SecurityFlag>) || undefined,
                        metadata: (data.metadata as AgentMetadata) || undefined,
                        status: "connected",
                        owner_email: (data.owner_email as string) || undefined,
                        is_public: (data.is_public as boolean) || false,
                    } as Agent];
                });
                break;

            case "agent_list":
                setAgents((data.agents as Agent[]) || []);
                break;

            case "agent_creation_progress":
                // Dispatch a custom event so CreateAgentModal can listen
                window.dispatchEvent(new CustomEvent("agent_creation_progress", { detail: data }));
                break;

            case "audit_append":
                // 003-agent-audit-log: live-push a new audit entry to whichever
                // panel is open. The hook does not retain audit state itself —
                // panels subscribe via the "audit:append" custom event.
                window.dispatchEvent(new CustomEvent("audit:append", { detail: data.event }));
                break;

            case "llm_usage_report":
                // 006-user-llm-config: per-call token usage for personal-credential
                // calls. useTokenUsage subscribes to "llm-usage-report" and
                // accumulates session/today/lifetime/perModel counters.
                window.dispatchEvent(new CustomEvent("llm-usage-report", { detail: data }));
                break;

            case "llm_config_ack":
                // 006-user-llm-config: server ack for llm_config_set / _clear.
                // Currently no UI consumer needs this; left as a debug hook.
                break;

            case "chat_status":
                setChatStatus({
                    status: (data.status as "idle" | "thinking" | "executing" | "done") || "idle",
                    message: (data.message as string) || ""
                });
                break;

            case "ui_render": {
                // Don't auto-clear chat status here — the backend sends
                // an explicit chat_status: "done" when processing is complete.
                const renderTarget = (data.target as string) || "canvas";
                const components = (data.components as Record<string, unknown>[]) || [];
                setUiComponents(components);

                if (renderTarget === "chat") {
                    // Text-only responses go to the floating chat panel
                    setMessages(prev => [
                        ...prev,
                        { role: "assistant", content: components, _target: "chat" }
                    ]);
                } else {
                    // Canvas components: save immediately to backend for persistence
                    // The component_saved handler will add them to canvasComponents with real IDs
                    const chatId = activeChatIdRef.current;
                    if (chatId && wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
                        for (const comp of components) {
                            const sourceTool = comp._source_tool as string | undefined;
                            const sourceParams = (comp._source_params as Record<string, unknown> | undefined) || {};
                            const cfg = sourceTool ? streamableToolsRef.current[sourceTool] : undefined;
                            // 001-tool-stream-ui (US2 T047): skip auto-save for
                            // streaming components. Saving every chunk would bloat
                            // history and confuse the "latest version" semantics —
                            // the subscription metadata is the persistent thing, not
                            // the chunks (per A-007 / FR-009).
                            const isStreamComponent = (
                                (typeof comp.id === "string" && (comp.id as string).startsWith("stream-"))
                                || (cfg?.kind === "push")
                            );
                            if (!isStreamComponent) {
                                wsRef.current.send(JSON.stringify({
                                    type: "ui_event",
                                    action: "save_component",
                                    payload: {
                                        chat_id: chatId,
                                        component_data: comp,
                                        component_type: (comp.type as string) || "unknown",
                                        title: (comp.title as string) || (comp.type as string) || "Component",
                                    }
                                }));
                            }

                            // Auto-subscribe to live streaming if this tool is streamable.
                            // Runs for BOTH push and poll kinds — for push tools this is
                            // how the first snapshot turns into a live-updating stream.
                            if (sourceTool && cfg && !activeSubscriptionsRef.current.has(sourceTool)) {
                                activeSubscriptionsRef.current.set(sourceTool, { interval: cfg.default_interval, params: sourceParams });
                                sendStreamSubscribe(wsRef.current, sourceTool, cfg, sourceParams, chatId);
                            }
                        }
                    }
                    // Also add to messages for history, marked as canvas
                    setMessages(prev => [
                        ...prev,
                        { role: "assistant", content: components, _target: "canvas" }
                    ]);
                }
                break;
            }

            case "ui_update":
                setUiComponents((data.components as Record<string, unknown>[]) || []);
                break;

            // 001-tool-stream-ui: incoming push streaming chunk.
            // See contracts/frontend-events.md §1.
            case "ui_stream_data": {
                const msg = data as unknown as UIStreamDataMessage;

                // Defense in depth: drop chunks for chats other than the
                // currently-loaded one. The server already gates by chat,
                // but this catches the race where a chunk arrives just as
                // the user navigates away.
                if (msg.session_id && msg.session_id !== activeChatIdRef.current) {
                    break;
                }

                // Drop out-of-order chunks (a retry may have re-issued the
                // tool call and a stale chunk from the previous attempt
                // might arrive late).
                const lastSeq = streamSeqRef.current.get(msg.stream_id) ?? -1;
                if (msg.seq <= lastSeq) {
                    break;
                }
                streamSeqRef.current.set(msg.stream_id, msg.seq);

                // Merge into uiComponents by id (preserves React fiber
                // identity for sibling components).
                setUiComponents((prev) => mergeStreamChunk(prev, msg));

                // Terminal chunk → drop the client-side subscription record
                // and the seq tracker.
                if (msg.terminal) {
                    pushStreamsRef.current.delete(msg.stream_id);
                    streamSeqRef.current.delete(msg.stream_id);
                }
                break;
            }

            case "ui_append":
                setUiComponents(prev => [...prev, ...((data.components as Record<string, unknown>[]) || [])]);
                break;

            case "history_list":
                setChatHistory((data.chats as ChatSession[]) || []);
                break;

            case "chat_created":
                setActiveChatId((data.payload as Record<string, unknown>).chat_id as string, true);

                // Only clear messages and UI if this wasn't created as a side-effect of a message
                if (!(data.payload as Record<string, unknown>).from_message) {
                    setMessages([]);
                    setUiComponents([]);
                    setSavedComponents([]);
                    setCanvasComponents([]);
                }


                // Refresh history
                if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
                    wsRef.current.send(JSON.stringify({
                        type: "ui_event",
                        action: "get_history",
                        payload: {}
                    }));
                }
                break;

            case "chat_loaded":
                if (data.chat) {
                    setActiveChatId((data.chat as Record<string, unknown>).id as string);
                    // Convert stored messages to UI format if needed
                    // For now, we just load them into the messages array
                    // You might need to parse "content" if it's stored as a string or handle UI components
                    const loadedMessages = (data.chat as Record<string, unknown>).messages
                        ? ((data.chat as Record<string, unknown>).messages as Array<Record<string, unknown>>).map(m => ({
                            role: m.role as string,
                            content: m.content
                        }))
                        : [];
                    setMessages(loadedMessages);

                    // If the last message was from assistant, we might want to restore UI components?
                    // For simplicity, we just clear current UI components unless we reconstruct them
                    setUiComponents([]);
                    setSavedComponents([]);
                    setCanvasComponents([]);

                    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
                        wsRef.current.send(JSON.stringify({
                            type: "ui_event",
                            action: "get_saved_components",
                            payload: { chat_id: (data.chat as Record<string, unknown>).id as string }
                        }));
                    }

                    // Restore saved subscriptions for this chat (if any)
                    const loadedChatId = (data.chat as Record<string, unknown>).id as string;
                    const savedSubs = chatSubscriptionsMapRef.current.get(loadedChatId);
                    if (savedSubs && savedSubs.size > 0) {
                        setTimeout(() => {
                            if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
                                for (const [toolName, config] of savedSubs.entries()) {
                                    if (!activeSubscriptionsRef.current.has(toolName)) {
                                        activeSubscriptionsRef.current.set(toolName, config);
                                        const cfg = streamableToolsRef.current[toolName]
                                            ?? { default_interval: config.interval, kind: "poll" };
                                        sendStreamSubscribe(wsRef.current, toolName, cfg, config.params, loadedChatId);
                                    }
                                }
                            }
                        }, 500); // Delay to let saved_components_list auto-subscribe run first
                    }
                }
                break;

            // Saved components messages
            case "saved_components_list":
                if (data.components) {
                    setSavedComponents(data.components as SavedComponent[]);
                    // Also populate canvas with saved components when loading a chat
                    setCanvasComponents(data.components as SavedComponent[]);

                    // Auto-subscribe to streams for any streamable tools on this chat's canvas
                    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
                        const chatId = activeChatIdRef.current;
                        for (const sc of data.components as SavedComponent[]) {
                            const sourceTool = sc.component_data?._source_tool as string | undefined;
                            const sourceParams = (sc.component_data?._source_params as Record<string, unknown> | undefined) || {};
                            if (sourceTool && streamableToolsRef.current[sourceTool] && !activeSubscriptionsRef.current.has(sourceTool)) {
                                const cfg = streamableToolsRef.current[sourceTool];
                                activeSubscriptionsRef.current.set(sourceTool, { interval: cfg.default_interval, params: sourceParams });
                                sendStreamSubscribe(wsRef.current, sourceTool, cfg, sourceParams, chatId);
                            }
                        }
                    }
                }
                break;

            case "component_saved": {
                const savedComp = data.component as SavedComponent;
                setSavedComponents(prev => [savedComp, ...prev]);
                // Also add to canvas if not already there
                setCanvasComponents(prev => {
                    if (prev.some(c => c.id === savedComp.id)) return prev;
                    return [savedComp, ...prev];
                });
                if (pendingSaveResolveRef.current) {
                    pendingSaveResolveRef.current(true);
                    pendingSaveResolveRef.current = null;
                    pendingSaveRejectRef.current = null;
                }
                break;
            }

            case "component_save_error":
                if (pendingSaveRejectRef.current) {
                    pendingSaveRejectRef.current(new Error((data.error as string) || "Failed to save component"));
                    pendingSaveResolveRef.current = null;
                    pendingSaveRejectRef.current = null;
                }
                break;

            case "component_deleted":
                if (data.component_id) {
                    setSavedComponents((prev) => prev.filter(c => c.id !== data.component_id));
                    setCanvasComponents((prev) => prev.filter(c => c.id !== data.component_id));
                }
                break;

            case "combine_status":
                setIsCombining(true);
                setCombineError(null);
                break;

            case "components_combined":
                if (condenseTimeoutRef.current) { clearTimeout(condenseTimeoutRef.current); condenseTimeoutRef.current = null; }
                setIsCombining(false);
                setCombineError(null);
                if (data.new_components) {
                    const updateCombined = (prev: SavedComponent[]) => {
                        let filtered = prev;
                        if (data.removed_ids) {
                            filtered = prev.filter(c => !(data.removed_ids as string[]).includes(c.id));
                        }
                        return [...(data.new_components as SavedComponent[]), ...filtered];
                    };
                    setSavedComponents(updateCombined);
                    setCanvasComponents(updateCombined);
                }
                break;
            case "components_condensed": {
                if (condenseTimeoutRef.current) { clearTimeout(condenseTimeoutRef.current); condenseTimeoutRef.current = null; }
                setIsCombining(false);
                setCombineError(null);
                const updateCondensed = (prev: SavedComponent[]) => {
                    const removedIds = new Set((data.removed_ids as string[]) || []);
                    const remaining = prev.filter(c => !removedIds.has(c.id as string));
                    return [...((data.new_components as SavedComponent[]) || []), ...remaining];
                };
                setSavedComponents(updateCondensed);
                setCanvasComponents(updateCondensed);
                break;
            }

            case "components_replaced": {
                // In-place replacement: swap old components with new ones at the same position
                const removedArray = (data.removed_ids as string[]) || [];
                const newComps = (data.new_components as SavedComponent[]) || [];
                const replaceMap = new Map<string, SavedComponent>();
                removedArray.forEach((oldId, idx) => {
                    if (idx < newComps.length) replaceMap.set(oldId, newComps[idx]);
                });
                const updateReplaced = (prev: SavedComponent[]) => {
                    return prev.map(c => {
                        const replacement = replaceMap.get(c.id);
                        return replacement ? replacement : c;
                    });
                };
                setSavedComponents(updateReplaced);
                setCanvasComponents(updateReplaced);
                break;
            }

            case "combine_error":
                if (condenseTimeoutRef.current) { clearTimeout(condenseTimeoutRef.current); condenseTimeoutRef.current = null; }
                setIsCombining(false);
                setCombineError((data.error as string) || "Failed to combine components");
                console.error("Combine error:", data.error);
                toast.error("Failed to combine components");
                // Auto-clear error after 5 seconds
                setTimeout(() => setCombineError(null), 5000);
                break;

            case "agent_permissions":
                setAgentPermissions(data as unknown as AgentPermissionsData);
                break;

            case "agent_permissions_updated":
                // Update scopes and derived permissions in local state
                if (data.agent_id) {
                    setAgents(prev => prev.map(a =>
                        a.id === data.agent_id
                            ? {
                                ...a,
                                scopes: (data.scopes as Record<string, boolean>) || a.scopes,
                                permissions: (data.permissions as Record<string, boolean>) || a.permissions,
                            }
                            : a
                    ));
                    setAgentPermissions(prev =>
                        prev && prev.agent_id === data.agent_id
                            ? {
                                ...prev,
                                scopes: (data.scopes as Record<string, boolean>) || prev.scopes,
                                permissions: (data.permissions as Record<string, boolean>) || prev.permissions,
                            }
                            : prev
                    );
                }
                break;

            case "rote_config": {
                // ROTE has confirmed the device profile — extract capability flags
                // so the UI can conditionally render mic/TTS/location features.
                const profile = data.device_profile as Record<string, unknown> | undefined;
                const caps = profile?.capabilities as Record<string, unknown> | undefined;
                setDeviceCapabilities({
                    hasMicrophone: Boolean(caps?.has_microphone),
                    hasGeolocation: Boolean(caps?.has_geolocation),
                    speechServerAvailable: Boolean(data.speech_server_available),
                });
                break;
            }

            case "user_preferences":
                // Server sent stored user preferences (theme, etc.)
                // Dispatch to ThemeContext via CustomEvent
                window.dispatchEvent(new CustomEvent("astral-server-preferences", {
                    detail: (data as Record<string, unknown>).preferences,
                }));
                break;

            case "heartbeat":
                // Server is still processing — no UI action needed.
                // This prevents WebSocket timeout during long operations.
                break;

            // --- Live Streaming ---
            case "stream_data": {
                const toolName = data.tool_name as string;
                const streamComponents = (data.components as Record<string, unknown>[]) || [];
                setStreamData(prev => ({
                    ...prev,
                    [toolName]: {
                        components: streamComponents,
                        data: (data.data as Record<string, unknown>) || {},
                        timestamp: data.timestamp as number,
                    }
                }));

                // Live-update matching canvas components in-place (no DB save)
                if (streamComponents.length > 0) {
                    setCanvasComponents(prev => prev.map(sc => {
                        if ((sc.component_data?._source_tool as string) === toolName) {
                            return { ...sc, component_data: streamComponents[0] };
                        }
                        return sc;
                    }));
                }
                break;
            }

            case "stream_subscribed": {
                // Existing legacy poll path: no client-side bookkeeping.
                // 001-tool-stream-ui push path: record the subscription so
                // we can re-issue on manual retry. The server includes
                // `attached: true` when this client joined an existing
                // deduplicated subscription (FR-009a) — same recording.
                const sub = data as unknown as StreamSubscribedMessage;
                if (sub.stream_id) {
                    pushStreamsRef.current.set(sub.stream_id, {
                        stream_id: sub.stream_id,
                        chat_id: sub.session_id ?? "",
                        tool_name: sub.tool_name,
                        agent_id: sub.agent_id,
                        params: {}, // populated by the original subscribe call
                    });
                }
                break;
            }

            case "stream_unsubscribed": {
                const unsubTool = data.tool_name as string;
                setStreamData(prev => {
                    const next = { ...prev };
                    delete next[unsubTool];
                    return next;
                });
                break;
            }

            case "stream_error":
                console.error(`Stream error for ${data.tool_name}:`, data.error);
                toast.error(`Stream error: ${data.error}`);
                // Remove from active subscriptions so we don't re-subscribe on reconnect
                activeSubscriptionsRef.current.delete(data.tool_name as string);
                break;

            case "stream_list":
                break;

            default:
            // console.log("Unknown message type:", data.type, data);
        }
    }, [setActiveChatId]);

    const connect = useCallback(() => {
        const currentToken = tokenRef.current;
        if (!currentToken) return; // Don't connect without token

        const isReconnect = reconnectAttemptsRef.current > 0;
        setConnectionState(isReconnect ? "reconnecting" : "connecting");

        try {
            const ws = new WebSocket(url);
            wsRef.current = ws;

            ws.onopen = () => {
                const currentChatId = activeChatIdRef.current;
                // On first connect, check URL for a chat ID to restore
                const urlChatId = new URLSearchParams(window.location.search).get("chat");
                const chatToLoad = currentChatId || urlChatId;
                setIsConnected(true);
                setConnectionState("connected");

                if (isReconnect) {
                    toast.success("Reconnected to server");
                }
                reconnectAttemptsRef.current = 0;

                setChatStatus({ status: "idle", message: "" });
                // Send RegisterUI with token and ROTE device capabilities.
                // 006-user-llm-config: also forward any saved personal LLM
                // config so the orchestrator's per-WebSocket credential store
                // is seeded immediately. The key is held in process memory
                // only and cleared on disconnect (FR-002).
                let initialLlmConfig: { api_key: string; base_url: string; model: string } | undefined;
                try {
                    const raw = window.localStorage.getItem("astralbody.llm.config.v1");
                    if (raw) {
                        const parsed = JSON.parse(raw);
                        if (
                            parsed && typeof parsed === "object" &&
                            typeof parsed.apiKey === "string" && parsed.apiKey &&
                            typeof parsed.baseUrl === "string" && parsed.baseUrl &&
                            typeof parsed.model === "string" && parsed.model
                        ) {
                            initialLlmConfig = {
                                api_key: parsed.apiKey,
                                base_url: parsed.baseUrl,
                                model: parsed.model,
                            };
                        }
                    }
                } catch {
                    // Corrupt JSON — register without the field.
                }
                ws.send(JSON.stringify({
                    type: "register_ui",
                    token: currentToken,
                    capabilities: ["render", "stream"],
                    session_id: `ui-${Date.now()}`,
                    device: detectDeviceCapabilities(),
                    ...(initialLlmConfig ? { llm_config: initialLlmConfig } : {}),
                }));
                // Fetch history
                ws.send(JSON.stringify({
                    type: "ui_event",
                    action: "get_history",
                    payload: {}
                }));

                // If we have an active chat ID (from state or URL), load it
                if (chatToLoad) {
                    setTimeout(() => {
                        if (ws.readyState === WebSocket.OPEN) {
                            ws.send(JSON.stringify({
                                type: "ui_event",
                                action: "load_chat",
                                payload: { chat_id: chatToLoad }
                            }));
                        } else {
                            console.error('WebSocket not OPEN when trying to reload chat. State:', ws.readyState);
                        }
                    }, 500); // Small delay to ensure registration is processed
                }

                // Re-subscribe to active streams after reconnection
                if (isReconnect && activeSubscriptionsRef.current.size > 0) {
                    setTimeout(() => {
                        if (ws.readyState === WebSocket.OPEN) {
                            for (const [toolName, config] of activeSubscriptionsRef.current.entries()) {
                                ws.send(JSON.stringify({
                                    type: "ui_event",
                                    action: "stream_subscribe",
                                    payload: { tool_name: toolName, interval_seconds: config.interval, params: config.params }
                                }));
                            }
                        }
                    }, 1000); // After registration + chat reload
                }
            };

            ws.onmessage = (event) => {
                try {
                    const data: WSMessage = JSON.parse(event.data);
                    handleMessage(data);
                } catch (e) {
                    console.error("Failed to parse WS message:", e);
                    toast.error("Received malformed message from server");
                }
            };

            ws.onclose = () => {
                // Reject any pending save operation so the UI doesn't hang
                if (pendingSaveRejectRef.current) {
                    pendingSaveRejectRef.current(new Error("Connection lost during save"));
                    pendingSaveResolveRef.current = null;
                    pendingSaveRejectRef.current = null;
                }
                setIsConnected(false);
                reconnectAttemptsRef.current += 1;

                if (reconnectAttemptsRef.current <= MAX_RECONNECT_ATTEMPTS) {
                    setConnectionState("reconnecting");
                    if (reconnectAttemptsRef.current === 1) {
                        toast.error("Connection lost. Reconnecting...");
                    }
                    reconnectTimer.current = window.setTimeout(() => {
                        const c = wsRef.current as WebSocket & { _reconnect?: () => void };
                        if (c && c._reconnect) c._reconnect();
                    }, 3000);
                } else {
                    setConnectionState("disconnected");
                    toast.error("Unable to reconnect. Please refresh the page.");
                }
            };

            ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                ws.close();
            };

            // Circular reconnect is handled by the useEffect below
        } catch (e) {
            console.error("WebSocket connection failed:", e);
            reconnectAttemptsRef.current += 1;
            if (reconnectAttemptsRef.current <= MAX_RECONNECT_ATTEMPTS) {
                setConnectionState("reconnecting");
                reconnectTimer.current = window.setTimeout(() => {
                    const c = wsRef.current as WebSocket & { _reconnect?: () => void };
                    if (c && c._reconnect) c._reconnect();
                }, 3000);
            } else {
                setConnectionState("disconnected");
                toast.error("Unable to connect. Please refresh the page.");
            }
        }
    }, [url, handleMessage, userId]);

    // Also update previously bound reconnect loop
    useEffect(() => {
        if (wsRef.current) {
            // Assign the connect function to _reconnect property for circular reference
            // This allows onclose/onerror to call the latest 'connect' without stale closures
            (wsRef.current as WebSocket & { _reconnect?: () => void })._reconnect = connect;
        }
    }, [connect]);

    // 006-user-llm-config: when the settings panel saves or clears the
    // user's personal config, the useLlmConfig hook fires the
    // "llm-config-changed" window event. Translate that into the
    // matching server-side message.
    useEffect(() => {
        if (typeof window === "undefined") return;
        const onChange = (ev: Event) => {
            const ws = wsRef.current;
            if (!ws || ws.readyState !== WebSocket.OPEN) return;
            const detail = (ev as CustomEvent).detail as { action: "set" | "cleared"; config?: { apiKey?: string; baseUrl?: string; model?: string } | null };
            if (!detail) return;
            if (detail.action === "cleared") {
                ws.send(JSON.stringify({ type: "llm_config_clear" }));
                return;
            }
            const c = detail.config;
            if (!c?.apiKey || !c?.baseUrl || !c?.model) return;
            ws.send(JSON.stringify({
                type: "llm_config_set",
                config: {
                    api_key: c.apiKey,
                    base_url: c.baseUrl,
                    model: c.model,
                },
            }));
        };
        window.addEventListener("llm-config-changed", onChange);
        return () => window.removeEventListener("llm-config-changed", onChange);
    }, []);

    const sendMessage = useCallback((message: string, displayMessage?: string, explicitChatId?: string) => {
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

        const targetChatId = explicitChatId || activeChatId;

        setMessages(prev => [...prev, { role: "user", content: displayMessage || message }]);
        setChatStatus({ status: "thinking", message: "Processing..." });

        wsRef.current.send(JSON.stringify({
            type: "ui_event",
            action: "chat_message",
            session_id: targetChatId || undefined,
            payload: {
                message,
                chat_id: targetChatId,
                display_message: displayMessage
            }
        }));
    }, [activeChatId]);

    const cancelTask = useCallback(() => {
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
        wsRef.current.send(JSON.stringify({
            type: "ui_event",
            action: "cancel_task",
            payload: {}
        }));
        setChatStatus({ status: "idle", message: "" });
    }, []);

    const loadChat = useCallback((chatId: string) => {
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
        // Save current chat's active subscriptions before switching
        const currentChatId = activeChatIdRef.current;
        if (currentChatId && activeSubscriptionsRef.current.size > 0) {
            chatSubscriptionsMapRef.current.set(currentChatId, new Map(activeSubscriptionsRef.current));
        }
        // Unsubscribe all active streams when switching chats
        for (const toolName of activeSubscriptionsRef.current.keys()) {
            wsRef.current.send(JSON.stringify({
                type: "ui_event",
                action: "stream_unsubscribe",
                payload: { tool_name: toolName }
            }));
        }
        activeSubscriptionsRef.current.clear();
        setStreamData({});
        wsRef.current.send(JSON.stringify({
            type: "ui_event",
            action: "load_chat",
            payload: { chat_id: chatId }
        }));
    }, []);

    const createNewChat = useCallback(() => {
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
        // Save current chat's active subscriptions before creating new chat
        const currentChatId = activeChatIdRef.current;
        if (currentChatId && activeSubscriptionsRef.current.size > 0) {
            chatSubscriptionsMapRef.current.set(currentChatId, new Map(activeSubscriptionsRef.current));
        }
        // Unsubscribe all active streams when creating new chat
        for (const toolName of activeSubscriptionsRef.current.keys()) {
            wsRef.current.send(JSON.stringify({
                type: "ui_event",
                action: "stream_unsubscribe",
                payload: { tool_name: toolName }
            }));
        }
        activeSubscriptionsRef.current.clear();
        setStreamData({});
        wsRef.current.send(JSON.stringify({
            type: "ui_event",
            action: "new_chat",
            payload: {}
        }));
    }, []);

    // Handle browser back/forward navigation
    useEffect(() => {
        const handlePopState = () => {
            const urlChatId = new URLSearchParams(window.location.search).get("chat");
            if (urlChatId && urlChatId !== activeChatIdRef.current) {
                loadChat(urlChatId);
            } else if (!urlChatId && activeChatIdRef.current) {
                createNewChat();
            }
        };
        window.addEventListener("popstate", handlePopState);
        return () => window.removeEventListener("popstate", handlePopState);
    }, [loadChat, createNewChat]);

    const deleteChat = useCallback(async (chatId: string) => {
        // Clean up saved subscriptions for deleted chat
        chatSubscriptionsMapRef.current.delete(chatId);
        try {
            const currentToken = tokenRef.current;
            const headers: Record<string, string> = {};
            if (currentToken) {
                headers["Authorization"] = `Bearer ${currentToken}`;
            }

            const response = await fetch(`${API_URL}/api/chats/${chatId}`, {
                method: "DELETE",
                headers
            });

            if (response.ok) {
                if (chatId === activeChatIdRef.current) {
                    createNewChat();
                }
                if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
                    wsRef.current.send(JSON.stringify({
                        type: "ui_event",
                        action: "get_history",
                        payload: {}
                    }));
                }
            } else {
                console.error("Failed to delete chat", await response.text());
                toast.error("Failed to delete chat");
            }
        } catch (e) {
            console.error("Error deleting chat", e);
            toast.error("Failed to delete chat");
        }
    }, [createNewChat]);

    const discoverAgents = useCallback(() => {
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
        wsRef.current.send(JSON.stringify({
            type: "ui_event",
            action: "discover_agents",
            payload: {}
        }));
    }, []);

    const registerExternalAgent = useCallback((url: string) => {
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
        wsRef.current.send(JSON.stringify({
            type: "ui_event",
            action: "register_external_agent",
            payload: { url }
        }));
    }, []);

    // Saved components functions
    const saveComponent = useCallback(async (componentData: Record<string, unknown>, componentType: string, title?: string): Promise<boolean> => {
        // console.log('saveComponent called:', { componentType, title, wsRefCurrent: wsRef.current, wsReadyState: wsRef.current?.readyState, activeChatId, timestamp: new Date().toISOString() });

        if (!wsRef.current) {
            console.error('WebSocket reference is null - cannot save component');
            throw new Error('WebSocket connection lost. Please refresh the page.');
        }

        if (wsRef.current.readyState !== WebSocket.OPEN) {
            console.error('WebSocket not in OPEN state:', wsRef.current.readyState, 'Connection state:', wsRef.current.readyState === WebSocket.CONNECTING ? 'CONNECTING' : wsRef.current.readyState === WebSocket.CLOSING ? 'CLOSING' : wsRef.current.readyState === WebSocket.CLOSED ? 'CLOSED' : 'UNKNOWN');
            throw new Error('WebSocket connection is not open. State: ' + wsRef.current.readyState + '. Please try again or refresh the page.');
        }

        if (!activeChatId) {
            console.error('No active chat ID - cannot save component without active chat');
            throw new Error('No active chat session. Please start a new chat or load an existing one.');
        }

        // Validate required data
        if (!componentData || !componentType) {
            throw new Error('Component data and type are required');
        }

        // Create a promise that will be resolved/rejected when WebSocket confirmation arrives
        const promise = new Promise<boolean>((resolve, reject) => {
            // Store resolve/reject functions
            pendingSaveResolveRef.current = resolve;
            pendingSaveRejectRef.current = reject;
            // Set a timeout to reject if no response within 10 seconds
            setTimeout(() => {
                if (pendingSaveRejectRef.current === reject) {
                    pendingSaveRejectRef.current = null;
                    pendingSaveResolveRef.current = null;
                    reject(new Error('Save request timed out after 10 seconds'));
                }
            }, 10000);
        });

        // Send the save request
        wsRef.current.send(JSON.stringify({
            type: "ui_event",
            action: "save_component",
            payload: {
                chat_id: activeChatId,
                component_data: componentData,
                component_type: componentType,
                title: title || componentType.replace('_', ' ').replace('chart', 'Chart'),
            }
        }));

        // console.log('Save request sent for component:', componentType, 'to chat:', activeChatId);
        return promise;
    }, [activeChatId]);

    const deleteSavedComponent = useCallback((componentId: string) => {
        // Remove from canvas immediately
        setCanvasComponents(prev => prev.filter(c => c.id !== componentId));

        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
        wsRef.current.send(JSON.stringify({
            type: "ui_event",
            action: "delete_saved_component",
            payload: { component_id: componentId }
        }));
    }, []);

    const loadSavedComponents = useCallback(() => {
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
        wsRef.current.send(JSON.stringify({
            type: "ui_event",
            action: "get_saved_components",
            payload: { chat_id: activeChatId }
        }));
    }, [activeChatId]);

    const combineComponents = useCallback((sourceId: string, targetId: string) => {
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
        setIsCombining(true);
        setCombineError(null);
        wsRef.current.send(JSON.stringify({
            type: "ui_event",
            action: "combine_components",
            payload: { source_id: sourceId, target_id: targetId }
        }));
    }, []);

    const condenseComponents = useCallback((componentIds: string[]) => {
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
        setIsCombining(true);
        setCombineError(null);
        // Safety timeout: reset spinner if backend never responds
        if (condenseTimeoutRef.current) clearTimeout(condenseTimeoutRef.current);
        condenseTimeoutRef.current = setTimeout(() => {
            setIsCombining(false);
            setCombineError("Condense timed out — no response from server");
            toast.error("Condense timed out — please try again");
            setTimeout(() => setCombineError(null), 5000);
            condenseTimeoutRef.current = null;
        }, 60_000);
        wsRef.current.send(JSON.stringify({
            type: "ui_event",
            action: "condense_components",
            payload: { component_ids: componentIds }
        }));
    }, []);

    const getAgentPermissions = useCallback((agentId: string) => {
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
        wsRef.current.send(JSON.stringify({
            type: "ui_event",
            action: "get_agent_permissions",
            payload: { agent_id: agentId }
        }));
    }, []);

    const setAgentPermissionsAction = useCallback((agentId: string, scopes: Record<string, boolean>, toolOverrides?: Record<string, boolean>) => {
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
        wsRef.current.send(JSON.stringify({
            type: "ui_event",
            action: "set_agent_permissions",
            payload: { agent_id: agentId, scopes, ...(toolOverrides ? { tool_overrides: toolOverrides } : {}) }
        }));
    }, []);

    // ── Credential Management (REST) ────────────────────────────────────
    const [agentCredentialKeys, setAgentCredentialKeys] = useState<Record<string, string[]>>({});

    const fetchAgentCredentials = useCallback(async (agentId: string) => {
        try {
            const headers: Record<string, string> = {};
            if (tokenRef.current) headers["Authorization"] = `Bearer ${tokenRef.current}`;
            const resp = await fetch(`${API_URL}/api/agents/${agentId}/credentials`, { headers });
            if (resp.ok) {
                const data = await resp.json();
                setAgentCredentialKeys(prev => ({ ...prev, [agentId]: data.credential_keys || [] }));
                return data;
            }
        } catch (e) {
            console.error("Failed to fetch credentials for", agentId, e);
        }
        return null;
    }, []);

    const saveAgentCredentials = useCallback(async (agentId: string, credentials: Record<string, string>): Promise<boolean> => {
        try {
            const headers: Record<string, string> = { "Content-Type": "application/json" };
            if (tokenRef.current) headers["Authorization"] = `Bearer ${tokenRef.current}`;
            const resp = await fetch(`${API_URL}/api/agents/${agentId}/credentials`, {
                method: "PUT",
                headers,
                body: JSON.stringify({ credentials }),
            });
            if (resp.ok) {
                const data = await resp.json();
                setAgentCredentialKeys(prev => ({ ...prev, [agentId]: data.credential_keys || [] }));
                toast.success("Credentials saved");
                return true;
            } else {
                toast.error("Failed to save credentials");
            }
        } catch (e) {
            console.error("Failed to save credentials for", agentId, e);
            toast.error("Failed to save credentials");
        }
        return false;
    }, []);

    const deleteAgentCredential = useCallback(async (agentId: string, key: string): Promise<boolean> => {
        try {
            const headers: Record<string, string> = {};
            if (tokenRef.current) headers["Authorization"] = `Bearer ${tokenRef.current}`;
            const resp = await fetch(`${API_URL}/api/agents/${agentId}/credentials/${key}`, {
                method: "DELETE",
                headers,
            });
            if (resp.ok) {
                setAgentCredentialKeys(prev => ({
                    ...prev,
                    [agentId]: (prev[agentId] || []).filter(k => k !== key),
                }));
                toast.success("Credential removed");
                return true;
            }
        } catch (e) {
            console.error("Failed to delete credential", key, "for", agentId, e);
        }
        return false;
    }, []);

    const startOAuthFlow = useCallback(async (agentId: string): Promise<boolean> => {
        try {
            const headers: Record<string, string> = {};
            if (tokenRef.current) headers["Authorization"] = `Bearer ${tokenRef.current}`;
            const resp = await fetch(`${API_URL}/api/agents/${agentId}/oauth/authorize`, { headers });
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({ detail: "Failed to start OAuth flow" }));
                toast.error(err.detail || "Failed to start OAuth flow");
                return false;
            }
            const data = await resp.json();
            const authUrl = data.authorization_url;
            if (!authUrl) {
                toast.error("No authorization URL returned");
                return false;
            }

            // Open authorization in a popup
            const popup = window.open(authUrl, "linkedin_oauth", "width=600,height=700,scrollbars=yes");

            // Listen for the callback postMessage
            return new Promise<boolean>((resolve) => {
                const timeout = setTimeout(() => {
                    window.removeEventListener("message", handler);
                    resolve(false);
                }, 300000); // 5 minute timeout

                const handler = (event: MessageEvent) => {
                    if (event.data?.type === "linkedin_oauth_complete") {
                        clearTimeout(timeout);
                        window.removeEventListener("message", handler);
                        if (event.data.success) {
                            toast.success("LinkedIn authorized successfully");
                            // Refresh credential keys to reflect new tokens
                            fetchAgentCredentials(agentId);
                            resolve(true);
                        } else {
                            toast.error("LinkedIn authorization failed");
                            resolve(false);
                        }
                    }
                };
                window.addEventListener("message", handler);

                // Also poll for popup close (user may close without completing)
                const pollClose = setInterval(() => {
                    if (popup?.closed) {
                        clearInterval(pollClose);
                        clearTimeout(timeout);
                        window.removeEventListener("message", handler);
                        // Refresh credentials in case it completed before close
                        fetchAgentCredentials(agentId);
                        resolve(false);
                    }
                }, 1000);
            });
        } catch (e) {
            console.error("OAuth flow error for", agentId, e);
            toast.error("Failed to start OAuth flow");
            return false;
        }
    }, [fetchAgentCredentials]);

    useEffect(() => {
        // Only connect in the top-level window (avoids connections in OIDC renew iframes)
        // and delay slightly to allow the environment to stabilize on reload.
        if (window.self !== window.top) return;

        const timer = setTimeout(() => {
            connect();
        }, 500);

        return () => {
            clearTimeout(timer);
            if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
            wsRef.current?.close();
        };
    }, [connect]);

    // ROTE: Send updated device capabilities on viewport resize
    useEffect(() => {
        let debounceTimer: ReturnType<typeof setTimeout> | null = null;
        let lastDeviceType = detectDeviceType();
        let lastViewportWidth = window.innerWidth;

        const onResize = () => {
            if (debounceTimer) clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => {
                const ws = wsRef.current;
                if (!ws || ws.readyState !== WebSocket.OPEN) return;

                const caps = detectDeviceCapabilities();
                const newDeviceType = caps.device_type as string;
                const newWidth = caps.viewport_width as number;

                // Send when device type changes or viewport width shifts
                // meaningfully (>50px) to avoid spamming on tiny adjustments.
                if (
                    newDeviceType !== lastDeviceType ||
                    Math.abs(newWidth - lastViewportWidth) > 50
                ) {
                    lastDeviceType = newDeviceType;
                    lastViewportWidth = newWidth;
                    ws.send(JSON.stringify({
                        type: "ui_event",
                        action: "update_device",
                        payload: { device: caps },
                    }));
                }
            }, 500);
        };

        window.addEventListener("resize", onResize);
        return () => {
            window.removeEventListener("resize", onResize);
            if (debounceTimer) clearTimeout(debounceTimer);
        };
    }, []);

    // Listen for theme save requests from ThemeContext
    useEffect(() => {
        const onSaveTheme = (e: Event) => {
            const detail = (e as CustomEvent).detail;
            const ws = wsRef.current;
            if (!ws || ws.readyState !== WebSocket.OPEN) return;
            ws.send(JSON.stringify({
                type: "ui_event",
                action: "save_theme",
                payload: { theme: detail },
            }));
        };
        window.addEventListener("astral-save-theme", onSaveTheme);
        return () => window.removeEventListener("astral-save-theme", onSaveTheme);
    }, []);

    // ── Agent Visibility ──────────────────────────────────────────────
    const sendTablePaginate = useCallback((event: { source_tool: string; source_agent: string; source_params: Record<string, unknown>; limit: number; offset: number }) => {
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
        wsRef.current.send(JSON.stringify({
            type: "ui_event",
            action: "table_paginate",
            payload: {
                tool_name: event.source_tool,
                agent_id: event.source_agent,
                params: { ...event.source_params, limit: event.limit, offset: event.offset },
            }
        }));
        setChatStatus({ status: "executing", message: "Loading table data..." });
    }, []);

    const setAgentVisibility = useCallback(async (agentId: string, isPublic: boolean): Promise<boolean> => {
        try {
            const headers: Record<string, string> = { "Content-Type": "application/json" };
            if (tokenRef.current) headers["Authorization"] = `Bearer ${tokenRef.current}`;
            const resp = await fetch(`${API_URL}/api/agents/${agentId}/visibility`, {
                method: "PUT",
                headers,
                body: JSON.stringify({ is_public: isPublic }),
            });
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({}));
                toast.error(err.detail || "Failed to update agent visibility");
                return false;
            }
            // Update local agents state
            setAgents(prev => prev.map(a =>
                a.id === agentId ? { ...a, is_public: isPublic } : a
            ));
            toast.success(isPublic ? "Agent is now public" : "Agent is now private");
            return true;
        } catch (e) {
            console.error("Failed to set agent visibility:", e);
            toast.error("Failed to update agent visibility");
            return false;
        }
    }, []);

    // --- Live Streaming ---
    const subscribeStream = useCallback((toolName: string, intervalSeconds: number = 2, params: Record<string, unknown> = {}) => {
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
        activeSubscriptionsRef.current.set(toolName, { interval: intervalSeconds, params });
        wsRef.current.send(JSON.stringify({
            type: "ui_event",
            action: "stream_subscribe",
            payload: { tool_name: toolName, interval_seconds: intervalSeconds, params }
        }));
    }, []);

    const unsubscribeStream = useCallback((toolName: string) => {
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
        activeSubscriptionsRef.current.delete(toolName);
        wsRef.current.send(JSON.stringify({
            type: "ui_event",
            action: "stream_unsubscribe",
            payload: { tool_name: toolName }
        }));
    }, []);

    return {
        isConnected,
        connectionState,
        agents,
        chatStatus,
        uiComponents,
        messages,
        sendMessage,
        cancelTask,
        discoverAgents,
        registerExternalAgent,
        activeChatId,
        chatHistory,
        loadChat,
        createNewChat,
        deleteChat,
        savedComponents,
        canvasComponents,
        saveComponent,
        deleteSavedComponent,
        loadSavedComponents,
        combineComponents,
        condenseComponents,
        isCombining,
        combineError,
        agentPermissions,
        getAgentPermissions,
        setAgentPermissions: setAgentPermissionsAction,
        agentCredentialKeys,
        fetchAgentCredentials,
        saveAgentCredentials,
        deleteAgentCredential,
        startOAuthFlow,
        setAgentVisibility,
        sendTablePaginate,
        deviceCapabilities,
        streamData,
        subscribeStream,
        unsubscribeStream,
        // Feature 004 — exposed so FeedbackProvider can wire the WS through
        // to FeedbackControl without an additional hook in the component tree.
        wsRef,
    };
}
