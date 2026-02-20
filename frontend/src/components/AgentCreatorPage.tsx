import React, { useState, useRef, useEffect } from "react";
import { ArrowLeft, Bot, Send, Loader2, CheckCircle, Code, Shield, RefreshCw } from "lucide-react";
import ReactMarkdown from "react-markdown";
import Editor from "react-simple-code-editor";
import Prism from "prismjs";
import "prismjs/components/prism-python";
import "prismjs/themes/prism-tomorrow.css";
import { ProgressDisplay } from "./ProgressDisplay";
import type { ProgressState } from "../types/progress";

interface AgentCreatorPageProps {
    onBack: () => void;
    initialDraftId?: string | null;
}

interface Message {
    role: "user" | "assistant" | "system";
    content: string;
}

export default function AgentCreatorPage({ onBack, initialDraftId }: AgentCreatorPageProps) {
    const [step, setStep] = useState<"form" | "chat" | "progress" | "editor" | "testing" | "approved">("form");
    const [formData, setFormData] = useState({
        name: "",
        persona: "",
        toolsDescription: "",
        apiKeys: "",
    });

    const [messages, setMessages] = useState<Message[]>([]);
    const [inputVal, setInputVal] = useState("");
    const [isProcessing, setIsProcessing] = useState(false);
    const [sessionId, setSessionId] = useState<string | null>(null);
    const [generatedFiles, setGeneratedFiles] = useState<{tools: string, agent: string, server: string}>({
        tools: "",
        agent: "",
        server: ""
    });
    const [activeFile, setActiveFile] = useState<"tools" | "agent" | "server">("tools");
    const [testOutput, setTestOutput] = useState<string>("");
    const [pendingInstall, setPendingInstall] = useState<{ toolCallId: string, packages: string[] } | null>(null);
    
    // Progress state
    const [generationProgress, setGenerationProgress] = useState<ProgressState | null>(null);
    const [testingProgress, setTestingProgress] = useState<ProgressState | null>(null);

    const messagesEndRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages]);

    useEffect(() => {
        if (initialDraftId) {
            const fetchDraft = async () => {
                setIsProcessing(true);
                try {
                    const resp = await fetch(`${import.meta.env.VITE_AUTH_URL || "http://localhost:8002"}/api/agent-creator/session/${initialDraftId}`);
                    if (resp.ok) {
                        const data = await resp.json();
                        setFormData({
                            name: data.name || "",
                            persona: data.persona || "",
                            toolsDescription: data.tools_desc || "",
                            apiKeys: data.api_keys || "",
                        });
                        setMessages(data.messages || []);
                        setSessionId(data.session_id);
                        setStep("chat");
                    }
                } catch (err) {
                    console.error("Failed to load draft session", err);
                } finally {
                    setIsProcessing(false);
                }
            };
            fetchDraft();
        } else {
            setStep("form");
            setFormData({
                name: "",
                persona: "",
                toolsDescription: "",
                apiKeys: "",
            });
            setMessages([]);
            setSessionId(null);
            setGeneratedFiles({ tools: "", agent: "", server: "" });
            setActiveFile("tools");
            setTestOutput("");
            setPendingInstall(null);
        }
    }, [initialDraftId]);

    const handleFormSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!formData.name || !formData.persona) return;

        setIsProcessing(true);
        try {
            const resp = await fetch(`${import.meta.env.VITE_AUTH_URL || "http://localhost:8002"}/api/agent-creator/start`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(formData)
            });
            const data = await resp.json();
            setSessionId(data.session_id);
            setMessages([
                { role: "system", content: "Agent creation session started. Reviewing your requirements..." },
                { role: "assistant", content: data.initial_response || "I have received your requirements. Let's refine the tools and behavior. What else would you like this agent to be able to do?" }
            ]);
            setStep("chat");
        } catch (err) {
            console.error(err);
            alert("Failed to start agent creator session.");
        } finally {
            setIsProcessing(false);
        }
    };

    const handleSendMessage = async () => {
        if (!inputVal.trim() || !sessionId) return;
        const msg = inputVal.trim();
        setInputVal("");
        setMessages((prev) => [...prev, { role: "user", content: msg }]);

        setIsProcessing(true);
        try {
            const resp = await fetch(`${import.meta.env.VITE_AUTH_URL || "http://localhost:8002"}/api/agent-creator/chat`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ session_id: sessionId, message: msg })
            });
            const data = await resp.json();
            setMessages((prev) => [...prev, { role: "assistant", content: data.response }]);
            if (data.tool_call_id && data.required_packages && data.required_packages.length > 0) {
                setPendingInstall({ toolCallId: data.tool_call_id, packages: data.required_packages });
            }
        } catch (err) {
            console.error(err);
            setMessages((prev) => [...prev, { role: "system", content: "Error communicating with server." }]);
        } finally {
            setIsProcessing(false);
        }
    };

    const handleResolveInstall = async (approved: boolean) => {
        if (!sessionId || !pendingInstall) return;
        setIsProcessing(true);
        try {
            const resp = await fetch(`${import.meta.env.VITE_AUTH_URL || "http://localhost:8002"}/api/agent-creator/resolve-install`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    session_id: sessionId,
                    tool_call_id: pendingInstall.toolCallId,
                    approved,
                    packages: pendingInstall.packages
                })
            });
            const data = await resp.json();
            setMessages((prev) => [...prev, { role: "assistant", content: data.response }]);
        } catch (err) {
            console.error(err);
            setMessages((prev) => [...prev, { role: "system", content: "Failed to resolve installation." }]);
        } finally {
            setIsProcessing(false);
            setPendingInstall(null);
        }
    };

    const handleGenerateCode = async () => {
        if (!sessionId) return;
        
        // Reset progress state
        setGenerationProgress(null);
        setStep("progress");
        setIsProcessing(true);
        
        // Try to use the new progress endpoint first
        const useProgressEndpoint = async () => {
            try {
                const resp = await fetch(`${import.meta.env.VITE_AUTH_URL || "http://localhost:8002"}/api/agent-creator/generate-with-progress`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ session_id: sessionId })
                });
                
                if (!resp.ok) {
                    throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);
                }
                
                const reader = resp.body?.getReader();
                if (!reader) throw new Error("No response stream");
                
                const decoder = new TextDecoder();
                let resultData: any = null;
                
                while (true) {
                    const { value, done } = await reader.read();
                    if (done) break;
                    const chunk = decoder.decode(value, { stream: true });
                    
                    // Parse SSE stream
                    const lines = chunk.split('\n');
                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            try {
                                const data = JSON.parse(line.slice(6));
                                
                                // Handle progress events
                                if (data.type === 'progress') {
                                    // Update progress state
                                    setGenerationProgress({
                                        phase: data.phase,
                                        currentStep: data.step,
                                        percentage: data.percentage,
                                        message: data.message,
                                        data: data.data,
                                        startTime: Date.now() - (data.timestamp ? (Date.now() - data.timestamp * 1000) : 0),
                                        elapsedTime: data.timestamp ? (Date.now() - data.timestamp * 1000) : 0,
                                        steps: [], // Will be populated by component
                                        completedSteps: new Set(),
                                        failedSteps: new Set(),
                                        isComplete: false,
                                        isError: false
                                    });
                                } else if (data.type === 'complete') {
                                    // Generation complete
                                    resultData = data.result;
                                } else if (data.type === 'error') {
                                    // Error occurred
                                    setGenerationProgress(prev => prev ? {
                                        ...prev,
                                        isError: true,
                                        errorMessage: data.error,
                                        percentage: 100
                                    } : null);
                                    throw new Error(data.error);
                                }
                            } catch (parseError) {
                                console.error("Failed to parse SSE line", parseError, line);
                            }
                        }
                    }
                }
                
                return resultData;
            } catch (err) {
                console.error("Progress endpoint failed, falling back to legacy endpoint", err);
                throw err;
            }
        };
        
        // Fallback to legacy endpoint
        const useLegacyEndpoint = async () => {
            const resp = await fetch(`${import.meta.env.VITE_AUTH_URL || "http://localhost:8002"}/api/agent-creator/generate`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ session_id: sessionId })
            });
            return await resp.json();
        };
        
        try {
            let data;
            try {
                data = await useProgressEndpoint();
            } catch (progressErr) {
                console.log("Falling back to legacy endpoint");
                data = await useLegacyEndpoint();
            }
            
            // Handle both old and new response formats
            if (data?.files) {
                // New format: three files
                setGeneratedFiles({
                    tools: data.files.tools || "",
                    agent: data.files.agent || "",
                    server: data.files.server || ""
                });
                setStep("editor");
                
                // If fallback mode (missing agent/server), show message
                if (data.fallback) {
                    setMessages((prev) => [...prev, { 
                        role: "system", 
                        content: "Note: Agent and server files will be generated from templates. You can edit them in the editor." 
                    }]);
                }
            } else if (data?.code) {
                // Old format: single tools file
                setGeneratedFiles({
                    tools: data.code,
                    agent: "",
                    server: ""
                });
                setStep("editor");
                setMessages((prev) => [...prev, { 
                    role: "system", 
                    content: "Note: Only tools.py was generated. Agent and server files will be created from templates." 
                }]);
            } else {
                throw new Error("No code or files returned");
            }
            
            // Mark progress as complete
            setGenerationProgress(prev => prev ? {
                ...prev,
                percentage: 100,
                isComplete: true,
                message: "Code generation complete"
            } : null);
            
        } catch (err) {
            console.error(err);
            setMessages((prev) => [...prev, { role: "system", content: "Failed to generate code." }]);
            setGenerationProgress(prev => prev ? {
                ...prev,
                isError: true,
                errorMessage: err instanceof Error ? err.message : "Unknown error",
                percentage: 100
            } : null);
            
            // Return to chat after error
            setTimeout(() => {
                setStep("chat");
            }, 3000);
        } finally {
            setIsProcessing(false);
        }
    };

    const handleRunTests = async () => {
        if (!sessionId) return;
        setStep("testing");
        setTestOutput("Saving files and starting test suite...\n");
        setIsProcessing(true);
        setTestingProgress(null);

        try {
            const resp = await fetch(`${import.meta.env.VITE_AUTH_URL || "http://localhost:8002"}/api/agent-creator/test`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ 
                    session_id: sessionId, 
                    files: generatedFiles 
                })
            });

            const reader = resp.body?.getReader();
            if (!reader) throw new Error("No response stream");

            const decoder = new TextDecoder();

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                const chunk = decoder.decode(value, { stream: true });

                // Parse SSE stream
                const lines = chunk.split('\n');
                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));
                            
                            // Handle both legacy and new progress formats
                            if (data.type === 'progress') {
                                // New progress event format
                                setTestingProgress({
                                    phase: data.phase,
                                    currentStep: data.step,
                                    percentage: data.percentage,
                                    message: data.message,
                                    data: data.data,
                                    startTime: Date.now() - (data.timestamp ? (Date.now() - data.timestamp * 1000) : 0),
                                    elapsedTime: data.timestamp ? (Date.now() - data.timestamp * 1000) : 0,
                                    steps: [], // Will be populated by component
                                    completedSteps: new Set(),
                                    failedSteps: new Set(),
                                    isComplete: false,
                                    isError: false
                                });
                                setTestOutput((prev) => prev + data.message + "\n");
                            } else if (data.status === 'log') {
                                // Legacy log format
                                setTestOutput((prev) => prev + data.message + "\n");
                                // Convert to progress event
                                setTestingProgress(prev => prev ? {
                                    ...prev,
                                    message: data.message,
                                    percentage: Math.min(prev.percentage + 5, 95)
                                } : null);
                            } else if (data.status === 'success') {
                                setStep("approved");
                                setIsProcessing(false);
                                setTestingProgress(prev => prev ? {
                                    ...prev,
                                    percentage: 100,
                                    isComplete: true,
                                    message: "Testing completed successfully"
                                } : null);
                                return;
                            } else if (data.status === 'error') {
                                setTestOutput((prev) => prev + "\n[ERROR] Tests failed. Returning to chat...\n");
                                setTestingProgress(prev => prev ? {
                                    ...prev,
                                    percentage: 100,
                                    isError: true,
                                    errorMessage: data.message,
                                    message: "Testing failed"
                                } : null);
                                // Go back to chat after a brief pause
                                setTimeout(() => {
                                    setStep("chat");
                                    setMessages((prev) => [
                                        ...prev,
                                        { role: "system", content: "Agent failed testing. Please investigate the error and try again." },
                                        { role: "assistant", content: `I encountered an error during testing:\n\n\`\`\`text\n${data.message}\n\`\`\`\n\nHow should we fix this?` }
                                    ]);
                                    setIsProcessing(false);
                                }, 3000);
                                return;
                            }
                        } catch (e) {
                            console.error("Failed to parse SSE line", line);
                        }
                    }
                }
            }
        } catch (err) {
            console.error(err);
            setTestOutput((prev) => prev + "\n[ERROR] Failed to execute testing.\n");
            setTestingProgress(prev => prev ? {
                ...prev,
                percentage: 100,
                isError: true,
                errorMessage: err instanceof Error ? err.message : "Unknown error",
                message: "Testing failed"
            } : null);
            setIsProcessing(false);
            setTimeout(() => setStep("editor"), 2000);
        }
    };

    return (
        <div className="h-full flex flex-col bg-astral-bg/50">
            <header className="px-6 py-4 flex items-center justify-between border-b border-white/5 flex-shrink-0">
                <div className="flex items-center gap-3 text-white">
                    <button onClick={onBack} className="p-1 hover:bg-white/10 rounded transition-colors mr-2">
                        <ArrowLeft size={18} />
                    </button>
                    <Bot size={20} className="text-astral-primary" />
                    <h2 className="text-lg font-medium">Create New Agent</h2>
                </div>
            </header>

            <div className="flex-1 overflow-y-auto p-6 flex flex-col">
                {step === "form" && (
                    <div className="max-w-3xl mx-auto w-full">
                        <div className="bg-astral-surface border border-white/10 rounded-xl p-6 shadow-xl">
                            <h3 className="text-lg text-white font-medium mb-4 flex items-center gap-2">
                                <Shield size={18} className="text-astral-accent" />
                                Agent Parameters
                            </h3>

                            <form onSubmit={handleFormSubmit} className="space-y-5">
                                <div>
                                    <label className="block text-xs font-medium text-astral-muted mb-1">Agent Name *</label>
                                    <input
                                        required
                                        value={formData.name}
                                        onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                                        placeholder="e.g. SalesAnalyzer"
                                        className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-astral-primary"
                                    />
                                </div>

                                <div>
                                    <label className="block text-xs font-medium text-astral-muted mb-1">Persona / Description *</label>
                                    <textarea
                                        required
                                        value={formData.persona}
                                        onChange={(e) => setFormData({ ...formData, persona: e.target.value })}
                                        placeholder="Describe how the agent should behave and what its purpose is..."
                                        className="w-full h-24 bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-astral-primary resize-none"
                                    />
                                </div>

                                <div>
                                    <label className="block text-xs font-medium text-astral-muted mb-1">Required API Keys (comma separated)</label>
                                    <input
                                        value={formData.apiKeys}
                                        onChange={(e) => setFormData({ ...formData, apiKeys: e.target.value })}
                                        placeholder="e.g. GITHUB_TOKEN, WEATHER_API_KEY"
                                        className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-astral-primary"
                                    />
                                </div>

                                <div>
                                    <label className="block text-xs font-medium text-astral-muted mb-1">Tools Needed (Natural Language Description)</label>
                                    <textarea
                                        value={formData.toolsDescription}
                                        onChange={(e) => setFormData({ ...formData, toolsDescription: e.target.value })}
                                        placeholder="e.g. Needs a tool to fetch weather from an API, and a tool to plot temperature data..."
                                        className="w-full h-24 bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-astral-primary resize-none"
                                    />
                                </div>

                                <div className="pt-4 flex justify-end">
                                    <button
                                        type="submit"
                                        disabled={isProcessing}
                                        className="flex items-center gap-2 bg-astral-primary text-white px-5 py-2.5 rounded-lg hover:bg-astral-primary/90 transition-colors disabled:opacity-50"
                                    >
                                        {isProcessing ? <Loader2 size={16} className="animate-spin" /> : <Code size={16} />}
                                        Start Generation Session
                                    </button>
                                </div>
                            </form>
                        </div>
                    </div>
                )}

                {step === "chat" && (
                    <div className="flex-1 flex flex-col w-full bg-astral-surface/50 border border-white/5 rounded-xl overflow-hidden">
                        <div className="flex-1 overflow-y-auto p-4 space-y-4">
                            {messages.map((msg, idx) => (
                                <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'} w-full`}>
                                    <div className={`${msg.role === 'user' ? 'max-w-[80%]' : 'w-full'} rounded-2xl px-4 py-3 text-sm flex gap-3
                    ${msg.role === 'user' ? 'bg-astral-primary text-white' :
                                            msg.role === 'system' ? 'bg-white/5 text-astral-secondary border border-white/10' :
                                                'bg-white/10 text-white'}`}
                                    >
                                        {msg.role === 'system' && <Shield size={16} className="mt-0.5 flex-shrink-0" />}
                                        {msg.role === 'assistant' && <Bot size={16} className="mt-0.5 flex-shrink-0 text-astral-primary" />}
                                        <div className="prose prose-invert prose-sm max-w-none overflow-x-auto">
                                            <ReactMarkdown>{msg.content}</ReactMarkdown>
                                        </div>
                                    </div>
                                </div>
                            ))}
                            {pendingInstall && (
                                <div className="flex w-full mt-4 justify-start">
                                    <div className="w-full rounded-2xl p-5 border border-astral-secondary/30 bg-astral-secondary/10 flex flex-col gap-3">
                                        <div className="flex items-center gap-2 text-astral-secondary font-medium">
                                            <Shield size={16} />
                                            Package Installation Required
                                        </div>
                                        <p className="text-sm text-white">
                                            The agent needs to install the following Python packages to function correctly:
                                        </p>
                                        <div className="flex flex-wrap gap-2">
                                            {pendingInstall.packages.map(pkg => (
                                                <span key={pkg} className="px-2 py-1 bg-black/40 text-xs text-astral-muted rounded-md">{pkg}</span>
                                            ))}
                                        </div>
                                        <div className="flex gap-3 mt-2">
                                            <button
                                                onClick={() => handleResolveInstall(true)}
                                                disabled={isProcessing}
                                                className="flex items-center justify-center gap-2 bg-astral-primary text-white py-2 px-4 rounded-lg text-sm hover:bg-astral-primary/80 transition-colors disabled:opacity-50"
                                            >
                                                {isProcessing ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle size={16} />}
                                                Approve & Install
                                            </button>
                                            <button
                                                onClick={() => handleResolveInstall(false)}
                                                disabled={isProcessing}
                                                className="flex items-center justify-center bg-white/10 text-white py-2 px-4 rounded-lg text-sm hover:bg-white/20 transition-colors disabled:opacity-50"
                                            >
                                                Decline
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            )}
                            <div ref={messagesEndRef} />
                        </div>

                        <div className="p-4 border-t border-white/5 bg-astral-surface mt-auto">
                            <div className="flex items-center gap-2 mb-3">
                                <button
                                    onClick={handleGenerateCode}
                                    disabled={isProcessing}
                                    className="flex items-center gap-2 bg-astral-primary/20 text-astral-primary border border-astral-primary/30 px-4 py-2 rounded-lg hover:bg-astral-primary/30 transition-colors ml-auto text-sm font-medium"
                                >
                                    {isProcessing ? <Loader2 size={16} className="animate-spin" /> : <Code size={16} />}
                                    Generate Code
                                </button>
                            </div>

                            <form
                                onSubmit={(e) => { e.preventDefault(); handleSendMessage(); }}
                                className="flex gap-3 w-full"
                            >
                                <input
                                    type="text"
                                    value={inputVal}
                                    onChange={(e) => setInputVal(e.target.value)}
                                    placeholder={pendingInstall ? "Please resolve the installation first..." : "Refine the agent further..."}
                                    disabled={isProcessing || pendingInstall !== null}
                                    className="flex-1 bg-black/40 border border-white/10 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-astral-primary/50"
                                />
                                <button
                                    type="submit"
                                    disabled={!inputVal.trim() || isProcessing || pendingInstall !== null}
                                    className="px-4 py-3 bg-astral-primary/20 text-astral-primary rounded-xl hover:bg-astral-primary/30 transition-colors disabled:opacity-50 flex items-center justify-center shrink-0"
                                >
                                    <Send size={16} />
                                </button>
                            </form>
                        </div>
                    </div>
                )}

                {step === "editor" && (
                    <div className="flex-1 flex flex-col w-full bg-astral-surface/50 border border-white/5 rounded-xl overflow-hidden shadow-xl">
                        <div className="p-4 border-b border-white/5 flex items-center justify-between bg-black/40">
                            <div className="flex items-center gap-4">
                                <h3 className="text-white font-medium flex items-center gap-2 text-sm">
                                    <Code size={16} className="text-astral-primary" />
                                    Review & Edit Agent Files
                                </h3>
                                <div className="flex gap-1 border border-white/10 rounded-lg p-1 bg-black/40">
                                    {(["tools", "agent", "server"] as const).map((fileType) => (
                                        <button
                                            key={fileType}
                                            onClick={() => setActiveFile(fileType)}
                                            className={`px-3 py-1.5 text-xs rounded-md transition-colors ${activeFile === fileType
                                                ? 'bg-astral-primary text-white'
                                                : 'text-astral-muted hover:text-white hover:bg-white/5'}`}
                                        >
                                            {fileType === "tools" ? "tools.py" : 
                                             fileType === "agent" ? "agent.py" : 
                                             "server.py"}
                                        </button>
                                    ))}
                                </div>
                            </div>
                            <div className="flex items-center gap-3">
                                <button
                                    onClick={() => setStep("chat")}
                                    disabled={isProcessing}
                                    className="px-4 py-1.5 rounded-lg border border-white/10 text-white hover:bg-white/5 transition-colors text-sm"
                                >
                                    Back to Chat
                                </button>
                                <button
                                    onClick={handleRunTests}
                                    disabled={isProcessing}
                                    className="flex items-center gap-2 bg-green-500/20 text-green-400 border border-green-500/30 px-4 py-1.5 rounded-lg hover:bg-green-500/30 transition-colors text-sm font-medium"
                                >
                                    {isProcessing ? <Loader2 size={14} className="animate-spin" /> : <Shield size={14} />}
                                    Save & Run Tests
                                </button>
                            </div>
                        </div>
                        <div className="flex-1 overflow-y-auto bg-[#1d1f21] relative">
                            <Editor
                                value={generatedFiles[activeFile]}
                                onValueChange={code => setGeneratedFiles(prev => ({ ...prev, [activeFile]: code }))}
                                highlight={code => Prism.highlight(code, Prism.languages.python, 'python')}
                                padding={24}
                                style={{
                                    fontFamily: 'monospace',
                                    fontSize: 14,
                                    minHeight: '100%',
                                    color: '#c5c8c6'
                                }}
                                textareaClassName="focus:outline-none"
                            />
                        </div>
                    </div>
                )}

                {step === "progress" && (
                    <div className="flex-1 max-w-4xl mx-auto w-full flex flex-col bg-astral-surface border border-white/10 rounded-xl overflow-hidden p-6 shadow-xl">
                        <h3 className="text-lg text-white font-medium flex items-center gap-2 mb-4">
                            <RefreshCw size={18} className="text-astral-secondary animate-spin" />
                            Generating Agent Code
                        </h3>
                        <div className="flex-1">
                            {generationProgress ? (
                                <ProgressDisplay
                                    state={generationProgress}
                                    title="Code Generation Progress"
                                    mode="full"
                                    onCancel={() => {
                                        // Cancel generation and return to chat
                                        setStep("chat");
                                        setIsProcessing(false);
                                        setMessages(prev => [...prev, { 
                                            role: "system", 
                                            content: "Code generation cancelled by user." 
                                        }]);
                                    }}
                                    onRetry={() => {
                                        // Retry generation
                                        handleGenerateCode();
                                    }}
                                />
                            ) : (
                                <div className="flex flex-col items-center justify-center h-full">
                                    <RefreshCw size={32} className="text-astral-secondary animate-spin mb-4" />
                                    <p className="text-astral-muted">Starting code generation...</p>
                                </div>
                            )}
                        </div>
                    </div>
                )}

                {step === "testing" && (
                    <div className="flex-1 max-w-4xl mx-auto w-full flex flex-col bg-astral-surface border border-white/10 rounded-xl overflow-hidden p-6 shadow-xl">
                        <h3 className="text-lg text-white font-medium flex items-center gap-2 mb-4">
                            <RefreshCw size={18} className="text-astral-secondary animate-spin" />
                            Testing Agent
                        </h3>
                        <div className="flex-1 flex flex-col gap-4">
                            {testingProgress && (
                                <div className="mb-4">
                                    <ProgressDisplay
                                        state={testingProgress}
                                        title="Testing Progress"
                                        mode="compact"
                                    />
                                </div>
                            )}
                            <div className="flex-1 bg-black/60 rounded-lg border border-white/5 p-4 font-mono text-xs text-green-400 overflow-y-auto whitespace-pre-wrap">
                                {testOutput}
                            </div>
                        </div>
                    </div>
                )}

                {step === "approved" && (
                    <div className="flex-1 flex items-center justify-center">
                        <div className="text-center bg-astral-surface border border-green-500/30 rounded-2xl p-8 max-w-md">
                            <div className="w-16 h-16 bg-green-500/20 rounded-full flex items-center justify-center mx-auto mb-4">
                                <CheckCircle size={32} className="text-green-400" />
                            </div>
                            <h3 className="text-xl font-medium text-white mb-2">Agent Active!</h3>
                            <p className="text-sm text-astral-muted mb-6">
                                Your new agent has passed all tests and is now running. You can interact with it in the main chat.
                            </p>
                            <button
                                onClick={onBack}
                                className="bg-astral-primary text-white px-6 py-2 rounded-lg hover:bg-astral-primary/90 transition-colors"
                            >
                                Go to Dashboard
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
