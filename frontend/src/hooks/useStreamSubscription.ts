/**
 * Convenience hook for auto-subscribing to a live-streaming MCP tool.
 *
 * Subscribes on mount, unsubscribes on unmount.
 * Returns the latest stream payload or null if no data yet.
 */
import { useEffect } from "react";

interface StreamPayload {
    components: Record<string, unknown>[];
    data: Record<string, unknown>;
    timestamp: number;
}

interface StreamHookDeps {
    streamData: Record<string, StreamPayload>;
    subscribeStream: (toolName: string, intervalSeconds?: number, params?: Record<string, unknown>) => void;
    unsubscribeStream: (toolName: string) => void;
}

export function useStreamSubscription(
    toolName: string,
    deps: StreamHookDeps,
    intervalSeconds: number = 2,
    params: Record<string, unknown> = {},
): StreamPayload | null {
    const { streamData, subscribeStream, unsubscribeStream } = deps;

    useEffect(() => {
        subscribeStream(toolName, intervalSeconds, params);
        return () => unsubscribeStream(toolName);
    }, [toolName, intervalSeconds, subscribeStream, unsubscribeStream]);

    return streamData[toolName] ?? null;
}
