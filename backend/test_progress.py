#!/usr/bin/env python3
"""Test script to verify progress system functionality"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from shared.progress import (
    ProgressEvent,
    ProgressPhase,
    ProgressStep,
    ProgressEmitter,
    create_log_event
)

def test_progress_module():
    print("Testing progress module...")
    
    # Test 1: ProgressEvent creation
    event = ProgressEvent(
        phase=ProgressPhase.GENERATION,
        step=ProgressStep.PROMPT_CONSTRUCTION,
        percentage=10,
        message="Constructing prompt...",
        data={"agent_name": "test_agent"},
        timestamp=1234567890.0
    )
    print(f"[OK] ProgressEvent created: {event.phase}.{event.step} at {event.percentage}%")
    
    # Test 2: ProgressEmitter with callback
    events_received = []
    def callback(evt: ProgressEvent):
        events_received.append(evt)
        print(f"  Callback: {evt.step} - {evt.message}")
    
    emitter = ProgressEmitter(ProgressPhase.GENERATION, callback)
    
    # Test 3: Emit progress
    emitter.emit(
        ProgressStep.PROMPT_CONSTRUCTION,
        percentage=10,
        message="Constructing generation prompt...",
        data={"test": True}
    )
    
    emitter.emit(
        ProgressStep.LLM_API_CALL,
        percentage=30,
        message="Calling LLM API..."
    )
    
    # Test 4: Emit error
    try:
        raise ValueError("Test error")
    except Exception as e:
        emitter.emit_error(
            message="Test error occurred",
            error=e,
            data={"error_type": "test"}
        )
    
    # Test 5: Create log event
    log_event = create_log_event("Test log message", {"extra": "data"})
    print(f"[OK] Log event created: {log_event}")
    
    # Test 6: Verify events were received
    print(f"\nTotal events received: {len(events_received)}")
    for i, evt in enumerate(events_received):
        print(f"  {i+1}. {evt.step} ({evt.percentage}%): {evt.message[:50]}...")
    
    print("\n[PASS] All progress module tests passed!")
    return True

if __name__ == "__main__":
    try:
        test_progress_module()
    except Exception as e:
        print(f"[FAIL] Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)