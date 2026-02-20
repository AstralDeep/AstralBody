// Progress indication system types for AstralBody

export type ProgressPhase = 'generation' | 'testing' | 'installation';

export type ProgressStep =
  // Generation steps
  | 'prompt_construction'
  | 'llm_api_call'
  | 'response_received'
  | 'json_parsing'
  | 'structure_validation'
  | 'code_cleaning'
  | 'generation_complete'
  // Testing steps
  | 'saving_files'
  | 'starting_process'
  | 'waiting_for_boot'
  | 'websocket_connection'
  | 'agent_registration'
  | 'tools_list_test'
  | 'tools_call_test'
  | 'validation_complete'
  | 'integration_ready'
  | 'testing_complete'
  // Error/status steps
  | 'error'
  | 'warning'
  | 'info';

export interface ProgressEvent {
  type: 'progress';
  phase: ProgressPhase;
  step: ProgressStep;
  percentage: number; // 0-100
  message: string;
  data?: Record<string, any>;
  timestamp: number;
}

export interface LegacyLogEvent {
  status: 'log' | 'success' | 'error';
  message: string;
  timestamp?: number;
}

export interface ProgressState {
  phase: ProgressPhase;
  currentStep: ProgressStep;
  percentage: number;
  message: string;
  data?: Record<string, any>;
  startTime: number;
  elapsedTime: number;
  steps: ProgressStep[];
  completedSteps: Set<ProgressStep>;
  failedSteps: Set<ProgressStep>;
  isComplete: boolean;
  isError: boolean;
  errorMessage?: string;
}

// Helper functions
export function getPhaseSteps(phase: ProgressPhase): ProgressStep[] {
  const phaseSteps: Record<ProgressPhase, ProgressStep[]> = {
    generation: [
      'prompt_construction',
      'llm_api_call',
      'response_received',
      'json_parsing',
      'structure_validation',
      'code_cleaning',
      'generation_complete'
    ],
    testing: [
      'saving_files',
      'starting_process',
      'waiting_for_boot',
      'websocket_connection',
      'agent_registration',
      'tools_list_test',
      'tools_call_test',
      'validation_complete',
      'integration_ready',
      'testing_complete'
    ],
    installation: [
      'starting_process',
      'waiting_for_boot',
      'testing_complete'
    ]
  };
  
  return phaseSteps[phase] || [];
}

export function getStepLabel(step: ProgressStep): string {
  const labels: Record<ProgressStep, string> = {
    // Generation steps
    prompt_construction: 'Constructing Prompt',
    llm_api_call: 'Calling LLM API',
    response_received: 'Receiving Response',
    json_parsing: 'Parsing JSON',
    structure_validation: 'Validating Structure',
    code_cleaning: 'Cleaning Code',
    generation_complete: 'Generation Complete',
    
    // Testing steps
    saving_files: 'Saving Files',
    starting_process: 'Starting Process',
    waiting_for_boot: 'Waiting for Boot',
    websocket_connection: 'WebSocket Connection',
    agent_registration: 'Agent Registration',
    tools_list_test: 'Tools/List Test',
    tools_call_test: 'Tools/Call Test',
    validation_complete: 'Validation Complete',
    integration_ready: 'Integration Ready',
    testing_complete: 'Testing Complete',
    
    // Error/status steps
    error: 'Error',
    warning: 'Warning',
    info: 'Info'
  };
  
  return labels[step] || step;
}

export function getStepDescription(step: ProgressStep): string {
  const descriptions: Record<ProgressStep, string> = {
    // Generation steps
    prompt_construction: 'Building generation prompt with session context',
    llm_api_call: 'Making asynchronous request to LLM',
    response_received: 'LLM response received, starting parsing',
    json_parsing: 'Extracting JSON from LLM response',
    structure_validation: 'Validating required file structure',
    code_cleaning: 'Removing markdown fences and cleaning code',
    generation_complete: 'Code files ready for editing',
    
    // Testing steps
    saving_files: 'Writing files to agent directory',
    starting_process: 'Launching agent subprocess on free port',
    waiting_for_boot: 'Waiting for agent to initialize (3 seconds)',
    websocket_connection: 'Establishing WebSocket connection',
    agent_registration: 'Receiving register_agent message',
    tools_list_test: 'Testing tools/list endpoint',
    tools_call_test: 'Testing tools/call with dummy data',
    validation_complete: 'All protocol tests passed',
    integration_ready: 'Agent ready for orchestrator discovery',
    testing_complete: 'All tests passed, agent active',
    
    // Error/status steps
    error: 'An error occurred during processing',
    warning: 'A warning was generated during processing',
    info: 'Informational message'
  };
  
  return descriptions[step] || '';
}

export function isCriticalStep(step: ProgressStep): boolean {
  const criticalSteps: ProgressStep[] = [
    'llm_api_call',
    'saving_files',
    'starting_process',
    'websocket_connection'
  ];
  
  return criticalSteps.includes(step);
}

export function canSkipStep(step: ProgressStep): boolean {
  return !isCriticalStep(step);
}
