import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { AuthProvider } from 'react-oidc-context'
import { MockAuthProvider } from './contexts/MockAuthContext'
import './index.css'
import App from './App.tsx'

const BFF_URL = import.meta.env.VITE_BFF_URL || 'http://localhost:8002';
const AUTHORITY = import.meta.env.VITE_KEYCLOAK_AUTHORITY;

const oidcConfig = {
  authority: AUTHORITY,
  client_id: import.meta.env.VITE_KEYCLOAK_CLIENT_ID,
  redirect_uri: window.location.origin,
  // Provide full OIDC metadata so discovery doesn't override our custom token_endpoint.
  // All endpoints point at Keycloak except token_endpoint which goes through our BFF.
  metadata: {
    issuer: AUTHORITY,
    authorization_endpoint: `${AUTHORITY}/protocol/openid-connect/auth`,
    token_endpoint: `${BFF_URL}/auth/token`,  // ← BFF proxy (injects client_secret server-side)
    userinfo_endpoint: `${AUTHORITY}/protocol/openid-connect/userinfo`,
    end_session_endpoint: `${AUTHORITY}/protocol/openid-connect/logout`,
    jwks_uri: `${AUTHORITY}/protocol/openid-connect/certs`,
    revocation_endpoint: `${AUTHORITY}/protocol/openid-connect/revoke`,
  },
  onSigninCallback: () => {
    window.history.replaceState({}, document.title, window.location.pathname)
  }
}

const useMock = import.meta.env.VITE_USE_MOCK_AUTH === 'true';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {useMock ? (
      <MockAuthProvider>
        <App />
      </MockAuthProvider>
    ) : (
      <AuthProvider {...oidcConfig}>
        <App />
      </AuthProvider>
    )}
  </StrictMode>,
)


