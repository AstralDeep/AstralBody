
import { useAuth as useOidcAuth } from "react-oidc-context";
import { useMockAuth } from "../contexts/MockAuthContext";

const useMock = import.meta.env.VITE_USE_MOCK_AUTH === 'true';
console.log("useSmartAuth Debug:", { VITE_USE_MOCK_AUTH: import.meta.env.VITE_USE_MOCK_AUTH, useMock });

export const useSmartAuth = useMock ? useMockAuth : useOidcAuth;
