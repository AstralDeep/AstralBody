/**
 * App — Root component with login gate and dashboard.
 */
import { useSmartAuth as useAuth } from "./hooks/useSmartAuth";
import LoginScreen from "./components/LoginScreen";
import DashboardLayout from "./components/DashboardLayout";
import ChatInterface from "./components/ChatInterface";
import { useWebSocket } from "./hooks/useWebSocket";
import { AlertCircle } from "lucide-react";

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
    loadSavedComponents,
    combineComponents,
    condenseComponents,
    isCombining,
    combineError
  } = useWebSocket(
    "ws://localhost:8001",
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

  return (
    <DashboardLayout
      agents={agents}
      isConnected={isConnected}
      onLogout={() => void auth.signoutRedirect()}
      chatHistory={chatHistory}
      activeChatId={activeChatId}
      onLoadChat={loadChat}
      onNewChat={createNewChat}
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
      />
    </DashboardLayout>
  );
}

export default App;
