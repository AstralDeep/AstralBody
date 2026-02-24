#!/usr/bin/env python3
"""
Integration test for progress system frontend-backend communication.
"""

import sys
import os
import json
import asyncio
import time
from unittest.mock import Mock, patch, AsyncMock

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from shared.progress import ProgressPhase, ProgressStep, ProgressEvent, ProgressEmitter


def test_progress_event_compatibility():
    """Test that backend ProgressEvent matches frontend TypeScript interface."""
    # Create a backend event
    backend_event = ProgressEvent(
        phase=ProgressPhase.GENERATION,
        step=ProgressStep.PROMPT_CONSTRUCTION,
        percentage=10,
        message="Constructing prompt...",
        data={"agent_name": "test"},
        timestamp=time.time()
    )
    
    # Convert to dict (as would be sent over SSE)
    event_dict = backend_event.to_dict()
    
    # Verify structure matches frontend expectations
    assert event_dict["type"] == "progress"
    assert event_dict["phase"] == "generation"  # lowercase string
    assert event_dict["step"] == "prompt_construction"  # lowercase string
    assert event_dict["percentage"] == 10
    assert event_dict["message"] == "Constructing prompt..."
    assert event_dict["data"]["agent_name"] == "test"
    assert "timestamp" in event_dict
    
    # Verify all required fields are present
    required_fields = ["type", "phase", "step", "percentage", "message", "data", "timestamp"]
    for field in required_fields:
        assert field in event_dict, f"Missing field: {field}"
    
    print("[OK] ProgressEvent compatibility test passed")


def test_sse_format():
    """Test SSE format matches frontend expectations."""
    backend_event = ProgressEvent(
        phase=ProgressPhase.TESTING,
        step=ProgressStep.SAVING_FILES,
        percentage=10,
        message="Saving files...",
        timestamp=time.time()
    )
    
    sse = backend_event.to_sse()
    
    # Verify SSE format
    assert sse.startswith("data: ")
    assert sse.endswith("\n\n")
    
    # Extract JSON and verify it's valid
    json_str = sse[6:-2]  # Remove "data: " and "\n\n"
    parsed = json.loads(json_str)
    assert parsed["type"] == "progress"
    
    print("[OK] SSE format test passed")


def test_legacy_log_compatibility():
    """Test legacy log events are properly formatted."""
    from shared.progress import create_log_event
    
    # Test log event
    sse_log = create_log_event("Test log message", "log")
    assert sse_log.startswith("data: ")
    assert sse_log.endswith("\n\n")
    
    # Parse and verify structure
    json_str = sse_log[6:-2]
    log_data = json.loads(json_str)
    assert log_data["status"] == "log"
    assert log_data["message"] == "Test log message"
    assert "timestamp" in log_data
    
    # Test success event
    sse_success = create_log_event("Success!", "success")
    json_str = sse_success[6:-2]
    success_data = json.loads(json_str)
    assert success_data["status"] == "success"
    
    # Test error event
    sse_error = create_log_event("Error!", "error")
    json_str = sse_error[6:-2]
    error_data = json.loads(json_str)
    assert error_data["status"] == "error"
    
    print("[OK] Legacy log compatibility test passed")


def test_progress_emitter_integration():
    """Test ProgressEmitter produces events that can be consumed by frontend."""
    collected_events = []
    
    def collect_event(event):
        collected_events.append(event)
    
    emitter = ProgressEmitter(
        phase=ProgressPhase.GENERATION,
        callback=collect_event
    )
    
    # Simulate a generation flow
    steps = [
        (ProgressStep.PROMPT_CONSTRUCTION, 10, "Building prompt..."),
        (ProgressStep.LLM_API_CALL, 30, "Calling LLM..."),
        (ProgressStep.RESPONSE_RECEIVED, 40, "Response received"),
        (ProgressStep.GENERATION_COMPLETE, 100, "Done!")
    ]
    
    for step, percentage, message in steps:
        emitter.emit(step, percentage, message, force=True)
    
    # Verify events were collected
    assert len(collected_events) == 4
    
    # Verify each event has proper structure
    for event in collected_events:
        event_dict = event.to_dict()
        assert event_dict["type"] == "progress"
        assert event_dict["phase"] == "generation"
        assert event_dict["percentage"] >= 0
        assert event_dict["percentage"] <= 100
        assert isinstance(event_dict["message"], str)
        
    print("[OK] ProgressEmitter integration test passed")


def test_endpoint_simulation():
    """Simulate the generate-with-progress endpoint behavior."""
    # This test simulates what the endpoint does
    from unittest.mock import AsyncMock
    
    # Mock the agent_generator.generate_code method
    with patch('orchestrator.agent_generator.agent_generator') as mock_gen:
        # Setup mock to call progress callback
        def mock_generate_code(session_id, progress_callback=None, user_id=None):
            # Simulate progress events
            emitter = ProgressEmitter(ProgressPhase.GENERATION, progress_callback)
            
            if progress_callback:
                # Emit some progress events
                event1 = ProgressEvent(
                    phase=ProgressPhase.GENERATION,
                    step=ProgressStep.PROMPT_CONSTRUCTION,
                    percentage=10,
                    message="Building prompt..."
                )
                progress_callback(event1)
                
                event2 = ProgressEvent(
                    phase=ProgressPhase.GENERATION,
                    step=ProgressStep.LLM_API_CALL,
                    percentage=30,
                    message="Calling LLM..."
                )
                progress_callback(event2)
                
                event3 = ProgressEvent(
                    phase=ProgressPhase.GENERATION,
                    step=ProgressStep.GENERATION_COMPLETE,
                    percentage=100,
                    message="Generation complete!"
                )
                progress_callback(event3)
            
            return {"files": {"tools": "# Test code", "agent": "", "server": ""}}
        
        mock_gen.generate_code = AsyncMock(side_effect=mock_generate_code)
        
        # Simulate what the endpoint does
        collected = []
        
        async def simulate_endpoint():
            queue = asyncio.Queue()
            
            def progress_callback(event):
                queue.put_nowait(f"data: {json.dumps(event.to_dict())}\n\n")
            
            # Simulate background task
            async def generate_task():
                result = await mock_gen.generate_code(
                    "test-session",
                    progress_callback=progress_callback,
                    user_id="test-user"
                )
                await queue.put(json.dumps({
                    "type": "complete",
                    "result": result
                }))
            
            asyncio.create_task(generate_task())
            
            # Collect events
            events = []
            for _ in range(4):  # Expect 3 progress + 1 complete
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=1.0)
                    events.append(event)
                except asyncio.TimeoutError:
                    break
            
            return events
        
        # Run simulation
        events = asyncio.run(simulate_endpoint())
        
        # Verify we got events
        assert len(events) >= 3  # At least 3 progress events
        
        # First events should be SSE formatted
        for i in range(min(3, len(events))):
            if events[i].startswith('data: '):
                # Parse and verify
                json_str = events[i][6:-2]
                data = json.loads(json_str)
                assert data["type"] == "progress"
        
        print("[OK] Endpoint simulation test passed")


def test_frontend_hook_compatibility():
    """Test that events match what useProgressSSE hook expects."""
    # Create a sample event that would come from backend
    backend_event = ProgressEvent(
        phase=ProgressPhase.GENERATION,
        step=ProgressStep.PROMPT_CONSTRUCTION,
        percentage=10,
        message="Test message",
        data={"test": True},
        timestamp=time.time()
    )
    
    event_dict = backend_event.to_dict()
    
    # This is what the frontend hook expects for new progress events
    # Based on useProgressSSE.ts line 168-170:
    # if ('type' in data && data.type === 'progress') {
    #   handleProgressEvent(data as ProgressEvent);
    # }
    
    # Verify the event has 'type' property
    assert "type" in event_dict
    assert event_dict["type"] == "progress"
    
    # Verify phase and step are strings (not enum objects)
    assert isinstance(event_dict["phase"], str)
    assert isinstance(event_dict["step"], str)
    
    # Verify percentage is a number
    assert isinstance(event_dict["percentage"], int)
    
    # Verify message is a string
    assert isinstance(event_dict["message"], str)
    
    # Verify data is an object (or empty dict)
    assert isinstance(event_dict["data"], dict)
    
    # Verify timestamp is a number
    assert isinstance(event_dict["timestamp"], (int, float))
    
    print("[OK] Frontend hook compatibility test passed")


def main():
    """Run all integration tests."""
    print("\n" + "="*60)
    print("Progress System Integration Tests")
    print("="*60 + "\n")
    
    tests = [
        test_progress_event_compatibility,
        test_sse_format,
        test_legacy_log_compatibility,
        test_progress_emitter_integration,
        test_frontend_hook_compatibility,
        test_endpoint_simulation,
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"[FAIL] {test_func.__name__} failed: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "="*60)
    print(f"Integration Test Results: {passed} passed, {failed} failed")
    print("="*60)
    
    if failed > 0:
        sys.exit(1)
    else:
        print("\nAll integration tests passed! Frontend-backend compatibility verified.")


if __name__ == "__main__":
    main()
