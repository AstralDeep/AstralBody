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

import { WS_URL } from "./config";

function App() {
  const auth = useAuth();
  const [auditOpen, setAuditOpen] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return new URLSearchParams(window.location.search).get("audit") === "open";
  });
  const [feedbackAdminOpen, setFeedbackAdminOpen] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return new URLSearchParams(window.location.search).get("feedback") === "open";
  });
  const [tutorialAdminOpen, setTutorialAdminOpen] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return new URLSearchParams(window.location.search).get("tutorial_admin") === "open";
  });

  // Keep auditOpen in sync with browser back/forward navigation
  useEffect(() => {
    if (typeof window === "undefined") return;
    const onPop = () => {
      setAuditOpen(new URLSearchParams(window.location.search).get("audit") === "open");
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  // Pass the token to the WebSocket hook.
  // It will only connect when token is available.
  const {
    isConnected,
    connectionState,
    agents,
    chatStatus,
    messages,
    sendMessage,
    cancelTask,
    activeChatId,
    chatHistory,
    loadChat,
    createNewChat,
    deleteChat,
    canvasComponents,
    deleteSavedComponent,
    combineComponents,
    condenseComponents,
    isCombining,
    combineError,
    agentPermissions,
    getAgentPermissions,
    setAgentPermissions,
    agentCredentialKeys,
    fetchAgentCredentials,
    saveAgentCredentials,
    deleteAgentCredential,
    startOAuthFlow,
    setAgentVisibility,
    registerExternalAgent,
    discoverAgents,
    sendTablePaginate,
    deviceCapabilities,
    wsRef,
  } = useWebSocket(
    WS_URL,
    auth.user?.access_token
  );

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

  // ----- Inner shell that consumes OnboardingContext -----------------------
  function Shell() {
    const onboarding = useOnboarding();
    return (
      <>
        <DashboardLayout
          agents={agents}
          isConnected={isConnected}
          connectionState={connectionState}
          onLogout={() => void auth.signoutRedirect()}
          chatHistory={chatHistory}
          activeChatId={activeChatId}
          onLoadChat={loadChat}
          onNewChat={createNewChat}
          onDeleteChat={deleteChat}
          isAdmin={isAdmin}
          accessToken={auth.user?.access_token}
          agentPermissions={agentPermissions}
          onGetAgentPermissions={getAgentPermissions}
          onSetAgentPermissions={setAgentPermissions}
          agentCredentialKeys={agentCredentialKeys}
          onFetchAgentCredentials={fetchAgentCredentials}
          onSaveAgentCredentials={saveAgentCredentials}
          onDeleteAgentCredential={deleteAgentCredential}
          onStartOAuthFlow={startOAuthFlow}
          userEmail={userEmail}
          onSetAgentVisibility={setAgentVisibility}
          onRegisterExternalAgent={registerExternalAgent}
          onDiscoverAgents={discoverAgents}
          onOpenAuditLog={() => setAuditOpen(true)}
          onOpenFeedbackAdmin={isAdmin ? () => setFeedbackAdminOpen(true) : undefined}
          onReplayTutorial={() => void onboarding.replay()}
          onOpenTutorialAdmin={isAdmin ? () => setTutorialAdminOpen(true) : undefined}
        >
          <FeedbackProvider token={auth.user?.access_token ?? null} ws={wsRef?.current ?? null} isAdmin={isAdmin}>
            <AgentPermissionProvider agents={agents}>
              <SDUICanvas
                canvasComponents={canvasComponents}
                onDeleteComponent={deleteSavedComponent}
                onCombineComponents={combineComponents}
                onCondenseComponents={condenseComponents}
                isCombining={isCombining}
                combineError={combineError}
                onTablePaginate={sendTablePaginate}
                onSendMessage={sendMessage}
                activeChatId={activeChatId}
              />
              <FloatingChatPanel
                messages={messages}
                chatStatus={chatStatus}
                onSendMessage={sendMessage}
                onCancelTask={cancelTask}
                isConnected={isConnected}
                activeChatId={activeChatId}
                accessToken={auth.user?.access_token}
                deviceCapabilities={deviceCapabilities}
              />
            </AgentPermissionProvider>
          </FeedbackProvider>
        </DashboardLayout>
        <TutorialOverlay />
      </>
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
          <Shell />
          <AuditLogPanel
            open={auditOpen}
            accessToken={auth.user?.access_token}
            onClose={() => setAuditOpen(false)}
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
        </OnboardingProvider>
      </TooltipProvider>
    </ThemeProvider>
  );
}

export default App;
