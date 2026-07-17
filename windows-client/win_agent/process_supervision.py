"""Frozen-safe, bounded supervision for Windows-hosted BYO agent children.

This module deliberately has no dependency on the backend application tree or
Qt.  It is bundled into ``AstralDeep.exe`` and owns every process-tree, pipe,
buffer, and cleanup decision for desktop-hosted personal agents.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any, BinaryIO, Callable, Mapping, Sequence


logger = logging.getLogger("astral.client.byo.supervision")


class OutputStream(str, Enum):
    STDOUT = "stdout"
    STDERR = "stderr"


class ProcessState(str, Enum):
    RUNNING = "running"
    STOPPING = "stopping"
    EXITED = "exited"
    FAILED = "failed"
    KILLED = "killed"


class TerminationReason(str, Enum):
    STOP = "stop"
    QUIT = "quit"
    CANCEL = "cancel"
    FAILURE = "failure"


@dataclass(frozen=True)
class ProcessSupervisionLimits:
    """The immutable feature-060 neutral supervisor limits."""

    read_chunk_bytes: int = 16 * 1024
    maximum_logical_line_bytes: int = 64 * 1024
    ring_capacity_bytes_per_stream: int = 256 * 1024
    ring_capacity_bytes_per_process: int = 512 * 1024
    force_kill_after_seconds: float = 4.0
    termination_deadline_seconds: float = 5.0

    def __post_init__(self) -> None:
        byte_values = (
            self.read_chunk_bytes,
            self.maximum_logical_line_bytes,
            self.ring_capacity_bytes_per_stream,
            self.ring_capacity_bytes_per_process,
        )
        if any(type(value) is not int or value <= 0 for value in byte_values):
            raise ValueError("process-supervision byte limits must be positive integers")
        if (
            self.ring_capacity_bytes_per_stream * 2
            > self.ring_capacity_bytes_per_process
        ):
            raise ValueError("per-stream rings exceed the per-process output bound")
        if not 0 < self.force_kill_after_seconds < self.termination_deadline_seconds:
            raise ValueError("force-kill time must precede the cleanup deadline")


DEFAULT_PROCESS_SUPERVISION_LIMITS = ProcessSupervisionLimits()


@dataclass(frozen=True)
class StreamSnapshot:
    stream: OutputStream
    lines: tuple[bytes, ...]
    total_bytes: int
    total_lines: int
    retained_bytes: int
    dropped_bytes: int
    dropped_lines: int
    overlong_lines: int
    maximum_retained_line_bytes: int
    reader_done: bool
    pipe_closed: bool
    read_error: str | None


@dataclass(frozen=True)
class ProcessSnapshot:
    process_id: uuid.UUID
    pid: int
    state: ProcessState
    exit_code: int | None
    termination_reason: TerminationReason | None
    stdout: StreamSnapshot
    stderr: StreamSnapshot
    readers_joined: bool
    monitor_joined: bool
    pipes_closed: bool
    process_tree_terminated: bool
    cleanup_duration_seconds: float
    cleanup_error: str | None


LineCallback = Callable[[bytes], None]
DiagnosticCallback = Callable[[str, OutputStream], None]
EofCallback = Callable[[OutputStream], None]


class BoundedStreamReader:
    """Continuously drain one pipe in fixed binary reads and retain a byte ring."""

    def __init__(
        self,
        *,
        stream: OutputStream,
        pipe: BinaryIO,
        limits: ProcessSupervisionLimits = DEFAULT_PROCESS_SUPERVISION_LIMITS,
        on_line: LineCallback | None = None,
        on_diagnostic: DiagnosticCallback | None = None,
        on_eof: EofCallback | None = None,
    ) -> None:
        self.stream = stream
        self._pipe = pipe
        self._limits = limits
        self._on_line = on_line
        self._on_diagnostic = on_diagnostic
        self._on_eof = on_eof
        self._condition = threading.Condition(threading.RLock())
        self._lines: deque[tuple[bytes, int]] = deque()
        self._partial = bytearray()
        self._partial_overlong = False
        self._total_bytes = 0
        self._total_lines = 0
        self._retained_bytes = 0
        self._dropped_bytes = 0
        self._dropped_lines = 0
        self._overlong_lines = 0
        self._maximum_retained_line_bytes = 0
        self._reader_done = False
        self._pipe_closed = False
        self._read_error: str | None = None

    def _append_segment_locked(self, segment: bytes) -> None:
        available = self._limits.maximum_logical_line_bytes - len(self._partial)
        retained = max(0, min(len(segment), available))
        if retained:
            self._partial.extend(segment[:retained])
        discarded = len(segment) - retained
        if discarded:
            self._dropped_bytes += discarded
            self._partial_overlong = True

    def _finish_line_locked(self, delimiter_bytes: int) -> tuple[bytes, bool]:
        line = bytes(self._partial)
        was_overlong = self._partial_overlong
        storage_bytes = len(line) + delimiter_bytes
        self._total_lines += 1
        if was_overlong:
            self._overlong_lines += 1
        self._maximum_retained_line_bytes = max(
            self._maximum_retained_line_bytes, len(line)
        )
        while (
            self._lines
            and self._retained_bytes + storage_bytes
            > self._limits.ring_capacity_bytes_per_stream
        ):
            _discarded_line, removed = self._lines.popleft()
            self._retained_bytes -= removed
            self._dropped_bytes += removed
            self._dropped_lines += 1
        if storage_bytes <= self._limits.ring_capacity_bytes_per_stream:
            self._lines.append((line, storage_bytes))
            self._retained_bytes += storage_bytes
        else:
            self._dropped_bytes += storage_bytes
            self._dropped_lines += 1
        self._partial.clear()
        self._partial_overlong = False
        self._condition.notify_all()
        return line, was_overlong

    def _consume_locked(self, chunk: bytes) -> list[tuple[bytes, bool]]:
        self._total_bytes += len(chunk)
        completed: list[tuple[bytes, bool]] = []
        cursor = 0
        while cursor < len(chunk):
            newline = chunk.find(b"\n", cursor)
            if newline < 0:
                self._append_segment_locked(chunk[cursor:])
                break
            self._append_segment_locked(chunk[cursor:newline])
            completed.append(self._finish_line_locked(delimiter_bytes=1))
            cursor = newline + 1
        return completed

    def _publish(self, lines: list[tuple[bytes, bool]]) -> None:
        for line, overlong in lines:
            try:
                if overlong:
                    if self._on_diagnostic is not None:
                        self._on_diagnostic("output_line_too_long", self.stream)
                elif self._on_line is not None:
                    self._on_line(line)
            except Exception:  # noqa: BLE001 - a consumer cannot kill the drain
                logger.exception("BYO %s output callback failed", self.stream.value)

    def close_pipe(self) -> None:
        """Idempotently close the owned pipe."""

        with self._condition:
            if self._pipe_closed:
                return
            try:
                self._pipe.close()
            except (OSError, ValueError):
                pass
            self._pipe_closed = True
            self._condition.notify_all()

    def _read_chunk(self) -> bytes:
        read = getattr(self._pipe, "read", None)
        if callable(read):
            value = read(self._limits.read_chunk_bytes)
        else:
            # Narrow injected-process compatibility seam used by the existing
            # feature-058 fake pipes. Production Popen pipes always use read().
            value = self._pipe.readline()
        if isinstance(value, str):
            return value.encode("utf-8", errors="replace")
        return value or b""

    def run(self) -> None:
        """Drain to EOF, publish bounded lines, close the pipe, then signal EOF."""

        try:
            while True:
                chunk = self._read_chunk()
                if not chunk:
                    break
                with self._condition:
                    completed = self._consume_locked(chunk)
                self._publish(completed)
        except (OSError, ValueError) as exc:
            with self._condition:
                if not self._pipe_closed:
                    self._read_error = f"{type(exc).__name__}: {exc}"
        finally:
            with self._condition:
                trailing = (
                    [self._finish_line_locked(delimiter_bytes=0)]
                    if self._partial or self._partial_overlong
                    else []
                )
            self._publish(trailing)
            self.close_pipe()
            with self._condition:
                self._reader_done = True
                self._condition.notify_all()
            if self._on_eof is not None:
                try:
                    self._on_eof(self.stream)
                except Exception:  # noqa: BLE001
                    logger.exception("BYO %s EOF callback failed", self.stream.value)

    def wait_for_line(self, *, prefix: bytes, timeout: float) -> bytes:
        deadline = time.monotonic() + timeout
        with self._condition:
            while True:
                for line, _stored_bytes in self._lines:
                    if line.startswith(prefix):
                        return line
                if self._reader_done:
                    raise EOFError(f"{self.stream.value} reached EOF before {prefix!r}")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(
                        f"timed out waiting for {prefix!r} on {self.stream.value}"
                    )
                self._condition.wait(remaining)

    def snapshot(self) -> StreamSnapshot:
        with self._condition:
            return StreamSnapshot(
                stream=self.stream,
                lines=tuple(line for line, _stored in self._lines),
                total_bytes=self._total_bytes,
                total_lines=self._total_lines,
                retained_bytes=self._retained_bytes,
                dropped_bytes=self._dropped_bytes,
                dropped_lines=self._dropped_lines,
                overlong_lines=self._overlong_lines,
                maximum_retained_line_bytes=self._maximum_retained_line_bytes,
                reader_done=self._reader_done,
                pipe_closed=self._pipe_closed,
                read_error=self._read_error,
            )


ExitCallback = Callable[["SupervisedProcess", ProcessSnapshot], None]


class _WindowsJob:
    """Kill-on-close Windows Job Object for one BYO process tree."""

    _KILL_ON_JOB_CLOSE = 0x00002000
    _BASIC_ACCOUNTING = 1
    _EXTENDED_LIMIT = 9

    def __init__(self, process: Any) -> None:  # pragma: no cover - Windows CI
        import ctypes
        from ctypes import wintypes

        class BasicLimitInformation(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class IoCounters(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_ulonglong),
                ("WriteOperationCount", ctypes.c_ulonglong),
                ("OtherOperationCount", ctypes.c_ulonglong),
                ("ReadTransferCount", ctypes.c_ulonglong),
                ("WriteTransferCount", ctypes.c_ulonglong),
                ("OtherTransferCount", ctypes.c_ulonglong),
            ]

        class ExtendedLimitInformation(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BasicLimitInformation),
                ("IoInfo", IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        class BasicAccountingInformation(ctypes.Structure):
            _fields_ = [
                ("TotalUserTime", ctypes.c_longlong),
                ("TotalKernelTime", ctypes.c_longlong),
                ("ThisPeriodTotalUserTime", ctypes.c_longlong),
                ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
                ("TotalPageFaultCount", wintypes.DWORD),
                ("TotalProcesses", wintypes.DWORD),
                ("ActiveProcesses", wintypes.DWORD),
                ("TotalTerminatedProcesses", wintypes.DWORD),
            ]

        self._ctypes = ctypes
        self._accounting_type = BasicAccountingInformation
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
        self._kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        self._kernel32.SetInformationJobObject.argtypes = (
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        )
        self._kernel32.SetInformationJobObject.restype = wintypes.BOOL
        self._kernel32.AssignProcessToJobObject.argtypes = (
            wintypes.HANDLE,
            wintypes.HANDLE,
        )
        self._kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        self._kernel32.QueryInformationJobObject.argtypes = (
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.c_void_p,
        )
        self._kernel32.QueryInformationJobObject.restype = wintypes.BOOL
        self._kernel32.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
        self._kernel32.TerminateJobObject.restype = wintypes.BOOL
        self._kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        self._kernel32.CloseHandle.restype = wintypes.BOOL

        handle = self._kernel32.CreateJobObjectW(None, None)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        self._handle = handle
        self._closed = False
        limits = ExtendedLimitInformation()
        limits.BasicLimitInformation.LimitFlags = self._KILL_ON_JOB_CLOSE
        if not self._kernel32.SetInformationJobObject(
            handle,
            self._EXTENDED_LIMIT,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        ):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error
        process_handle = wintypes.HANDLE(int(process._handle))  # noqa: SLF001
        if not self._kernel32.AssignProcessToJobObject(handle, process_handle):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def active_processes(self) -> int:  # pragma: no cover - Windows CI
        if self._closed:
            return 0
        value = self._accounting_type()
        if not self._kernel32.QueryInformationJobObject(
            self._handle,
            self._BASIC_ACCOUNTING,
            self._ctypes.byref(value),
            self._ctypes.sizeof(value),
            None,
        ):
            raise self._ctypes.WinError(self._ctypes.get_last_error())
        return int(value.ActiveProcesses)

    def terminate(self) -> None:  # pragma: no cover - Windows CI
        if not self._closed and not self._kernel32.TerminateJobObject(self._handle, 1):
            raise self._ctypes.WinError(self._ctypes.get_last_error())

    def close(self) -> None:  # pragma: no cover - Windows CI
        if self._closed:
            return
        self._kernel32.CloseHandle(self._handle)
        self._closed = True


class SupervisedProcess:
    """One process, its complete tree, and both continuously-drained pipes."""

    def __init__(
        self,
        *,
        process_id: uuid.UUID,
        process: Any,
        stdout_reader: BoundedStreamReader,
        stderr_reader: BoundedStreamReader,
        limits: ProcessSupervisionLimits,
        isolated_tree: bool,
        windows_job: _WindowsJob | None,
        on_exit: ExitCallback | None,
    ) -> None:
        self.process_id = process_id
        self.raw_process = process
        self._process = process
        self._limits = limits
        self._isolated_tree = isolated_tree
        self._windows_job = windows_job
        self._tree_terminated_after_job_close: bool | None = None
        self._on_exit = on_exit
        self._readers = {
            OutputStream.STDOUT: stdout_reader,
            OutputStream.STDERR: stderr_reader,
        }
        self._reader_threads = {
            stream: threading.Thread(
                target=reader.run,
                name=f"byo-{process_id}-{stream.value}",
                daemon=True,
            )
            for stream, reader in self._readers.items()
        }
        self._cleanup_lock = threading.RLock()
        self._stdin_lock = threading.Lock()
        self._termination_reason: TerminationReason | None = None
        self._cleanup_started: float | None = None
        self._terminal_snapshot: ProcessSnapshot | None = None
        self._terminal_event = threading.Event()
        self._exit_callback_lock = threading.Lock()
        self._exit_callback_sent = False
        for thread in self._reader_threads.values():
            thread.start()
        self._monitor_thread = threading.Thread(
            target=self._monitor_exit,
            name=f"byo-{process_id}-monitor",
            daemon=True,
        )
        self._monitor_thread.start()

    @property
    def pid(self) -> int:
        return int(self._process.pid)

    def poll(self) -> int | None:
        return self._process.poll()

    @property
    def cleanup_complete(self) -> bool:
        """Whether exit cleanup and its callback publication have completed."""

        return self._terminal_event.is_set()

    def _wait_for_parent_exit(self, timeout: float | None = None) -> int:
        wait = getattr(self._process, "wait", None)
        if callable(wait):
            return int(wait(timeout=timeout))
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            result = self._process.poll()
            if result is not None:
                return int(result)
            if deadline is not None and time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(getattr(self._process, "args", []), timeout)
            time.sleep(0.005)

    @staticmethod
    def _remaining(deadline: float) -> float:
        return max(0.0, deadline - time.monotonic())

    def _wait_parent_until(self, deadline: float) -> None:
        if self.poll() is not None:
            return
        try:
            self._wait_for_parent_exit(self._remaining(deadline))
        except subprocess.TimeoutExpired:
            return

    def process_tree_alive(self) -> bool:
        if self._tree_terminated_after_job_close is not None:
            return not self._tree_terminated_after_job_close
        if not self._isolated_tree:
            return self.poll() is None
        if os.name == "posix":
            try:
                os.killpg(self.pid, 0)
            except ProcessLookupError:
                return False
            except PermissionError:
                return True
            return True
        if os.name == "nt" and self._windows_job is not None:
            try:
                return self._windows_job.active_processes() > 0
            except OSError:
                return True
        return self.poll() is None

    def _windows_taskkill(self, *, force: bool, timeout: float) -> None:
        command = ["taskkill"]
        if force:
            command.append("/F")
        command.extend(("/T", "/PID", str(self.pid)))
        try:
            subprocess.run(
                command,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=max(timeout, 0.05),
            )
        except (OSError, subprocess.TimeoutExpired):
            logger.debug("taskkill failed for BYO pid %s", self.pid, exc_info=True)

    def _signal_tree(self, *, force: bool, reason: TerminationReason) -> None:
        if not self._isolated_tree:
            method = getattr(self._process, "kill" if force else "terminate", None)
            if callable(method):
                try:
                    method()
                except (OSError, ValueError):
                    pass
            return
        if os.name == "posix":
            selected = signal.SIGKILL if force else (
                signal.SIGINT if reason is TerminationReason.QUIT else signal.SIGTERM
            )
            try:
                os.killpg(self.pid, selected)
            except ProcessLookupError:
                pass
            return
        if os.name == "nt":  # pragma: no cover - exercised by Windows CI
            if force and self._windows_job is not None:
                try:
                    self._windows_job.terminate()
                except OSError:
                    logger.debug("TerminateJobObject failed for pid %s", self.pid,
                                 exc_info=True)
                return
            if not force and reason is TerminationReason.QUIT:
                try:
                    self._process.send_signal(signal.CTRL_BREAK_EVENT)
                    return
                except (OSError, ValueError):
                    pass
            self._windows_taskkill(
                force=force,
                timeout=self._limits.termination_deadline_seconds / 3,
            )
            return
        method = getattr(self._process, "kill" if force else "terminate", None)
        if callable(method):  # pragma: no cover - unsupported platform fallback
            method()

    def close_stdin(self) -> None:
        with self._stdin_lock:
            stream = getattr(self._process, "stdin", None)
            if stream is None or getattr(stream, "closed", False):
                return
            try:
                stream.close()
            except (OSError, ValueError):
                pass

    def write_line(self, value: str | bytes) -> None:
        if isinstance(value, str):
            text = value.rstrip("\n") + "\n"
            encoded = text.encode("utf-8")
        else:
            encoded = value.rstrip(b"\n") + b"\n"
            text = encoded.decode("utf-8", errors="strict")
        with self._stdin_lock:
            stream = getattr(self._process, "stdin", None)
            if stream is None or getattr(stream, "closed", False):
                raise BrokenPipeError("supervised child stdin is closed")
            if not self._isolated_tree:
                # Existing feature-058 injected process fakes expose text-mode
                # stdin. Production children are always the binary branch.
                stream.write(text)
            else:
                stream.write(encoded)
            stream.flush()

    def _begin_termination(self, reason: TerminationReason) -> None:
        with self._cleanup_lock:
            if self._terminal_snapshot is not None:
                return
            if self._termination_reason is None:
                self._termination_reason = reason
            self._cleanup_started = self._cleanup_started or time.monotonic()
            self.close_stdin()
            self._signal_tree(force=False, reason=self._termination_reason)

    def _wait_for_tree(self, deadline: float) -> None:
        while self.process_tree_alive() and self._remaining(deadline) > 0:
            time.sleep(min(0.01, self._remaining(deadline)))

    def _join_readers(self, deadline: float) -> None:
        for thread in self._reader_threads.values():
            thread.join(self._remaining(deadline))

    def _close_output_pipes(self) -> None:
        for reader in self._readers.values():
            reader.close_pipe()

    def _state(self) -> ProcessState:
        result = self.poll()
        if result is None:
            return ProcessState.STOPPING if self._termination_reason else ProcessState.RUNNING
        if self._termination_reason is TerminationReason.FAILURE:
            return ProcessState.FAILED
        if self._termination_reason is not None:
            return ProcessState.KILLED
        return ProcessState.EXITED if result == 0 else ProcessState.FAILED

    def _complete_cleanup(self, *, deadline: float) -> ProcessSnapshot:
        with self._cleanup_lock:
            if self._terminal_snapshot is not None:
                return self.snapshot()
            self._cleanup_started = self._cleanup_started or time.monotonic()
            reason = self._termination_reason or TerminationReason.FAILURE
            force_deadline = min(
                deadline,
                self._cleanup_started + self._limits.force_kill_after_seconds,
            )
            self._wait_parent_until(force_deadline)
            self._wait_for_tree(force_deadline)
            if self.process_tree_alive():
                self._signal_tree(force=True, reason=reason)
            self._wait_parent_until(deadline)
            self._wait_for_tree(deadline)
            self._join_readers(deadline)
            self._close_output_pipes()
            self._join_readers(deadline)

            stdout = self._readers[OutputStream.STDOUT].snapshot()
            stderr = self._readers[OutputStream.STDERR].snapshot()
            readers_joined = all(
                not thread.is_alive() for thread in self._reader_threads.values()
            )
            pipes_closed = stdout.pipe_closed and stderr.pipe_closed
            tree_terminated = not self.process_tree_alive()
            if self._windows_job is not None:
                # Closing a kill-on-close job is the final kernel-owned safety
                # net. Record whether the complete tree had already settled so
                # cleanup evidence never mistakes an unverified close for proof.
                self._tree_terminated_after_job_close = tree_terminated
                self._windows_job.close()
                self._windows_job = None
            errors: list[str] = []
            if not tree_terminated:
                errors.append("process tree remains alive")
            if not readers_joined:
                errors.append("output readers did not join")
            if not pipes_closed:
                errors.append("output pipes did not close")
            duration = time.monotonic() - self._cleanup_started
            if duration > self._limits.termination_deadline_seconds + 0.05:
                errors.append("cleanup exceeded deadline")
            self._terminal_snapshot = ProcessSnapshot(
                process_id=self.process_id,
                pid=self.pid,
                state=self._state(),
                exit_code=self.poll(),
                termination_reason=self._termination_reason,
                stdout=stdout,
                stderr=stderr,
                readers_joined=readers_joined,
                monitor_joined=False,
                pipes_closed=pipes_closed,
                process_tree_terminated=tree_terminated,
                cleanup_duration_seconds=duration,
                cleanup_error="; ".join(errors) or None,
            )
            self._terminal_event.set()
            return self._terminal_snapshot

    def _publish_exit_once(self) -> None:
        with self._exit_callback_lock:
            if self._exit_callback_sent:
                return
            self._exit_callback_sent = True
        if self._on_exit is not None:
            try:
                self._on_exit(self, self.snapshot())
            except Exception:  # noqa: BLE001 - cleanup is already authoritative
                logger.exception("BYO process-exit callback failed")

    def _monitor_exit(self) -> None:
        self._wait_for_parent_exit()
        deadline = time.monotonic() + self._limits.termination_deadline_seconds
        if self.process_tree_alive() and self._termination_reason is None:
            self._begin_termination(TerminationReason.FAILURE)
        self._complete_cleanup(deadline=deadline)
        self._publish_exit_once()

    def snapshot(self) -> ProcessSnapshot:
        terminal = self._terminal_snapshot
        if terminal is not None:
            joined = not self._monitor_thread.is_alive()
            return replace(terminal, monitor_joined=joined)
        stdout = self._readers[OutputStream.STDOUT].snapshot()
        stderr = self._readers[OutputStream.STDERR].snapshot()
        return ProcessSnapshot(
            process_id=self.process_id,
            pid=self.pid,
            state=self._state(),
            exit_code=self.poll(),
            termination_reason=self._termination_reason,
            stdout=stdout,
            stderr=stderr,
            readers_joined=all(
                not thread.is_alive() for thread in self._reader_threads.values()
            ),
            monitor_joined=not self._monitor_thread.is_alive(),
            pipes_closed=stdout.pipe_closed and stderr.pipe_closed,
            process_tree_terminated=not self.process_tree_alive(),
            cleanup_duration_seconds=(
                0.0
                if self._cleanup_started is None
                else time.monotonic() - self._cleanup_started
            ),
            cleanup_error=None,
        )

    def wait(self, timeout: float | None = None) -> ProcessSnapshot:
        if not self._terminal_event.wait(timeout):
            raise subprocess.TimeoutExpired(getattr(self._process, "args", []), timeout)
        self._monitor_thread.join(self._limits.termination_deadline_seconds)
        return self.snapshot()

    def wait_for_line(
        self, stream: OutputStream, *, prefix: bytes, timeout: float
    ) -> bytes:
        return self._readers[stream].wait_for_line(prefix=prefix, timeout=timeout)

    def terminate(self, *, reason: TerminationReason) -> ProcessSnapshot:
        started = time.monotonic()
        deadline = started + self._limits.termination_deadline_seconds
        self._begin_termination(reason)
        self._complete_cleanup(deadline=deadline)
        self._monitor_thread.join(self._remaining(deadline))
        return self.snapshot()


class ProcessSupervisor:
    """Factory and ownership boundary for every packaged BYO worker tree."""

    def __init__(
        self,
        *,
        limits: ProcessSupervisionLimits = DEFAULT_PROCESS_SUPERVISION_LIMITS,
    ) -> None:
        self.limits = limits
        self._lock = threading.RLock()
        self._processes: dict[uuid.UUID, SupervisedProcess] = {}

    def spawn(
        self,
        *,
        process_id: uuid.UUID,
        argv: Sequence[str | os.PathLike[str]],
        cwd: str | os.PathLike[str] | None = None,
        env: Mapping[str, str] | None = None,
        process_factory: Callable[[list[str]], Any] | None = None,
        on_stdout_line: LineCallback | None = None,
        on_stderr_line: LineCallback | None = None,
        on_diagnostic: DiagnosticCallback | None = None,
        on_stream_eof: EofCallback | None = None,
        on_exit: ExitCallback | None = None,
        **popen_kwargs: Any,
    ) -> SupervisedProcess:
        if not isinstance(process_id, uuid.UUID) or process_id.version != 4:
            raise TypeError("process_id must be a UUID4")
        command = [os.fspath(value) for value in argv]
        if not command or any(not value for value in command):
            raise ValueError("argv must contain non-empty arguments")
        with self._lock:
            if process_id in self._processes:
                raise ValueError(f"duplicate supervised process id {process_id}")

        if process_factory is not None:
            if popen_kwargs:
                raise ValueError("injected process factories do not accept Popen options")
            process = process_factory(command)
            isolated_tree = False
            windows_job = None
        else:
            forbidden = {
                "args",
                "shell",
                "stdout",
                "stderr",
                "stdin",
                "text",
                "encoding",
                "errors",
                "universal_newlines",
                "start_new_session",
            }
            overlap = forbidden & set(popen_kwargs)
            if overlap:
                raise ValueError(f"supervisor owns Popen options: {sorted(overlap)}")
            platform_kwargs: dict[str, Any] = {}
            if os.name == "posix":
                platform_kwargs["start_new_session"] = True
            elif os.name == "nt":  # pragma: no cover - Windows CI
                creationflags = int(popen_kwargs.pop("creationflags", 0))
                platform_kwargs["creationflags"] = (
                    creationflags
                    | subprocess.CREATE_NEW_PROCESS_GROUP
                    | getattr(subprocess, "CREATE_NO_WINDOW", 0)
                )
            process = subprocess.Popen(
                command,
                cwd=Path(cwd) if cwd is not None else None,
                env=dict(env) if env is not None else None,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
                **platform_kwargs,
                **popen_kwargs,
            )
            isolated_tree = True
            windows_job = None
            if os.name == "nt":  # pragma: no cover - Windows CI
                try:
                    windows_job = _WindowsJob(process)
                except Exception:
                    process.kill()
                    process.wait(timeout=2)
                    raise RuntimeError(
                        "could not bind BYO worker to a Windows Job Object"
                    ) from None
        if (
            getattr(process, "stdout", None) is None
            or getattr(process, "stderr", None) is None
            or getattr(process, "stdin", None) is None
        ):
            try:
                process.kill()
            except (AttributeError, OSError):
                pass
            raise RuntimeError("supervised child pipes were not created")

        def release_process(
            completed: SupervisedProcess, snapshot: ProcessSnapshot
        ) -> None:
            # A host can revise/restart agents for days. Retaining every terminal
            # 512-KiB diagnostic ring in the supervisor would turn honest crash
            # handling into an unbounded process-lifetime memory leak.
            with self._lock:
                if self._processes.get(process_id) is completed:
                    self._processes.pop(process_id, None)
            if on_exit is not None:
                on_exit(completed, snapshot)

        supervised = SupervisedProcess(
            process_id=process_id,
            process=process,
            stdout_reader=BoundedStreamReader(
                stream=OutputStream.STDOUT,
                pipe=process.stdout,
                limits=self.limits,
                on_line=on_stdout_line,
                on_diagnostic=on_diagnostic,
                on_eof=on_stream_eof,
            ),
            stderr_reader=BoundedStreamReader(
                stream=OutputStream.STDERR,
                pipe=process.stderr,
                limits=self.limits,
                on_line=on_stderr_line,
                on_diagnostic=on_diagnostic,
                on_eof=on_stream_eof,
            ),
            limits=self.limits,
            isolated_tree=isolated_tree,
            windows_job=windows_job,
            on_exit=release_process,
        )
        with self._lock:
            self._processes[process_id] = supervised
            # A very short-lived child may finish before construction returns
            # and before the callback can observe its registry entry.
            if supervised.cleanup_complete:
                self._processes.pop(process_id, None)
        return supervised

    def terminate(
        self, process_id: uuid.UUID, *, reason: TerminationReason
    ) -> ProcessSnapshot:
        with self._lock:
            process = self._processes[process_id]
        return process.terminate(reason=reason)

    def terminate_all(
        self, *, reason: TerminationReason = TerminationReason.QUIT
    ) -> tuple[ProcessSnapshot, ...]:
        with self._lock:
            processes = tuple(self._processes.values())
        return tuple(process.terminate(reason=reason) for process in processes)

    def snapshots(self) -> tuple[ProcessSnapshot, ...]:
        with self._lock:
            processes = sorted(
                self._processes.values(), key=lambda item: str(item.process_id)
            )
        return tuple(process.snapshot() for process in processes)
