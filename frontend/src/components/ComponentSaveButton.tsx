import React, { useState } from 'react';
import { Plus, Check } from 'lucide-react';

type ComponentSaveButtonProps = {
  componentData: Record<string, unknown>;
  componentType: string;
  onSave: (componentData: Record<string, unknown>, componentType: string) => Promise<boolean>;
  isSaved?: boolean;
  title?: string;
};

export default function ComponentSaveButton({
  componentData,
  componentType,
  onSave,
  isSaved = false,
  title = '',
}: ComponentSaveButtonProps) {
  const [isSaving, setIsSaving] = useState(false);
  const [saved, setSaved] = useState(isSaved);
  const [error, setError] = useState<string | null>(null);

  const handleClick = async (e: React.MouseEvent) => {
    e.stopPropagation();

    if (saved || isSaving) return;

    // Basic validation
    if (!componentData || !componentType) {
      setError('Component data and type are required');
      return;
    }

    setError(null);
    setIsSaving(true);
    try {
      const success = await onSave(componentData, componentType);
      if (success) {
        setSaved(true);
        // Reset after 3 seconds
        setTimeout(() => setSaved(false), 3000);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to save component';
      setError(errorMessage);
      console.error('Failed to save component:', error);
      // Auto-clear error after 5 seconds
      setTimeout(() => setError(null), 5000);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <button
      onClick={handleClick}
      disabled={isSaving || saved}
      className={`flex items-center justify-center p-1.5 rounded-lg text-xs font-medium transition-all duration-200
        ${saved
          ? 'bg-green-500/20 text-green-400 border border-green-500/30'
          : isSaving
            ? 'bg-astral-primary/20 text-astral-primary border border-astral-primary/30'
            : error
              ? 'bg-red-500/10 text-red-400 border border-red-500/30 hover:bg-red-500/20 hover:border-red-500/50'
              : 'bg-white/10 text-astral-muted hover:text-white hover:bg-white/20 border border-white/10 hover:border-astral-primary/30'
        }
        disabled:opacity-50 disabled:cursor-not-allowed`}
      title={error ? `Error: ${error}` : saved ? 'Added to UI drawer' : `Save ${title || componentType} to UI drawer`}
      aria-label={error ? 'Error saving component' : saved ? 'Component saved' : 'Save component to UI drawer'}
    >
      {saved ? (
        <Check size={14} />
      ) : isSaving ? (
        <div className="animate-spin rounded-full h-3.5 w-3.5 border-t-2 border-b-2 border-current" />
      ) : error ? (
        <div className="text-red-400 text-sm font-bold">!</div>
      ) : (
        <Plus size={14} />
      )}
    </button>
  );
}

