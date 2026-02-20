import { useState, useEffect, useCallback, useRef } from 'react';
import type { ProgressEvent, LegacyLogEvent, ProgressState, ProgressPhase } from '../types/progress';
import { getPhaseSteps } from '../types/progress';

type SSEData = ProgressEvent | LegacyLogEvent | { type: 'complete', result?: any } | { type: 'error', error: string };

interface UseProgressSSEResult {
  state: ProgressState;
  connect: () => void;
  disconnect: () => void;
  isConnected: boolean;
  error: string | null;
}

export function useProgressSSE(sessionId: string, phase: ProgressPhase): UseProgressSSEResult {
  const [state, setState] = useState<ProgressState>(() => ({
    phase,
    currentStep: getPhaseSteps(phase)[0],
    percentage: 0,
    message: `Starting ${phase}...`,
    startTime: Date.now(),
    elapsedTime: 0,
    steps: getPhaseSteps(phase),
    completedSteps: new Set(),
    failedSteps: new Set(),
    isComplete: false,
    isError: false
  }));
  
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const maxReconnectAttempts = 5;
  
  // Update elapsed time every second
  useEffect(() => {
    const interval = setInterval(() => {
      setState(prev => ({
        ...prev,
        elapsedTime: Date.now() - prev.startTime
      }));
    }, 1000);
    
    return () => clearInterval(interval);
  }, []);
  
  const handleProgressEvent = useCallback((event: ProgressEvent) => {
    setState(prev => {
      const completedSteps = new Set(prev.completedSteps);
      const failedSteps = new Set(prev.failedSteps);
      
      // Mark previous step as completed if we're moving to a new step
      if (event.step !== prev.currentStep && !prev.isError) {
        completedSteps.add(prev.currentStep);
      }
      
      // Check for error in data
      const isError = event.step === 'error' || 
                     event.data?.error === true || 
                     event.message.toLowerCase().includes('error') ||
                     event.message.toLowerCase().includes('failed');
      
      if (isError) {
        failedSteps.add(event.step);
      }
      
      const isComplete = event.percentage >= 100 && !isError;
      
      return {
        ...prev,
        phase: event.phase,
        currentStep: event.step,
        percentage: event.percentage,
        message: event.message,
        data: event.data,
        completedSteps,
        failedSteps,
        isComplete,
        isError,
        errorMessage: isError ? event.message : prev.errorMessage
      };
    });
  }, []);
  
  const handleLegacyLogEvent = useCallback((event: LegacyLogEvent) => {
    // Convert legacy log event to progress event
    const progressEvent: ProgressEvent = {
      type: 'progress',
      phase,
      step: state.currentStep,
      percentage: state.percentage,
      message: event.message,
      data: { log: true, status: event.status },
      timestamp: event.timestamp || Date.now() / 1000
    };
    
    handleProgressEvent(progressEvent);
    
    // Handle success/error status
    if (event.status === 'success') {
      setState(prev => ({
        ...prev,
        percentage: 100,
        isComplete: true,
        message: event.message
      }));
    } else if (event.status === 'error') {
      setState(prev => ({
        ...prev,
        percentage: 100,
        isError: true,
        errorMessage: event.message
      }));
    }
  }, [phase, state.currentStep, state.percentage, handleProgressEvent]);
  
  const connect = useCallback(() => {
    if (eventSourceRef.current) {
      disconnect();
    }
    
    setError(null);
    reconnectAttemptsRef.current = 0;
    
    // Determine endpoint based on phase
    let endpoint = '';
    const baseUrl = import.meta.env.VITE_AUTH_URL || 'http://localhost:8002';
    
    if (phase === 'generation') {
      endpoint = `${baseUrl}/api/agent-creator/generate-with-progress`;
    } else if (phase === 'testing') {
      endpoint = `${baseUrl}/api/agent-creator/test`;
    }
    
    if (!endpoint) {
      setError(`No endpoint configured for phase: ${phase}`);
      return;
    }
    
    try {
      const eventSource = new EventSource(`${endpoint}?session_id=${sessionId}`, {
        withCredentials: false
      });
      
      eventSourceRef.current = eventSource;
      
      eventSource.onopen = () => {
        setIsConnected(true);
        setError(null);
        reconnectAttemptsRef.current = 0;
      };
      
      eventSource.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data) as SSEData;
          
          if ('type' in data && data.type === 'progress') {
            // New progress event format
            handleProgressEvent(data as ProgressEvent);
          } else if ('status' in data) {
            // Legacy log format
            handleLegacyLogEvent(data as LegacyLogEvent);
          } else if ('type' in data && data.type === 'complete') {
            // Completion event
            setState(prev => ({
              ...prev,
              percentage: 100,
              isComplete: true,
              data: { ...prev.data, result: (data as any).result }
            }));
          } else if ('type' in data && data.type === 'error') {
            // Error event
            setState(prev => ({
              ...prev,
              percentage: 100,
              isError: true,
              errorMessage: (data as any).error
            }));
          }
        } catch (parseError) {
          console.error('Failed to parse SSE event:', parseError, e.data);
        }
      };
      
      eventSource.onerror = (err) => {
        console.error('SSE connection error:', err);
        setError('Connection lost. Attempting to reconnect...');
        setIsConnected(false);
        
        // Auto-reconnect with exponential backoff
        if (reconnectAttemptsRef.current < maxReconnectAttempts) {
          reconnectAttemptsRef.current++;
          const delay = 1000 * Math.pow(2, reconnectAttemptsRef.current - 1);
          
          setTimeout(() => {
            if (eventSourceRef.current?.readyState === EventSource.CLOSED) {
              connect();
            }
          }, delay);
        }
      };
      
    } catch (err) {
      setError(`Failed to establish SSE connection: ${err}`);
      setIsConnected(false);
    }
  }, [sessionId, phase, handleProgressEvent, handleLegacyLogEvent]);
  
  const disconnect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    setIsConnected(false);
  }, []);
  
  // Auto-connect on mount, disconnect on unmount
  useEffect(() => {
    connect();
    return () => {
      disconnect();
    };
  }, [connect, disconnect]);
  
  return {
    state,
    connect,
    disconnect,
    isConnected,
    error
  };
}
