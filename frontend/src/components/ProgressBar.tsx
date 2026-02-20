import React from 'react';
import type { ProgressStep } from '../types/progress';
import { getStepLabel, isCriticalStep } from '../types/progress';

interface ProgressBarProps {
  percentage: number;
  currentStep: ProgressStep;
  steps: ProgressStep[];
  completedSteps: Set<ProgressStep>;
  failedSteps: Set<ProgressStep>;
  isError: boolean;
  isComplete: boolean;
}

export function ProgressBar({
  percentage,
  currentStep,
  steps,
  completedSteps,
  failedSteps,
  isError,
  isComplete
}: ProgressBarProps) {
  const stepWidth = 100 / Math.max(steps.length, 1);
  
  return (
    <div className="w-full">
      {/* Overall progress bar */}
      <div className="relative h-4 w-full bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden mb-4">
        <div 
          className={`h-full transition-all duration-300 ease-out ${isError ? 'bg-red-500' : isComplete ? 'bg-green-500' : 'bg-blue-500'}`}
          style={{ width: `${percentage}%` }}
        />
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-xs font-semibold text-gray-800 dark:text-gray-200">
            {percentage.toFixed(0)}%
          </span>
        </div>
      </div>
      
      {/* Step indicators */}
      <div className="flex justify-between relative mb-8">
        {/* Connecting line */}
        <div className="absolute top-3 left-0 right-0 h-0.5 bg-gray-300 dark:bg-gray-600 -z-10" />
        
        {steps.map((step, index) => {
          const isCompleted = completedSteps.has(step);
          const isFailed = failedSteps.has(step);
          const isCurrent = step === currentStep && !isCompleted && !isFailed;
          const isCritical = isCriticalStep(step);
          
          let bgColor = 'bg-gray-300 dark:bg-gray-600';
          let borderColor = 'border-gray-400 dark:border-gray-500';
          let textColor = 'text-gray-600 dark:text-gray-400';
          
          if (isFailed) {
            bgColor = 'bg-red-500';
            borderColor = 'border-red-600 dark:border-red-700';
            textColor = 'text-red-700 dark:text-red-300';
          } else if (isCompleted) {
            bgColor = 'bg-green-500';
            borderColor = 'border-green-600 dark:border-green-700';
            textColor = 'text-green-700 dark:text-green-300';
          } else if (isCurrent) {
            bgColor = 'bg-blue-500';
            borderColor = 'border-blue-600 dark:border-blue-700';
            textColor = 'text-blue-700 dark:text-blue-300';
          }
          
          return (
            <div 
              key={step}
              className="flex flex-col items-center relative"
              style={{ width: `${stepWidth}%` }}
            >
              {/* Step circle */}
              <div 
                className={`w-6 h-6 rounded-full border-2 ${borderColor} ${bgColor} flex items-center justify-center transition-all duration-300`}
              >
                {isFailed ? (
                  <span className="text-xs font-bold text-white">!</span>
                ) : isCompleted ? (
                  <span className="text-xs font-bold text-white">✓</span>
                ) : (
                  <span className="text-xs font-bold text-white">{index + 1}</span>
                )}
              </div>
              
              {/* Step label */}
              <div className="mt-2 text-center">
                <div className={`text-xs font-medium ${textColor}`}>
                  {getStepLabel(step)}
                </div>
                {isCritical && (
                  <div className="text-[10px] text-gray-500 dark:text-gray-400 mt-0.5">
                    Critical
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
