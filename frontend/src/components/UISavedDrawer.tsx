/**
 * UISavedDrawer — Drawer for managing saved UI components.
 *
 * Features:
 * - Display saved components with their real titles
 * - Drag-and-drop to combine components (HTML5 DnD API)
 * - "Condense" button to merge all compatible components
 * - Loading & error states for combine operations
 */
import React, { useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, ChevronDown, ChevronUp, Trash2, Loader2, Layers, GripVertical, AlertCircle, Maximize2, Minimize2 } from "lucide-react";
import DynamicRenderer from "./DynamicRenderer";

console.log('UISavedDrawer component loaded');

type SavedComponent = {
  id: string;
  chat_id: string;
  component_data: Record<string, unknown>;
  component_type: string;
  title: string;
  created_at: number;
};

interface UISavedDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  onOpen?: () => void;
  savedComponents: SavedComponent[];
  onDeleteComponent: (componentId: string) => void;
  onCombineComponents: (sourceId: string, targetId: string) => void;
  onCondenseComponents: (componentIds: string[]) => void;
  isCombining: boolean;
  combineError: string | null;
  activeChatId: string | null;
}

export default function UISavedDrawer({
  isOpen,
  onClose,
  savedComponents,
  onDeleteComponent,
  onCombineComponents,
  onCondenseComponents,
  isCombining,
  combineError,
}: UISavedDrawerProps) {
  const [collapsedComponents, setCollapsedComponents] = useState<Set<string>>(new Set());
  const [isFullScreen, setIsFullScreen] = useState(false);
  const [dragOverId, setDragOverId] = useState<string | null>(null);
  const [draggedId, setDraggedId] = useState<string | null>(null);
  const dragCounterRef = useRef<Map<string, number>>(new Map());

  const getComponentSpan = (type: string) => {
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

  const toggleCollapse = (id: string) => {
    setCollapsedComponents(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  // ── Drag and Drop handlers ──
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
    if (draggedId && targetId !== draggedId) {
      setDragOverId(targetId);
    }
  };

  const handleDragOver = (e: React.DragEvent, targetId: string) => {
    e.preventDefault();
    e.stopPropagation();
    if (draggedId && targetId !== draggedId) {
      e.dataTransfer.dropEffect = "move";
    }
  };

  const handleDragLeave = (e: React.DragEvent, targetId: string) => {
    e.preventDefault();
    e.stopPropagation();
    const count = (dragCounterRef.current.get(targetId) || 0) - 1;
    dragCounterRef.current.set(targetId, count);
    if (count <= 0) {
      dragCounterRef.current.delete(targetId);
      if (dragOverId === targetId) {
        setDragOverId(null);
      }
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
    if (savedComponents.length < 2 || isCombining) return;
    const ids = savedComponents.map(c => c.id);
    onCondenseComponents(ids);
  };

  if (!isOpen) return null;

  return (
    <motion.div
      initial={{ x: "100%" }}
      animate={{ x: 0 }}
      exit={{ x: "100%" }}
      transition={{ type: "spring", damping: 25, stiffness: 250 }}
      className={`fixed right-0 top-0 h-full z-50 bg-astral-bg/95 backdrop-blur-xl border-l border-white/10 shadow-2xl flex flex-col transition-all duration-300 ${isFullScreen ? "w-screen" : "w-[75vw]"}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-white/10">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-astral-primary to-astral-secondary flex items-center justify-center">
            <Layers size={16} className="text-white" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-white">Saved Components</h3>
            <p className="text-xs text-astral-muted">{savedComponents.length} item{savedComponents.length !== 1 ? 's' : ''}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* Condense Button */}
          {savedComponents.length >= 2 && (
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
              id="condense-btn"
            >
              {isCombining ? (
                <Loader2 size={12} className="animate-spin" />
              ) : (
                <Layers size={12} />
              )}
              Condense
            </button>
          )}
          <button
            onClick={() => setIsFullScreen(!isFullScreen)}
            className="p-1.5 rounded-lg hover:bg-white/10 text-astral-muted hover:text-white transition-colors"
            title={isFullScreen ? "Exit Full Screen" : "Full Screen"}
          >
            {isFullScreen ? <Minimize2 size={18} /> : <Maximize2 size={18} />}
          </button>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-white/10 text-astral-muted hover:text-white transition-colors"
          >
            <X size={18} />
          </button>
        </div>
      </div>

      {/* Combine Error Banner */}
      <AnimatePresence>
        {combineError && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden"
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
            className="absolute inset-0 z-10 bg-astral-bg/60 backdrop-blur-sm flex items-center justify-center rounded-none"
          >
            <div className="flex flex-col items-center gap-3">
              <Loader2 size={32} className="text-astral-primary animate-spin" />
              <span className="text-sm text-astral-muted">Combining components...</span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Components List */}
      <div className="flex-1 overflow-y-auto px-4 py-3 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-4 content-start items-start grid-flow-row-dense">
        {savedComponents.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center py-12 col-span-full">
            <Layers size={32} className="text-astral-muted/30 mb-3" />
            <p className="text-sm text-astral-muted">No saved components</p>
            <p className="text-xs text-astral-muted/60 mt-1">
              Save components from chat to see them here
            </p>
          </div>
        ) : (
          savedComponents.map((component) => {
            const isCollapsed = collapsedComponents.has(component.id);
            const isDraggedOver = dragOverId === component.id;
            const isBeingDragged = draggedId === component.id;

            return (
              <motion.div
                key={component.id}
                layout
                initial={{ opacity: 0, y: 10 }}
                animate={{
                  opacity: isBeingDragged ? 0.4 : 1,
                  y: 0,
                  scale: isDraggedOver ? 1.02 : 1,
                }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ duration: 0.15 }}
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
                  <GripVertical size={14} className="text-astral-muted/40 flex-shrink-0" />
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
                        <div className="max-h-[300px] overflow-y-auto rounded-lg">
                          <DynamicRenderer
                            components={
                              Array.isArray(component.component_data)
                                ? component.component_data
                                : [component.component_data]
                            }
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
      {savedComponents.length >= 2 && !isCombining && (
        <div className="px-5 py-2.5 border-t border-white/5 text-center">
          <p className="text-[10px] text-astral-muted/50">
            Drag a component onto another to combine them
          </p>
        </div>
      )}
    </motion.div>
  );
}
