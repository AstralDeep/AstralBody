/**
 * FloatingChatPanel — Collapsible floating text-only chat panel.
 *
 * Handles user query input and displays text-only LLM responses (summaries).
 * UI components are routed to the SDUICanvas instead.
 *
 * Features:
 * - Collapse/expand toggle
 * - Text-only message rendering (no SDUI components)
 * - File upload, voice input/output
 * - Mobile bottom sheet layout
 * - Chat status indicator
 */
import React, { useState, useRef, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
    Send, Bot, User, MessageSquare, Loader2,
    Paperclip, X, FileMinus, FileText, Square, Mic, Volume2, VolumeX, Minus, UploadCloud,
} from "lucide-react";
import { toast } from "sonner";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { normalizeLlmMarkdown } from "../utils/normalizeLlmMarkdown";
import { BFF_URL } from "../config";
import { ACCEPT_ATTRIBUTE } from "../lib/attachmentTypes";
import { useAttachments, formatAttachmentRefs } from "../hooks/useAttachments";
import { RotateCcw } from "lucide-react";
import type { ChatStatus, DeviceCapabilityFlags } from "../hooks/useWebSocket";

interface FloatingChatPanelProps {
    messages: { role: string; content: unknown; _target?: string }[];
    chatStatus: ChatStatus;
    onSendMessage: (message: string, displayMessage?: string, explicitChatId?: string) => void;
    onCancelTask: () => void;
    isConnected: boolean;
    activeChatId: string | null;
    accessToken?: string;
    deviceCapabilities?: DeviceCapabilityFlags;
}

export default function FloatingChatPanel({
    messages,
    chatStatus,
    onSendMessage,
    onCancelTask,
    isConnected,
    activeChatId,
    accessToken,
    deviceCapabilities = { hasMicrophone: false, hasGeolocation: false, speechServerAvailable: false },
}: FloatingChatPanelProps) {
    const canUseVoiceInput = deviceCapabilities.hasMicrophone && deviceCapabilities.speechServerAvailable;
    const canUseVoiceOutput = deviceCapabilities.speechServerAvailable;
    const canUseGeolocation = deviceCapabilities.hasGeolocation;

    const [isOpen, setIsOpen] = useState(true);
    const [input, setInput] = useState(() => {
        try { return localStorage.getItem("astral-draft") || ""; } catch { return ""; }
    });
    const [isDragging, setIsDragging] = useState(false);
    const [previewFile, setPreviewFile] = useState<{ name: string; content: string } | null>(null);

    // Attachment state — feature 002-file-uploads. Replaces the legacy
    // single-file FileReader path so binary uploads (PDFs, images, Office
    // formats) are not corrupted by treating them as text.
    const attachments = useAttachments({ accessToken });
    const isProcessingFile = attachments.pending.some((p) => p.status === "uploading");
    const readyAttachments = attachments.pending.filter((p) => p.status === "ready");

    const bottomRef = useRef<HTMLDivElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const inputRef = useRef<HTMLInputElement>(null);
    const prevChatIdRef = useRef(activeChatId);

    // Voice Input (STT)
    const [isRecording, setIsRecording] = useState(false);
    const [isTranscribing, setIsTranscribing] = useState(false);
    const [streamingTranscript, setStreamingTranscript] = useState("");
    const mediaRecorderRef = useRef<MediaRecorder | null>(null);
    const voiceWsRef = useRef<WebSocket | null>(null);
    const mediaStreamRef = useRef<MediaStream | null>(null);
    const audioContextRef = useRef<AudioContext | null>(null);
    const audioChunksRef = useRef<Blob[]>([]);

    // Voice Output (TTS)
    const [ttsEnabled, setTtsEnabled] = useState(false);
    const [isSpeaking, setIsSpeaking] = useState(false);
    const audioRef = useRef<HTMLAudioElement | null>(null);
    const lastSpokenMsgIdx = useRef<number>(-1);

    // Geolocation
    const [userLocation, setUserLocation] = useState<{ latitude: number; longitude: number } | null>(null);

    useEffect(() => {
        if (!canUseGeolocation || userLocation) return;
        navigator.geolocation.getCurrentPosition(
            (pos) => setUserLocation({
                latitude: parseFloat(pos.coords.latitude.toFixed(4)),
                longitude: parseFloat(pos.coords.longitude.toFixed(4)),
            }),
            (err) => console.debug("Geolocation unavailable:", err.message),
            { timeout: 8000, maximumAge: 300_000 }
        );
    }, [canUseGeolocation, userLocation]);

    const enrichWithLocation = useCallback((text: string): string => {
        if (!userLocation) return text;
        return `${text}\n\n[User location: ${userLocation.latitude}, ${userLocation.longitude}]`;
    }, [userLocation]);

    // Auto-focus input when panel opens
    useEffect(() => {
        if (isOpen) {
            setTimeout(() => inputRef.current?.focus(), 100);
        }
    }, [isOpen]);

    // Auto-focus input on new chat or chat switch
    useEffect(() => {
        if (activeChatId && activeChatId !== prevChatIdRef.current) {
            setTimeout(() => inputRef.current?.focus(), 100);
        }
        prevChatIdRef.current = activeChatId;
    }, [activeChatId]);

    // Filter messages to only show chat-targeted messages (text summaries) and user messages
    const chatMessages = messages.filter(msg => {
        if (msg.role === "user") return true;
        // Show assistant messages that are targeted to "chat" or have no target (legacy/loaded history)
        const target = msg._target;
        return target === "chat" || target === undefined;
    });

    // Unread count when panel is collapsed
    const [lastSeenCount, setLastSeenCount] = useState(0);
    const unreadCount = isOpen ? 0 : Math.max(0, chatMessages.length - lastSeenCount);

    useEffect(() => {
        if (isOpen) setLastSeenCount(chatMessages.length);
    }, [isOpen, chatMessages.length]);

    // Auto-scroll
    useEffect(() => {
        if (!isOpen) return;
        const frameId = requestAnimationFrame(() => {
            bottomRef.current?.scrollIntoView({ behavior: "smooth" });
        });
        return () => cancelAnimationFrame(frameId);
    }, [chatMessages, chatStatus, isOpen]);

    // Draft auto-save
    useEffect(() => {
        const timer = setTimeout(() => {
            try {
                if (input) localStorage.setItem("astral-draft", input);
                else localStorage.removeItem("astral-draft");
            } catch { /* ignore */ }
        }, 300);
        return () => clearTimeout(timer);
    }, [input]);

    const clearAttachment = () => {
        attachments.clear();
        if (fileInputRef.current) fileInputRef.current.value = '';
    };

    // Extract text content from assistant component arrays
    const extractTextFromComponents = (content: unknown): string => {
        if (typeof content === "string") return content;
        if (!Array.isArray(content)) return "";
        let text = "";
        for (const comp of content as Record<string, unknown>[]) {
            if (comp.type === "text" && typeof comp.content === "string") {
                text += comp.content + "\n\n";
            } else if (comp.type === "card") {
                const cardContent = comp.content as Record<string, unknown>[] | undefined;
                if (Array.isArray(cardContent)) {
                    for (const child of cardContent) {
                        if (child.type === "text" && typeof child.content === "string") {
                            text += child.content + "\n\n";
                        }
                    }
                }
            }
        }
        return text.trim() || "Processing complete.";
    };

    // Voice helpers (simplified from ChatInterface)
    const float32ToPcm16 = useCallback((float32: Float32Array): ArrayBuffer => {
        const buf = new ArrayBuffer(float32.length * 2);
        const view = new DataView(buf);
        for (let i = 0; i < float32.length; i++) {
            const s = Math.max(-1, Math.min(1, float32[i]));
            view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
        }
        return buf;
    }, []);

    const sendAudioForTranscription = useCallback(async (audioBlob: Blob) => {
        setIsTranscribing(true);
        try {
            const formData = new FormData();
            formData.append("file", audioBlob, "recording.webm");
            const headers: HeadersInit = {};
            if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;
            const res = await fetch(`${BFF_URL}/api/voice/transcribe`, {
                method: "POST", headers, body: formData,
            });
            if (!res.ok) throw new Error("Transcription failed");
            const data = await res.json();
            const text = data.text?.trim();
            if (text) onSendMessage(enrichWithLocation(text), text);
            else toast.error("No speech detected");
        } catch (err) {
            console.error("Transcription error:", err);
            toast.error("Failed to transcribe audio");
        } finally {
            setIsTranscribing(false);
        }
    }, [accessToken, onSendMessage, enrichWithLocation]);

    const startRecording = useCallback(async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({
                audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
            });
            mediaStreamRef.current = stream;

            const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
                ? "audio/webm;codecs=opus"
                : MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "audio/mp4";
            const mediaRecorder = new MediaRecorder(stream, { mimeType });
            mediaRecorderRef.current = mediaRecorder;
            audioChunksRef.current = [];
            mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) audioChunksRef.current.push(e.data); };
            mediaRecorder.start(250);

            const audioCtx = new AudioContext();
            audioContextRef.current = audioCtx;
            const nativeSR = audioCtx.sampleRate;
            const targetSR = 24000;
            const source = audioCtx.createMediaStreamSource(stream);
            const processor = audioCtx.createScriptProcessor(4096, 1, 1);
            let streamingActive = false;
            let gotTranscription = false;

            const wsScheme = window.location.protocol === "https:" ? "wss" : "ws";
            const voiceWsUrl = `${wsScheme}://${window.location.host}/api/voice/stream`;
            const voiceWs = new WebSocket(voiceWsUrl);
            voiceWsRef.current = voiceWs;

            voiceWs.onopen = () => { streamingActive = true; };

            processor.onaudioprocess = (e) => {
                if (streamingActive && voiceWs.readyState === WebSocket.OPEN) {
                    let samples = e.inputBuffer.getChannelData(0);
                    if (nativeSR !== targetSR) {
                        const ratio = nativeSR / targetSR;
                        const newLen = Math.floor(samples.length / ratio);
                        const resampled = new Float32Array(newLen);
                        for (let i = 0; i < newLen; i++) resampled[i] = samples[Math.floor(i * ratio)];
                        samples = resampled;
                    }
                    voiceWs.send(float32ToPcm16(samples));
                }
            };
            source.connect(processor);
            processor.connect(audioCtx.destination);

            voiceWs.onmessage = (event) => {
                try {
                    const msg = JSON.parse(event.data);
                    if (msg.type === "transcription.delta") {
                        setStreamingTranscript((prev) => prev + msg.text);
                    } else if (msg.type === "transcription.done") {
                        gotTranscription = true;
                        const finalText = msg.text?.trim();
                        setStreamingTranscript("");
                        setIsRecording(false);
                        setIsTranscribing(false);
                        processor.disconnect(); source.disconnect(); audioCtx.close();
                        audioContextRef.current = null;
                        stream.getTracks().forEach((t) => t.stop());
                        mediaStreamRef.current = null;
                        if (mediaRecorderRef.current?.state === "recording") mediaRecorderRef.current.stop();
                        voiceWs.close(); voiceWsRef.current = null;
                        if (finalText) onSendMessage(enrichWithLocation(finalText), finalText);
                        else toast.error("No speech detected");
                    } else if (msg.type === "error") {
                        streamingActive = false; voiceWs.close();
                    }
                } catch { /* ignore */ }
            };

            voiceWs.onerror = () => { streamingActive = false; };
            voiceWs.onclose = () => {
                voiceWsRef.current = null;
                try { processor.disconnect(); } catch { /* */ }
                try { source.disconnect(); } catch { /* */ }
                try { audioCtx.close(); } catch { /* */ }
                audioContextRef.current = null;
                if (!gotTranscription) {
                    if (mediaRecorderRef.current?.state === "recording") mediaRecorderRef.current.stop();
                    stream.getTracks().forEach((t) => t.stop());
                    mediaStreamRef.current = null;
                    setIsRecording(false);
                    if (audioChunksRef.current.length > 0) {
                        const audioBlob = new Blob(audioChunksRef.current, { type: mimeType });
                        sendAudioForTranscription(audioBlob);
                    } else { setIsTranscribing(false); setStreamingTranscript(""); }
                }
            };

            setIsRecording(true);
            setStreamingTranscript("");
        } catch (err) {
            const msg = err instanceof DOMException && err.name === "NotAllowedError"
                ? "Microphone access denied"
                : `Microphone error: ${err instanceof Error ? err.message : String(err)}`;
            toast.error(msg);
        }
    }, [onSendMessage, enrichWithLocation, sendAudioForTranscription, float32ToPcm16]);

    const stopRecording = useCallback(() => {
        if (voiceWsRef.current?.readyState === WebSocket.OPEN) {
            voiceWsRef.current.send(JSON.stringify({ type: "stop" }));
            setIsTranscribing(true);
        } else {
            if (mediaRecorderRef.current?.state === "recording") mediaRecorderRef.current.stop();
            if (mediaStreamRef.current) { mediaStreamRef.current.getTracks().forEach((t) => t.stop()); mediaStreamRef.current = null; }
            if (audioContextRef.current) { audioContextRef.current.close(); audioContextRef.current = null; }
            setIsRecording(false);
            if (audioChunksRef.current.length > 0) {
                const mimeType = mediaRecorderRef.current?.mimeType || "audio/webm";
                sendAudioForTranscription(new Blob(audioChunksRef.current, { type: mimeType }));
            }
        }
    }, [sendAudioForTranscription]);

    // TTS
    const speakAnalysis = useCallback(async (text: string) => {
        setIsSpeaking(true);
        try {
            const headers: HeadersInit = { "Content-Type": "application/json" };
            if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;
            const res = await fetch(`${BFF_URL}/api/voice/speak`, {
                method: "POST", headers, body: JSON.stringify({ text }),
            });
            if (!res.ok) throw new Error("TTS failed");
            const audioBlob = await res.blob();
            const audioUrl = URL.createObjectURL(audioBlob);
            const audio = new Audio(audioUrl);
            audioRef.current = audio;
            audio.onended = () => { setIsSpeaking(false); URL.revokeObjectURL(audioUrl); audioRef.current = null; };
            audio.play();
        } catch { setIsSpeaking(false); }
    }, [accessToken]);

    useEffect(() => {
        if (!ttsEnabled || chatMessages.length === 0) return;
        if (lastSpokenMsgIdx.current >= chatMessages.length - 1) return;
        const lastMsg = chatMessages[chatMessages.length - 1];
        if (lastMsg.role !== "assistant") return;
        const plainText = extractTextFromComponents(lastMsg.content);
        if (!plainText) return;
        lastSpokenMsgIdx.current = chatMessages.length - 1;
        speakAnalysis(plainText);
    }, [ttsEnabled, chatMessages, speakAnalysis]);

    // Stage one or more files via the shared attachments hook (multi-file
    // safe, validates extension + 30 MB cap, uploads via /api/upload).
    const stageFiles = useCallback(async (files: FileList | File[]) => {
        if (!isConnected) return;
        await attachments.upload(files);
    }, [isConnected, attachments]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        const hasText = input.trim().length > 0;
        const hasReadyAttachments = readyAttachments.length > 0;
        if ((!hasText && !hasReadyAttachments) || !isConnected) return;
        if (isProcessingFile) {
            toast.message("Waiting for uploads to finish…");
            return;
        }

        const targetChatId = activeChatId || crypto.randomUUID();
        const refs = formatAttachmentRefs(attachments.pending);
        const filenames = readyAttachments.map((p) => p.attachment?.filename).filter(Boolean).join(", ");
        const promptPrefix = hasText ? `${input.trim()}\n\n` : "";
        const fullMsg = hasReadyAttachments
            ? `${promptPrefix}${refs}\n\nThe user has attached the file(s) above. Use the appropriate file-reading tool (read_document / read_spreadsheet / read_presentation / read_text / read_image) with the given attachment_id(s) to read the contents before answering.`
            : input.trim();
        const displayMsg = hasReadyAttachments
            ? `${promptPrefix}[Attached: ${filenames}]`
            : input.trim();

        onSendMessage(enrichWithLocation(fullMsg), displayMsg, targetChatId);

        setInput("");
        try { localStorage.removeItem("astral-draft"); } catch { /* ignore */ }
        clearAttachment();
    };

    const extractFileContentFromMsg = (content: string) => {
        const match = /```[\w]*\s*([\s\S]*?)```/g.exec(content);
        return match ? match[1].trim() : "Preview not available.";
    };

    const renderUserMessage = (content: string) => {
        const cleanContent = content
            .replace(/I have uploaded .* to the backend at: `.*`/g, "")
            .replace(/Here is a preview \(first 50 lines\):/g, "")
            .replace(/Please use the `analyze_csv_file` tool .*/g, "")
            .replace(/Here is my data from .*\. Please run various data analyses .*/g, "")
            .replace(/I've attached a file named .*\. Here are the contents:/g, "")
            .replace(/```[\w]*\s*([\s\S]*?)```/g, "")
            .trim();

        const fileRegex = /\[Attached File: (.*?)\]/g;
        const parts: React.ReactNode[] = [];
        let lastIndex = 0;
        let match;

        while ((match = fileRegex.exec(cleanContent)) !== null) {
            if (match.index > lastIndex) {
                const textBefore = cleanContent.substring(lastIndex, match.index).trim();
                if (textBefore) parts.push(<p key={`t-${lastIndex}`} className="text-xs text-white whitespace-pre-wrap">{textBefore}</p>);
            }
            const fileName = match[1];
            parts.push(
                <button key={`f-${match.index}`} type="button"
                    onClick={() => setPreviewFile({ name: fileName, content: extractFileContentFromMsg(content) })}
                    className="flex items-center gap-1.5 px-2 py-1 bg-white/10 border border-white/10 rounded-lg text-left hover:bg-white/15 transition-all text-xs"
                >
                    <FileText size={12} className="text-astral-primary" />
                    <span className="text-white truncate max-w-[140px]">{fileName}</span>
                </button>
            );
            lastIndex = match.index + match[0].length;
        }

        if (lastIndex < cleanContent.length) {
            const remaining = cleanContent.substring(lastIndex).trim();
            if (remaining) parts.push(<p key={`t-${lastIndex}`} className="text-xs text-white whitespace-pre-wrap">{remaining}</p>);
        }

        return parts.length > 0 ? parts : <p className="text-xs text-white">{cleanContent || content.split('[Attached File:')[0].trim()}</p>;
    };

    // File drag-and-drop
    const handleFileDragOver = useCallback((e: React.DragEvent) => {
        if (!e.dataTransfer.types.includes("Files")) return;
        e.preventDefault(); e.stopPropagation();
        if (!isDragging) setIsDragging(true);
    }, [isDragging]);

    const handleFileDragLeave = useCallback((e: React.DragEvent) => {
        if (!e.dataTransfer.types.includes("Files")) return;
        e.preventDefault(); e.stopPropagation();
        if (e.currentTarget === e.target) setIsDragging(false);
    }, []);

    const handleFileDrop = useCallback((e: React.DragEvent) => {
        if (!e.dataTransfer.types.includes("Files")) return;
        e.preventDefault(); e.stopPropagation();
        setIsDragging(false);
        if (e.dataTransfer.files?.length) void stageFiles(e.dataTransfer.files);
    }, [stageFiles]);

    // Collapsed state — just a floating button
    if (!isOpen) {
        return (
            <motion.button
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                onClick={() => setIsOpen(true)}
                className="fixed bottom-4 right-4 z-40 w-14 h-14 rounded-full bg-gradient-to-br from-astral-primary to-astral-secondary shadow-2xl flex items-center justify-center hover:scale-105 transition-transform"
            >
                <MessageSquare size={22} className="text-white" />
                {unreadCount > 0 && (
                    <span className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center">
                        {unreadCount > 9 ? "9+" : unreadCount}
                    </span>
                )}
            </motion.button>
        );
    }

    return (
        <>
            {/* File Preview Modal */}
            <AnimatePresence>
                {previewFile && (
                    <motion.div
                        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                        className="fixed inset-0 z-[60] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4"
                        onClick={() => setPreviewFile(null)}
                    >
                        <motion.div
                            initial={{ scale: 0.9 }} animate={{ scale: 1 }} exit={{ scale: 0.9 }}
                            className="bg-astral-bg border border-white/10 rounded-xl max-w-lg w-full max-h-[60vh] overflow-auto p-4"
                            onClick={(e) => e.stopPropagation()}
                        >
                            <div className="flex justify-between items-center mb-3">
                                <h3 className="text-sm font-medium text-white">{previewFile.name}</h3>
                                <button onClick={() => setPreviewFile(null)} className="p-1 hover:bg-white/10 rounded"><X size={14} className="text-astral-muted" /></button>
                            </div>
                            <pre className="text-xs text-astral-muted whitespace-pre-wrap font-mono">{previewFile.content}</pre>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Floating Panel */}
            <motion.div
                initial={{ opacity: 0, y: 20, scale: 0.95 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: 20, scale: 0.95 }}
                className="fixed bottom-4 right-4 z-40 w-[380px] sm:w-[420px] max-h-[70vh] max-sm:left-4 max-sm:w-auto
                           bg-astral-bg/95 backdrop-blur-xl border border-white/10 rounded-2xl shadow-2xl
                           flex flex-col overflow-hidden"
                onDragOver={handleFileDragOver}
                onDragLeave={handleFileDragLeave}
                onDrop={handleFileDrop}
            >
                {/* File drag overlay */}
                <AnimatePresence>
                    {isDragging && (
                        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                            className="absolute inset-0 z-50 bg-astral-bg/80 backdrop-blur-sm border-2 border-dashed border-astral-primary/50 rounded-2xl flex flex-col items-center justify-center"
                        >
                            <UploadCloud size={32} className="text-astral-primary mb-2" />
                            <p className="text-sm text-astral-muted">Drop file here</p>
                        </motion.div>
                    )}
                </AnimatePresence>

                {/* Header */}
                <div className="flex items-center justify-between px-4 py-3 border-b border-white/10 flex-shrink-0">
                    <div className="flex items-center gap-2">
                        <div className="w-6 h-6 rounded-lg bg-gradient-to-br from-astral-primary to-astral-secondary flex items-center justify-center">
                            <MessageSquare size={12} className="text-white" />
                        </div>
                        <span className="text-sm font-medium text-white">Chat</span>
                        {chatStatus.status !== "idle" && chatStatus.status !== "done" && (
                            <span className="text-[10px] text-astral-primary animate-pulse ml-1">
                                {chatStatus.status === "thinking" ? "Thinking..." : "Executing..."}
                            </span>
                        )}
                    </div>
                    <button
                        onClick={() => setIsOpen(false)}
                        className="p-1 rounded-lg hover:bg-white/10 text-astral-muted hover:text-white transition-colors"
                        title="Minimize chat"
                    >
                        <Minus size={16} />
                    </button>
                </div>

                {/* Messages */}
                <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3 min-h-0">
                    {chatMessages.length === 0 && (
                        <div className="flex flex-col items-center justify-center h-full text-center py-8">
                            <Bot size={24} className="text-astral-muted/30 mb-2" />
                            <p className="text-xs text-astral-muted">Send a message to get started</p>
                        </div>
                    )}

                    {chatMessages.map((msg, i) => (
                        <motion.div
                            key={i}
                            initial={{ opacity: 0, y: 6 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ duration: 0.15 }}
                            className={`flex gap-2 ${msg.role === "user" ? "justify-end" : ""}`}
                        >
                            {msg.role === "assistant" && (
                                <div className="w-6 h-6 rounded-md bg-gradient-to-br from-astral-primary to-astral-secondary flex items-center justify-center flex-shrink-0 mt-0.5">
                                    <Bot size={12} className="text-white" />
                                </div>
                            )}
                            <div className={msg.role === "user"
                                ? "max-w-[80%] bg-astral-primary/20 border border-astral-primary/30 rounded-xl rounded-tr-sm px-3 py-2"
                                : "flex-1 max-w-[calc(100%-2rem)] min-w-0 bg-white/5 border border-white/10 rounded-xl rounded-tl-sm px-3 py-2"
                            }>
                                {msg.role === "user" ? (
                                    <div className="space-y-1">
                                        {renderUserMessage(msg.content as string)}
                                    </div>
                                ) : (
                                    <div className="text-xs text-astral-text prose prose-invert prose-xs max-w-none [&_p]:text-xs [&_li]:text-xs [&_h1]:text-sm [&_h2]:text-xs [&_h3]:text-xs">
                                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                            {normalizeLlmMarkdown(extractTextFromComponents(msg.content))}
                                        </ReactMarkdown>
                                    </div>
                                )}
                            </div>
                            {msg.role === "user" && (
                                <div className="w-6 h-6 rounded-md bg-white/10 flex items-center justify-center flex-shrink-0 mt-0.5">
                                    <User size={12} className="text-astral-muted" />
                                </div>
                            )}
                        </motion.div>
                    ))}

                    {/* Loading state */}
                    <AnimatePresence>
                        {chatStatus.status !== "idle" && chatStatus.status !== "done" && (
                            <motion.div
                                initial={{ opacity: 0, y: 6 }}
                                animate={{ opacity: 1, y: 0 }}
                                exit={{ opacity: 0 }}
                                className="flex gap-2"
                            >
                                <div className="w-6 h-6 rounded-md bg-gradient-to-br from-astral-primary to-astral-secondary flex items-center justify-center flex-shrink-0 pulse-glow">
                                    <Bot size={12} className="text-white" />
                                </div>
                                <div className="glass-card px-3 py-2 flex items-center gap-2">
                                    <Loader2 size={12} className="text-astral-primary animate-spin" />
                                    <span className="text-xs text-astral-muted">
                                        {chatStatus.message || "Processing..."}
                                    </span>
                                    <button
                                        onClick={onCancelTask}
                                        className="p-1 rounded-md bg-white/5 hover:bg-red-500/20 text-astral-muted hover:text-red-400 transition-colors"
                                        title="Stop"
                                    >
                                        <Square size={10} />
                                    </button>
                                </div>
                            </motion.div>
                        )}
                    </AnimatePresence>

                    <div ref={bottomRef} />
                </div>

                {/* Input Area */}
                <div className="px-3 py-2 border-t border-white/10 flex-shrink-0">
                    <form onSubmit={handleSubmit} className="flex flex-col gap-1.5">
                        {/* Recording Indicator */}
                        <AnimatePresence>
                            {isRecording && (
                                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                                    className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-red-500/15 border border-red-500/30 text-red-400 text-[10px] font-medium self-start"
                                >
                                    <span className="w-1.5 h-1.5 rounded-full bg-red-400 animate-pulse" />
                                    Recording...
                                </motion.div>
                            )}
                        </AnimatePresence>

                        {/* Staged attachment chips — feature 002-file-uploads */}
                        {attachments.pending.length > 0 && (
                            <div className="flex flex-wrap gap-1 self-start">
                                {attachments.pending.map((p) => {
                                    const isError = p.status === "error";
                                    const isUploading = p.status === "uploading";
                                    return (
                                        <div
                                            key={p.localId}
                                            className={`flex items-center gap-1.5 px-2 py-1 rounded-md border text-[11px] font-medium ${
                                                isError
                                                    ? "bg-red-500/10 border-red-500/30 text-red-400"
                                                    : "bg-astral-primary/10 border-astral-primary/30 text-astral-primary"
                                            }`}
                                        >
                                            {isUploading
                                                ? <Loader2 size={12} className="animate-spin" />
                                                : <FileMinus size={12} className={isError ? "text-red-400" : "text-astral-primary"} />}
                                            <span className="truncate max-w-[120px]" title={p.filename}>{p.filename}</span>
                                            {isError && p.source && (
                                                <button type="button" onClick={(e) => { e.stopPropagation(); void attachments.retry(p.localId); }} className="p-0.5 rounded hover:bg-white/10" title="Retry"><RotateCcw size={10} /></button>
                                            )}
                                            <button type="button" onClick={(e) => { e.stopPropagation(); attachments.remove(p.localId); }} className="p-0.5 rounded hover:bg-white/10" title="Remove"><X size={10} /></button>
                                            {isError && p.error && <span className="ml-0.5 opacity-90">{p.error.message}</span>}
                                        </div>
                                    );
                                })}
                            </div>
                        )}

                        <div className="flex gap-1.5">
                            <div className="flex-1 relative flex items-center gap-1 bg-astral-surface/60 border border-white/10 rounded-xl px-1.5 transition-all focus-within:border-astral-primary/50 focus-within:ring-1 focus-within:ring-astral-primary/20">
                                <button type="button" onClick={() => fileInputRef.current?.click()}
                                    disabled={!isConnected || isProcessingFile}
                                    className="p-1.5 text-astral-muted hover:text-white rounded-md hover:bg-white/10 transition-colors disabled:opacity-50 flex-shrink-0"
                                    title="Attach File"
                                >
                                    {isProcessingFile ? <Loader2 size={16} className="animate-spin text-astral-primary" /> : <Paperclip size={16} />}
                                </button>
                                <input type="file" className="hidden" ref={fileInputRef}
                                    onChange={(e) => { const fs = e.target.files; if (fs && fs.length) void stageFiles(fs); if (fileInputRef.current) fileInputRef.current.value = ''; }}
                                    accept={ACCEPT_ATTRIBUTE}
                                    multiple />

                                <input type="text"
                                    ref={inputRef}
                                    value={isRecording || isTranscribing ? streamingTranscript || "" : input}
                                    onChange={(e) => { if (!isRecording && !isTranscribing) setInput(e.target.value); }}
                                    placeholder={isRecording ? "Listening..." : isTranscribing ? "Transcribing..." : isConnected ? "Ask anything..." : "Connecting..."}
                                    disabled={!isConnected || isRecording || isTranscribing || (chatStatus.status !== "idle" && chatStatus.status !== "done")}
                                    className="w-full py-2 bg-transparent text-xs text-white placeholder:text-astral-muted/50 focus:outline-none disabled:opacity-50"
                                />

                                {canUseVoiceInput && (
                                    <button type="button" onClick={isRecording ? stopRecording : startRecording}
                                        disabled={!isConnected || isTranscribing || (chatStatus.status !== "idle" && chatStatus.status !== "done")}
                                        className={`p-1.5 rounded-md transition-colors flex-shrink-0 ${isRecording ? "text-red-400 bg-red-500/20" : "text-astral-muted hover:text-white hover:bg-white/10"} disabled:opacity-50`}
                                    >
                                        {isTranscribing ? <Loader2 size={14} className="animate-spin" /> : isRecording ? <Square size={12} /> : <Mic size={16} />}
                                    </button>
                                )}

                                {canUseVoiceOutput && (
                                    <button type="button"
                                        onClick={() => { setTtsEnabled(prev => !prev); if (ttsEnabled && audioRef.current) { audioRef.current.pause(); audioRef.current = null; setIsSpeaking(false); } }}
                                        className={`p-1.5 rounded-md transition-colors flex-shrink-0 ${ttsEnabled ? "text-astral-primary bg-astral-primary/20" : "text-astral-muted hover:text-white hover:bg-white/10"}`}
                                    >
                                        {isSpeaking ? <Volume2 size={14} className="animate-pulse" /> : ttsEnabled ? <Volume2 size={14} /> : <VolumeX size={14} />}
                                    </button>
                                )}
                            </div>
                            <button type="submit"
                                disabled={(!input.trim() && readyAttachments.length === 0) || !isConnected || isProcessingFile || (chatStatus.status !== "idle" && chatStatus.status !== "done")}
                                className="px-3 py-2 rounded-xl bg-astral-primary hover:bg-astral-primary/80 disabled:opacity-30 disabled:cursor-not-allowed transition-colors flex items-center flex-shrink-0"
                            >
                                <Send size={14} className="text-white" />
                            </button>
                        </div>
                    </form>
                </div>
            </motion.div>
        </>
    );
}
