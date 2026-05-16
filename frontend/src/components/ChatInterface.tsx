/**
 * ChatInterface — Real-time chat with the orchestrator.
 *
 * Features:
 * - Message input with send button
 * - Chat history display (user + assistant messages)
 * - Loading states (thinking, executing)
 * - Dynamic UI rendering for assistant responses via DynamicRenderer
 */
import React, { useState, useRef, useEffect, useLayoutEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Send, Bot, User, Sparkles, Loader2, ChevronLeft, Paperclip, UploadCloud, X, FileMinus, FileText, Square, Mic, Volume2, VolumeX, FolderOpen, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import DynamicRenderer from "./DynamicRenderer";
import type { TablePaginateEvent } from "./DynamicRenderer";
import UISavedDrawer from "./UISavedDrawer";
import AttachmentLibrary from "./AttachmentLibrary";
import { CosmicProgressIndicator } from "./chat/CosmicProgressIndicator";
import { ChatStepEntry } from "./chat/ChatStepEntry";
import { BFF_URL } from "../config";
import type { ChatStatus, DeviceCapabilityFlags } from "../hooks/useWebSocket";
import type { ChatStepMap } from "../types/chatSteps";
import { useAttachments, formatAttachmentRefs } from "../hooks/useAttachments";
import { ACCEPT_ATTRIBUTE } from "../lib/attachmentTypes";

interface ChatInterfaceProps {
    messages: { role: string; content: unknown }[];
    chatStatus: ChatStatus;
    /**
     * Feature 014 — persistent step entries for the active chat (US2).
     * The map shape is ``{ [step_id]: ChatStep }``; rendering sorts by
     * ``started_at`` and groups by ``turn_message_id`` to interleave each
     * turn's steps between the user message and the assistant reply.
     */
    chatSteps?: ChatStepMap;
    onSendMessage: (message: string, displayMessage?: string, explicitChatId?: string) => void;
    onCancelTask: () => void;
    isConnected: boolean;
    activeChatId: string | null;
    savedComponents: Array<{ id: string; chat_id: string; component_data: Record<string, unknown>; component_type: string; title: string; created_at: number }>;
    onSaveComponent: (componentData: Record<string, unknown>, componentType: string) => Promise<boolean>;
    onDeleteSavedComponent: (componentId: string) => void;
    onCombineComponents: (sourceId: string, targetId: string) => void;
    onCondenseComponents: (componentIds: string[]) => void;
    onCancelCombine: () => void;
    isCombining: boolean;
    combineError: string | null;
    accessToken?: string;
    onTablePaginate?: (event: TablePaginateEvent) => void;
    deviceCapabilities?: DeviceCapabilityFlags;
}

const SUGGESTIONS = [
    "Get me all patients over 30 and graph their ages",
    "What is my system's CPU and memory usage?",
    "Search Wikipedia for artificial intelligence",
    "Show me disk usage information",
];

export default function ChatInterface({
    messages,
    chatStatus,
    chatSteps,
    onSendMessage,
    onCancelTask,
    isConnected,
    activeChatId,
    savedComponents,
    onSaveComponent,
    onDeleteSavedComponent,
    onCombineComponents,
    onCondenseComponents,
    onCancelCombine,
    isCombining,
    combineError,
    accessToken,
    onTablePaginate,
    deviceCapabilities = { hasMicrophone: false, hasGeolocation: false, speechServerAvailable: false },
}: ChatInterfaceProps) {
    // Capability gating — buttons hidden until rote_config confirms capabilities
    const canUseVoiceInput = deviceCapabilities.hasMicrophone && deviceCapabilities.speechServerAvailable;
    const canUseVoiceOutput = deviceCapabilities.speechServerAvailable;
    const canUseGeolocation = deviceCapabilities.hasGeolocation;

    const [input, setInput] = useState(() => {
        try { return localStorage.getItem("astral-draft") || ""; } catch { return ""; }
    });
    const [isDrawerOpen, setIsDrawerOpen] = useState(false);
    const [isDragging, setIsDragging] = useState(false);
    const [previewFile, setPreviewFile] = useState<{ name: string; content: string } | null>(null);
    const [isLibraryOpen, setIsLibraryOpen] = useState(false);

    // Attachment state — feature 002-file-uploads. Replaces the legacy
    // single-file FileReader path; supports the FR-001 expanded type list,
    // 30 MB cap, multi-file, and cross-chat reuse via AttachmentLibrary.
    const attachments = useAttachments({ accessToken });
    const isProcessingFile = attachments.pending.some((p) => p.status === "uploading");
    const readyAttachments = attachments.pending.filter((p) => p.status === "ready");

    const bottomRef = useRef<HTMLDivElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    // Voice Input (STT) state — real-time streaming via WebSocket
    const [isRecording, setIsRecording] = useState(false);
    const [isTranscribing, setIsTranscribing] = useState(false);
    const [streamingTranscript, setStreamingTranscript] = useState("");
    const mediaRecorderRef = useRef<MediaRecorder | null>(null);
    const voiceWsRef = useRef<WebSocket | null>(null);
    const mediaStreamRef = useRef<MediaStream | null>(null);
    const audioContextRef = useRef<AudioContext | null>(null);
    const audioChunksRef = useRef<Blob[]>([]);

    // Voice Output (TTS) state
    const [ttsEnabled, setTtsEnabled] = useState(false);
    const [isSpeaking, setIsSpeaking] = useState(false);
    const audioRef = useRef<HTMLAudioElement | null>(null);
    const lastSpokenMsgIdx = useRef<number>(-1);

    const [userLocation, setUserLocation] = useState<{ latitude: number; longitude: number } | null>(null);

    useEffect(() => {
        if (!canUseGeolocation || userLocation) return;
        navigator.geolocation.getCurrentPosition(
            (pos) => {
                setUserLocation({
                    latitude: parseFloat(pos.coords.latitude.toFixed(4)),
                    longitude: parseFloat(pos.coords.longitude.toFixed(4)),
                });
            },
            (err) => console.debug("Geolocation unavailable:", err.message),
            { timeout: 8000, maximumAge: 300_000 }
        );
    }, [canUseGeolocation, userLocation]);

    const enrichWithLocation = useCallback((text: string): string => {
        if (!userLocation) return text;
        return `${text}\n\n[User location: ${userLocation.latitude}, ${userLocation.longitude}]`;
    }, [userLocation]);

    // Auto-scroll to bottom on new messages
    useEffect(() => {
        const frameId = requestAnimationFrame(() => {
            bottomRef.current?.scrollIntoView({ behavior: "smooth" });
        });
        return () => cancelAnimationFrame(frameId);
    }, [messages, chatStatus]);

    // Auto-grow the chat textarea to fit its content; CSS max-h caps it.
    useLayoutEffect(() => {
        const el = textareaRef.current;
        if (!el) return;
        el.style.height = "auto";
        el.style.height = `${el.scrollHeight}px`;
    }, [input, streamingTranscript, isRecording, isTranscribing]);

    // Draft auto-save
    useEffect(() => {
        const timer = setTimeout(() => {
            try {
                if (input) localStorage.setItem("astral-draft", input);
                else localStorage.removeItem("astral-draft");
            } catch { /* quota exceeded or private mode */ }
        }, 300);
        return () => clearTimeout(timer);
    }, [input]);

    const clearAttachment = useCallback(() => {
        attachments.clear();
        if (fileInputRef.current) {
            fileInputRef.current.value = '';
        }
    }, [attachments]);

    // ── Voice Input (STT) — Real-time streaming via WebSocket ────────
    const sendAudioForTranscription = useCallback(async (audioBlob: Blob) => {
        // Fallback batch transcription (used if streaming WS fails)
        setIsTranscribing(true);
        try {
            const formData = new FormData();
            formData.append("file", audioBlob, "recording.webm");
            const headers: HeadersInit = {};
            if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;
            const res = await fetch(`${BFF_URL}/api/voice/transcribe`, {
                method: "POST",
                headers,
                body: formData,
            });
            if (!res.ok) throw new Error("Transcription failed");
            const data = await res.json();
            const text = data.text?.trim();
            if (text) {
                onSendMessage(enrichWithLocation(text), text);
            } else {
                toast.error("No speech detected");
            }
        } catch (err) {
            console.error("Transcription error:", err);
            toast.error("Failed to transcribe audio");
        } finally {
            setIsTranscribing(false);
        }
    }, [accessToken, onSendMessage, enrichWithLocation]);

    // Helper: convert Float32 audio samples to Int16 PCM buffer
    const float32ToPcm16 = useCallback((float32: Float32Array): ArrayBuffer => {
        const buf = new ArrayBuffer(float32.length * 2);
        const view = new DataView(buf);
        for (let i = 0; i < float32.length; i++) {
            const s = Math.max(-1, Math.min(1, float32[i]));
            view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
        }
        return buf;
    }, []);

    const startRecording = useCallback(async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({
                audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
            });
            mediaStreamRef.current = stream;

            // Also start MediaRecorder for batch fallback (it handles webm fine)
            const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
                ? "audio/webm;codecs=opus"
                : MediaRecorder.isTypeSupported("audio/webm")
                    ? "audio/webm"
                    : "audio/mp4";
            const mediaRecorder = new MediaRecorder(stream, { mimeType });
            mediaRecorderRef.current = mediaRecorder;
            audioChunksRef.current = [];
            mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) audioChunksRef.current.push(e.data);
            };
            mediaRecorder.start(250);

            // Set up AudioContext at the mic's native sample rate
            // and downsample to 24kHz PCM16 before sending to Speaches
            const audioCtx = new AudioContext();
            audioContextRef.current = audioCtx;
            const nativeSR = audioCtx.sampleRate;
            const targetSR = 24000;
            const source = audioCtx.createMediaStreamSource(stream);
            const processor = audioCtx.createScriptProcessor(4096, 1, 1);

            // Open streaming WebSocket with auto-retry (exponential backoff)
            const wsScheme = window.location.protocol === "https:" ? "wss" : "ws";
            const voiceWsUrl = `${wsScheme}://${window.location.host}/api/voice/stream`;

            let retryCount = 0;
            const maxRetries = 2;
            let streamingActive = false;
            let gotTranscription = false;

            const connectVoiceWebSocket = () => {
                const voiceWs = new WebSocket(voiceWsUrl);
                voiceWsRef.current = voiceWs;

                voiceWs.onopen = () => {
                    streamingActive = true;
                    retryCount = 0;
                };

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
                            // Clean up audio pipeline
                            processor.disconnect();
                            source.disconnect();
                            audioCtx.close();
                            audioContextRef.current = null;
                            stream.getTracks().forEach((t) => t.stop());
                            mediaStreamRef.current = null;
                            if (mediaRecorderRef.current?.state === "recording") {
                                mediaRecorderRef.current.stop();
                            }
                            voiceWs.close();
                            voiceWsRef.current = null;
                            if (finalText) {
                                onSendMessage(enrichWithLocation(finalText), finalText);
                            } else {
                                toast.error("No speech detected");
                            }
                        } else if (msg.type === "error") {
                            console.warn("Voice stream server error:", msg.message);
                            streamingActive = false;
                            voiceWs.close();
                        }
                    } catch {
                        // Ignore parse errors
                    }
                };

                voiceWs.onerror = () => {
                    console.warn(`Voice stream WebSocket error (retry ${retryCount}/${maxRetries})`);
                    streamingActive = false;
                };

                voiceWs.onclose = () => {
                    voiceWsRef.current = null;
                    // Clean up audio pipeline if we're done or if retries exhausted
                    if (gotTranscription) {
                        // Normal completion — clean up
                        try { processor.disconnect(); } catch { /* already disconnected */ }
                        try { source.disconnect(); } catch { /* already disconnected */ }
                        try { audioCtx.close(); } catch { /* already closed */ }
                        audioContextRef.current = null;
                        return;
                    }

                    if (!streamingActive || retryCount >= maxRetries) {
                        // Exhausted retries or connection was actively refused
                        try { processor.disconnect(); } catch { /* already disconnected */ }
                        try { source.disconnect(); } catch { /* already disconnected */ }
                        try { audioCtx.close(); } catch { /* already closed */ }
                        audioContextRef.current = null;

                        // Fall back to batch transcription
                        if (mediaRecorderRef.current?.state === "recording") {
                            mediaRecorderRef.current.stop();
                        }
                        stream.getTracks().forEach((t) => t.stop());
                        mediaStreamRef.current = null;
                        setIsRecording(false);
                        if (audioChunksRef.current.length > 0) {
                            console.info("Falling back to batch transcription");
                            const audioBlob = new Blob(audioChunksRef.current, { type: mimeType });
                            sendAudioForTranscription(audioBlob);
                        } else {
                            setIsTranscribing(false);
                            setStreamingTranscript("");
                        }
                        return;
                    }

                    // Retry with exponential backoff
                    retryCount++;
                    const delay = Math.pow(2, retryCount) * 500;
                    console.info(`Retrying voice WebSocket in ${delay}ms (attempt ${retryCount}/${maxRetries})`);
                    setTimeout(connectVoiceWebSocket, delay);
                };
            };

            connectVoiceWebSocket();

            // Stream raw PCM16 audio to the WebSocket, downsampling if needed
            processor.onaudioprocess = (e) => {
                if (streamingActive && voiceWsRef.current?.readyState === WebSocket.OPEN) {
                    let samples = e.inputBuffer.getChannelData(0);
                    // Downsample from native rate (e.g. 48kHz) to 24kHz
                    if (nativeSR !== targetSR) {
                        const ratio = nativeSR / targetSR;
                        const newLen = Math.floor(samples.length / ratio);
                        const resampled = new Float32Array(newLen);
                        for (let i = 0; i < newLen; i++) {
                            resampled[i] = samples[Math.floor(i * ratio)];
                        }
                        samples = resampled;
                    }
                    const pcm16 = float32ToPcm16(samples);
                    voiceWsRef.current.send(pcm16);
                }
            };
            source.connect(processor);
            processor.connect(audioCtx.destination);

            setIsRecording(true);
            setStreamingTranscript("");
        } catch (err) {
            const msg = err instanceof DOMException && err.name === "NotAllowedError"
                ? "Microphone access denied"
                : `Microphone error: ${err instanceof Error ? err.message : String(err)}`;
            console.error("startRecording error:", err);
            toast.error(msg);
        }
    }, [onSendMessage, enrichWithLocation, sendAudioForTranscription, float32ToPcm16]);

    const stopRecording = useCallback(() => {
        // Signal the streaming server to commit and produce final transcription
        if (voiceWsRef.current?.readyState === WebSocket.OPEN) {
            voiceWsRef.current.send(JSON.stringify({ type: "stop" }));
            setIsTranscribing(true);
        } else {
            // No streaming WS — stop MediaRecorder for batch fallback
            if (mediaRecorderRef.current?.state === "recording") {
                mediaRecorderRef.current.stop();
            }
            if (mediaStreamRef.current) {
                mediaStreamRef.current.getTracks().forEach((t) => t.stop());
                mediaStreamRef.current = null;
            }
            if (audioContextRef.current) {
                audioContextRef.current.close();
                audioContextRef.current = null;
            }
            setIsRecording(false);
            if (audioChunksRef.current.length > 0) {
                const mimeType = mediaRecorderRef.current?.mimeType || "audio/webm";
                const audioBlob = new Blob(audioChunksRef.current, { type: mimeType });
                sendAudioForTranscription(audioBlob);
            }
        }
    }, [sendAudioForTranscription]);

    // ── Voice Output (TTS) — fires on ui_render, not waiting for "done" ──
    const extractAnalysisText = useCallback((components: Array<Record<string, unknown>>): string => {
        let text = "";
        for (const comp of components) {
            if (comp.type === "card" && comp.title === "Analysis") {
                const content = comp.content as Array<Record<string, unknown>>;
                if (Array.isArray(content)) {
                    for (const child of content) {
                        if (child.type === "text" && typeof child.content === "string") {
                            text += child.content + " ";
                        }
                    }
                }
            }
        }
        return text
            .replace(/#{1,6}\s/g, "")
            .replace(/\*\*(.*?)\*\*/g, "$1")
            .replace(/\*(.*?)\*/g, "$1")
            .replace(/`(.*?)`/g, "$1")
            .replace(/```[\s\S]*?```/g, "")
            .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
            .trim();
    }, []);

    const speakAnalysis = useCallback(async (text: string) => {
        setIsSpeaking(true);
        try {
            const headers: HeadersInit = { "Content-Type": "application/json" };
            if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;
            const res = await fetch(`${BFF_URL}/api/voice/speak`, {
                method: "POST",
                headers,
                body: JSON.stringify({ text }),
            });
            if (!res.ok) throw new Error("TTS failed");
            const audioBlob = await res.blob();
            const audioUrl = URL.createObjectURL(audioBlob);
            const audio = new Audio(audioUrl);
            audioRef.current = audio;
            audio.onended = () => {
                setIsSpeaking(false);
                URL.revokeObjectURL(audioUrl);
                audioRef.current = null;
            };
            audio.play();
        } catch (err) {
            console.error("TTS error:", err);
            setIsSpeaking(false);
        }
    }, [accessToken]);

    // Trigger TTS as soon as an Analysis card arrives (on each new assistant message)
    useEffect(() => {
        if (!ttsEnabled || messages.length === 0) return;
        if (lastSpokenMsgIdx.current >= messages.length - 1) return;

        const lastMsg = messages[messages.length - 1];
        if (lastMsg.role !== "assistant") return;

        const components = lastMsg.content as Array<Record<string, unknown>>;
        if (!Array.isArray(components)) return;

        const plainText = extractAnalysisText(components);
        if (!plainText) return;

        lastSpokenMsgIdx.current = messages.length - 1;
        speakAnalysis(plainText);
    }, [ttsEnabled, messages, extractAnalysisText, speakAnalysis]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        const hasText = input.trim().length > 0;
        const hasReadyAttachments = readyAttachments.length > 0;

        if ((!hasText && !hasReadyAttachments) || !isConnected) return;
        // Don't send while uploads are still in flight — prevents losing
        // attachments mid-message.
        if (isProcessingFile) {
            toast.message("Waiting for uploads to finish…");
            return;
        }

        const targetChatId = activeChatId || crypto.randomUUID();

        // Build the agent-facing message: user prompt + structured attachment
        // hints the LLM uses to call read_document / read_spreadsheet / etc.
        // Display message keeps the human-readable filename chips.
        const refs = formatAttachmentRefs(attachments.pending);
        const filenames = readyAttachments
            .map((p) => p.attachment?.filename)
            .filter(Boolean)
            .join(", ");
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

    // Helper to extract file content from a message for preview
    const extractFileContent = (content: string) => {
        // Try to find the first code block
        const codeBlockRegex = /```[\w]*\s*([\s\S]*?)```/g;
        let match;
        while ((match = codeBlockRegex.exec(content)) !== null) {
            // Return the first code block found
            return match[1].trim();
        }
        return "Preview content not available for this message.";
    };

    // Helper to render user message with visual file tokens
    const renderUserMessage = (content: string) => {
        // Cleanup instructions and other boilerplate from full messages in history
        const cleanContent = content
            .replace(/I have uploaded .* to the backend at: `.*`/g, "")
            .replace(/Here is a preview \(first 50 lines\):/g, "")
            .replace(/Please use the `analyze_csv_file` tool .*/g, "")
            .replace(/Here is my data from .*\. Please run various data analyses .*/g, "")
            .replace(/I've attached a file named .*\. Here are the contents:/g, "")
            .replace(/```[\w]*\s*([\s\S]*?)```/g, "") // Remove code blocks from visible bubble
            .trim();

        // Regex to find [Attached File: filename.ext]
        const fileRegex = /\[Attached File: (.*?)\]/g;
        const parts = [];
        let lastIndex = 0;
        let match;

        while ((match = fileRegex.exec(cleanContent)) !== null) {
            // Add text before the match
            if (match.index > lastIndex) {
                const textBefore = cleanContent.substring(lastIndex, match.index).trim();
                if (textBefore) {
                    parts.push(
                        <p key={`text-${lastIndex}`} className="text-sm text-white whitespace-pre-wrap">
                            {textBefore}
                        </p>
                    );
                }
            }
            // ... (rest of the loop is the same)

            // Add the file attachment component
            const fileName = match[1];
            parts.push(
                <button
                    key={`file-${match.index}`}
                    type="button"
                    onClick={() => {
                        const fileContent = extractFileContent(content);
                        setPreviewFile({ name: fileName, content: fileContent });
                    }}
                    className="flex items-center gap-2 px-3 py-2 bg-white/10 border border-white/10 rounded-xl backdrop-blur-md group hover:bg-white/15 hover:border-astral-primary/30 transition-all duration-200 self-start mt-1 mb-1 text-left"
                >
                    <div className="w-8 h-8 rounded-lg bg-astral-primary/20 flex items-center justify-center group-hover:bg-astral-primary/30 transition-colors">
                        <FileText size={16} className="text-astral-primary" />
                    </div>
                    <div className="flex flex-col">
                        <span className="text-xs font-medium text-white truncate max-w-[200px]">{fileName}</span>
                        <span className="text-[10px] text-astral-muted uppercase tracking-wider">Click to Preview</span>
                    </div>
                </button>
            );

            lastIndex = match.index + match[0].length;
        }

        // Add remaining text
        if (lastIndex < cleanContent.length) {
            const remaining = cleanContent.substring(lastIndex).trim();
            if (remaining) {
                parts.push(
                    <p key={`text-${lastIndex}`} className="text-sm text-white whitespace-pre-wrap">
                        {remaining}
                    </p>
                );
            }
        }

        return parts.length > 0 ? parts : <p className="text-sm text-white">{cleanContent || content.split('[Attached File:')[0].trim()}</p>;
    };

    const handleSuggestion = (text: string) => {
        if (!isConnected) return;
        onSendMessage(text);
    };

    /**
     * Stage one or more files: validates against the FR-001 allow-list and
     * 30 MB cap, then uploads each via /api/upload. Multi-file safe.
     */
    const stageFiles = useCallback(async (files: FileList | File[]) => {
        if (!isConnected) return;
        await attachments.upload(files);
    }, [isConnected, attachments]);

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const files = e.target.files;
        if (files && files.length > 0) {
            void stageFiles(files);
        }
        if (fileInputRef.current) {
            fileInputRef.current.value = '';
        }
    };

    // ── Drag and Drop ────────────────────────────────────────────────
    const handleDragOver = useCallback((e: React.DragEvent) => {
        if (!e.dataTransfer.types.includes("Files")) return;
        e.preventDefault();
        e.stopPropagation();
        if (!isDragging) setIsDragging(true);
    }, [isDragging]);

    const handleDragLeave = useCallback((e: React.DragEvent) => {
        if (!e.dataTransfer.types.includes("Files")) return;
        e.preventDefault();
        e.stopPropagation();
        if (e.currentTarget === e.target) {
            setIsDragging(false);
        }
    }, []);

    const handleDrop = useCallback((e: React.DragEvent) => {
        if (!e.dataTransfer.types.includes("Files")) return;
        e.preventDefault();
        e.stopPropagation();
        setIsDragging(false);
        if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            void stageFiles(e.dataTransfer.files);
        }
    }, [stageFiles]);

    return (
        <div
            className="flex flex-col h-full relative"
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
        >
            {/* Drag & Drop Overlay */}
            <AnimatePresence>
                {isDragging && (
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="absolute inset-0 z-50 bg-astral-bg/80 backdrop-blur-sm border-2 border-dashed border-astral-primary/50 rounded-lg flex flex-col items-center justify-center m-4"
                    >
                        <div className="w-20 h-20 rounded-full bg-astral-primary/20 flex items-center justify-center mb-4 pulse-glow">
                            <UploadCloud size={40} className="text-astral-primary" />
                        </div>
                        <h3 className="text-2xl font-bold text-white mb-2">Drop it like it's hot</h3>
                        <p className="text-astral-muted">Upload CSV or text files directly to chat</p>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Messages Area */}
            <div className="flex-1 overflow-y-auto px-3 sm:px-8 py-3 sm:py-4 space-y-4 sm:space-y-6">
                {messages.length === 0 && (
                    <div className="flex flex-col items-center justify-center h-full text-center">
                        <motion.div
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            className="space-y-6"
                        >
                            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-astral-primary to-astral-secondary flex items-center justify-center mx-auto">
                                <Sparkles className="text-white" size={28} />
                            </div>
                            <div>
                                <h2 className="text-xl font-semibold text-white mb-2">
                                    AstralDeep
                                </h2>
                                <p className="text-sm text-astral-muted max-w-lg">
                                    Ask anything — your connected agents will search, analyze, and visualize results as interactive UI components. You can attach files, manage agent permissions in the sidebar, and save components for later.
                                </p>
                            </div>
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 sm:gap-3 max-w-lg">
                                {SUGGESTIONS.map((s, i) => (
                                    <button
                                        key={i}
                                        onClick={() => handleSuggestion(s)}
                                        className="p-3 text-left text-xs text-astral-muted hover:text-white
                               bg-white/5 hover:bg-white/10 rounded-lg border border-white/5
                               hover:border-astral-primary/30 transition-all duration-200"
                                    >
                                        {s}
                                    </button>
                                ))}
                            </div>
                        </motion.div>
                    </div>
                )}

                {messages.map((msg, i) => (
                    <motion.div
                        key={i}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.2 }}
                        className={`flex gap-3 ${msg.role === "user" ? "justify-end" : ""}`}
                    >
                        {msg.role === "assistant" && (
                            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-astral-primary to-astral-secondary flex items-center justify-center flex-shrink-0 mt-1">
                                <Bot size={16} className="text-white" />
                            </div>
                        )}
                        <div
                            className={`${msg.role === "user"
                                ? "max-w-[85%] bg-astral-primary/20 border border-astral-primary/30 rounded-2xl rounded-tr-sm px-3 sm:px-4 py-2.5 sm:py-3"
                                : "flex-1 max-w-[calc(100%-5rem)] min-w-0"
                                }`}
                        >
                            {msg.role === "user" ? (
                                <div className="space-y-2">
                                    {renderUserMessage(msg.content as string)}
                                </div>
                            ) : (
                                <DynamicRenderer
                                    components={msg.content as unknown[]}
                                    onSaveComponent={onSaveComponent}
                                    activeChatId={activeChatId}
                                    onSendMessage={onSendMessage}
                                    onTablePaginate={onTablePaginate}
                                />
                            )}
                        </div>
                        {msg.role === "user" && (
                            <div className="w-8 h-8 rounded-lg bg-white/10 flex items-center justify-center flex-shrink-0 mt-1">
                                <User size={16} className="text-astral-muted" />
                            </div>
                        )}
                    </motion.div>
                ))}

                {/* Feature 014 — persistent step trail (T025). Rendered as a
                    chronological block right after the assistant/user
                    exchange so live and historical entries appear in one
                    consistent location. Entries persist across reloads
                    (sourced from `GET /api/chats/{id}/steps`) and update
                    live via the `chat_step` WebSocket arm. */}
                {chatSteps && Object.keys(chatSteps).length > 0 && (
                    <div data-testid="chat-step-trail" className="ml-11 space-y-1.5">
                        {Object.values(chatSteps)
                            .sort((a, b) => a.started_at - b.started_at)
                            .map((step) => (
                                <ChatStepEntry key={step.id} step={step} />
                            ))}
                    </div>
                )}

                {/* Loading state */}
                <AnimatePresence>
                    {chatStatus.status !== "idle" && chatStatus.status !== "done" && (
                        <motion.div
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0 }}
                            className="flex gap-3"
                        >
                            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-astral-primary to-astral-secondary flex items-center justify-center flex-shrink-0 pulse-glow">
                                <Bot size={16} className="text-white" />
                            </div>
                            <div className="glass-card px-4 py-3 flex items-center gap-3">
                                <Loader2 size={16} className="text-astral-primary animate-spin" />
                                <CosmicProgressIndicator chatStatus={chatStatus} />
                                <button
                                    onClick={onCancelTask}
                                    className="ml-2 p-1.5 rounded-lg bg-white/5 hover:bg-red-500/20 text-astral-muted hover:text-red-400 transition-colors"
                                    title="Stop processing"
                                >
                                    <Square size={12} />
                                </button>
                            </div>
                        </motion.div>
                    )}
                </AnimatePresence>

                <div ref={bottomRef} />
            </div>

            {/* Input Area */}
            <div className="p-2 sm:px-8 sm:py-4 bg-astral-bg/80 backdrop-blur-md safe-bottom">
                <form onSubmit={handleSubmit} className="flex flex-col gap-2 sm:gap-3 mx-auto w-full">

                    {/* Recording Indicator */}
                    <AnimatePresence>
                        {isRecording && (
                            <motion.div
                                initial={{ opacity: 0, y: 6 }}
                                animate={{ opacity: 1, y: 0 }}
                                exit={{ opacity: 0, y: 6 }}
                                className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-red-500/15 border border-red-500/30 text-red-400 text-xs font-medium self-start"
                            >
                                <span className="w-2 h-2 rounded-full bg-red-400 animate-pulse" />
                                Recording your voice...
                            </motion.div>
                        )}
                    </AnimatePresence>

                    {/* Attachment library panel (cross-chat reuse, FR-009) */}
                    {isLibraryOpen && (
                        <div className="self-stretch">
                            <AttachmentLibrary
                                api={attachments}
                                open={isLibraryOpen}
                                onAttach={() => setIsLibraryOpen(false)}
                            />
                        </div>
                    )}

                    {/* Staged attachment chips — feature 002-file-uploads (multi-file safe). */}
                    {attachments.pending.length > 0 && (
                        <div className="flex flex-wrap gap-2 self-start">
                            {attachments.pending.map((p) => {
                                const isError = p.status === "error";
                                const isUploading = p.status === "uploading";
                                return (
                                    <div
                                        key={p.localId}
                                        className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs font-medium ${
                                            isError
                                                ? "bg-red-500/10 border-red-500/30 text-red-400"
                                                : "bg-astral-primary/10 border-astral-primary/30 text-astral-primary"
                                        }`}
                                    >
                                        {isUploading ? (
                                            <Loader2 size={14} className="animate-spin" />
                                        ) : (
                                            <FileMinus size={14} className={isError ? "text-red-400" : "text-astral-primary"} />
                                        )}
                                        <span className="truncate max-w-[200px]" title={p.filename}>
                                            {p.filename}
                                        </span>
                                        {p.attachment && (
                                            <span className="text-[10px] uppercase tracking-wide opacity-60">
                                                {p.attachment.category}
                                            </span>
                                        )}
                                        {isError && p.source && (
                                            <button
                                                type="button"
                                                onClick={(e) => { e.stopPropagation(); void attachments.retry(p.localId); }}
                                                className="p-1 rounded-md hover:bg-white/10"
                                                title="Retry upload"
                                            >
                                                <RotateCcw size={12} />
                                            </button>
                                        )}
                                        <button
                                            type="button"
                                            onClick={(e) => { e.stopPropagation(); attachments.remove(p.localId); }}
                                            className="p-1 rounded-md hover:bg-white/10"
                                            title="Remove"
                                        >
                                            <X size={12} />
                                        </button>
                                        {isError && p.error && (
                                            <span className="ml-1 text-[10px] opacity-90">{p.error.message}</span>
                                        )}
                                    </div>
                                );
                            })}
                        </div>
                    )}

                    <div className="flex gap-2 sm:gap-3">
                        <div className="flex-1 relative flex items-center gap-1 sm:gap-2 bg-astral-surface/60 border border-white/10 rounded-xl px-1.5 sm:px-2 transition-all focus-within:border-astral-primary/50 focus-within:ring-1 focus-within:ring-astral-primary/20">

                            {/* File Upload Button inside input wrapper */}
                            <button
                                type="button"
                                onClick={() => fileInputRef.current?.click()}
                                disabled={!isConnected}
                                className="p-2 text-astral-muted hover:text-white rounded-lg hover:bg-white/10 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0"
                                title="Attach files"
                            >
                                {isProcessingFile ? (
                                    <Loader2 size={20} className="animate-spin text-astral-primary" />
                                ) : (
                                    <Paperclip size={20} />
                                )}
                            </button>
                            <button
                                type="button"
                                onClick={() => setIsLibraryOpen((v) => !v)}
                                disabled={!isConnected}
                                className={`p-2 rounded-lg hover:bg-white/10 transition-colors flex-shrink-0 ${
                                    isLibraryOpen ? "text-astral-primary" : "text-astral-muted hover:text-white"
                                } disabled:opacity-50 disabled:cursor-not-allowed`}
                                title="Browse your uploaded files"
                                data-testid="attachment-library-toggle"
                            >
                                <FolderOpen size={20} />
                            </button>
                            <input
                                type="file"
                                className="hidden"
                                ref={fileInputRef}
                                onChange={handleFileChange}
                                accept={ACCEPT_ATTRIBUTE}
                                multiple
                            />

                            <textarea
                                ref={textareaRef}
                                rows={1}
                                value={isRecording || isTranscribing ? streamingTranscript || "" : input}
                                onChange={(e) => { if (!isRecording && !isTranscribing) setInput(e.target.value); }}
                                onKeyDown={(e) => {
                                    // Skip while IME composition is active so Enter commits the candidate
                                    // instead of submitting the message.
                                    if (e.nativeEvent.isComposing || e.keyCode === 229) return;
                                    if (e.key === "Enter" && !e.shiftKey) {
                                        e.preventDefault();
                                        e.currentTarget.form?.requestSubmit();
                                    }
                                }}
                                placeholder={
                                    isRecording
                                        ? "Listening..."
                                        : isTranscribing
                                            ? "Transcribing..."
                                            : isConnected
                                                ? "Ask anything or attach a file..."
                                                : "Connecting to orchestrator..."
                                }
                                disabled={!isConnected || isRecording || isTranscribing || (chatStatus.status !== "idle" && chatStatus.status !== "done")}
                                className="w-full py-3 bg-transparent text-sm text-white placeholder:text-astral-muted/50
                             focus:outline-none disabled:opacity-50 resize-none overflow-y-auto
                             max-h-[9rem] leading-6"
                                id="chat-input"
                                aria-label="Chat message input"
                            />

                            {/* Mic (STT) Button — only shown when device has mic AND speech server is available */}
                            {canUseVoiceInput && (
                                <button
                                    type="button"
                                    onClick={isRecording ? stopRecording : startRecording}
                                    disabled={!isConnected || isTranscribing || (chatStatus.status !== "idle" && chatStatus.status !== "done")}
                                    className={`p-2 rounded-lg transition-colors flex-shrink-0 ${
                                        isRecording
                                            ? "text-red-400 hover:text-red-300 bg-red-500/20"
                                            : "text-astral-muted hover:text-white hover:bg-white/10"
                                    } disabled:opacity-50 disabled:cursor-not-allowed`}
                                    title={isRecording ? "Stop recording" : "Voice input"}
                                >
                                    {isTranscribing ? (
                                        <Loader2 size={20} className="animate-spin text-astral-primary" />
                                    ) : isRecording ? (
                                        <Square size={16} />
                                    ) : (
                                        <Mic size={20} />
                                    )}
                                </button>
                            )}

                            {/* TTS Toggle Button — only shown when speech server is available */}
                            {canUseVoiceOutput && (
                                <button
                                    type="button"
                                    onClick={() => {
                                        setTtsEnabled((prev) => !prev);
                                        if (ttsEnabled && audioRef.current) {
                                            audioRef.current.pause();
                                            audioRef.current = null;
                                            setIsSpeaking(false);
                                        }
                                    }}
                                    className={`p-2 rounded-lg transition-colors flex-shrink-0 ${
                                        ttsEnabled
                                            ? "text-astral-primary bg-astral-primary/20"
                                            : "text-astral-muted hover:text-white hover:bg-white/10"
                                    }`}
                                    title={ttsEnabled ? "Disable voice output" : "Enable voice output"}
                                >
                                    {isSpeaking ? (
                                        <Volume2 size={20} className="animate-pulse" />
                                    ) : ttsEnabled ? (
                                        <Volume2 size={20} />
                                    ) : (
                                        <VolumeX size={20} />
                                    )}
                                </button>
                            )}
                        </div>
                        <button
                            type="submit"
                            disabled={(!input.trim() && readyAttachments.length === 0) || !isConnected || isProcessingFile || (chatStatus.status !== "idle" && chatStatus.status !== "done")}
                            className="px-3 sm:px-4 py-2.5 sm:py-3 rounded-xl bg-astral-primary hover:bg-astral-primary/80
                           disabled:opacity-30 disabled:cursor-not-allowed
                           transition-colors flex items-center gap-2 flex-shrink-0"
                            id="chat-submit"
                        >
                            <Send size={16} className="text-white" />
                        </button>
                    </div>
                </form>
            </div>

            {/* Saved Components Drawer */}
            <UISavedDrawer
                isOpen={isDrawerOpen}
                onClose={() => setIsDrawerOpen(false)}
                onOpen={() => setIsDrawerOpen(true)}
                savedComponents={savedComponents}
                onDeleteComponent={onDeleteSavedComponent}
                onCombineComponents={onCombineComponents}
                onCondenseComponents={onCondenseComponents}
                onCancelCombine={onCancelCombine}
                isCombining={isCombining}
                combineError={combineError}
                activeChatId={activeChatId}
            />

            {/* File Preview Modal */}
            <AnimatePresence>
                {previewFile && (
                    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6 lg:p-8">
                        <motion.div
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                            onClick={() => setPreviewFile(null)}
                            className="absolute inset-0 bg-astral-bg/80 backdrop-blur-md"
                        />
                        <motion.div
                            initial={{ opacity: 0, scale: 0.95, y: 20 }}
                            animate={{ opacity: 1, scale: 1, y: 0 }}
                            exit={{ opacity: 0, scale: 0.95, y: 20 }}
                            className="relative w-full max-w-5xl max-h-[85vh] bg-astral-surface/90 border border-white/10 rounded-2xl shadow-2xl flex flex-col overflow-hidden glass-card"
                        >
                            {/* Header */}
                            <div className="flex items-center justify-between p-4 border-b border-white/5 bg-white/5">
                                <div className="flex items-center gap-3">
                                    <div className="w-10 h-10 rounded-xl bg-astral-primary/20 flex items-center justify-center text-astral-primary shadow-inner">
                                        <FileText size={20} />
                                    </div>
                                    <div>
                                        <h3 className="text-lg font-bold text-white leading-tight">{previewFile.name}</h3>
                                        <p className="text-xs text-astral-muted">File Preview</p>
                                    </div>
                                </div>
                                <button
                                    onClick={() => setPreviewFile(null)}
                                    className="p-2 rounded-xl hover:bg-white/10 transition-colors text-astral-muted hover:text-white"
                                >
                                    <X size={20} />
                                </button>
                            </div>

                            {/* Content */}
                            <div className="flex-1 overflow-auto p-6 bg-[#0B0E14]">
                                <pre className="text-sm font-mono text-astral-muted selection:bg-astral-primary/30 selection:text-white leading-relaxed">
                                    <code>{previewFile.content}</code>
                                </pre>
                            </div>

                            {/* Footer */}
                            <div className="p-3 border-t border-white/5 bg-white/5 text-right">
                                <button
                                    onClick={() => setPreviewFile(null)}
                                    className="px-6 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-white font-medium transition-colors border border-white/5"
                                >
                                    Close
                                </button>
                            </div>
                        </motion.div>
                    </div>
                )}
            </AnimatePresence>

            {/* Drawer Toggle Button */}
            <AnimatePresence>
                {!isDrawerOpen && savedComponents.length > 0 && (
                    <motion.button
                        key="drawer-toggle"
                        initial={{ x: 60, opacity: 0 }}
                        animate={{ x: 0, opacity: 1 }}
                        exit={{ x: 60, opacity: 0 }}
                        transition={{ type: "spring", damping: 25, stiffness: 300 }}
                        onClick={() => setIsDrawerOpen(true)}
                        className="fixed right-0 top-1/2 -translate-y-1/2 z-30 bg-astral-surface/80 hover:bg-astral-surface border border-white/10 border-r-0 p-2 rounded-l-xl shadow-lg transition-colors duration-200 flex flex-col items-center justify-center group"
                        aria-label="Open saved components drawer"
                    >
                        <ChevronLeft size={24} className="text-astral-muted group-hover:text-white transition-colors" />
                        <div className="absolute -top-2 -left-2 bg-astral-primary text-white text-[10px] w-5 h-5 rounded-full flex items-center justify-center shadow-sm">
                            {savedComponents.length}
                        </div>
                    </motion.button>
                )}
            </AnimatePresence>
        </div>
    );
}
