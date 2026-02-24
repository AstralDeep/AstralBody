import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import AgentCreatorPage from '../AgentCreatorPage';

// Mock the hooks and dependencies
vi.mock('../../hooks/useProgressSSE', () => ({
  useProgressSSE: vi.fn(() => ({
    state: {
      phase: 'idle',
      currentStep: 0,
      percentage: 0,
      message: '',
      data: null,
      startTime: Date.now(),
      elapsedTime: 0,
      steps: [],
      completedSteps: new Set(),
      failedSteps: new Set(),
      isComplete: false,
      isError: false,
    },
    connect: vi.fn(),
    disconnect: vi.fn(),
    isConnected: false,
    error: null,
  })),
}));

vi.mock('react-markdown', () => ({
  default: ({ children }: { children: string }) => <div>{children}</div>,
}));

vi.mock('react-simple-code-editor', () => ({
  default: ({ value, onValueChange }: any) => (
    <textarea
      data-testid="code-editor"
      value={value}
      onChange={(e) => onValueChange(e.target.value)}
    />
  ),
}));

vi.mock('prismjs', () => ({
  highlight: vi.fn((code) => code),
  languages: {
    python: {},
  },
}));

describe('AgentCreatorPage', () => {
  const mockOnBack = vi.fn();
  const mockAccessToken = 'mock-token';

  beforeEach(() => {
    global.fetch = vi.fn();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the form step by default', () => {
    render(<AgentCreatorPage onBack={mockOnBack} />);
    
    expect(screen.getByText('Agent Parameters')).toBeInTheDocument();
    expect(screen.getByLabelText(/Agent Name/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Persona/)).toBeInTheDocument();
    expect(screen.getByText('Start Generation Session')).toBeInTheDocument();
  });

  it('validates required fields in form', async () => {
    render(<AgentCreatorPage onBack={mockOnBack} />);
    
    const submitButton = screen.getByText('Start Generation Session');
    fireEvent.click(submitButton);
    
    // Should not call fetch because required fields are empty
    await waitFor(() => {
      expect(global.fetch).not.toHaveBeenCalled();
    });
  });

  it('submits form and transitions to chat step', async () => {
    // Mock successful API response
    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'test-session-123',
        initial_response: 'I have received your requirements.',
      }),
    });

    render(<AgentCreatorPage onBack={mockOnBack} accessToken={mockAccessToken} />);
    
    // Fill form
    fireEvent.change(screen.getByLabelText(/Agent Name/), {
      target: { value: 'TestAgent' },
    });
    fireEvent.change(screen.getByLabelText(/Persona/), {
      target: { value: 'A test agent for demonstration' },
    });
    
    // Submit form
    fireEvent.click(screen.getByText('Start Generation Session'));
    
    // Verify API call
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/agent-creator/start'),
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Authorization': 'Bearer mock-token',
          }),
          body: JSON.stringify({
            name: 'TestAgent',
            persona: 'A test agent for demonstration',
            toolsDescription: '',
            apiKeys: '',
          }),
        })
      );
    });

    // Should transition to chat step
    await waitFor(() => {
      expect(screen.getByText('I have received your requirements.')).toBeInTheDocument();
    });
  });

  it('handles chat message sending', async () => {
    // Mock session start
    (global.fetch as any)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          session_id: 'test-session-123',
          initial_response: 'Initial response',
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          response: 'Assistant response',
        }),
      });

    render(<AgentCreatorPage onBack={mockOnBack} accessToken={mockAccessToken} />);
    
    // Fill and submit form to get to chat
    fireEvent.change(screen.getByLabelText(/Agent Name/), {
      target: { value: 'TestAgent' },
    });
    fireEvent.change(screen.getByLabelText(/Persona/), {
      target: { value: 'Test persona' },
    });
    fireEvent.click(screen.getByText('Start Generation Session'));
    
    // Wait for chat to appear
    await waitFor(() => {
      expect(screen.getByText('Initial response')).toBeInTheDocument();
    });
    
    // Find chat input and send message
    const chatInput = screen.getByPlaceholderText(/Refine the agent further/);
    fireEvent.change(chatInput, { target: { value: 'Test message' } });
    fireEvent.click(screen.getByRole('button', { name: /send/i }));
    
    // Verify chat API call
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/agent-creator/chat'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            session_id: 'test-session-123',
            message: 'Test message',
          }),
        })
      );
    });

    // Should show assistant response
    await waitFor(() => {
      expect(screen.getByText('Assistant response')).toBeInTheDocument();
    });
  });

  it('handles package installation prompt', async () => {
    // Mock chat response with package installation required
    (global.fetch as any)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          session_id: 'test-session-123',
          initial_response: 'Initial',
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          response: 'Need packages',
          tool_call_id: 'tool-123',
          required_packages: ['requests', 'pandas'],
        }),
      });

    render(<AgentCreatorPage onBack={mockOnBack} accessToken={mockAccessToken} />);
    
    // Get to chat
    fireEvent.change(screen.getByLabelText(/Agent Name/), { target: { value: 'Test' } });
    fireEvent.change(screen.getByLabelText(/Persona/), { target: { value: 'Test' } });
    fireEvent.click(screen.getByText('Start Generation Session'));
    
    // Send message that triggers package prompt
    await waitFor(() => {
      const chatInput = screen.getByPlaceholderText(/Refine the agent further/);
      fireEvent.change(chatInput, { target: { value: 'Test' } });
      fireEvent.click(screen.getByRole('button', { name: /send/i }));
    });
    
    // Should show package installation prompt
    await waitFor(() => {
      expect(screen.getByText('Package Installation Required')).toBeInTheDocument();
      expect(screen.getByText('requests')).toBeInTheDocument();
      expect(screen.getByText('pandas')).toBeInTheDocument();
    });
  });

  it('transitions to editor step when generation completes', async () => {
    // Mock useProgressSSE to simulate completion
    const mockUseProgressSSE = vi.fn();
    vi.doMock('../../hooks/useProgressSSE', () => ({
      useProgressSSE: mockUseProgressSSE,
    }));

    // Re-import with mock
    const { default: AgentCreatorPage } = await import('../AgentCreatorPage');
    
    // Mock progress completion with files
    mockUseProgressSSE.mockReturnValue({
      state: {
        phase: 'generation',
        currentStep: 5,
        percentage: 100,
        message: 'Generation complete',
        data: {
          result: {
            files: {
              tools: 'def tool1(): pass',
              agent: 'class Agent: pass',
              server: 'from fastapi import FastAPI',
            },
          },
        },
        startTime: Date.now() - 5000,
        elapsedTime: 5000,
        steps: [],
        completedSteps: new Set(),
        failedSteps: new Set(),
        isComplete: true,
        isError: false,
      },
      connect: vi.fn(),
      disconnect: vi.fn(),
      isConnected: true,
      error: null,
    });

    // Mock session start
    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'test-session-123',
        initial_response: 'Initial',
      }),
    });

    render(<AgentCreatorPage onBack={mockOnBack} accessToken={mockAccessToken} />);
    
    // Get to chat first
    fireEvent.change(screen.getByLabelText(/Agent Name/), { target: { value: 'Test' } });
    fireEvent.change(screen.getByLabelText(/Persona/), { target: { value: 'Test' } });
    fireEvent.click(screen.getByText('Start Generation Session'));
    
    // Click generate code button
    await waitFor(() => {
      const generateButton = screen.getByText('Generate Code');
      fireEvent.click(generateButton);
    });
    
    // Should show editor with generated files
    await waitFor(() => {
      expect(screen.getByText('Review & Edit Agent Files')).toBeInTheDocument();
      expect(screen.getByText('tools.py')).toBeInTheDocument();
      expect(screen.getByText('agent.py')).toBeInTheDocument();
      expect(screen.getByText('server.py')).toBeInTheDocument();
    });
  });
});
