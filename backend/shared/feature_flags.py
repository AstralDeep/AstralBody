"""
Feature Flags — Environment-driven feature gating for safe rollout.

Usage:
    from shared.feature_flags import flags
    if flags.is_enabled("message_compaction"):
        ...
"""
import os


class FeatureFlags:
    """Simple env-var-driven feature flag registry."""

    def __init__(self):
        self._flags = {
            "denial_loop_detection": self._read("FF_DENIAL_LOOP_DETECTION", True),
            "tool_concurrency_safety": self._read("FF_TOOL_CONCURRENCY_SAFETY", True),
            "message_compaction": self._read("FF_MESSAGE_COMPACTION", False),
            "progress_streaming": self._read("FF_PROGRESS_STREAMING", False),
            "hook_system": self._read("FF_HOOK_SYSTEM", False),
            "task_state_machine": self._read("FF_TASK_STATE_MACHINE", False),
            "coordinator_mode": self._read("FF_COORDINATOR_MODE", False),
            "knowledge_synthesis": self._read("FF_KNOWLEDGE_SYNTHESIS", False),
            "live_streaming": self._read("FF_LIVE_STREAMING", False),
        }

    @staticmethod
    def _read(env_var: str, default: bool) -> bool:
        return os.getenv(env_var, str(default)).lower() in ("true", "1", "yes")

    def is_enabled(self, flag: str) -> bool:
        return self._flags.get(flag, False)


flags = FeatureFlags()
