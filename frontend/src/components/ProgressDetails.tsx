import React from 'react';
import type { ProgressState } from '../types/progress';
import { getStepLabel, getStepDescription } from '../types/progress';

interface ProgressDetailsProps {
  state: ProgressState;
}

export function ProgressDetails({ state }: ProgressDetailsProps) {
  const formatTime = (ms: number) => {
    const seconds = Math.floor(ms / 1000);
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    
    if (minutes > 0) {
      return `${minutes}m ${remainingSeconds}s`;
    }
    return `${remainingSeconds}s`;
  };
  
  return (
    <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Current status */}
        <div>
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
            Current Status
          </h3>
          <div className="space-y-2">
            <div className="flex justify-between">
              <span className="text-sm text-gray-600 dark:text-gray-400">Phase:</span>
              <span className="text-sm font-medium text-gray-800 dark:text-gray-200 capitalize">
                {state.phase}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm text-gray-600 dark:text-gray-400">Step:</span>
              <span className="text-sm font-medium text-gray-800 dark:text-gray-200">
                {getStepLabel(state.currentStep)}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm text-gray-600 dark:text-gray-400">Progress:</span>
              <span className="text-sm font-medium text-gray-800 dark:text-gray-200">
                {state.percentage}%
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm text-gray-600 dark:text-gray-400">Elapsed Time:</span>
              <span className="text-sm font-medium text-gray-800 dark:text-gray-200">
                {formatTime(state.elapsedTime)}
              </span>
            </div>
          </div>
        </div>
        
        {/* Step details */}
        <div>
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
            Step Details
          </h3>
          <div className="space-y-2">
            <div>
              <div className="text-sm text-gray-600 dark:text-gray-400 mb-1">
                Description:
              </div>
              <div className="text-sm text-gray-800 dark:text-gray-200">
                {getStepDescription(state.currentStep)}
              </div>
            </div>
            <div>
              <div className="text-sm text-gray-600 dark:text-gray-400 mb-1">
                Message:
              </div>
              <div className={`text-sm ${state.isError ? 'text-red-600 dark:text-red-400' : 'text-gray-800 dark:text-gray-200'}`}>
                {state.message}
              </div>
            </div>
            {state.data && Object.keys(state.data).length > 0 && (
              <div>
                <div className="text-sm text-gray-600 dark:text-gray-400 mb-1">
                  Additional Data:
                </div>
                <pre className="text-xs bg-gray-100 dark:bg-gray-900 p-2 rounded overflow-x-auto">
                  {JSON.stringify(state.data, null, 2)}
                </pre>
              </div>
            )}
          </div>
        </div>
      </div>
      
      {/* Progress summary */}
      <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
        <div className="flex justify-between text-sm">
          <div>
            <span className="text-gray-600 dark:text-gray-400">Completed Steps:</span>
            <span className="ml-2 font-medium text-green-600 dark:text-green-400">
              {state.completedSteps.size}/{state.steps.length}
            </span>
          </div>
          <div>
            <span className="text-gray-600 dark:text-gray-400">Failed Steps:</span>
            <span className="ml-2 font-medium text-red-600 dark:text-red-400">
              {state.failedSteps.size}
            </span>
          </div>
          <div>
            <span className="text-gray-600 dark:text-gray-400">Status:</span>
            <span className={`ml-2 font-medium ${state.isError ? 'text-red-600 dark:text-red-400' : state.isComplete ? 'text-green-600 dark:text-green-400' : 'text-blue-600 dark:text-blue-400'}`}>
              {state.isError ? 'Error' : state.isComplete ? 'Complete' : 'In Progress'}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
