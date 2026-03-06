/**
 * ChatInterface — Real-time chat with the orchestrator.
 *
 * Features:
 * - Message input with send button
 * - Chat history display (user + assistant messages)
 * - Loading states (thinking, executing)
 * - Dynamic UI rendering for assistant responses via DynamicRenderer
 */
import React, { useState, useRef, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Send, Bot, User, Sparkles, Loader2, ChevronLeft, Paperclip, UploadCloud, X, FileMinus, FileText, Square, Mic, Volume2, VolumeX } from "lucide-react";
import { toast } from "sonner";
import DynamicRenderer from "./DynamicRenderer";
import type { TablePaginateEvent } from "./DynamicRenderer";
import UISavedDrawer from "./UISavedDrawer";
import { BFF_URL } from "../config";
import type { ChatStatus, DeviceCapabilityFlags } from "../hooks/useWebSocket";

interface ChatInterfaceProps {
    messages: { role: string; content: unknown }[];
    chatStatus: ChatStatus;
    onSendMessage: (message: string, displayMessage?: string, explicitChatId?: string) => void;
    onCancelTask: () => void;
    isConnected: boolean;
    activeChatId: string | null;
    savedComponents: Array<{ id: string; chat_id: string; component_data: Record<string, unknown>; component_type: string; title: string; created_at: number }>;
    onSaveComponent: (componentData: Record<string, unknown>, componentType: string) => Promise<boolean>;
    onDeleteSavedComponent: (componentId: string) => void;
    onCombineComponents: (sourceId: string, targetId: string) => void;
    onCondenseComponents: (componentIds: string[]) => void;
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
    onSendMessage,
    onCancelTask,
    isConnected,
    activeChatId,
    savedComponents,
    onSaveComponent,
    onDeleteSavedComponent,
    onCombineComponents,
    onCondenseComponents,
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
    const [isProcessingFile, setIsProcessingFile] = useState(false);

    // File Staging State
    const [attachedFile, setAttachedFile] = useState<File | null>(null);
    const [fileContent, setFileContent] = useState<string | null>(null);
    const [fileError, setFileError] = useState<string | null>(null);
    const [previewFile, setPreviewFile] = useState<{ name: string; content: string } | null>(null);

    const bottomRef = useRef<HTMLDivElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

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

    // Geolocation — silently acquire once when capability is confirmed
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

    const clearAttachment = () => {
        setAttachedFile(null);
        setFileContent(null);
        setFileError(null);
        if (fileInputRef.current) {
            fileInputRef.current.value = '';
        }
    };

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

            let streamingActive = false;
            let gotTranscription = false;

            // Open streaming WebSocket
            const wsScheme = window.location.protocol === "https:" ? "wss" : "ws";
            const voiceWsUrl = `${wsScheme}://${window.location.host}/api/voice/stream`;
            const voiceWs = new WebSocket(voiceWsUrl);
            voiceWsRef.current = voiceWs;

            voiceWs.onopen = () => {
                streamingActive = true;
            };

            // Stream raw PCM16 audio to the WebSocket, downsampling if needed
            processor.onaudioprocess = (e) => {
                if (streamingActive && voiceWs.readyState === WebSocket.OPEN) {
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
                    voiceWs.send(pcm16);
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
                console.warn("Voice stream WebSocket error");
                streamingActive = false;
            };

            voiceWs.onclose = () => {
                voiceWsRef.current = null;
                // Clean up audio pipeline
                try { processor.disconnect(); } catch { /* already disconnected */ }
                try { source.disconnect(); } catch { /* already disconnected */ }
                try { audioCtx.close(); } catch { /* already closed */ }
                audioContextRef.current = null;

                if (!gotTranscription) {
                    // Streaming failed — fall back to batch transcription
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
                }
            };

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
        const hasFile = attachedFile !== null;

        if ((!hasText && !hasFile) || !isConnected) return;

        if (hasFile && attachedFile) {
            if (fileError) {
                onSendMessage(`System Note: The user tried to upload a file (${attachedFile.name}) but there was an error: ${fileError}. Try to explain to the user what went wrong.`);
            } else if (fileContent) {
                const targetChatId = activeChatId || crypto.randomUUID();

                // If file is large (> 10KB), upload it and send path + preview
                const isLarge = attachedFile.size > 10 * 1024;

                if (isLarge) {
                    setIsProcessingFile(true);
                    try {
                        const formData = new FormData();
                        formData.append('file', attachedFile);
                        formData.append('session_id', targetChatId);

                        const uploadUrl = `${BFF_URL}/api/upload`;
                        const headers: HeadersInit = {};
                        if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;

                        const uploadRes = await fetch(uploadUrl, {
                            method: 'POST',
                            headers,
                            body: formData
                        });

                        if (!uploadRes.ok) throw new Error("File upload failed");
                        const data = await uploadRes.json();
                        const filePath = data.file_path;

                        // Create a truncated preview
                        const lines = fileContent.split(/\r?\n/);
                        const preview = lines.slice(0, 50).join('\n');
                        const isTruncated = lines.length > 50;
                        const truncatedContent = isTruncated ? `${preview}\n... [TRUNCATED: ${lines.length - 50} more lines]` : preview;

                        const promptPrefix = hasText ? `${input.trim()}\n\n` : '';
                        const displayMsg = `${promptPrefix}[Attached File: ${attachedFile.name}]\n\n\`\`\`\n${truncatedContent}\n\`\`\``;

                        const fullMsg = `${promptPrefix}I have uploaded ${attachedFile.name} to the backend at: \`${filePath}\`
 
 Here is a preview (first 50 lines):
 \`\`\`${attachedFile.name.toLowerCase().endsWith('.csv') ? 'csv' : 'text'}
 ${truncatedContent}
 \`\`\`
 
 Please use the provided absolute \`file_path\` with an appropriate tool (like \`analyze_csv_file\`) to handle this request. Only use \`modify_data\` if the user explicitly asks to edit the file or add columns.`;

                        onSendMessage(enrichWithLocation(fullMsg), displayMsg, targetChatId);
                    } catch (err: unknown) {
                        const errorMessage = err instanceof Error ? err.message : String(err);
                        console.error("Upload error:", err);
                        toast.error(`File upload failed: ${errorMessage}`);
                        onSendMessage(`System Note: Failed to upload large file ${attachedFile.name}: ${errorMessage}. The model might fail if the full file is sent instead.`, undefined, targetChatId);
                    } finally {
                        setIsProcessingFile(false);
                    }
                } else {
                    // Original small file logic
                    if (attachedFile.name.toLowerCase().endsWith('.csv')) {
                        const prompt = hasText ? `${input.trim()}\n\n` : '';
                        const displayMsg = `${prompt}[Attached File: ${attachedFile.name}]\n\n\`\`\`csv\n${fileContent}\n\`\`\``;
                        onSendMessage(enrichWithLocation(`${prompt}Here is my data from ${attachedFile.name}. Please run various data analyses on it and tell me the results:\n\n\`\`\`csv\n${fileContent}\n\`\`\``), displayMsg, targetChatId);
                    } else {
                        const prompt = hasText ? `${input.trim()}\n\n` : '';
                        const displayMsg = `${prompt}[Attached File: ${attachedFile.name}]\n\n\`\`\`text\n${fileContent}\n\`\`\``;
                        onSendMessage(enrichWithLocation(`${prompt}I've attached a file named ${attachedFile.name}. Here are the contents:\n\n\`\`\`text\n${fileContent}\n\`\`\``), displayMsg, targetChatId);
                    }
                }
            }
        } else if (hasText) {
            const targetChatId = activeChatId || crypto.randomUUID();
            onSendMessage(enrichWithLocation(input.trim()), input.trim(), targetChatId);
        }

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

    const processFile = useCallback((file: File) => {
        if (!file || !isConnected) return;

        setIsProcessingFile(true);
        const reader = new FileReader();

        reader.onload = (event) => {
            try {
                const text = event.target?.result as string;
                if (!text) throw new Error("File is empty");

                setFileContent(text);
                setAttachedFile(file);
                setFileError(null);

                // If it's a CSV, ensure it's not completely empty
                if (file.name.toLowerCase().endsWith('.csv')) {
                    const lines = text.split(/\r?\n/).filter(line => line.trim() !== '');
                    if (lines.length === 0) throw new Error("CSV file contains no data");
                }
            } catch (err: unknown) {
                setAttachedFile(file);
                setFileError(err instanceof Error ? err.message : "Failed to parse file.");
                setFileContent(null);
            } finally {
                setIsProcessingFile(false);
            }
        };

        reader.onerror = () => {
            setIsProcessingFile(false);
            setAttachedFile(file);
            setFileError("Error reading file. The browser failed to process it.");
            setFileContent(null);
        };

        reader.readAsText(file);
    }, [isConnected]);

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (file) {
            processFile(file);
        }
        // Reset input so the same file can be uploaded again if needed
        if (fileInputRef.current) {
            fileInputRef.current.value = '';
        }
    };

    // Drag and Drop Handlers
    const handleDragOver = useCallback((e: React.DragEvent) => {
        // Only react to file drag events, ignore component drags from drawer
        if (!e.dataTransfer.types.includes("Files")) return;

        e.preventDefault();
        e.stopPropagation();
        if (!isDragging) setIsDragging(true);
    }, [isDragging]);

    const handleDragLeave = useCallback((e: React.DragEvent) => {
        if (!e.dataTransfer.types.includes("Files")) return;

        e.preventDefault();
        e.stopPropagation();
        // Prevent flickering when dragging over children
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
            const file = e.dataTransfer.files[0];
            processFile(file);
        }
    }, [processFile]);

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
                                <p className="text-sm text-astral-muted max-w-md">
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
                                <span className="text-sm text-astral-muted">
                                    {chatStatus.message || "Processing..."}
                                </span>
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

                    {/* Staged File View */}
                    <AnimatePresence>
                        {attachedFile && (
                            <motion.div
                                initial={{ opacity: 0, y: 10 }}
                                animate={{ opacity: 1, y: 0 }}
                                exit={{ opacity: 0, scale: 0.95 }}
                                className="self-start"
                            >
                                <div className={`flex items-center gap-3 px-3 py-2 rounded-lg border ${fileError ? 'bg-red-500/10 border-red-500/30 text-red-400' : 'bg-astral-primary/10 border-astral-primary/30 text-astral-primary'} backdrop-blur-sm text-sm font-medium`}>
                                    <FileMinus size={16} className={fileError ? 'text-red-400' : 'text-astral-primary'} />
                                    <span className="truncate max-w-[200px]">{attachedFile.name}</span>
                                    <button
                                        type="button"
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            clearAttachment();
                                        }}
                                        className="p-1 rounded-md hover:bg-white/10 transition-colors ml-2"
                                        title="Remove File"
                                    >
                                        <X size={14} />
                                    </button>
                                </div>
                                {fileError && (
                                    <p className="text-xs text-red-400 mt-1 ml-1">{fileError}</p>
                                )}
                            </motion.div>
                        )}
                    </AnimatePresence>

                    <div className="flex gap-2 sm:gap-3">
                        <div className="flex-1 relative flex items-center gap-1 sm:gap-2 bg-astral-surface/60 border border-white/10 rounded-xl px-1.5 sm:px-2 transition-all focus-within:border-astral-primary/50 focus-within:ring-1 focus-within:ring-astral-primary/20">

                            {/* File Upload Button inside input wrapper */}
                            <button
                                type="button"
                                onClick={() => fileInputRef.current?.click()}
                                disabled={!isConnected || isProcessingFile}
                                className="p-2 text-astral-muted hover:text-white rounded-lg hover:bg-white/10 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0"
                                title="Attach File"
                            >
                                {isProcessingFile ? (
                                    <Loader2 size={20} className="animate-spin text-astral-primary" />
                                ) : (
                                    <Paperclip size={20} />
                                )}
                            </button>
                            <input
                                type="file"
                                className="hidden"
                                ref={fileInputRef}
                                onChange={handleFileChange}
                                accept=".csv,.txt,.json,.md"
                            />

                            <input
                                type="text"
                                value={isRecording || isTranscribing ? streamingTranscript || "" : input}
                                onChange={(e) => { if (!isRecording && !isTranscribing) setInput(e.target.value); }}
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
                             focus:outline-none disabled:opacity-50"
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
                            disabled={(!input.trim() && !attachedFile) || !isConnected || (chatStatus.status !== "idle" && chatStatus.status !== "done")}
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
