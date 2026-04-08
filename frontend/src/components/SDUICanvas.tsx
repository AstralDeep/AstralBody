/**
 * SDUICanvas — Main dynamic SDUI canvas area.
 *
 * Displays streamed UI components in a responsive grid with:
 * - Drag-and-drop to combine components (HTML5 DnD + touch)
 * - Collapse/expand individual components
 * - "Condense" button to merge all compatible components
 * - Auto-arranging responsive grid layout
 *
 * Derived from UISavedDrawer.tsx, adapted as the primary content area.
 */
import React, { useState, useRef, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, ChevronUp, Trash2, Loader2, Layers, GripVertical, AlertCircle, Sparkles, Minimize2, Maximize2, X } from "lucide-react";
import DynamicRenderer from "./DynamicRenderer";
import type { TablePaginateEvent } from "./DynamicRenderer";
import type { SavedComponent } from "../hooks/useWebSocket";

const SUGGESTIONS = [
    "Get me all patients over 30 and graph their ages",
    "What is my system's CPU and memory usage?",
    "Search Wikipedia for artificial intelligence",
    "Show me disk usage information",
];

interface SDUICanvasProps {
    canvasComponents: SavedComponent[];
    onDeleteComponent: (componentId: string) => void;
    onCombineComponents: (sourceId: string, targetId: string) => void;
    onCondenseComponents: (componentIds: string[]) => void;
    isCombining: boolean;
    combineError: string | null;
    onTablePaginate?: (event: TablePaginateEvent) => void;
    onSendMessage: (message: string) => void;
    activeChatId: string | null;
}

export default function SDUICanvas({
    canvasComponents,
    onDeleteComponent,
    onCombineComponents,
    onCondenseComponents,
    isCombining,
    combineError,
    onTablePaginate,
    onSendMessage,
    activeChatId,
}: SDUICanvasProps) {
    const [collapsedComponents, setCollapsedComponents] = useState<Set<string>>(new Set());
    const [dragOverId, setDragOverId] = useState<string | null>(null);
    const [draggedId, setDraggedId] = useState<string | null>(null);
    const dragCounterRef = useRef<Map<string, number>>(new Map());

    // Fullscreen: which component is expanded to full screen (null = none)
    const [fullscreenId, setFullscreenId] = useState<string | null>(null);

    // Adaptive sizing: tracks whether content overflows the viewport
    // Levels: 0 = normal, 1 = compact (smaller max-h), 2 = all collapsed, 3 = trigger auto-condense
    const [sizeLevel, setSizeLevel] = useState(0);
    const autoCondenseTriggeredRef = useRef(false);
    const prevComponentCountRef = useRef(0);

    // Touch drag-and-drop state
    const touchDragRef = useRef<{
        componentId: string;
        isDragging: boolean;
        offsetX: number;
        offsetY: number;
        clone: HTMLElement | null;
    }>({ componentId: '', isDragging: false, offsetX: 0, offsetY: 0, clone: null });
    const touchTargetRef = useRef<string | null>(null);
    const scrollContainerRef = useRef<HTMLDivElement>(null);

    // Non-passive touchmove listener to prevent scrolling during touch drag
    useEffect(() => {
        const container = scrollContainerRef.current;
        if (!container) return;
        const onTouchMove = (e: TouchEvent) => {
            if (touchDragRef.current.isDragging) e.preventDefault();
        };
        container.addEventListener('touchmove', onTouchMove, { passive: false });
        return () => {
            container.removeEventListener('touchmove', onTouchMove);
            if (touchDragRef.current.clone) {
                touchDragRef.current.clone.remove();
            }
        };
    }, []);

    // Reset size level and auto-condense flag when component count changes significantly
    useEffect(() => {
        const prevCount = prevComponentCountRef.current;
        const curCount = canvasComponents.length;
        // Reset when components are removed (e.g. after condense) or cleared
        if (curCount < prevCount || curCount === 0) {
            setSizeLevel(0);
            autoCondenseTriggeredRef.current = false;
        }
        prevComponentCountRef.current = curCount;
    }, [canvasComponents.length]);

    // Detect overflow and escalate size level
    const checkOverflow = useCallback(() => {
        const container = scrollContainerRef.current;
        if (!container || canvasComponents.length < 2) return;

        const isOverflowing = container.scrollHeight > container.clientHeight + 20;

        if (isOverflowing && sizeLevel === 0) {
            // Step 1: switch to compact mode (smaller max-heights)
            setSizeLevel(1);
        } else if (isOverflowing && sizeLevel === 1) {
            // Step 2: auto-collapse all components
            setSizeLevel(2);
            setCollapsedComponents(new Set(canvasComponents.map(c => c.id)));
        } else if (isOverflowing && sizeLevel === 2 && !autoCondenseTriggeredRef.current && !isCombining) {
            // Step 3: trigger auto-condense
            autoCondenseTriggeredRef.current = true;
            const ids = canvasComponents.map(c => c.id);
            onCondenseComponents(ids);
        }
    }, [canvasComponents, sizeLevel, isCombining, onCondenseComponents]);

    // Run overflow check after render when components change or size level changes
    useEffect(() => {
        if (canvasComponents.length < 2) return;
        // Delay to let the DOM settle after render
        const timer = setTimeout(checkOverflow, 300);
        return () => clearTimeout(timer);
    }, [canvasComponents.length, sizeLevel, checkOverflow]);

    // Get max-height for component content based on current size level and component count
    const getContentMaxHeight = () => {
        const count = canvasComponents.length;
        if (sizeLevel >= 2) return '0px'; // collapsed
        if (sizeLevel === 1 || count > 6) return '150px';
        if (count > 4) return '200px';
        return '400px';
    };

    const getComponentSpan = (type: string) => {
        const count = canvasComponents.length;

        // In collapsed or compact mode, everything fits in single cells
        if (sizeLevel >= 2) return 'col-span-1';
        if (sizeLevel === 1) {
            // Compact: charts/tables get 2 cols max, everything else single
            switch (type.toLowerCase()) {
                case 'bar_chart': case 'line_chart': case 'pie_chart':
                case 'plotly_chart': case 'table':
                    return 'col-span-1 md:col-span-2';
                default:
                    return 'col-span-1';
            }
        }

        if (count <= 2) {
            switch (type.toLowerCase()) {
                case 'metric':
                case 'alert':
                case 'progress':
                case 'button':
                    return 'col-span-1';
                default:
                    return 'col-span-full';
            }
        }

        if (count <= 4) {
            switch (type.toLowerCase()) {
                case 'bar_chart':
                case 'line_chart':
                case 'pie_chart':
                case 'plotly_chart':
                case 'table':
                    return 'col-span-full';
                case 'card':
                case 'grid':
                case 'list':
                case 'text':
                case 'code':
                case 'collapsible':
                    return 'col-span-1 md:col-span-1 lg:col-span-2 xl:col-span-2 2xl:col-span-2';
                case 'metric':
                case 'alert':
                case 'progress':
                case 'button':
                default:
                    return 'col-span-1';
            }
        }

        switch (type.toLowerCase()) {
            case 'bar_chart':
            case 'line_chart':
            case 'pie_chart':
            case 'plotly_chart':
            case 'table':
                return 'col-span-1 md:col-span-2 lg:col-span-3 xl:col-span-3 2xl:col-span-4';
            case 'card':
            case 'grid':
            case 'list':
            case 'text':
            case 'code':
            case 'collapsible':
                return 'col-span-1 md:col-span-2 lg:col-span-2 xl:col-span-2';
            case 'metric':
            case 'alert':
            case 'progress':
            case 'button':
            default:
                return 'col-span-1';
        }
    };

    const getGridColsClass = () => {
        const count = canvasComponents.length;
        if (sizeLevel >= 2) {
            // Collapsed mode: pack tightly
            return 'grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6';
        }
        if (sizeLevel === 1 || count > 6) {
            // Compact mode: more columns
            return 'grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5';
        }
        if (count <= 2) return 'grid-cols-1 md:grid-cols-2';
        if (count <= 4) return 'grid-cols-1 md:grid-cols-2 lg:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4';
        return 'grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5';
    };

    const toggleCollapse = (id: string) => {
        setCollapsedComponents(prev => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });
    };

    // HTML5 Drag and Drop handlers
    const handleDragStart = (e: React.DragEvent, componentId: string) => {
        e.dataTransfer.setData("text/plain", componentId);
        e.dataTransfer.effectAllowed = "move";
        setDraggedId(componentId);
    };

    const handleDragEnd = () => {
        setDraggedId(null);
        setDragOverId(null);
        dragCounterRef.current.clear();
    };

    const handleDragEnter = (e: React.DragEvent, targetId: string) => {
        e.preventDefault();
        e.stopPropagation();
        const count = (dragCounterRef.current.get(targetId) || 0) + 1;
        dragCounterRef.current.set(targetId, count);
        if (draggedId && targetId !== draggedId) setDragOverId(targetId);
    };

    const handleDragOver = (e: React.DragEvent, targetId: string) => {
        e.preventDefault();
        e.stopPropagation();
        if (draggedId && targetId !== draggedId) e.dataTransfer.dropEffect = "move";
    };

    const handleDragLeave = (e: React.DragEvent, targetId: string) => {
        e.preventDefault();
        e.stopPropagation();
        const count = (dragCounterRef.current.get(targetId) || 0) - 1;
        dragCounterRef.current.set(targetId, count);
        if (count <= 0) {
            dragCounterRef.current.delete(targetId);
            if (dragOverId === targetId) setDragOverId(null);
        }
    };

    const handleDrop = (e: React.DragEvent, targetId: string) => {
        e.preventDefault();
        e.stopPropagation();
        const sourceId = e.dataTransfer.getData("text/plain");
        dragCounterRef.current.clear();
        setDragOverId(null);
        setDraggedId(null);
        if (sourceId && sourceId !== targetId && !isCombining) {
            onCombineComponents(sourceId, targetId);
        }
    };

    const handleCondense = () => {
        if (canvasComponents.length < 2 || isCombining) return;
        const ids = canvasComponents.map(c => c.id);
        onCondenseComponents(ids);
    };

    // Touch drag-and-drop handlers
    const handleTouchStart = (e: React.TouchEvent, componentId: string) => {
        if (isCombining) return;
        e.stopPropagation();
        const ref = touchDragRef.current;
        ref.componentId = componentId;
        ref.isDragging = true;
        setDraggedId(componentId);
        if (navigator.vibrate) navigator.vibrate(30);

        const touch = e.touches[0];
        const card = (e.currentTarget as HTMLElement).closest('[data-component-id]') as HTMLElement | null;
        if (card) {
            const rect = card.getBoundingClientRect();
            const clone = card.cloneNode(true) as HTMLElement;
            Object.assign(clone.style, {
                position: 'fixed',
                width: `${rect.width}px`,
                left: `${touch.clientX - rect.width / 2}px`,
                top: `${touch.clientY - 24}px`,
                opacity: '0.85',
                pointerEvents: 'none',
                zIndex: '9999',
                transform: 'scale(0.92)',
                boxShadow: '0 20px 60px rgba(0,0,0,0.5)',
                borderRadius: '12px',
                transition: 'none',
                overflow: 'hidden',
                maxHeight: `${rect.height}px`,
            });
            document.body.appendChild(clone);
            ref.clone = clone;
            ref.offsetX = rect.width / 2;
            ref.offsetY = 24;
        }
    };

    const handleTouchMove = (e: React.TouchEvent) => {
        const ref = touchDragRef.current;
        if (!ref.isDragging) return;
        const touch = e.touches[0];

        if (ref.clone) {
            ref.clone.style.left = `${touch.clientX - ref.offsetX}px`;
            ref.clone.style.top = `${touch.clientY - ref.offsetY}px`;
        }

        if (ref.clone) ref.clone.style.visibility = 'hidden';
        const el = document.elementFromPoint(touch.clientX, touch.clientY);
        if (ref.clone) ref.clone.style.visibility = 'visible';

        if (el) {
            const card = el.closest<HTMLElement>('[data-component-id]');
            if (card) {
                const targetId = card.dataset.componentId ?? null;
                if (targetId && targetId !== ref.componentId) {
                    touchTargetRef.current = targetId;
                    setDragOverId(targetId);
                    return;
                }
            }
        }
        touchTargetRef.current = null;
        setDragOverId(null);
    };

    const removeTouchClone = () => {
        const ref = touchDragRef.current;
        if (ref.clone) {
            ref.clone.remove();
            ref.clone = null;
        }
    };

    const handleTouchEnd = () => {
        const ref = touchDragRef.current;
        const targetId = touchTargetRef.current;
        removeTouchClone();
        if (ref.isDragging && targetId && targetId !== ref.componentId && !isCombining) {
            onCombineComponents(ref.componentId, targetId);
        }
        ref.isDragging = false;
        ref.componentId = '';
        touchTargetRef.current = null;
        setDraggedId(null);
        setDragOverId(null);
    };

    const handleTouchCancel = () => {
        removeTouchClone();
        touchDragRef.current.isDragging = false;
        touchDragRef.current.componentId = '';
        touchTargetRef.current = null;
        setDraggedId(null);
        setDragOverId(null);
    };

    const handleSuggestion = (suggestion: string) => {
        onSendMessage(suggestion);
    };

    return (
        <div className="flex-1 flex flex-col overflow-hidden relative">
            {/* Toolbar — only visible when components exist */}
            {canvasComponents.length > 0 && (
                <div className="flex items-center justify-between px-4 sm:px-6 py-3 border-b border-white/10 bg-astral-bg/50 backdrop-blur-sm flex-shrink-0">
                    <div className="flex items-center gap-3">
                        <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-astral-primary to-astral-secondary flex items-center justify-center">
                            <Layers size={14} className="text-white" />
                        </div>
                        <span className="text-sm font-medium text-white">
                            {canvasComponents.length} component{canvasComponents.length !== 1 ? 's' : ''}
                        </span>
                    </div>
                    <div className="flex items-center gap-2">
                        {sizeLevel > 0 && (
                            <button
                                onClick={() => {
                                    setSizeLevel(0);
                                    setCollapsedComponents(new Set());
                                    autoCondenseTriggeredRef.current = false;
                                }}
                                className="px-2.5 py-1.5 text-xs font-medium rounded-lg
                                         bg-white/5 border border-white/10 text-astral-muted
                                         hover:border-white/20 hover:text-white
                                         transition-all duration-200 flex items-center gap-1.5"
                                title="Expand all components"
                            >
                                <Minimize2 size={12} />
                                {sizeLevel === 1 ? "Compact" : "Collapsed"}
                            </button>
                        )}
                        {canvasComponents.length >= 2 && (
                            <button
                                onClick={handleCondense}
                                disabled={isCombining}
                                className="px-3 py-1.5 text-xs font-medium rounded-lg
                                         bg-gradient-to-r from-purple-500/20 to-astral-primary/20
                                         border border-purple-500/30 text-purple-300
                                         hover:border-purple-400/50 hover:text-purple-200
                                         disabled:opacity-40 disabled:cursor-not-allowed
                                         transition-all duration-200 flex items-center gap-1.5"
                                title="Combine all compatible components"
                            >
                                {isCombining ? (
                                    <Loader2 size={12} className="animate-spin" />
                                ) : (
                                    <Layers size={12} />
                                )}
                                Condense
                            </button>
                        )}
                    </div>
                </div>
            )}

            {/* Combine Error Banner */}
            <AnimatePresence>
                {combineError && (
                    <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: "auto" }}
                        exit={{ opacity: 0, height: 0 }}
                        className="overflow-hidden flex-shrink-0"
                    >
                        <div className="px-5 py-3 bg-red-500/10 border-b border-red-500/20 flex items-center gap-2">
                            <AlertCircle size={14} className="text-red-400 flex-shrink-0" />
                            <p className="text-xs text-red-300">{combineError}</p>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Combining Overlay */}
            <AnimatePresence>
                {isCombining && (
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="absolute inset-0 z-10 bg-astral-bg/60 backdrop-blur-sm flex items-center justify-center"
                    >
                        <div className="flex flex-col items-center gap-3">
                            <Loader2 size={32} className="text-astral-primary animate-spin" />
                            <span className="text-sm text-astral-muted">Combining components...</span>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Canvas Grid */}
            <div
                ref={scrollContainerRef}
                className={`flex-1 overflow-y-auto px-4 sm:px-6 py-4 ${
                    canvasComponents.length > 0
                        ? `grid ${getGridColsClass()} ${sizeLevel >= 1 ? 'gap-2' : 'gap-4'} content-start items-start grid-flow-row-dense`
                        : ''
                }`}
            >
                {canvasComponents.length === 0 ? (
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
                                    Ask anything in the chat panel — your connected agents will search, analyze, and visualize results as interactive UI components right here.
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
                ) : (
                    canvasComponents.map((component) => {
                        const isCollapsed = collapsedComponents.has(component.id);
                        const isDraggedOver = dragOverId === component.id;
                        const isBeingDragged = draggedId === component.id;

                        return (
                            <motion.div
                                key={component.id}
                                data-component-id={component.id}
                                layout
                                initial={{ opacity: 0, y: 20, scale: 0.95 }}
                                animate={{
                                    opacity: isBeingDragged ? 0.4 : 1,
                                    y: 0,
                                    scale: isDraggedOver ? 1.02 : 1,
                                }}
                                exit={{ opacity: 0, y: -10, scale: 0.95 }}
                                transition={{ duration: 0.2 }}
                                draggable={!isCombining}
                                onDragStart={(e) => handleDragStart(e as unknown as React.DragEvent, component.id)}
                                onDragEnd={handleDragEnd}
                                onDragEnter={(e) => handleDragEnter(e as unknown as React.DragEvent, component.id)}
                                onDragOver={(e) => handleDragOver(e as unknown as React.DragEvent, component.id)}
                                onDragLeave={(e) => handleDragLeave(e as unknown as React.DragEvent, component.id)}
                                onDrop={(e) => handleDrop(e as unknown as React.DragEvent, component.id)}
                                className={`
                                    ${getComponentSpan(component.component_type)}
                                    rounded-xl border transition-all duration-200
                                    ${isDraggedOver
                                        ? 'border-purple-400/60 bg-purple-500/10 shadow-lg shadow-purple-500/10'
                                        : 'border-white/8 bg-white/[0.03] hover:border-white/15'
                                    }
                                    ${isBeingDragged ? 'cursor-grabbing' : 'cursor-grab'}
                                `}
                            >
                                {/* Card Header */}
                                <div className="flex items-center gap-2 px-3 py-2.5">
                                    <div
                                        className="touch-none flex-shrink-0 p-1 -m-1 cursor-grab active:cursor-grabbing"
                                        onTouchStart={(e) => handleTouchStart(e, component.id)}
                                        onTouchMove={handleTouchMove}
                                        onTouchEnd={handleTouchEnd}
                                        onTouchCancel={handleTouchCancel}
                                    >
                                        <GripVertical size={14} className="text-astral-muted/40" />
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <h4 className="text-sm font-medium text-white truncate">
                                            {component.title}
                                        </h4>
                                        <span className="text-[10px] text-astral-muted/60 uppercase tracking-wider">
                                            {component.component_type}
                                        </span>
                                    </div>
                                    <div className="flex items-center gap-1">
                                        <button
                                            onClick={() => toggleCollapse(component.id)}
                                            className="p-1 rounded hover:bg-white/10 text-astral-muted hover:text-white transition-colors"
                                            title={isCollapsed ? "Expand" : "Collapse"}
                                        >
                                            {isCollapsed ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
                                        </button>
                                        <button
                                            onClick={() => setFullscreenId(component.id)}
                                            className="p-1 rounded hover:bg-white/10 text-astral-muted hover:text-white transition-colors"
                                            title="View full screen"
                                        >
                                            <Maximize2 size={14} />
                                        </button>
                                        <button
                                            onClick={() => onDeleteComponent(component.id)}
                                            className="p-1 rounded hover:bg-red-500/20 text-astral-muted hover:text-red-400 transition-colors"
                                            title="Delete component"
                                        >
                                            <Trash2 size={14} />
                                        </button>
                                    </div>
                                </div>

                                {/* Drop zone indicator */}
                                {isDraggedOver && (
                                    <div className="px-3 pb-2">
                                        <div className="border-2 border-dashed border-purple-400/40 rounded-lg p-2 text-center">
                                            <span className="text-xs text-purple-300/80">Drop to combine</span>
                                        </div>
                                    </div>
                                )}

                                {/* Card Content */}
                                <AnimatePresence>
                                    {!isCollapsed && (
                                        <motion.div
                                            initial={{ height: 0, opacity: 0 }}
                                            animate={{ height: "auto", opacity: 1 }}
                                            exit={{ height: 0, opacity: 0 }}
                                            transition={{ duration: 0.2 }}
                                            className="overflow-hidden"
                                        >
                                            <div className="px-3 pb-3 border-t border-white/5 pt-2">
                                                <div style={{ maxHeight: getContentMaxHeight() }} className="overflow-y-auto rounded-lg">
                                                    <DynamicRenderer
                                                        components={
                                                            Array.isArray(component.component_data)
                                                                ? component.component_data
                                                                : [component.component_data]
                                                        }
                                                        activeChatId={activeChatId}
                                                        onSendMessage={onSendMessage}
                                                        onTablePaginate={onTablePaginate}
                                                    />
                                                </div>
                                            </div>
                                        </motion.div>
                                    )}
                                </AnimatePresence>
                            </motion.div>
                        );
                    })
                )}
            </div>

            {/* Drag hint footer */}
            {canvasComponents.length >= 2 && !isCombining && (
                <div className="px-5 py-2 border-t border-white/5 text-center flex-shrink-0">
                    <p className="text-[10px] text-astral-muted/50">
                        Drag onto another to combine · use grip handle on touch devices
                    </p>
                </div>
            )}

            {/* Fullscreen Component Modal */}
            <AnimatePresence>
                {fullscreenId && (() => {
                    const comp = canvasComponents.find(c => c.id === fullscreenId);
                    if (!comp) return null;
                    return (
                        <motion.div
                            key="fullscreen-overlay"
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                            className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 sm:p-8"
                            onClick={() => setFullscreenId(null)}
                        >
                            <motion.div
                                initial={{ scale: 0.9, opacity: 0 }}
                                animate={{ scale: 1, opacity: 1 }}
                                exit={{ scale: 0.9, opacity: 0 }}
                                transition={{ duration: 0.2 }}
                                className="bg-astral-bg border border-white/10 rounded-2xl shadow-2xl w-full h-full max-w-[95vw] max-h-[92vh] flex flex-col overflow-hidden"
                                onClick={(e) => e.stopPropagation()}
                            >
                                {/* Fullscreen Header */}
                                <div className="flex items-center justify-between px-5 py-4 border-b border-white/10 flex-shrink-0">
                                    <div>
                                        <h3 className="text-base font-semibold text-white">{comp.title}</h3>
                                        <span className="text-[10px] text-astral-muted/60 uppercase tracking-wider">{comp.component_type}</span>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <button
                                            onClick={() => {
                                                onDeleteComponent(comp.id);
                                                setFullscreenId(null);
                                            }}
                                            className="p-1.5 rounded-lg hover:bg-red-500/20 text-astral-muted hover:text-red-400 transition-colors"
                                            title="Delete component"
                                        >
                                            <Trash2 size={16} />
                                        </button>
                                        <button
                                            onClick={() => setFullscreenId(null)}
                                            className="p-1.5 rounded-lg hover:bg-white/10 text-astral-muted hover:text-white transition-colors"
                                            title="Close full screen"
                                        >
                                            <X size={18} />
                                        </button>
                                    </div>
                                </div>
                                {/* Fullscreen Content */}
                                <div className="flex-1 overflow-y-auto p-5">
                                    <DynamicRenderer
                                        components={
                                            Array.isArray(comp.component_data)
                                                ? comp.component_data
                                                : [comp.component_data]
                                        }
                                        activeChatId={activeChatId}
                                        onSendMessage={onSendMessage}
                                        onTablePaginate={onTablePaginate}
                                    />
                                </div>
                            </motion.div>
                        </motion.div>
                    );
                })()}
            </AnimatePresence>
        </div>
    );
}
