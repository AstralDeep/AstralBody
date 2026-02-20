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

export interface ChatStatus {
    status: "idle" | "thinking" | "executing" | "done";
    message: string;
}

export interface WSMessage {
    type: string;
    [key: string]: any;
}

export function useWebSocket(url: string = "ws://localhost:8001", token?: string) {
    const [isConnected, setIsConnected] = useState(false);
    const [agents, setAgents] = useState<Agent[]>([]);
    const [chatStatus, setChatStatus] = useState<ChatStatus>({ status: "idle", message: "" });
    const [uiComponents, setUiComponents] = useState<any[]>([]);
    const [messages, setMessages] = useState<{ role: string; content: any }[]>([]);
    const [chatHistory, setChatHistory] = useState<ChatSession[]>([]);
    const [activeChatIdState, setActiveChatIdState] = useState<string | null>(null);
    const activeChatIdRef = useRef<string | null>(null);

    const setActiveChatId = useCallback((id: string | null) => {
        activeChatIdRef.current = id;
        setActiveChatIdState(id);
    }, []);

    const activeChatId = activeChatIdState;
    const [savedComponents, setSavedComponents] = useState<any[]>([]);
    const [isCombining, setIsCombining] = useState(false);
    const [combineError, setCombineError] = useState<string | null>(null);
    const wsRef = useRef<WebSocket | null>(null);
    const reconnectTimer = useRef<number | null>(null);
    const pendingSaveResolveRef = useRef<((value: boolean) => void) | null>(null);
    const pendingSaveRejectRef = useRef<((error: any) => void) | null>(null);

    const connect = useCallback(() => {
        if (!token) return; // Don't connect without token

        try {
            const ws = new WebSocket(url);
            wsRef.current = ws;

            ws.onopen = () => {
                const currentChatId = activeChatIdRef.current;
                console.log('WebSocket connection opened - readyState:', ws.readyState, 'activeChatId:', currentChatId, 'timestamp:', new Date().toISOString());
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
                    console.log('Reloading active chat after reconnection:', currentChatId);
                    setTimeout(() => {
                        console.log('Attempting to reload chat - WebSocket readyState:', ws.readyState, 'activeChatId still:', currentChatId);
                        if (ws.readyState === WebSocket.OPEN) {
                            ws.send(JSON.stringify({
                                type: "ui_event",
                                action: "load_chat",
                                payload: { chat_id: currentChatId }
                            }));
                            console.log('Chat reload request sent for:', currentChatId);
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

            ws.onclose = (event) => {
                console.log('WebSocket connection closed:', event.code, event.reason);
                setIsConnected(false);
                // Auto-reconnect after 3s
                reconnectTimer.current = window.setTimeout(connect, 3000);
            };

            ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                ws.close();
            };
        } catch (e) {
            console.error("WebSocket connection failed:", e);
            reconnectTimer.current = window.setTimeout(connect, 3000);
        }
    }, [url, token]); // Removed activeChatId from dependencies to prevent reconnect on chat creation

    const handleMessage = (data: WSMessage) => {
        switch (data.type) {
            case "system_config":
                if (data.config?.agents) {
                    setAgents(data.config.agents);
                }
                break;

            case "agent_registered":
                setAgents(prev => {
                    const existing = prev.find(a => a.id === data.agent_id);
                    if (existing) return prev;
                    return [...prev, {
                        id: data.agent_id,
                        name: data.name,
                        tools: data.tools || [],
                        status: "connected"
                    }];
                });
                break;

            case "agent_list":
                setAgents(data.agents || []);
                break;

            case "chat_status":
                setChatStatus({
                    status: data.status || "idle",
                    message: data.message || ""
                });
                break;

            case "ui_render":
                // Don't auto-clear chat status here — the backend sends
                // an explicit chat_status: "done" when processing is complete.
                setUiComponents(data.components || []);
                setMessages(prev => [
                    ...prev,
                    { role: "assistant", content: data.components || [] }
                ]);
                break;

            case "ui_update":
                setUiComponents(data.components || []);
                break;

            case "ui_append":
                setUiComponents(prev => [...prev, ...(data.components || [])]);
                break;

            case "history_list":
                setChatHistory(data.chats || []);
                break;

            case "chat_created":
                setActiveChatId(data.payload.chat_id);
                setMessages([]);
                setUiComponents([]);
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
                    setActiveChatId(data.chat.id);
                    // Convert stored messages to UI format if needed
                    // For now, we just load them into the messages array
                    // You might need to parse "content" if it's stored as a string or handle UI components
                    const loadedMessages = data.chat.messages.map((m: any) => ({
                        role: m.role,
                        content: m.content
                    }));
                    setMessages(loadedMessages);

                    // If the last message was from assistant, we might want to restore UI components?
                    // For simplicity, we just clear current UI components unless we reconstruct them
                    setUiComponents([]);
                }
                break;

            // Saved components messages
            case "saved_components_list":
                setSavedComponents(data.components || []);
                break;

            case "component_saved":
                setSavedComponents(prev => [data.component, ...prev]);
                if (pendingSaveResolveRef.current) {
                    pendingSaveResolveRef.current(true);
                    pendingSaveResolveRef.current = null;
                    pendingSaveRejectRef.current = null;
                }
                break;

            case "component_deleted":
                setSavedComponents(prev =>
                    prev.filter(comp => comp.id !== data.component_id)
                );
                break;

            case "component_save_error":
                console.error("Failed to save component:", data.error);
                if (pendingSaveRejectRef.current) {
                    pendingSaveRejectRef.current(new Error(data.error || 'Failed to save component'));
                    pendingSaveResolveRef.current = null;
                    pendingSaveRejectRef.current = null;
                }
                break;

            case "combine_status":
                setIsCombining(true);
                setCombineError(null);
                break;

            case "components_combined":
            case "components_condensed":
                setIsCombining(false);
                setCombineError(null);
                // Remove old components and add new ones
                setSavedComponents(prev => {
                    const removedIds = new Set(data.removed_ids || []);
                    const remaining = prev.filter(c => !removedIds.has(c.id));
                    return [...(data.new_components || []), ...remaining];
                });
                break;

            case "combine_error":
                setIsCombining(false);
                setCombineError(data.error || "Failed to combine components");
                console.error("Combine error:", data.error);
                // Auto-clear error after 5 seconds
                setTimeout(() => setCombineError(null), 5000);
                break;

            default:
                console.log("Unknown message type:", data.type, data);
        }
    };

    const sendMessage = useCallback((message: string) => {
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

        setMessages(prev => [...prev, { role: "user", content: message }]);
        setChatStatus({ status: "thinking", message: "Processing..." });

        wsRef.current.send(JSON.stringify({
            type: "ui_event",
            action: "chat_message",
            session_id: activeChatId || undefined,
            payload: {
                message,
                chat_id: activeChatId
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
    const saveComponent = useCallback(async (componentData: any, componentType: string, title?: string): Promise<boolean> => {
        console.log('saveComponent called:', { componentType, title, wsRefCurrent: wsRef.current, wsReadyState: wsRef.current?.readyState, activeChatId, timestamp: new Date().toISOString() });

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

        console.log('Save request sent for component:', componentType, 'to chat:', activeChatId);
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
