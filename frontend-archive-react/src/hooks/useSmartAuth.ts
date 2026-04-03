
import { useAuth as useOidcAuth } from "react-oidc-context";
import { useMockAuth } from "../contexts/MockAuthContext";
import { useMemo } from "react";

const useMock = import.meta.env.VITE_USE_MOCK_AUTH === 'true';
// console.log("useSmartAuth Debug:", { VITE_USE_MOCK_AUTH: import.meta.env.VITE_USE_MOCK_AUTH, useMock });

const useSmartAuthBase = useMock ? useMockAuth : useOidcAuth;

export const useSmartAuth = () => {
    const auth = useSmartAuthBase();
    const user_id = useMemo(() => {
        if (!auth.user) return null;
        if (useMock) {
            // Mock auth user has user_id field
            return (auth.user as any).user_id ?? null;
        } else {
            // OIDC user has profile.sub
            return (auth.user.profile as any)?.sub ?? null;
        }
    }, [auth.user]);
    return {
        ...auth,
        user_id,
    };
};
