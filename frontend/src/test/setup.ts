import '@testing-library/jest-dom';
import { vi, afterEach, beforeEach } from 'vitest';
import { backgroundFetchCache } from '../lib/backgroundFetchCache';

// Mock global objects
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// Mock ResizeObserver
(window as any).ResizeObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
}));

// Mock IntersectionObserver
(window as any).IntersectionObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
  root: null,
  rootMargin: '',
  thresholds: [],
}));

// Mock fetch for API calls
(window as any).fetch = vi.fn();

// Mock EventSource for SSE
(window as any).EventSource = vi.fn().mockImplementation(() => ({
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
  close: vi.fn(),
  readyState: 0,
  url: '',
}));

// Reset the module-scoped session fetch cache before every test so
// cached promises do not leak across tests (feature 010-fix-page-flash).
beforeEach(() => {
  backgroundFetchCache._resetForTests();
});

// Clean up after each test
afterEach(() => {
  vi.clearAllMocks();
});