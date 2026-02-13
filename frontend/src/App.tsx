/**
 * App — Root component with login gate and dashboard.
 */
import { useState } from "react";
import LoginScreen from "./components/LoginScreen";
import DashboardLayout from "./components/DashboardLayout";
import ChatInterface from "./components/ChatInterface";
import { useWebSocket } from "./hooks/useWebSocket";

function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(() => {
    return localStorage.getItem("isAuthenticated") === "true";
  });
  const { isConnected, agents, chatStatus, messages, sendMessage, activeChatId, chatHistory, loadChat, createNewChat } = useWebSocket();

  if (!isLoggedIn) {
    return <LoginScreen onLogin={() => setIsLoggedIn(true)} />;
  }

  return (
    <DashboardLayout
      agents={agents}
      isConnected={isConnected}
      onLogout={() => {
        localStorage.removeItem("isAuthenticated");
        setIsLoggedIn(false);
      }}
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
      />
    </DashboardLayout>
  );
}

export default App;
