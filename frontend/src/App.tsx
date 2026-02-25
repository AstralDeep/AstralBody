/**
 * App — Root component with login gate and dashboard.
 */
import { useSmartAuth as useAuth } from "./hooks/useSmartAuth";
import LoginScreen from "./components/LoginScreen";
import DashboardLayout from "./components/DashboardLayout";
import ChatInterface from "./components/ChatInterface";
import { useWebSocket } from "./hooks/useWebSocket";
import { AlertCircle } from "lucide-react";

import { WS_URL } from "./config";

function App() {
  const auth = useAuth();

  // Pass the token to the WebSocket hook.
  // It will only connect when token is available.
  const {
    isConnected,
    agents,
    chatStatus,
    messages,
    sendMessage,
    activeChatId,
    chatHistory,
    loadChat,
    createNewChat,
    savedComponents,
    saveComponent,
    deleteSavedComponent,
    combineComponents,
    condenseComponents,
    isCombining,
    combineError
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
          sub: 'dev-user-id',
          preferred_username: 'DevUser'
        };
      }
      return null;
    }
  };

  // The OIDC profile (ID Token) doesn't always contain roles unless configured in Keycloak mappers.
  // We extract roles from the Access Token instead, where Keycloak guarantees they exist.
  const tokenPayload = auth.user?.access_token ? decodeJwt(auth.user.access_token) : null;

  const clientId = import.meta.env.VITE_KEYCLOAK_CLIENT_ID || "astral-frontend";

  // For mock auth, always return admin and user roles
  const useMockAuth = import.meta.env.VITE_USE_MOCK_AUTH === 'true';
  
  // Debug: log environment variable value
  console.log('Environment debug:', {
    VITE_USE_MOCK_AUTH: import.meta.env.VITE_USE_MOCK_AUTH,
    VITE_KEYCLOAK_CLIENT_ID: import.meta.env.VITE_KEYCLOAK_CLIENT_ID,
    useMockAuth
  });
  
  let roles: string[] = [];
  let isUser = false;
  let isAdmin = false;
  
  if (useMockAuth) {
    // Mock auth always has admin and user roles
    console.log('Using mock auth - bypassing role checks');
    roles = ['admin', 'user'];
    isUser = true;
    isAdmin = true;
  } else {
    // Real auth: extract roles from token
    console.log('Using real auth - extracting roles from token');
    const realmRoles = tokenPayload?.realm_access?.roles || [];
    const accountRoles = tokenPayload?.resource_access?.account?.roles || [];
    const clientRoles = tokenPayload?.resource_access?.[clientId]?.roles || [];
    
    roles = [...realmRoles, ...accountRoles, ...clientRoles];
    isUser = roles.includes("user");
    isAdmin = roles.includes("admin");
  }

  // Debug logging
  console.log('Auth debug:', {
    useMockAuth,
    tokenPayload,
    clientId,
    roles,
    isUser,
    isAdmin,
    hasToken: !!auth.user?.access_token
  });
  
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
    <DashboardLayout
      agents={agents}
      isConnected={isConnected}
      onLogout={() => void auth.signoutRedirect()}
      chatHistory={chatHistory}
      activeChatId={activeChatId}
      onLoadChat={loadChat}
      onNewChat={createNewChat}
      isAdmin={isAdmin}
      accessToken={auth.user?.access_token}
    >
      <ChatInterface
        messages={messages}
        chatStatus={chatStatus}
        onSendMessage={sendMessage}
        isConnected={isConnected}
        activeChatId={activeChatId}
        savedComponents={savedComponents}
        onSaveComponent={saveComponent}
        onDeleteSavedComponent={deleteSavedComponent}
        onCombineComponents={combineComponents}
        onCondenseComponents={condenseComponents}
        isCombining={isCombining}
        combineError={combineError}
        accessToken={auth.user?.access_token}
      />
    </DashboardLayout>
  );
}

export default App;
