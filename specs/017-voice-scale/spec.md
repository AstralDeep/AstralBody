# Spec 017: Voice System Scalability & Resilience

**User Story**: US-16 — As a user, I want realtime voice in/out with the system.

**Status**: In Progress  
**Branch**: `016-voice-scale`  
**Constitution**: v1.1.0

## Overview

The realtime voice system already exists and works — STT via WebSocket streaming to
Speaches.ai's Realtime API, TTS via Speaches.ai REST, and WebRTC-compatible 24kHz
PCM16 audio streaming from the browser. This spec covers analyzing OpenAI's approach
to scaling voice AI and applying lessons from that analysis to make AstralBody's
voice system more robust, observable, and production-ready.

## Tasks

### Task 1: Analyze OpenAI's Voice Scaling Architecture (2 hrs)

**Reference**: https://openai.com/index/delivering-low-latency-voice-ai-at-scale/

**Findings to document**:

1. OpenAI uses a **transceiver model** — a WebRTC edge service terminates client
   connections and converts media/events into simpler internal protocols. This is
   already the pattern AstralBody uses (the `/api/voice/stream` WebSocket is a
   transceiver that proxies to Speaches.ai's Realtime API).

2. OpenAI's key challenge was **one-port-per-session vs Kubernetes** — they moved to
   single-port-per-server with application-level demux. AstralBody doesn't have this
   problem because: (a) we use HTTP WebSockets (not UDP/ICE), (b) all audio flows
   through Speaches.ai's hosted Realtime API, and (c) our Docker Compose deployment
   has a single backend instance.

3. OpenAI uses **split relay + transceiver** to keep WebRTC session state stable
   while routing packets dynamically. AstralBody's equivalent is the WebSocket
   proxy pattern where the backend holds the Speaches.ai Realtime connection and
   the frontend connects to the backend via WebSocket.

**Key takeaway**: AstralBody's architecture is fundamentally sound for our scale
(single deployment, not global 900M+ users). The primary improvements needed are
around **resilience** (connection drops, reconnection, graceful degradation) rather
than horizontal scaling.

### Task 2: Scale & Resilience Improvements (5 hrs)

Based on the analysis, implement the following improvements:

#### 2a. Connection Resilience
- [x] Review existing reconnection logic in frontend voice WebSocket
- [x] Add automatic retry with exponential backoff on WebSocket drops
- [x] Preserve graceful batch-transcription fallback (already exists)

#### 2b. Observability
- [x] Add structured logging for voice session lifecycle
  - Connection opened/closed with timing
  - Speech started/stopped events with timestamps
  - Transcription completion with char count
  - Error events with categorized types

#### 2c. Session Management
- [x] Add server-side voice session tracking with timeouts
- [x] Clean up stale sessions (idle > 30s)
- [x] Limit concurrent voice sessions per user to 1

#### 2d. Configuration & Graceful Degradation
- [x] Document SPEACHES_URL requirements in docker-compose.yml
- [x] Frontend should gracefully hide voice UI when SPEACHES_URL is unavailable
- [x] Add server health endpoint for voice capability (`GET /api/voice/health`)

#### 2e. Testing
- [x] Add unit tests for voice router endpoints
- [x] Add integration test for voice WebSocket lifecycle
- [x] Verify batch transcription fallback works
- [x] Test concurrent session limiting

## Constitution Compliance Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Python backend | ✅ | Backend changes in Python |
| II. Vite + React + TS | ✅ | Frontend changes in TS/TSX |
| III. 90% coverage | ✅ | New tests added for all changed paths |
| IV. Code quality | ✅ | PEP 8 + ESLint enforced |
| V. No new deps | ✅ | No new libraries |
| VI. Documentation | ✅ | Docstrings on all new functions |
| VII. Security | ✅ | No auth changes; voice endpoints already use `require_user_id` |
| VIII. UX consistency | ✅ | Voice UI components use existing design patterns |
| IX. Migrations | N/A | No schema changes |
| X. Production ready | ✅ | No stubs, proper error handling, structured logging |

## Implementation Notes

The voice system's existing architecture is:

```
Browser Microphone → MediaRecorder/AudioContext → PCM16 → WebSocket
  → Backend /api/voice/stream → Speaches.ai Realtime API WS
    → Transcription events → Backend → Frontend
```

And for output:

```
Backend Agent Text → /api/voice/speak → Speaches.ai TTS REST API
  → Audio stream → Browser Audio element playback
```

The improvements in this spec add:
- Per-session tracking on the backend with cleanup
- Better error handling and observability
- Health-check endpoint for capability detection
- Frontend graceful degradation when voice isn't available
- Tests for all new behavior