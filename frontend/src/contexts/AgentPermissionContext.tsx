import { createContext, useContext, useCallback } from "react";
import type { Agent } from "../hooks/useWebSocket";

interface AgentPermissionContextValue {
    isToolAllowed: (agentId: string, toolName: string) => boolean;
}

const AgentPermissionContext = createContext<AgentPermissionContextValue>({
    isToolAllowed: () => true,
});

export function AgentPermissionProvider({ agents, children }: { agents: Agent[]; children: React.ReactNode }) {
    const isToolAllowed = useCallback((agentId: string, toolName: string): boolean => {
        if (!agentId) return true; // no source metadata = system component, always allow
        const agent = agents.find(a => a.id === agentId);
        if (!agent) return true; // agent not found, allow by default

        // Check direct per-tool permission
        if (agent.permissions && toolName in agent.permissions) {
            return agent.permissions[toolName];
        }
        // Check scope-level permission
        if (agent.tool_scope_map && agent.scopes && toolName in agent.tool_scope_map) {
            const scope = agent.tool_scope_map[toolName];
            return agent.scopes[scope] !== false;
        }
        return true;
    }, [agents]);

    return (
        <AgentPermissionContext.Provider value={{ isToolAllowed }}>
            {children}
        </AgentPermissionContext.Provider>
    );
}

export function useAgentPermissions() {
    return useContext(AgentPermissionContext);
}
