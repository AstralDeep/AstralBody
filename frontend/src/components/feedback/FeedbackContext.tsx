/**
 * FeedbackContext — wraps the dashboard so any descendant component
 * (notably DynamicRenderer's per-component overlays) can access the
 * authenticated token, the live WebSocket, and the user's admin flag
 * without prop-drilling through every renderer signature.
 */
import { createContext, useContext, useMemo, type ReactNode } from "react";

interface FeedbackContextValue {
    token: string | null;
    ws: WebSocket | null;
    isAdmin: boolean;
}

const defaultValue: FeedbackContextValue = {
    token: null,
    ws: null,
    isAdmin: false,
};

const FeedbackContext = createContext<FeedbackContextValue>(defaultValue);

export interface FeedbackProviderProps {
    token: string | null;
    ws: WebSocket | null;
    isAdmin?: boolean;
    children: ReactNode;
}

export function FeedbackProvider({ token, ws, isAdmin = false, children }: FeedbackProviderProps) {
    const value = useMemo<FeedbackContextValue>(
        () => ({ token, ws, isAdmin }),
        [token, ws, isAdmin],
    );
    return <FeedbackContext.Provider value={value}>{children}</FeedbackContext.Provider>;
}

export function useFeedbackContext(): FeedbackContextValue {
    return useContext(FeedbackContext);
}
