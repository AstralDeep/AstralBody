"""Neutral-vector conformance for the frozen-safe Windows BYO supervisor."""

from __future__ import annotations

import ast
import dataclasses
import io
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

from win_agent.process_supervision import (
    DEFAULT_PROCESS_SUPERVISION_LIMITS,
    BoundedStreamReader,
    OutputStream,
    ProcessState,
    ProcessSupervisionLimits,
    ProcessSupervisor,
    TerminationReason,
)


_ROOT = Path(__file__).resolve().parents[2]
_VECTOR_PATH = (
    _ROOT
    / "backend"
    / "tests"
    / "fixtures"
    / "runtime_reliability_060"
    / "process-supervision-vectors.json"
)
_CORPUS = json.loads(_VECTOR_PATH.read_text(encoding="utf-8"))
_VECTORS = {item["id"]: item for item in _CORPUS["vectors"]}
_EXPECTED_IDS = {
    "dual-stream-high-output",
    "oversized-logical-line",
    "one-pipe-eof-other-continues",
    "descendant-tree-stop",
    "descendant-tree-quit",
    "crash-after-output",
    "silent-tree-cancellation",
}


class _RecordingPipe(io.BytesIO):
    def __init__(self, value: bytes) -> None:
        super().__init__(value)
        self.requested_sizes: list[int] = []
        self.close_called = False

    def read(self, size: int = -1) -> bytes:
        self.requested_sizes.append(size)
        return super().read(size)

    def close(self) -> None:
        self.close_called = True
        super().close()


def _spawn(supervisor: ProcessSupervisor, script: str):
    return supervisor.spawn(
        process_id=uuid.uuid4(),
        argv=(sys.executable, "-u", "-c", script),
    )


def _emit_script(stdout_count, stdout_size, stderr_count, stderr_size, exit_code=0):
    return (
        "import os\n"
        f"out = b'O' * {stdout_size} + b'\\n'\n"
        f"err = b'E' * {stderr_size} + b'\\n'\n"
        f"for _ in range({stdout_count}): os.write(1, out)\n"
        f"for _ in range({stderr_count}): os.write(2, err)\n"
        f"raise SystemExit({exit_code})\n"
    )


def _tree_script(period: float = 0.005) -> str:
    descendant = "import time\nwhile True: time.sleep(0.05)\n"
    return (
        "import os,subprocess,sys,time\n"
        f"child = subprocess.Popen([sys.executable, '-u', '-c', {descendant!r}])\n"
        "os.write(1, f'READY {child.pid}\\n'.encode())\n"
        f"while True: time.sleep({period!r})\n"
    )


def _assert_cleanup(snapshot) -> None:
    assert snapshot.readers_joined is True
    assert snapshot.monitor_joined is True
    assert snapshot.pipes_closed is True
    assert snapshot.process_tree_terminated is True
    assert snapshot.cleanup_duration_seconds <= 5.0
    assert snapshot.cleanup_error is None


def test_neutral_fixture_and_local_defaults_are_one_frozen_contract() -> None:
    assert _CORPUS["schema_version"] == 1
    assert _CORPUS["contract"] == "astraldeep-process-supervision-060"
    assert set(_VECTORS) == _EXPECTED_IDS
    fixture = _CORPUS["limits"]
    limits = DEFAULT_PROCESS_SUPERVISION_LIMITS
    assert limits.read_chunk_bytes == fixture["read_chunk_bytes"]
    assert limits.maximum_logical_line_bytes == fixture["maximum_logical_line_bytes"]
    assert limits.ring_capacity_bytes_per_stream == fixture["ring_capacity_bytes_per_stream"]
    assert limits.ring_capacity_bytes_per_process == fixture["ring_capacity_bytes_per_process"]
    assert limits.termination_deadline_seconds == fixture["termination_deadline_ms"] / 1000
    with pytest.raises(dataclasses.FrozenInstanceError):
        limits.read_chunk_bytes = 1  # type: ignore[misc]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"read_chunk_bytes": 0},
        {"force_kill_after_seconds": 5.0},
        {"ring_capacity_bytes_per_stream": 2, "ring_capacity_bytes_per_process": 3},
    ],
)
def test_invalid_supervision_limits_fail_closed(kwargs) -> None:
    with pytest.raises(ValueError):
        ProcessSupervisionLimits(**kwargs)


def test_reader_uses_fixed_binary_reads_bounds_lines_and_closes_pipe() -> None:
    limits = DEFAULT_PROCESS_SUPERVISION_LIMITS
    pipe = _RecordingPipe(b"A" * (limits.maximum_logical_line_bytes * 2) + b"\nend\n")
    diagnostics: list[tuple[str, str]] = []
    reader = BoundedStreamReader(
        stream=OutputStream.STDOUT,
        pipe=pipe,
        on_diagnostic=lambda code, stream: diagnostics.append((code, stream.value)),
    )

    reader.run()
    snapshot = reader.snapshot()

    assert set(pipe.requested_sizes) == {limits.read_chunk_bytes}
    assert snapshot.overlong_lines == 1
    assert snapshot.maximum_retained_line_bytes <= limits.maximum_logical_line_bytes
    assert diagnostics == [("output_line_too_long", "stdout")]
    assert snapshot.reader_done and snapshot.pipe_closed and pipe.close_called


def test_reader_error_timeout_eof_and_tiny_ring_paths_are_bounded() -> None:
    class BrokenPipe(_RecordingPipe):
        def read(self, size: int = -1) -> bytes:
            raise OSError("fixture read failure")

    broken = BoundedStreamReader(stream=OutputStream.STDERR, pipe=BrokenPipe(b""))
    broken.run()
    assert "fixture read failure" in (broken.snapshot().read_error or "")
    with pytest.raises(EOFError):
        broken.wait_for_line(prefix=b"never", timeout=0.01)

    pending = BoundedStreamReader(
        stream=OutputStream.STDOUT,
        pipe=_RecordingPipe(b""),
    )
    with pytest.raises(TimeoutError):
        pending.wait_for_line(prefix=b"never", timeout=0.001)
    pending.close_pipe()
    pending.close_pipe()

    tiny = BoundedStreamReader(
        stream=OutputStream.STDOUT,
        pipe=_RecordingPipe(b"abcdef\n"),
        limits=ProcessSupervisionLimits(
            read_chunk_bytes=4,
            maximum_logical_line_bytes=8,
            ring_capacity_bytes_per_stream=4,
            ring_capacity_bytes_per_process=8,
            force_kill_after_seconds=0.5,
            termination_deadline_seconds=1,
        ),
    )
    tiny.run()
    assert tiny.snapshot().dropped_lines == 1


def test_supervisor_rejects_invalid_or_duplicate_spawn_ownership() -> None:
    supervisor = ProcessSupervisor()
    with pytest.raises(TypeError):
        supervisor.spawn(process_id="not-a-uuid", argv=(sys.executable,))  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        supervisor.spawn(process_id=uuid.uuid4(), argv=())
    with pytest.raises(ValueError):
        supervisor.spawn(
            process_id=uuid.uuid4(),
            argv=(sys.executable, "-c", "pass"),
            stdout=subprocess.PIPE,
        )

    process_id = uuid.uuid4()
    process = supervisor.spawn(
        process_id=process_id,
        argv=(sys.executable, "-u", "-c", "import time; time.sleep(10)"),
    )
    with pytest.raises(ValueError):
        supervisor.spawn(
            process_id=process_id,
            argv=(sys.executable, "-c", "pass"),
        )
    with pytest.raises(subprocess.TimeoutExpired):
        process.wait(timeout=0.001)
    _assert_cleanup(supervisor.terminate(process_id, reason=TerminationReason.CANCEL))


def test_supervisor_snapshots_and_terminate_all_cover_every_owned_child() -> None:
    supervisor = ProcessSupervisor()
    for _index in range(2):
        supervisor.spawn(
            process_id=uuid.uuid4(),
            argv=(sys.executable, "-u", "-c", "import time; time.sleep(10)"),
        )
    running = supervisor.snapshots()
    assert len(running) == 2
    assert all(snapshot.state is ProcessState.RUNNING for snapshot in running)
    settled = supervisor.terminate_all(reason=TerminationReason.QUIT)
    assert len(settled) == 2
    assert all(snapshot.state is ProcessState.KILLED for snapshot in settled)
    for snapshot in settled:
        _assert_cleanup(snapshot)


def test_terminal_processes_release_bounded_rings_from_long_lived_registry() -> None:
    supervisor = ProcessSupervisor()
    for _trial in range(100):
        process = _spawn(supervisor, "raise SystemExit(0)\n")
        _assert_cleanup(process.wait(timeout=5))
        assert supervisor.snapshots() == ()
    assert supervisor.terminate_all(reason=TerminationReason.QUIT) == ()


def test_full_neutral_output_vectors_are_drained_and_bounded() -> None:
    high = _VECTORS["dual-stream-high-output"]["behavior"]
    supervisor = ProcessSupervisor()
    process = _spawn(
        supervisor,
        _emit_script(
            high["stdout"]["line_count"],
            high["stdout"]["line_bytes"],
            high["stderr"]["line_count"],
            high["stderr"]["line_bytes"],
        ),
    )
    high_snapshot = process.wait(timeout=10)
    assert high_snapshot.stdout.total_lines == high["stdout"]["line_count"]
    assert high_snapshot.stderr.total_lines == high["stderr"]["line_count"]
    assert high_snapshot.stdout.dropped_bytes > 0
    assert high_snapshot.stderr.dropped_bytes > 0
    _assert_cleanup(high_snapshot)

    oversized = _VECTORS["oversized-logical-line"]["behavior"]
    process = _spawn(
        ProcessSupervisor(),
        _emit_script(
            oversized["stdout"]["line_count"],
            oversized["stdout"]["line_bytes"],
            0,
            0,
        ),
    )
    oversized_snapshot = process.wait(timeout=10)
    assert oversized_snapshot.stdout.overlong_lines >= 1
    assert oversized_snapshot.stdout.maximum_retained_line_bytes <= 65536
    _assert_cleanup(oversized_snapshot)


def test_one_pipe_eof_does_not_stop_the_other_reader() -> None:
    vector = _VECTORS["one-pipe-eof-other-continues"]["behavior"]
    script = (
        "import os,time\n"
        "os.close(1)\n"
        f"time.sleep({vector['delay_after_close_ms'] / 1000!r})\n"
        f"line = b'E' * {vector['continuing_line_bytes']} + b'\\n'\n"
        f"for _ in range({vector['continuing_line_count']}): os.write(2, line)\n"
    )
    snapshot = _spawn(ProcessSupervisor(), script).wait(timeout=10)
    assert snapshot.stdout.reader_done is True
    assert snapshot.stderr.total_lines == vector["continuing_line_count"]
    _assert_cleanup(snapshot)


def test_crash_exit_is_failed_only_after_complete_cleanup() -> None:
    vector = _VECTORS["crash-after-output"]["behavior"]
    snapshot = _spawn(
        ProcessSupervisor(),
        _emit_script(
            vector["stdout"]["line_count"],
            vector["stdout"]["line_bytes"],
            vector["stderr"]["line_count"],
            vector["stderr"]["line_bytes"],
            vector["exit_code"],
        ),
    ).wait(timeout=10)
    assert snapshot.exit_code == 23
    assert snapshot.state is ProcessState.FAILED
    _assert_cleanup(snapshot)


def test_stop_quit_and_cancel_terminate_the_complete_descendant_tree() -> None:
    for reason in (TerminationReason.STOP, TerminationReason.QUIT, TerminationReason.CANCEL):
        process = _spawn(ProcessSupervisor(), _tree_script())
        process.wait_for_line(OutputStream.STDOUT, prefix=b"READY ", timeout=3)
        started = time.monotonic()
        snapshot = process.terminate(reason=reason)
        assert time.monotonic() - started <= 5.0
        _assert_cleanup(snapshot)


def test_noncooperative_tree_is_force_killed_by_four_and_clean_by_five_seconds() -> None:
    descendant = (
        "import signal,time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "signal.signal(signal.SIGINT, signal.SIG_IGN)\n"
        "while True: time.sleep(.05)\n"
    )
    script = (
        "import os,signal,subprocess,sys,time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "signal.signal(signal.SIGINT, signal.SIG_IGN)\n"
        f"child=subprocess.Popen([sys.executable,'-u','-c',{descendant!r}])\n"
        "os.write(1, f'READY {child.pid}\\n'.encode())\n"
        "while True: time.sleep(.05)\n"
    )
    process = _spawn(ProcessSupervisor(), script)
    process.wait_for_line(OutputStream.STDOUT, prefix=b"READY ", timeout=3)
    started = time.monotonic()
    snapshot = process.terminate(reason=TerminationReason.CANCEL)
    elapsed = time.monotonic() - started

    if sys.platform != "win32":
        assert 3.8 <= elapsed
    assert elapsed <= 5.0
    _assert_cleanup(snapshot)


def test_hundred_trials_per_behavior_leave_no_worker_resources() -> None:
    """One hundred independent launches for each neutral fault behavior."""

    observed = {vector_id: 0 for vector_id in _EXPECTED_IDS}
    cleanup_ms = {vector_id: [] for vector_id in _EXPECTED_IDS}
    ordered = sorted(_EXPECTED_IDS)
    for vector_id in ordered:
        for _trial in range(100):
            observed[vector_id] += 1
            supervisor = ProcessSupervisor()
            if vector_id in {
                "descendant-tree-stop",
                "descendant-tree-quit",
                "silent-tree-cancellation",
            }:
                process = _spawn(supervisor, _tree_script(0.001))
                process.wait_for_line(OutputStream.STDOUT, prefix=b"READY ", timeout=3)
                reason = {
                    "descendant-tree-stop": TerminationReason.STOP,
                    "descendant-tree-quit": TerminationReason.QUIT,
                    "silent-tree-cancellation": TerminationReason.CANCEL,
                }[vector_id]
                snapshot = process.terminate(reason=reason)
            elif vector_id == "oversized-logical-line":
                snapshot = _spawn(
                    supervisor,
                    _emit_script(1, 131072, 0, 0),
                ).wait(timeout=5)
                assert snapshot.stdout.overlong_lines == 1
            elif vector_id == "dual-stream-high-output":
                behavior = _VECTORS[vector_id]["behavior"]
                snapshot = _spawn(
                    supervisor,
                    _emit_script(
                        behavior["stdout"]["line_count"],
                        behavior["stdout"]["line_bytes"],
                        behavior["stderr"]["line_count"],
                        behavior["stderr"]["line_bytes"],
                    ),
                ).wait(timeout=5)
                assert snapshot.stdout.total_lines == snapshot.stderr.total_lines == 4096
                assert snapshot.stdout.dropped_bytes > 0
                assert snapshot.stderr.dropped_bytes > 0
            elif vector_id == "crash-after-output":
                snapshot = _spawn(
                    supervisor,
                    _emit_script(8, 64, 8, 64, 23),
                ).wait(timeout=5)
                assert snapshot.exit_code == 23
            else:
                behavior = _VECTORS[vector_id]["behavior"]
                snapshot = _spawn(
                    supervisor,
                    "import os,time\n"
                    "os.close(1)\n"
                    f"time.sleep({behavior['delay_after_close_ms'] / 1000!r})\n"
                    f"line = b'E' * {behavior['continuing_line_bytes']} + b'\\n'\n"
                    f"for _ in range({behavior['continuing_line_count']}): os.write(2,line)\n",
                ).wait(timeout=5)
                assert snapshot.stderr.total_lines == behavior["continuing_line_count"]
            _assert_cleanup(snapshot)
            cleanup_ms[vector_id].append(
                round(snapshot.cleanup_duration_seconds * 1000, 3)
            )

    assert observed == {vector_id: 100 for vector_id in _EXPECTED_IDS}
    distribution = {}
    for vector_id, samples in cleanup_ms.items():
        ordered_samples = sorted(samples)
        distribution[vector_id] = {
            "count": len(samples),
            "p50_ms": ordered_samples[49],
            "p95_ms": ordered_samples[94],
            "max_ms": ordered_samples[-1],
        }
    print(
        "US2_SUPERVISION_DISTRIBUTION="
        + json.dumps(distribution, sort_keys=True, separators=(",", ":"))
    )


def test_host_is_the_only_supervisor_and_worker_remains_a_child_entry() -> None:
    host_path = _ROOT / "windows-client" / "win_agent" / "byo_host.py"
    worker_path = _ROOT / "windows-client" / "win_agent" / "byo_worker.py"
    supervisor_path = _ROOT / "windows-client" / "win_agent" / "process_supervision.py"
    host_source = host_path.read_text(encoding="utf-8")
    worker_source = worker_path.read_text(encoding="utf-8")
    supervisor_source = supervisor_path.read_text(encoding="utf-8")

    assert "from win_agent.process_supervision import" in host_source
    assert "subprocess.Popen" not in host_source
    assert "process_supervision" not in worker_source
    assert "backend." not in supervisor_source
    assert "shared.process_supervision" not in supervisor_source

    host_tree = ast.parse(host_source)
    worker_tree = ast.parse(worker_source)
    assert any(
        isinstance(node, ast.Attribute) and node.attr == "spawn"
        for node in ast.walk(host_tree)
    )
    assert not any(
        isinstance(node, (ast.Import, ast.ImportFrom))
        and "process_supervision" in ast.unparse(node)
        for node in ast.walk(worker_tree)
    )
