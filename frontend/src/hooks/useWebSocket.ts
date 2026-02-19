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
    const [activeChatId, setActiveChatId] = useState<string | null>(null);
    const [savedComponents, setSavedComponents] = useState<any[]>([]);
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
                setIsConnected(false);
                // Auto-reconnect after 3s
                reconnectTimer.current = window.setTimeout(connect, 3000);
            };

            ws.onerror = () => {
                ws.close();
            };
        } catch (e) {
            console.error("WebSocket connection failed:", e);
            reconnectTimer.current = window.setTimeout(connect, 3000);
        }
    }, [url, token]);

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
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN || !activeChatId) {
            throw new Error('WebSocket not connected or no active chat');
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
                    reject(new Error('Save request timed out'));
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
        loadSavedComponents
    };
}
