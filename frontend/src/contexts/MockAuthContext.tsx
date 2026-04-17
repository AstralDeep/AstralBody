import { createContext, useContext, useState, type ReactNode } from 'react';

interface User {
    access_token: string;
    user_id: string;
    profile: {
        preferred_username: string;
        email?: string;
    };
}

interface MockAuthContextType {
    isAuthenticated: boolean;
    isLoading: boolean;
    error: Error | null;
    user: User | null;
    signinRedirect: () => Promise<void>;
    signoutRedirect: () => Promise<void>;
}

const MockAuthContext = createContext<MockAuthContextType | undefined>(undefined);

export function MockAuthProvider({ children }: { children: ReactNode }) {
    const [isAuthenticated, setIsAuthenticated] = useState<boolean>(() => {
        // For testing, always authenticate
        return true;
    });
    const [isLoading, setIsLoading] = useState<boolean>(false);

    const signinRedirect = async () => {
        setIsLoading(true);
        // Simulate network delay
        setTimeout(() => {
            localStorage.setItem("mock_is_authenticated", "true");
            setIsAuthenticated(true);
            setIsLoading(false);
        }, 500);
    };

    const signoutRedirect = async () => {
        setIsLoading(true);
        setTimeout(() => {
            localStorage.removeItem("mock_is_authenticated");
            setIsAuthenticated(false);
            setIsLoading(false);
        }, 300);
    };

    const user = isAuthenticated ? {
        access_token: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyZWFsbV9hY2Nlc3MiOnsicm9sZXMiOlsiYWRtaW4iLCJ1c2VyIl19LCJyZXNvdXJjZV9hY2Nlc3MiOnsiYXN0cmFsLWZyb250ZW5kIjp7InJvbGVzIjpbImFkbWluIiwidXNlciJdfX0sInN1YiI6InRlc3RfdXNlciIsInByZWZlcnJlZF91c2VybmFtZSI6InRlc3RfdXNlciIsImVtYWlsIjoidGVzdF91c2VyQGxvY2FsIn0.fake-signature-ignore",
        user_id: "test_user",
        profile: {
            preferred_username: "test_user",
            email: "test_user@local"
        }
    } : null;

    return (
        <MockAuthContext.Provider value={{
            isAuthenticated,
            isLoading,
            error: null,
            user,
            signinRedirect,
            signoutRedirect
        }}>
            {children}
        </MockAuthContext.Provider>
    );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useMockAuth() {
    const context = useContext(MockAuthContext);
    if (!context) {
        throw new Error("useMockAuth must be used within a MockAuthProvider");
    }
    return context;
}
