import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { AuthProvider } from 'react-oidc-context'
import { MockAuthProvider } from './contexts/MockAuthContext'
import './index.css'
import App from './App.tsx'

// Feature 016-persistent-login (T015): the OIDC configuration lives in
// its own module so integration tests can import the exact same object
// production uses. The headline change vs pre-feature-016 is that
// userStore/stateStore are wired to localStorage (via SafeWebStorageStateStore)
// so the user remains signed in across full browser/app restarts.
import { oidcConfig } from './auth/oidcConfig'
import { checkOnLaunch } from './auth/persistentLogin'
import { initRevocationQueue, REVOCATION_QUEUED_OFFLINE_EVENT } from './auth/revocationQueue'
import { PERSISTENCE_DISABLED_EVENT } from './auth/safeStorageStore'

const useMock = import.meta.env.VITE_USE_MOCK_AUTH === 'true';

// Feature 016 (T017 / FR-013): run the launch-time sanity check BEFORE
// the AuthProvider mounts. This clears the OIDC user record on:
//   - 365-day hard-max exceeded
//   - deployment_origin mismatch
//   - unknown anchor schema_version (future-proof migration)
// In any of these cases the user lands on the login screen cleanly
// instead of attempting to silently resume a credential we know we
// must reject.
if (!useMock) {
  try {
    checkOnLaunch();
  } catch {
    // Defensive — never block app start on this guard.
  }
}

// Feature 016 (FR-009b): kick off the revocation queue so pending
// sign-out revocations from a prior offline session drain on the next
// `online` event. No-op in mock-auth tests.
if (!useMock) {
  try {
    initRevocationQueue();
  } catch {
    /* defensive */
  }
}

// Feature 016 (FR-006 / FR-009b): the persistence-disabled and
// revocation-queued-offline events can fire BEFORE React mounts (for
// example, during onSigninCallback). Stash them in sessionStorage
// here so App.tsx can replay them through sonner once the Toaster is
// mounted.
if (typeof window !== 'undefined') {
  try {
    window.addEventListener(PERSISTENCE_DISABLED_EVENT, () => {
      try {
        window.sessionStorage.setItem('astralbody.toast.persistenceDisabled', '1');
      } catch {
        /* sessionStorage may itself be unavailable; nothing more we can do */
      }
    });
    window.addEventListener(REVOCATION_QUEUED_OFFLINE_EVENT, () => {
      try {
        window.sessionStorage.setItem('astralbody.toast.revocationQueuedOffline', '1');
      } catch {
        /* defensive */
      }
    });
  } catch {
    /* defensive */
  }
}

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


