import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, ChevronLeft, ChevronRight, Grid, Trash2, ExternalLink } from 'lucide-react';
import DynamicRenderer from './DynamicRenderer';

// Debug logging
console.log('UISavedDrawer component loaded');

type SavedComponent = {
  id: string;
  chat_id: string;
  component_data: any;
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
  activeChatId: string | null;
}

export default function UISavedDrawer({
  isOpen,
  onClose,
  onOpen,
  savedComponents,
  onDeleteComponent,
  activeChatId,
}: UISavedDrawerProps) {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isAnimating, setIsAnimating] = useState(false);

  // Filter components for current chat if activeChatId is provided
  const filteredComponents = activeChatId
    ? savedComponents.filter(comp => comp.chat_id === activeChatId)
    : savedComponents;

  // Log drawer state changes
  useEffect(() => {
    console.log('Drawer state changed - isOpen:', isOpen, 'isCollapsed:', isCollapsed, 'filteredComponents:', filteredComponents.length);
  }, [isOpen, isCollapsed, filteredComponents.length]);

  const handleToggleCollapse = () => {
    // Prevent toggling while animating
    if (isAnimating) {
      console.log('Drawer is animating, ignoring collapse toggle');
      return;
    }
    console.log('Drawer toggle collapse clicked. Current isCollapsed:', isCollapsed, 'New value:', !isCollapsed);
    setIsAnimating(true);
    setIsCollapsed(!isCollapsed);
    // Reset animating flag after animation completes
    // Using a timeout since spring animations don't have fixed duration
    setTimeout(() => {
      console.log('Collapse animation complete');
      setIsAnimating(false);
    }, 400); // Increased to 400ms to be safe
  };

  // Reset collapsed state when drawer closes and ensure it opens fully
  useEffect(() => {
    if (!isOpen) {
      console.log('Drawer closed, resetting isCollapsed to false');
      setIsCollapsed(false);
      setIsAnimating(false); // Also reset animating flag
    } else {
      // When drawer opens, ensure it's not collapsed
      console.log('Drawer opened, ensuring isCollapsed is false');
      setIsCollapsed(false);
      setIsAnimating(false); // Also reset animating flag
    }
  }, [isOpen]);

  const handleDelete = (e: React.MouseEvent, componentId: string) => {
    e.stopPropagation();
    e.preventDefault();
    console.log('handleDelete called for component:', componentId);
    if (window.confirm('Remove this component from the drawer?')) {
      onDeleteComponent(componentId);
    }
  };

  return (
    <>
      {/* Persistent toggle arrow when drawer is closed */}
      {!isOpen && (
        <button
          onClick={() => {
            console.log('Persistent toggle arrow clicked');
            onOpen?.();
          }}
          className="fixed right-0 top-1/2 transform -translate-y-1/2 z-40
                     bg-astral-primary/80 hover:bg-astral-primary text-white
                     p-2 rounded-l-lg shadow-lg transition-all duration-200
                     hover:shadow-xl hover:scale-105"
          aria-label="Open saved components drawer"
        >
          <ChevronLeft size={20} />
        </button>
      )}

      <AnimatePresence>
        {isOpen && (
          <>
            {/* Backdrop */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={onClose}
              className="fixed inset-0 bg-black/50 z-40"
            />

            {/* Drawer */}
            <motion.div
              initial={{ x: '100%' }}
              animate={{ x: isCollapsed ? 'calc(100% - 60px)' : '0%' }}
              exit={{ x: '100%' }}
              transition={{ type: 'spring', damping: 25, stiffness: 200 }}
              className="fixed right-0 top-0 h-full z-50 w-3/4 max-w-4xl
                         bg-astral-surface border-l border-white/10
                         shadow-2xl flex flex-col"
            >
              {/* Header */}
              <div className="flex items-center justify-between p-4 border-b border-white/10">
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded-lg bg-astral-primary/20">
                    <Grid size={20} className="text-astral-primary" />
                  </div>
                  <div>
                    <h2 className="text-lg font-semibold text-white">Saved UI Components</h2>
                    <p className="text-sm text-astral-muted">
                      {filteredComponents.length} component{filteredComponents.length !== 1 ? 's' : ''}
                      {activeChatId && ' from this chat'}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={handleToggleCollapse}
                    className="p-2 rounded-lg hover:bg-white/10 text-astral-muted hover:text-white transition-colors"
                    aria-label={isCollapsed ? 'Expand drawer' : 'Collapse drawer'}
                  >
                    {isCollapsed ? <ChevronRight size={20} /> : <ChevronLeft size={20} />}
                  </button>

                  <button
                    onClick={onClose}
                    className="p-2 rounded-lg hover:bg-white/10 text-astral-muted hover:text-white transition-colors"
                    aria-label="Close drawer"
                  >
                    <X size={20} />
                  </button>
                </div>
              </div>

              {/* Content */}
              <div className="flex-1 overflow-y-auto p-4">
                {isCollapsed ? (
                  <div className="h-full flex items-center justify-center">
                    <p className="text-astral-muted text-sm -rotate-90 whitespace-nowrap">
                      Saved Components
                    </p>
                  </div>
                ) : (
                  <>
                    {filteredComponents.length === 0 ? (
                      <div className="h-full flex flex-col items-center justify-center text-center p-8">
                        <div className="w-16 h-16 rounded-2xl bg-white/5 flex items-center justify-center mb-4">
                          <Grid size={24} className="text-astral-muted" />
                        </div>
                        <h3 className="text-lg font-medium text-white mb-2">No saved components yet</h3>
                        <p className="text-sm text-astral-muted max-w-md">
                          Click the "Add to UI" button on any chart, table, or card in the chat to save it here.
                        </p>
                      </div>
                    ) : (
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {filteredComponents.map((component) => (
                          <div
                            key={component.id}
                            className="relative group bg-white/5 border border-white/10 rounded-xl p-4 hover:border-astral-primary/30 transition-all duration-200"
                          >
                            {/* Component header */}
                            <div className="flex items-center justify-between mb-3">
                              <div className="flex items-center gap-2">
                                <h4 className="text-sm font-medium text-white truncate">
                                  {component.title || component.component_type.replace('_', ' ').replace('chart', 'Chart')}
                                </h4>
                                <span className="text-[10px] px-2 py-1 rounded-full bg-astral-primary/20 text-astral-primary uppercase tracking-wider">
                                  {component.component_type}
                                </span>
                              </div>

                              <button
                                onClick={(e) => handleDelete(e, component.id)}
                                className="relative z-10 p-1.5 rounded-md text-astral-muted hover:text-red-400 hover:bg-red-500/10 transition-all"
                                aria-label="Delete component"
                              >
                                <Trash2 size={16} />
                              </button>
                            </div>

                            {/* Component preview */}
                            <div className="relative min-h-[120px] max-h-[300px] overflow-y-auto rounded-lg bg-black/20 p-3">
                              <DynamicRenderer
                                components={[component.component_data]}
                              />

                              {/* Overlay to indicate it's interactive */}
                              <div className="absolute inset-0 bg-gradient-to-t from-astral-surface/50 to-transparent opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />
                            </div>

                          </div>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </div>

              {/* Footer */}
              {!isCollapsed && (
                <div className="p-3 border-t border-white/10 text-xs text-astral-muted flex items-center justify-between">
                  <div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-1 rounded bg-white/5">
                      {filteredComponents.length} saved
                    </span>
                  </div>
                </div>
              )}
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
