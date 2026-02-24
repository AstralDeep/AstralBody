#!/usr/bin/env python3
"""
Test the progress indication system.
"""

import sys
import os
import json
import asyncio
from unittest.mock import Mock, AsyncMock

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from shared.progress import (
    ProgressPhase,
    ProgressStep,
    ProgressEvent,
    ProgressEmitter,
    create_log_event,
    create_progress_from_log
)


def test_progress_event_creation():
    """Test basic ProgressEvent creation and serialization."""
    event = ProgressEvent(
        phase=ProgressPhase.GENERATION,
        step=ProgressStep.PROMPT_CONSTRUCTION,
        percentage=10,
        message="Constructing prompt...",
        data={"agent_name": "test_agent"}
    )
    
    # Test basic properties
    assert event.phase == ProgressPhase.GENERATION
    assert event.step == ProgressStep.PROMPT_CONSTRUCTION
    assert event.percentage == 10
    assert event.message == "Constructing prompt..."
    assert event.data["agent_name"] == "test_agent"
    assert event.timestamp is not None
    
    # Test to_dict
    event_dict = event.to_dict()
    assert event_dict["type"] == "progress"
    assert event_dict["phase"] == "generation"
    assert event_dict["step"] == "prompt_construction"
    assert event_dict["percentage"] == 10
    assert event_dict["message"] == "Constructing prompt..."
    assert event_dict["data"]["agent_name"] == "test_agent"
    assert "timestamp" in event_dict
    
    # Test to_sse
    sse = event.to_sse()
    assert sse.startswith("data: ")
    assert sse.endswith("\n\n")
    
    # Test from_dict
    event2 = ProgressEvent.from_dict(event_dict)
    assert event2.phase == event.phase
    assert event2.step == event.step
    assert event2.percentage == event.percentage
    assert event2.message == event.message
    assert event2.data == event.data
    
    print("✓ ProgressEvent creation and serialization tests passed")


def test_progress_event_validation():
    """Test percentage validation and edge cases."""
    # Test percentage clamping
    event_low = ProgressEvent(
        phase=ProgressPhase.GENERATION,
        step=ProgressStep.PROMPT_CONSTRUCTION,
        percentage=-10,
        message="Test"
    )
    assert event_low.percentage == 0  # Should be clamped to 0
    
    event_high = ProgressEvent(
        phase=ProgressPhase.GENERATION,
        step=ProgressStep.PROMPT_CONSTRUCTION,
        percentage=150,
        message="Test"
    )
    assert event_high.percentage == 100  # Should be clamped to 100
    
    # Test valid percentages
    event_valid = ProgressEvent(
        phase=ProgressPhase.GENERATION,
        step=ProgressStep.PROMPT_CONSTRUCTION,
        percentage=50,
        message="Test"
    )
    assert event_valid.percentage == 50
    
    print("✓ ProgressEvent validation tests passed")


def test_progress_emitter_basic():
    """Test ProgressEmitter basic functionality."""
    mock_callback = Mock()
    emitter = ProgressEmitter(
        phase=ProgressPhase.GENERATION,
        callback=mock_callback
    )
    
    # Test emit
    event = emitter.emit(
        step=ProgressStep.PROMPT_CONSTRUCTION,
        percentage=10,
        message="Constructing prompt...",
        data={"agent_name": "test"}
    )
    
    assert event is not None
    assert event.phase == ProgressPhase.GENERATION
    assert event.step == ProgressStep.PROMPT_CONSTRUCTION
    assert event.percentage == 10
    
    # Verify callback was called
    mock_callback.assert_called_once()
    callback_event = mock_callback.call_args[0][0]
    assert callback_event == event
    
    # Test current_step tracking
    assert emitter.current_step == ProgressStep.PROMPT_CONSTRUCTION
    assert emitter.emit_count == 1
    
    print("✓ ProgressEmitter basic tests passed")


def test_progress_emitter_throttling():
    """Test that rapid emissions are throttled."""
    mock_callback = Mock()
    emitter = ProgressEmitter(
        phase=ProgressPhase.GENERATION,
        callback=mock_callback
    )
    
    # First emit should work
    event1 = emitter.emit(
        step=ProgressStep.PROMPT_CONSTRUCTION,
        percentage=10,
        message="First"
    )
    assert event1 is not None
    
    # Immediately try second emit (should be throttled)
    event2 = emitter.emit(
        step=ProgressStep.LLM_API_CALL,
        percentage=20,
        message="Second"
    )
    # Should return None due to throttling
    assert event2 is None
    
    # Force emit should work
    event3 = emitter.emit(
        step=ProgressStep.LLM_API_CALL,
        percentage=20,
        message="Forced",
        force=True
    )
    assert event3 is not None
    
    # Verify only 2 calls (first + forced)
    assert mock_callback.call_count == 2
    
    print("✓ ProgressEmitter throttling tests passed")


def test_progress_emitter_error_warning():
    """Test error and warning emission."""
    mock_callback = Mock()
    emitter = ProgressEmitter(
        phase=ProgressPhase.GENERATION,
        callback=mock_callback
    )
    
    # Test error emission
    error = Exception("Test error")
    error_event = emitter.emit_error(
        message="Something went wrong",
        error=error,
        data={"extra": "info"}
    )
    
    assert error_event is not None
    assert error_event.step == ProgressStep.ERROR
    assert error_event.percentage == 100  # Errors complete the phase
    assert error_event.data["error"] == True
    assert error_event.data["error_type"] == "Exception"
    assert error_event.data["error_details"] == "Test error"
    assert error_event.data["extra"] == "info"
    
    # Test warning emission - might be throttled since we just emitted an error
    # Add a small delay to avoid throttling
    import time
    time.sleep(0.11)  # Just over 100ms
    
    warning_event = emitter.emit_warning(
        message="This is a warning",
        data={"severity": "low"}
    )
    
    assert warning_event is not None
    assert warning_event.step == ProgressStep.WARNING
    assert warning_event.data["warning"] == True
    assert warning_event.data["warning_message"] == "This is a warning"
    assert warning_event.data["severity"] == "low"
    
    print("✓ ProgressEmitter error/warning tests passed")


def test_progress_emitter_percentage_mapping():
    """Test automatic percentage mapping based on step."""
    emitter = ProgressEmitter(phase=ProgressPhase.GENERATION)
    
    # Test generation phase steps
    emitter.current_step = ProgressStep.PROMPT_CONSTRUCTION
    assert emitter._get_current_percentage() == 10
    
    emitter.current_step = ProgressStep.LLM_API_CALL
    assert emitter._get_current_percentage() == 30
    
    emitter.current_step = ProgressStep.GENERATION_COMPLETE
    assert emitter._get_current_percentage() == 100
    
    # Test testing phase steps
    emitter2 = ProgressEmitter(phase=ProgressPhase.TESTING)
    emitter2.current_step = ProgressStep.SAVING_FILES
    assert emitter2._get_current_percentage() == 10
    
    emitter2.current_step = ProgressStep.TESTING_COMPLETE
    assert emitter2._get_current_percentage() == 100
    
    # Test unknown step
    emitter3 = ProgressEmitter(phase=ProgressPhase.GENERATION)
    emitter3.current_step = ProgressStep.ERROR
    assert emitter3._get_current_percentage() == 0  # Default
    
    print("✓ ProgressEmitter percentage mapping tests passed")


def test_legacy_functions():
    """Test legacy compatibility functions."""
    # Test create_log_event
    sse_log = create_log_event("Test log message", "log")
    assert sse_log.startswith("data: ")
    assert sse_log.endswith("\n\n")
    
    # Parse the JSON to verify structure
    import json
    json_start = sse_log[6:-2]  # Remove "data: " and "\n\n"
    log_data = json.loads(json_start)
    assert log_data["status"] == "log"
    assert log_data["message"] == "Test log message"
    assert "timestamp" in log_data
    
    # Test create_progress_from_log
    progress_event = create_progress_from_log(
        message="Log converted to progress",
        phase=ProgressPhase.GENERATION,
        step=ProgressStep.INFO
    )
    assert progress_event.phase == ProgressPhase.GENERATION
    assert progress_event.step == ProgressStep.INFO
    assert progress_event.message == "Log converted to progress"
    assert progress_event.percentage == 0
    
    print("✓ Legacy functions tests passed")


def test_progress_emitter_sse():
    """Test SSE formatting from emitter."""
    emitter = ProgressEmitter(phase=ProgressPhase.GENERATION)
    
    sse_string = emitter.emit_sse(
        step=ProgressStep.PROMPT_CONSTRUCTION,
        percentage=10,
        message="Test SSE",
        data={"test": True}
    )
    
    assert sse_string.startswith("data: ")
    assert sse_string.endswith("\n\n")
    
    # Verify it contains valid JSON
    json_start = sse_string[6:-2]
    sse_data = json.loads(json_start)
    assert sse_data["type"] == "progress"
    assert sse_data["phase"] == "generation"
    assert sse_data["step"] == "prompt_construction"
    
    print("✓ ProgressEmitter SSE tests passed")


def test_integration_with_agent_generator():
    """Test that ProgressEmitter integrates with agent_generator."""
    # This is a more complex test that would require mocking
    # For now, just verify imports work
    from orchestrator.agent_generator import AgentGeneratorClient
    from shared.progress import ProgressEmitter, ProgressPhase
    
    # Create a mock callback to collect events
    collected_events = []
    
    def collect_event(event):
        collected_events.append(event)
    
    # Create emitter with callback
    emitter = ProgressEmitter(
        phase=ProgressPhase.GENERATION,
        callback=collect_event
    )
    
    # Simulate a generation flow
    steps = [
        (ProgressStep.PROMPT_CONSTRUCTION, 10, "Building prompt..."),
        (ProgressStep.LLM_API_CALL, 30, "Calling LLM..."),
        (ProgressStep.RESPONSE_RECEIVED, 40, "Response received"),
        (ProgressStep.GENERATION_COMPLETE, 100, "Generation complete!")
    ]
    
    for step, percentage, message in steps:
        emitter.emit(step, percentage, message, force=True)
    
    assert len(collected_events) == 4
    assert collected_events[0].step == ProgressStep.PROMPT_CONSTRUCTION
    assert collected_events[-1].step == ProgressStep.GENERATION_COMPLETE
    assert collected_events[-1].percentage == 100
    
    print("✓ Integration test passed")


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("Testing Progress Indication System")
    print("="*60 + "\n")
    
    tests = [
        test_progress_event_creation,
        test_progress_event_validation,
        test_progress_emitter_basic,
        test_progress_emitter_throttling,
        test_progress_emitter_error_warning,
        test_progress_emitter_percentage_mapping,
        test_legacy_functions,
        test_progress_emitter_sse,
        test_integration_with_agent_generator
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"✗ {test_func.__name__} failed: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "="*60)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("="*60)
    
    if failed > 0:
        sys.exit(1)
    else:
        print("\nAll progress system tests passed!")


if __name__ == "__main__":
    main()
