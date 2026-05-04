/**
 * App — Root component with login gate and dashboard.
 */
import { useEffect, useState } from "react";
import { useSmartAuth as useAuth } from "./hooks/useSmartAuth";
import LoginScreen from "./components/LoginScreen";
import DashboardLayout from "./components/DashboardLayout";
import SDUICanvas from "./components/SDUICanvas";
import FloatingChatPanel from "./components/FloatingChatPanel";
import AuditLogPanel from "./components/audit/AuditLogPanel";
import LlmSettingsPanel from "./components/llm/LlmSettingsPanel";
import { useWebSocket } from "./hooks/useWebSocket";
import { AlertCircle } from "lucide-react";
import { Toaster } from "sonner";
import { ThemeProvider } from "./contexts/ThemeContext";
import { AgentPermissionProvider } from "./contexts/AgentPermissionContext";
import { FeedbackProvider } from "./components/feedback/FeedbackContext";
import FeedbackAdminPanel from "./components/feedback/FeedbackAdminPanel";
import { OnboardingProvider, useOnboarding } from "./components/onboarding/OnboardingContext";
import { TooltipProvider } from "./components/onboarding/TooltipProvider";
import { TutorialOverlay } from "./components/onboarding/TutorialOverlay";
import { TutorialAdminPanel } from "./components/onboarding/TutorialAdminPanel";
import UserGuidePanel from "./components/guide/UserGuidePanel";

import { WS_URL } from "./config";

// `Shell` is declared at module scope (not inside `App`) so its function
// reference is stable across `App` re-renders. If it were declared inside
// `App`, every render would produce a new `Shell` type, and React would
// unmount/remount the entire subtree — wiping `DashboardLayout`'s local
// state (e.g., `agentsModalOpen`, `permModalAgent`) every time a WS
// message updated App-level state. That manifested as the Agents modal
// closing the moment a user clicked an agent card.
type ShellProps = {
  ws: ReturnType<typeof useWebSocket>;
  auth: { accessToken: string | undefined; signOut: () => void };
  user: { email: string; isAdmin: boolean };
  openers: {
    audit: () => void;
    llm: () => void;
    feedback: (() => void) | undefined;
    tutorial: (() => void) | undefined;
    guide: () => void;
  };
};

function Shell({ ws, auth, user, openers }: ShellProps) {
  const onboarding = useOnboarding();
  // Feature 008-llm-text-only-chat: bumped by the chat panel's
  // text-only banner CTA to ask DashboardLayout to open its
  // agents modal. A monotonically increasing key is the simplest
  // way to deliver "open it, again, even if it's already been
  // opened-then-closed once".
  const [agentsModalRequestKey, setAgentsModalRequestKey] = useState<number | undefined>(undefined);
  return (
    <>
      <DashboardLayout
        agents={ws.agents}
        isConnected={ws.isConnected}
        connectionState={ws.connectionState}
        onLogout={auth.signOut}
        chatHistory={ws.chatHistory}
        activeChatId={ws.activeChatId}
        onLoadChat={ws.loadChat}
        onNewChat={ws.createNewChat}
        onDeleteChat={ws.deleteChat}
        isAdmin={user.isAdmin}
        accessToken={auth.accessToken}
        agentPermissions={ws.agentPermissions}
        onGetAgentPermissions={ws.getAgentPermissions}
        onSetAgentPermissions={ws.setAgentPermissions}
        agentCredentialKeys={ws.agentCredentialKeys}
        onFetchAgentCredentials={ws.fetchAgentCredentials}
        onSaveAgentCredentials={ws.saveAgentCredentials}
        onDeleteAgentCredential={ws.deleteAgentCredential}
        onStartOAuthFlow={ws.startOAuthFlow}
        userEmail={user.email}
        onSetAgentVisibility={ws.setAgentVisibility}
        onRegisterExternalAgent={ws.registerExternalAgent}
        onDiscoverAgents={ws.discoverAgents}
        onOpenAuditLog={openers.audit}
        onOpenLlmSettings={openers.llm}
        onOpenFeedbackAdmin={openers.feedback}
        onReplayTutorial={() => void onboarding.replay()}
        onOpenTutorialAdmin={openers.tutorial}
        onOpenUserGuide={openers.guide}
        requestOpenAgentsModalKey={agentsModalRequestKey}
      >
        <FeedbackProvider token={auth.accessToken ?? null} ws={ws.wsRef?.current ?? null} isAdmin={user.isAdmin}>
          <AgentPermissionProvider agents={ws.agents}>
            <SDUICanvas
              canvasComponents={ws.canvasComponents}
              onDeleteComponent={ws.deleteSavedComponent}
              onCombineComponents={ws.combineComponents}
              onCondenseComponents={ws.condenseComponents}
              isCombining={ws.isCombining}
              combineError={ws.combineError}
              onTablePaginate={ws.sendTablePaginate}
              onSendMessage={ws.sendMessage}
              activeChatId={ws.activeChatId}
            />
            <FloatingChatPanel
              messages={ws.messages}
              chatStatus={ws.chatStatus}
              onSendMessage={ws.sendMessage}
              onCancelTask={ws.cancelTask}
              isConnected={ws.isConnected}
              activeChatId={ws.activeChatId}
              accessToken={auth.accessToken}
              deviceCapabilities={ws.deviceCapabilities}
              toolsAvailableForUser={ws.toolsAvailableForUser}
              onOpenAgentSettings={() => setAgentsModalRequestKey(Date.now())}
            />
          </AgentPermissionProvider>
        </FeedbackProvider>
      </DashboardLayout>
      <TutorialOverlay />
    </>
  );
}

function App() {
  const auth = useAuth();
  const [auditOpen, setAuditOpen] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return new URLSearchParams(window.location.search).get("audit") === "open";
  });
  const [llmSettingsOpen, setLlmSettingsOpen] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return new URLSearchParams(window.location.search).get("llm") === "open";
  });
  const [feedbackAdminOpen, setFeedbackAdminOpen] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return new URLSearchParams(window.location.search).get("feedback") === "open";
  });
  const [tutorialAdminOpen, setTutorialAdminOpen] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return new URLSearchParams(window.location.search).get("tutorial_admin") === "open";
  });
  const [userGuideOpen, setUserGuideOpen] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return new URLSearchParams(window.location.search).get("guide") === "open";
  });

  // Keep auditOpen in sync with browser back/forward navigation
  useEffect(() => {
    if (typeof window === "undefined") return;
    const onPop = () => {
      setAuditOpen(new URLSearchParams(window.location.search).get("audit") === "open");
      setLlmSettingsOpen(new URLSearchParams(window.location.search).get("llm") === "open");
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  // Pass the token to the WebSocket hook.
  // It will only connect when token is available.
  const ws = useWebSocket(WS_URL, auth.user?.access_token);

  if (auth.isLoading) {
    return (
      <div className="min-h-screen bg-astral-bg flex items-center justify-center text-white">
        <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-astral-primary"></div>
      </div>
    );
  }

  if (auth.error) {
    return (
      <div className="min-h-screen bg-astral-bg flex items-center justify-center text-white">
        <div className="bg-red-500/10 border border-red-500/20 p-4 rounded-lg flex items-center gap-2">
          <AlertCircle size={20} className="text-red-400" />
          <span>Auth Error: {auth.error.message}</span>
        </div>
      </div>
    );
  }

  if (!auth.isAuthenticated) {
    return <LoginScreen />;
  }

  // Helper to decode JWT payload without external libraries
  const decodeJwt = (token: string) => {
    try {
      const base64Url = token.split('.')[1];
      // Add padding if needed
      let base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
      const padLength = 4 - (base64.length % 4);
      if (padLength < 4) {
        base64 += '='.repeat(padLength);
      }
      const jsonPayload = decodeURIComponent(atob(base64).split('').map(function (c) {
        return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
      }).join(''));
      return JSON.parse(jsonPayload);
    } catch (e) {
      console.error("Failed to decode JWT", e, token);
      // For mock auth, if decoding fails, return a mock payload
      if (import.meta.env.VITE_USE_MOCK_AUTH === 'true') {
        return {
          realm_access: { roles: ['admin', 'user'] },
          resource_access: { 'astral-frontend': { roles: ['admin', 'user'] } },
          sub: 'test_user',
          preferred_username: 'test_user',
          email: 'test_user@local'
        };
      }
      return null;
    }
  };

  // The OIDC profile (ID Token) doesn't always contain roles unless configured in Keycloak mappers.
  // We extract roles from the Access Token instead, where Keycloak guarantees they exist.
  const tokenPayload = auth.user?.access_token ? decodeJwt(auth.user.access_token) : null;

  const userEmail = tokenPayload?.email || auth.user?.profile?.email || "";
  const clientId = import.meta.env.VITE_KEYCLOAK_CLIENT_ID || "astral-frontend";

  const useMockAuth = import.meta.env.VITE_USE_MOCK_AUTH === 'true';

  let isUser = false;
  let isAdmin = false;

  if (useMockAuth) {
    isUser = true;
    isAdmin = true;
  } else {
    const realmRoles = tokenPayload?.realm_access?.roles || [];
    const accountRoles = tokenPayload?.resource_access?.account?.roles || [];
    const clientRoles = tokenPayload?.resource_access?.[clientId]?.roles || [];

    const roles = [...realmRoles, ...accountRoles, ...clientRoles];
    isUser = roles.includes("user");
    isAdmin = roles.includes("admin");
  }

  if (!useMockAuth && !isUser && !isAdmin) {
    return (
      <div className="min-h-screen bg-astral-bg flex flex-col items-center justify-center text-white p-6 text-center">
        <AlertCircle size={48} className="text-red-400 mb-4" />
        <h1 className="text-2xl font-bold mb-2">Unauthorized Access</h1>
        <p className="text-astral-muted mb-6">
          You do not have the required roles to access this application.
          Please contact an administrator.
        </p>
        <button
          onClick={() => void auth.signoutRedirect()}
          className="bg-astral-primary text-white px-6 py-2 rounded-lg hover:bg-astral-primary/90 transition-colors"
        >
          Sign Out
        </button>
      </div>
    );
  }

  return (
    <ThemeProvider>
      <TooltipProvider>
        <OnboardingProvider accessToken={auth.user?.access_token ?? null}>
          <Toaster
            theme="dark"
            position="top-right"
            toastOptions={{
              style: {
                background: 'rgba(15, 18, 25, 0.95)',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                color: '#e2e8f0',
                backdropFilter: 'blur(12px)',
              },
            }}
          />
          <Shell
            ws={ws}
            auth={{ accessToken: auth.user?.access_token, signOut: () => void auth.signoutRedirect() }}
            user={{ email: userEmail, isAdmin }}
            openers={{
              audit: () => setAuditOpen(true),
              llm: () => setLlmSettingsOpen(true),
              feedback: isAdmin ? () => setFeedbackAdminOpen(true) : undefined,
              tutorial: isAdmin ? () => setTutorialAdminOpen(true) : undefined,
              guide: () => setUserGuideOpen(true),
            }}
          />
          <AuditLogPanel
            open={auditOpen}
            accessToken={auth.user?.access_token}
            onClose={() => setAuditOpen(false)}
          />
          <LlmSettingsPanel
            open={llmSettingsOpen}
            accessToken={auth.user?.access_token}
            onClose={() => setLlmSettingsOpen(false)}
          />
          {isAdmin && (
            <FeedbackAdminPanel
              open={feedbackAdminOpen}
              accessToken={auth.user?.access_token ?? null}
              onClose={() => setFeedbackAdminOpen(false)}
            />
          )}
          {isAdmin && (
            <TutorialAdminPanel
              open={tutorialAdminOpen}
              accessToken={auth.user?.access_token ?? null}
              onClose={() => setTutorialAdminOpen(false)}
            />
          )}
          <UserGuidePanel
            open={userGuideOpen}
            isAdmin={isAdmin}
            onClose={() => setUserGuideOpen(false)}
          />
        </OnboardingProvider>
      </TooltipProvider>
    </ThemeProvider>
  );
}

export default App;
