import { useState, useEffect, useCallback } from 'react';

type SavedComponent = {
  id: string;
  chat_id: string;
  component_data: unknown;
  component_type: string;
  title: string;
  created_at: number;
};

type UseSavedComponentsProps = {
  activeChatId: string | null;
  sendWebSocketMessage: (type: string, payload: Record<string, unknown>) => void;
};

export function useSavedComponents({
  activeChatId,
  sendWebSocketMessage,
}: UseSavedComponentsProps) {
  const [savedComponents, setSavedComponents] = useState<SavedComponent[]>([]);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const loadSavedComponents = useCallback(() => {
    setIsLoading(true);
    sendWebSocketMessage('ui_event', {
      action: 'get_saved_components',
      payload: { chat_id: activeChatId },
    });
  }, [activeChatId, sendWebSocketMessage]);

  // Load saved components on mount and when active chat changes
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadSavedComponents();
  }, [activeChatId, loadSavedComponents]);

  const saveComponent = useCallback(async (
    componentData: Record<string, unknown>,
    componentType: string,
    title?: string
  ): Promise<boolean> => {
    if (!activeChatId) {
      console.error('No active chat to save component to');
      return false;
    }

    try {
      sendWebSocketMessage('ui_event', {
        action: 'save_component',
        payload: {
          chat_id: activeChatId,
          component_data: componentData,
          component_type: componentType,
          title: title || componentType.replace('_', ' ').replace('chart', 'Chart'),
        },
      });
      return true;
    } catch (error) {
      console.error('Failed to save component:', error);
      return false;
    }
  }, [activeChatId, sendWebSocketMessage]);

  const deleteComponent = useCallback((componentId: string) => {
    sendWebSocketMessage('ui_event', {
      action: 'delete_saved_component',
      payload: { component_id: componentId },
    });
  }, [sendWebSocketMessage]);

  const handleWebSocketMessage = useCallback((data: Record<string, unknown>) => {
    switch (data.type) {
      case 'saved_components_list':
        setSavedComponents((data.components as SavedComponent[]) || []);
        setIsLoading(false);
        break;

      case 'component_saved':
        // Add new component to list and auto-open drawer if it's the first component
        setSavedComponents(prev => {
          const isFirstComponent = prev.length === 0;
          if (isFirstComponent) {
            setIsDrawerOpen(true);
          }
          return [(data.component as SavedComponent), ...prev];
        });
        break;

      case 'component_deleted':
        // Remove component from list
        setSavedComponents(prev =>
          prev.filter(comp => comp.id !== (data.component_id as string))
        );
        break;

      case 'component_save_error':
        console.error('Failed to save component:', data.error);
        break;
    }
  }, []);

  const toggleDrawer = useCallback(() => {
    setIsDrawerOpen(prev => !prev);
  }, []);

  const openDrawer = useCallback(() => {
    setIsDrawerOpen(true);
  }, []);

  const closeDrawer = useCallback(() => {
    setIsDrawerOpen(false);
  }, []);

  // Check if a specific component is already saved
  const isComponentSaved = useCallback((componentData: Record<string, unknown>): boolean => {
    // Simple check: compare component type and title
    const componentTitle = (componentData.title || componentData.content || '') as string;
    return savedComponents.some(comp =>
      comp.component_type === componentData.type &&
      comp.title.includes(componentTitle.substring(0, 50))
    );
  }, [savedComponents]);

  return {
    savedComponents,
    isDrawerOpen,
    isLoading,
    toggleDrawer,
    openDrawer,
    closeDrawer,
    saveComponent,
    deleteComponent,
    loadSavedComponents,
    handleWebSocketMessage,
    isComponentSaved,
  };
}
