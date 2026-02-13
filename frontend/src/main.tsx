import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { AuthProvider } from 'react-oidc-context'
import { MockAuthProvider } from './contexts/MockAuthContext'
import './index.css'
import App from './App.tsx'

const oidcConfig = {
  authority: import.meta.env.VITE_KEYCLOAK_AUTHORITY,
  client_id: import.meta.env.VITE_KEYCLOAK_CLIENT_ID,
  redirect_uri: window.location.origin,
  onSigninCallback: () => {
    window.history.replaceState({}, document.title, window.location.pathname)
  }
}

const useMock = import.meta.env.VITE_USE_MOCK_AUTH === 'true';

console.log("Environment Debug:", {
  VITE_USE_MOCK_AUTH: import.meta.env.VITE_USE_MOCK_AUTH,
  useMock,
  authority: import.meta.env.VITE_KEYCLOAK_AUTHORITY
});

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
