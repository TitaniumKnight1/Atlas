from __future__ import annotations

import ctypes
import os
import subprocess
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from backend.domain.setup import ProcessLaunchPlan, ServerProcessState, ServerProcessStatus


OutputCallback = Callable[[str, int | None, bool, list[str], list[str]], None]
LineCallback = Callable[[str, str, str, str], None]


@dataclass(slots=True)
class _ManagedProcess:
    process_run_id: str
    project_id: str
    process: subprocess.Popen[str]
    started_at: str
    stdout_tail: deque[str] = field(default_factory=lambda: deque(maxlen=200))
    stderr_tail: deque[str] = field(default_factory=lambda: deque(maxlen=200))
    stop_requested: bool = False
    job_handle: int | None = None
    process_group_id: int | None = None


class LocalProcessSupervisor:
    """Supervises external server processes with full-tree cleanup discipline."""

    def __init__(self, on_exit: OutputCallback | None = None, on_line: LineCallback | None = None) -> None:
        self._on_exit = on_exit
        self._on_line = on_line
        self._lock = threading.RLock()
        self._processes: dict[str, _ManagedProcess] = {}

    def set_on_exit(self, on_exit: OutputCallback) -> None:
        self._on_exit = on_exit

    def set_on_line(self, on_line: LineCallback) -> None:
        self._on_line = on_line

    def start(self, process_run_id: str, project_id: str, plan: ProcessLaunchPlan) -> ServerProcessStatus:
        kwargs: dict[str, object] = {
            "cwd": str(plan.working_directory),
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "stdin": subprocess.DEVNULL,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
        }
        if os.name != "nt":
            kwargs["start_new_session"] = True
        process = subprocess.Popen([str(plan.executable_path), *plan.arguments], **kwargs)
        managed = _ManagedProcess(process_run_id, project_id, process, datetime.now(UTC).isoformat())
        if os.name == "nt":
            managed.job_handle = _assign_windows_job(process.pid)
        else:
            managed.process_group_id = os.getpgid(process.pid)
        with self._lock:
            self._processes[process_run_id] = managed
        threading.Thread(target=self._read_stream, args=(managed, "stdout"), daemon=True).start()
        threading.Thread(target=self._read_stream, args=(managed, "stderr"), daemon=True).start()
        threading.Thread(target=self._watch_exit, args=(managed,), daemon=True).start()
        return self.status(process_run_id) or _status(managed, ServerProcessState.RUNNING)

    def stop(self, process_run_id: str, timeout_seconds: float = 5.0) -> ServerProcessStatus:
        with self._lock:
            managed = self._processes.get(process_run_id)
            if managed is None:
                raise KeyError(process_run_id)
            managed.stop_requested = True
        if managed.process.poll() is None:
            managed.process.terminate()
            try:
                managed.process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                pass
        self._kill_tree(managed)
        if managed.process.poll() is None:
            managed.process.wait(timeout=timeout_seconds)
        return self.status(process_run_id) or _status(managed, ServerProcessState.STOPPED)

    def status(self, process_run_id: str) -> ServerProcessStatus | None:
        with self._lock:
            managed = self._processes.get(process_run_id)
            if managed is None:
                return None
            code = managed.process.poll()
            if code is None:
                state = ServerProcessState.RUNNING
                stopped_at = None
            elif managed.stop_requested:
                state = ServerProcessState.STOPPED
                stopped_at = datetime.now(UTC).isoformat()
            else:
                state = ServerProcessState.CRASHED
                stopped_at = datetime.now(UTC).isoformat()
            return ServerProcessStatus(
                process_run_id=managed.process_run_id,
                project_id=managed.project_id,
                state=state,
                pid=managed.process.pid,
                started_at=managed.started_at,
                stopped_at=stopped_at,
                exit_code=code,
                stdout_tail=list(managed.stdout_tail),
                stderr_tail=list(managed.stderr_tail),
            )

    def _read_stream(self, managed: _ManagedProcess, stream_name: str) -> None:
        stream = managed.process.stdout if stream_name == "stdout" else managed.process.stderr
        if stream is None:
            return
        for line in stream:
            stripped = line.rstrip()
            with self._lock:
                target = managed.stdout_tail if stream_name == "stdout" else managed.stderr_tail
                target.append(stripped)
            if self._on_line:
                self._on_line(managed.process_run_id, managed.project_id, stream_name, stripped)

    def _watch_exit(self, managed: _ManagedProcess) -> None:
        code = managed.process.wait()
        if managed.job_handle is not None:
            _close_handle(managed.job_handle)
            managed.job_handle = None
        if self._on_exit:
            self._on_exit(
                managed.process_run_id,
                code,
                managed.stop_requested,
                list(managed.stdout_tail),
                list(managed.stderr_tail),
            )

    def _kill_tree(self, managed: _ManagedProcess) -> None:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(managed.process.pid), "/T", "/F"], capture_output=True, text=True)
            if managed.job_handle is not None:
                _close_handle(managed.job_handle)
                managed.job_handle = None
            return
        try:
            os.killpg(managed.process_group_id or os.getpgid(managed.process.pid), 15)
        except ProcessLookupError:
            return
        try:
            managed.process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            os.killpg(managed.process_group_id or os.getpgid(managed.process.pid), 9)


def _status(managed: _ManagedProcess, state: ServerProcessState) -> ServerProcessStatus:
    return ServerProcessStatus(
        process_run_id=managed.process_run_id,
        project_id=managed.project_id,
        state=state,
        pid=managed.process.pid,
        started_at=managed.started_at,
        stopped_at=None,
        exit_code=managed.process.poll(),
        stdout_tail=list(managed.stdout_tail),
        stderr_tail=list(managed.stderr_tail),
    )


def _assign_windows_job(pid: int) -> int | None:
    if os.name != "nt":
        return None
    kernel32 = _kernel32()
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return None
    info = _JobObjectExtendedLimitInformation()
    info.BasicLimitInformation.LimitFlags = 0x0000_2000
    ok = kernel32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))
    if not ok:
        _close_handle(job)
        return None
    process = kernel32.OpenProcess(0x0100 | 0x0001, False, pid)
    if not process:
        _close_handle(job)
        return None
    assigned = kernel32.AssignProcessToJobObject(job, process)
    kernel32.CloseHandle(process)
    if not assigned:
        _close_handle(job)
        return None
    return int(job)


def _close_handle(handle: int) -> None:
    if os.name == "nt" and handle:
        _kernel32().CloseHandle(ctypes.c_void_p(handle))


def _kernel32() -> ctypes.WinDLL:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
    kernel32.CreateJobObjectW.restype = ctypes.c_void_p
    kernel32.SetInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32]
    kernel32.SetInformationJobObject.restype = ctypes.c_int
    kernel32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    kernel32.AssignProcessToJobObject.restype = ctypes.c_int
    kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int
    return kernel32


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class _JobObjectBasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class _JobObjectExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JobObjectBasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]
