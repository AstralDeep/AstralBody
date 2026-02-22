import type { ProgressState } from '../types/progress';
import { ProgressBar } from './ProgressBar';
import { ProgressDetails } from './ProgressDetails';

type ProgressDisplayMode = 'compact' | 'detailed' | 'full';

interface ProgressDisplayProps {
  state: ProgressState;
  mode?: ProgressDisplayMode;
  title?: string;
  onCancel?: () => void;
  onRetry?: () => void;
}

export function ProgressDisplay({
  state,
  mode = 'full',
  title = 'Progress',
  onCancel,
  onRetry
}: ProgressDisplayProps) {
  const isCompact = mode === 'compact';
  const isDetailed = mode === 'detailed' || mode === 'full';

  return (
    <div className="w-full">
      {/* Header */}
      <div className="flex justify-between items-center mb-4">
        <div>
          <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200">
            {title}
          </h2>
          <div className="text-sm text-gray-600 dark:text-gray-400">
            {state.isError ? 'Error occurred' : state.isComplete ? 'Completed successfully' : 'Processing...'}
          </div>
        </div>

        <div className="flex space-x-2">
          {onCancel && !state.isComplete && !state.isError && (
            <button
              onClick={onCancel}
              className="px-3 py-1 text-sm bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-200 rounded hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
            >
              Cancel
            </button>
          )}
          {onRetry && state.isError && (
            <button
              onClick={onRetry}
              className="px-3 py-1 text-sm bg-blue-500 text-white rounded hover:bg-blue-600 transition-colors"
            >
              Retry
            </button>
          )}
        </div>
      </div>

      {/* Progress bar */}
      <div className="mb-6">
        <ProgressBar
          percentage={state.percentage}
          currentStep={state.currentStep}
          steps={state.steps}
          completedSteps={state.completedSteps}
          failedSteps={state.failedSteps}
          isError={state.isError}
          isComplete={state.isComplete}
        />
      </div>

      {/* Error display */}
      {state.isError && state.errorMessage && (
        <div className="mb-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <svg className="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
              </svg>
            </div>
            <div className="ml-3">
              <h3 className="text-sm font-medium text-red-800 dark:text-red-200">
                Error
              </h3>
              <div className="mt-2 text-sm text-red-700 dark:text-red-300">
                {state.errorMessage}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Completion message */}
      {state.isComplete && !state.isError && (
        <div className="mb-6 p-4 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg">
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <svg className="h-5 w-5 text-green-400" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
            </div>
            <div className="ml-3">
              <h3 className="text-sm font-medium text-green-800 dark:text-green-200">
                Complete
              </h3>
              <div className="mt-2 text-sm text-green-700 dark:text-green-300">
                {state.message || 'Process completed successfully.'}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Details section */}
      {isDetailed && (
        <div className="mb-4">
          <ProgressDetails state={state} />
        </div>
      )}

      {/* Log output (compact mode) */}
      {isCompact && (
        <div className="mt-4">
          <div className="text-sm text-gray-600 dark:text-gray-400 mb-1">
            Current step: {state.currentStep}
          </div>
          <div className="text-sm text-gray-800 dark:text-gray-200">
            {state.message}
          </div>
        </div>
      )}
    </div>
  );
}
