#!/usr/bin/env python3
"""
Progress indication system for AstralBody.

Provides ProgressEvent, ProgressPhase, ProgressStep enums and ProgressEmitter
for emitting structured progress events during agent generation and testing.
"""

import json
import time
import logging
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, Callable, Union
from enum import Enum

logger = logging.getLogger("ProgressSystem")


class ProgressPhase(str, Enum):
    """Phase of the agent creation process."""
    GENERATION = "generation"
    TESTING = "testing"
    INSTALLATION = "installation"


class ProgressStep(str, Enum):
    """Individual steps within each phase."""
    # Generation steps
    PROMPT_CONSTRUCTION = "prompt_construction"
    LLM_API_CALL = "llm_api_call"
    RESPONSE_RECEIVED = "response_received"
    JSON_PARSING = "json_parsing"
    STRUCTURE_VALIDATION = "structure_validation"
    CODE_CLEANING = "code_cleaning"
    GENERATION_COMPLETE = "generation_complete"
    
    # Testing steps
    SAVING_FILES = "saving_files"
    STARTING_PROCESS = "starting_process"
    WAITING_FOR_BOOT = "waiting_for_boot"
    WEBSOCKET_CONNECTION = "websocket_connection"
    AGENT_REGISTRATION = "agent_registration"
    TOOLS_LIST_TEST = "tools_list_test"
    TOOLS_CALL_TEST = "tools_call_test"
    VALIDATION_COMPLETE = "validation_complete"
    INTEGRATION_READY = "integration_ready"
    TESTING_COMPLETE = "testing_complete"
    
    # Error/status steps
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ProgressEvent:
    """Structured progress event for tracking agent creation progress."""
    phase: ProgressPhase
    step: ProgressStep
    percentage: int  # 0-100
    message: str
    data: Optional[Dict[str, Any]] = None
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()
        
        # Validate percentage
        if not 0 <= self.percentage <= 100:
            logger.warning(f"Progress percentage out of range: {self.percentage}")
            self.percentage = max(0, min(100, self.percentage))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "type": "progress",
            "phase": self.phase.value,
            "step": self.step.value,
            "percentage": self.percentage,
            "message": self.message,
            "data": self.data or {},
            "timestamp": self.timestamp
        }
    
    def to_sse(self) -> str:
        """Convert to Server-Sent Event format."""
        return f"data: {json.dumps(self.to_dict())}\n\n"
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProgressEvent":
        """Create ProgressEvent from dictionary."""
        return cls(
            phase=ProgressPhase(data["phase"]),
            step=ProgressStep(data["step"]),
            percentage=data["percentage"],
            message=data["message"],
            data=data.get("data"),
            timestamp=data.get("timestamp", time.time())
        )


class ProgressEmitter:
    """Utility class for emitting progress events with callbacks."""
    
    def __init__(self, 
                 phase: ProgressPhase,
                 callback: Optional[Callable[[ProgressEvent], None]] = None):
        self.phase = phase
        self.callback = callback
        self.current_step: Optional[ProgressStep] = None
        self.start_time = time.time()
        self.last_emit_time = 0.0
        self.emit_count = 0
    
    def emit(self, 
             step: ProgressStep,
             percentage: int,
             message: str,
             data: Optional[Dict[str, Any]] = None,
             force: bool = False) -> ProgressEvent:
        """
        Emit a progress event.
        
        Args:
            step: The current progress step
            percentage: Completion percentage (0-100)
            message: Human-readable message
            data: Additional context data
            force: Force emission even if throttled
            
        Returns:
            The emitted ProgressEvent
        """
        # Throttle rapid emissions (min 100ms between events)
        current_time = time.time()
        if not force and current_time - self.last_emit_time < 0.1:
            # Skip rapid emissions to avoid overwhelming the client
            return None
        
        event = ProgressEvent(
            phase=self.phase,
            step=step,
            percentage=percentage,
            message=message,
            data=data
        )
        
        self.current_step = step
        self.last_emit_time = current_time
        self.emit_count += 1
        
        # Log for debugging
        logger.debug(f"Progress: {self.phase.value}.{step.value} ({percentage}%): {message}")
        
        # Call callback if provided
        if self.callback:
            try:
                self.callback(event)
            except Exception as e:
                logger.error(f"Progress callback failed: {e}")
                # Don't raise, continue execution
        
        return event
    
    def emit_sse(self, 
                 step: ProgressStep,
                 percentage: int,
                 message: str,
                 data: Optional[Dict[str, Any]] = None) -> str:
        """
        Emit and return SSE formatted string.
        
        Returns:
            SSE formatted string ready for streaming
        """
        event = self.emit(step, percentage, message, data)
        if event:
            return event.to_sse()
        return ""
    
    def emit_error(self, 
                   message: str,
                   error: Optional[Exception] = None,
                   data: Optional[Dict[str, Any]] = None) -> ProgressEvent:
        """Emit an error progress event."""
        error_data = {
            "error": True,
            "error_message": message,
            "error_type": error.__class__.__name__ if error else "Unknown",
            "error_details": str(error) if error else None
        }
        if data:
            error_data.update(data)
        
        return self.emit(
            step=ProgressStep.ERROR,
            percentage=100,  # Error completes the phase
            message=message,
            data=error_data,
            force=True  # Always emit errors
        )
    
    def emit_warning(self, 
                     message: str,
                     data: Optional[Dict[str, Any]] = None) -> ProgressEvent:
        """Emit a warning progress event."""
        warning_data = {"warning": True, "warning_message": message}
        if data:
            warning_data.update(data)
        
        return self.emit(
            step=ProgressStep.WARNING,
            percentage=self._get_current_percentage(),
            message=message,
            data=warning_data
        )
    
    def get_elapsed_time(self) -> float:
        """Get elapsed time in seconds since emitter creation."""
        return time.time() - self.start_time
    
    def _get_current_percentage(self) -> int:
        """Get current percentage based on phase and step."""
        # Default mapping if not explicitly provided
        phase_steps = {
            ProgressPhase.GENERATION: [
                (ProgressStep.PROMPT_CONSTRUCTION, 10),
                (ProgressStep.LLM_API_CALL, 30),
                (ProgressStep.RESPONSE_RECEIVED, 40),
                (ProgressStep.JSON_PARSING, 50),
                (ProgressStep.STRUCTURE_VALIDATION, 60),
                (ProgressStep.CODE_CLEANING, 70),
                (ProgressStep.GENERATION_COMPLETE, 100)
            ],
            ProgressPhase.TESTING: [
                (ProgressStep.SAVING_FILES, 10),
                (ProgressStep.STARTING_PROCESS, 20),
                (ProgressStep.WAITING_FOR_BOOT, 30),
                (ProgressStep.WEBSOCKET_CONNECTION, 40),
                (ProgressStep.AGENT_REGISTRATION, 50),
                (ProgressStep.TOOLS_LIST_TEST, 60),
                (ProgressStep.TOOLS_CALL_TEST, 70),
                (ProgressStep.VALIDATION_COMPLETE, 80),
                (ProgressStep.INTEGRATION_READY, 90),
                (ProgressStep.TESTING_COMPLETE, 100)
            ]
        }
        
        steps = phase_steps.get(self.phase, [])
        for step_def, percentage in steps:
            if self.current_step == step_def:
                return percentage
        
        # Default to 0 if not found
        return 0


def create_log_event(message: str, status: str = "log") -> str:
    """
    Create a legacy log event for backward compatibility.
    
    Returns:
        SSE formatted log event
    """
    event = {
        "status": status,
        "message": message,
        "timestamp": time.time()
    }
    return f"data: {json.dumps(event)}\n\n"


def create_progress_from_log(message: str, 
                             phase: ProgressPhase,
                             step: ProgressStep) -> ProgressEvent:
    """
    Create a progress event from a log message.
    
    Useful for converting existing log messages to progress events.
    """
    return ProgressEvent(
        phase=phase,
        step=step,
        percentage=0,  # Unknown percentage
        message=message
    )
