/**
 * WebSocket hook for real-time communication with the orchestrator.
 */
import { useState, useEffect, useRef, useCallback } from "react";

export interface Agent {
    id: string;
    name: string;
    tools: string[];
    status: string;
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

export interface WSMessage {
    type: string;
    [key: string]: unknown;
}

export function useWebSocket(url: string = "ws://localhost:8001", token?: string) {
    const [isConnected, setIsConnected] = useState(false);
    const [agents, setAgents] = useState<Agent[]>([]);
    const [chatStatus, setChatStatus] = useState<ChatStatus>({ status: "idle", message: "" });
    const [uiComponents, setUiComponents] = useState<Record<string, unknown>[]>([]);
    const [messages, setMessages] = useState<{ role: string; content: unknown }[]>([]);
    const [chatHistory, setChatHistory] = useState<ChatSession[]>([]);
    const [activeChatIdState, setActiveChatIdState] = useState<string | null>(null);
    const activeChatIdRef = useRef<string | null>(null);
    const [userId, setUserId] = useState<string | null>(null);

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
                const jsonPayload = decodeURIComponent(atob(base64).split('').map(function(c) {
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

    const setActiveChatId = useCallback((id: string | null) => {
        activeChatIdRef.current = id;
        setActiveChatIdState(id);
    }, []);

    const activeChatId = activeChatIdState;
    const [savedComponents, setSavedComponents] = useState<SavedComponent[]>([]);
    const [isCombining, setIsCombining] = useState(false);
    const [combineError, setCombineError] = useState<string | null>(null);
    const wsRef = useRef<WebSocket | null>(null);
    const reconnectTimer = useRef<number | null>(null);
    const pendingSaveResolveRef = useRef<((value: boolean) => void) | null>(null);
    const pendingSaveRejectRef = useRef<((error: unknown) => void) | null>(null);

    const handleMessage = useCallback((data: WSMessage) => {
        switch (data.type) {
            case "system_config":
                if ((data.config as Record<string, unknown>)?.agents) {
                    setAgents((data.config as Record<string, unknown>).agents as Agent[]);
                }
                break;

            case "agent_registered":
                setAgents(prev => {
                    const existing = prev.find(a => a.id === data.agent_id);
                    if (existing) return prev;
                    return [...prev, {
                        id: data.agent_id as string,
                        name: data.name as string,
                        tools: (data.tools as string[]) || [],
                        status: "connected"
                    } as Agent];
                });
                break;

            case "agent_list":
                setAgents((data.agents as Agent[]) || []);
                break;

            case "chat_status":
                setChatStatus({
                    status: (data.status as "idle" | "thinking" | "executing" | "done") || "idle",
                    message: (data.message as string) || ""
                });
                break;

            case "ui_render":
                // Don't auto-clear chat status here — the backend sends
                // an explicit chat_status: "done" when processing is complete.
                setUiComponents((data.components as Record<string, unknown>[]) || []);
                setMessages(prev => [
                    ...prev,
                    { role: "assistant", content: data.components || [] }
                ]);
                break;

            case "ui_update":
                setUiComponents((data.components as Record<string, unknown>[]) || []);
                break;

            case "ui_append":
                setUiComponents(prev => [...prev, ...((data.components as Record<string, unknown>[]) || [])]);
                break;

            case "history_list":
                setChatHistory((data.chats as ChatSession[]) || []);
                break;

            case "chat_created":
                setActiveChatId((data.payload as Record<string, unknown>).chat_id as string);

                // Only clear messages and UI if this wasn't created as a side-effect of a message
                if (!(data.payload as Record<string, unknown>).from_message) {
                    setMessages([]);
                    setUiComponents([]);
                    setSavedComponents([]);
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

                    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
                        wsRef.current.send(JSON.stringify({
                            type: "ui_event",
                            action: "get_saved_components",
                            payload: { chat_id: (data.chat as Record<string, unknown>).id as string }
                        }));
                    }
                }
                break;

            // Saved components messages
            case "saved_components_list":
                if (data.components) {
                    setSavedComponents(data.components as SavedComponent[]);
                }
                break;

            case "component_saved":
                setSavedComponents(prev => [(data.component as SavedComponent), ...prev]);
                if (pendingSaveResolveRef.current) {
                    pendingSaveResolveRef.current(true);
                    pendingSaveResolveRef.current = null;
                    pendingSaveRejectRef.current = null;
                }
                break;

            case "component_deleted":
                if (data.component_id) {
                    setSavedComponents((prev) => prev.filter(c => c.id !== data.component_id));
                }
                break;

            case "combine_status":
                setIsCombining(true);
                setCombineError(null);
                break;

            case "components_combined":
                setIsCombining(false);
                setCombineError(null);
                if (data.new_components) {
                    // Prepend new combined components and remove deleted ones if any
                    setSavedComponents(prev => {
                        let filtered = prev;
                        if (data.removed_ids) {
                            filtered = prev.filter(c => !(data.removed_ids as string[]).includes(c.id));
                        }
                        return [...(data.new_components as SavedComponent[]), ...filtered];
                    });
                }
                break;
            case "components_condensed":
                setIsCombining(false);
                setCombineError(null);
                // Remove old components and add new ones
                setSavedComponents(prev => {
                    const removedIds = new Set((data.removed_ids as string[]) || []);
                    const remaining = prev.filter(c => !removedIds.has(c.id as string));
                    return [...((data.new_components as SavedComponent[]) || []), ...remaining];
                });
                break;

            case "combine_error":
                setIsCombining(false);
                setCombineError((data.error as string) || "Failed to combine components");
                console.error("Combine error:", data.error);
                // Auto-clear error after 5 seconds
                setTimeout(() => setCombineError(null), 5000);
                break;

            default:
            // console.log("Unknown message type:", data.type, data);
        }
    }, [setActiveChatId]);

    const connect = useCallback(() => {
        if (!token) return; // Don't connect without token

        try {
            const ws = new WebSocket(url);
            wsRef.current = ws;

            ws.onopen = () => {
                const currentChatId = activeChatIdRef.current;
                // console.log('WebSocket connection opened - readyState:', ws.readyState, 'activeChatId:', currentChatId, 'timestamp:', new Date().toISOString());
                setIsConnected(true);
                setChatStatus({ status: "idle", message: "" });
                // Send RegisterUI with token
                ws.send(JSON.stringify({
                    type: "register_ui",
                    token: token,
                    capabilities: ["render", "stream"],
                    session_id: `ui-${Date.now()}`
                }));
                // Fetch history
                ws.send(JSON.stringify({
                    type: "ui_event",
                    action: "get_history",
                    payload: {}
                }));

                // If we have an active chat ID, reload it after reconnection
                if (currentChatId) {
                    // console.log('Reloading active chat after reconnection:', currentChatId);
                    setTimeout(() => {
                        // console.log('Attempting to reload chat - WebSocket readyState:', ws.readyState, 'activeChatId still:', currentChatId);
                        if (ws.readyState === WebSocket.OPEN) {
                            ws.send(JSON.stringify({
                                type: "ui_event",
                                action: "load_chat",
                                payload: { chat_id: currentChatId }
                            }));
                            // console.log('Chat reload request sent for:', currentChatId);
                        } else {
                            console.error('WebSocket not OPEN when trying to reload chat. State:', ws.readyState);
                        }
                    }, 500); // Small delay to ensure registration is processed
                }
            };

            ws.onmessage = (event) => {
                try {
                    const data: WSMessage = JSON.parse(event.data);
                    handleMessage(data);
                } catch (e) {
                    console.error("Failed to parse WS message:", e);
                }
            };

            ws.onclose = () => {
                // console.log('WebSocket connection closed:', event.code, event.reason);
                setIsConnected(false);
                // Auto-reconnect after 3s
                reconnectTimer.current = window.setTimeout(() => {
                    // Safe reference check for connect, implemented below
                    const c = wsRef.current as WebSocket & { _reconnect?: () => void };
                    if (c && c._reconnect) c._reconnect();
                }, 3000);
            };

            ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                ws.close();
            };

            // Circular reconnect is handled by the useEffect below
        } catch (e) {
            console.error("WebSocket connection failed:", e);
            reconnectTimer.current = window.setTimeout(() => {
                // Use the _reconnect function assigned by the useEffect below
                const c = wsRef.current as WebSocket & { _reconnect?: () => void };
                if (c && c._reconnect) c._reconnect();
            }, 3000);
        }
    }, [url, token, handleMessage, userId]); // Added handleMessage dependency

    // Also update previously bound reconnect loop
    useEffect(() => {
        if (wsRef.current) {
            // Assign the connect function to _reconnect property for circular reference
            // This allows onclose/onerror to call the latest 'connect' without stale closures
            (wsRef.current as WebSocket & { _reconnect?: () => void })._reconnect = connect;
        }
    }, [connect]);



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

    const loadChat = useCallback((chatId: string) => {
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
        wsRef.current.send(JSON.stringify({
            type: "ui_event",
            action: "load_chat",
            payload: { chat_id: chatId }
        }));
    }, []);

    const createNewChat = useCallback(() => {
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
        wsRef.current.send(JSON.stringify({
            type: "ui_event",
            action: "new_chat",
            payload: {}
        }));
    }, []);

    const discoverAgents = useCallback(() => {
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
        wsRef.current.send(JSON.stringify({
            type: "ui_event",
            action: "discover_agents",
            payload: {}
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
        wsRef.current.send(JSON.stringify({
            type: "ui_event",
            action: "condense_components",
            payload: { component_ids: componentIds }
        }));
    }, []);

    useEffect(() => {
        connect();
        return () => {
            if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
            wsRef.current?.close();
        };
    }, [connect]);

    return {
        isConnected,
        agents,
        chatStatus,
        uiComponents,
        messages,
        sendMessage,
        discoverAgents,
        activeChatId,
        chatHistory,
        loadChat,
        createNewChat,
        savedComponents,
        saveComponent,
        deleteSavedComponent,
        loadSavedComponents,
        combineComponents,
        condenseComponents,
        isCombining,
        combineError
    };
}
