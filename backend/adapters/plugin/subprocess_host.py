from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from backend.adapters.plugin.process_teardown import assign_windows_job, kill_process_tree
from backend.domain.plugin.ipc import (
    MESSAGE_CAPABILITY_REQUEST,
    MESSAGE_CAPABILITY_RESPONSE,
    MESSAGE_SHUTDOWN,
    capability_response_message,
    host_ready_message,
)


@dataclass(slots=True)
class SubprocessPluginSession:
  process: subprocess.Popen[str]
  job_handle: int | None = None
  stdout_thread: threading.Thread | None = None
  request_queue: list[dict[str, Any]] = field(default_factory=list)
  queue_lock: threading.Lock = field(default_factory=threading.Lock)
  shutdown: bool = False


class SubprocessPluginHost:
    """Isolated plugin subprocess with newline-delimited JSON IPC on stdin/stdout."""

    def __init__(
        self,
        *,
        bootstrap_script: Path,
        plugin_script: Path,
        plugin_id: str,
        granted_capabilities: list[str],
        mode: str = "normal",
        startup_timeout_seconds: float = 5.0,
        call_timeout_seconds: float = 10.0,
    ) -> None:
        self._bootstrap_script = bootstrap_script
        self._plugin_script = plugin_script
        self._plugin_id = plugin_id
        self._granted_capabilities = granted_capabilities
        self._mode = mode
        self._startup_timeout_seconds = startup_timeout_seconds
        self._call_timeout_seconds = call_timeout_seconds
        self._session: SubprocessPluginSession | None = None

    @property
    def pid(self) -> int | None:
        if self._session is None:
            return None
        return self._session.process.pid

    def start(self) -> int:
        kwargs: dict[str, object] = {
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "bufsize": 1,
        }
        if os.name != "nt":
            kwargs["start_new_session"] = True
        process = subprocess.Popen(
            [sys.executable, str(self._bootstrap_script), str(self._plugin_script), self._mode],
            **kwargs,
        )
        job_handle = assign_windows_job(process.pid) if os.name == "nt" else None
        session = SubprocessPluginSession(process=process, job_handle=job_handle)
        session.stdout_thread = threading.Thread(target=self._read_stdout, args=(session,), daemon=True)
        session.stdout_thread.start()
        self._session = session
        self._write(
            host_ready_message(
                plugin_id=self._plugin_id,
                granted_capabilities=self._granted_capabilities,
                mode=self._mode,
                plugin_script=str(self._plugin_script),
            )
        )
        return process.pid

    def run_until_shutdown(self, handler: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
        if self._session is None:
            raise RuntimeError("Plugin subprocess not started")
        responses: list[dict[str, Any]] = []
        while True:
            if self._session.process.poll() is not None and not self._pending_requests():
                break
            message = self._wait_for_request(timeout_seconds=self._call_timeout_seconds)
            if message is None:
                if self._session.process.poll() is not None:
                    break
                continue
            if message.get("type") == MESSAGE_SHUTDOWN:
                break
            if message.get("type") != MESSAGE_CAPABILITY_REQUEST:
                continue
            response = handler(message)
            responses.append(response)
            self._write(response)
        return {"responses": responses, "exit_code": self._session.process.poll()}

    def stop(self, *, timeout_seconds: float = 3.0) -> int | None:
        if self._session is None:
            return None
        session = self._session
        pid = session.process.pid
        if session.process.poll() is None:
            try:
                session.process.terminate()
                session.process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                pass
        if session.process.poll() is None and pid:
            kill_process_tree(pid, job_handle=session.job_handle)
            try:
                session.process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                if pid:
                    kill_process_tree(pid, job_handle=None)
        session.shutdown = True
        if session.stdout_thread is not None:
            session.stdout_thread.join(timeout=timeout_seconds)
        self._session = None
        return session.process.poll()

    def is_running(self) -> bool:
        return self._session is not None and self._session.process.poll() is None

    def _write(self, payload: dict[str, Any]) -> None:
        if self._session is None or self._session.process.stdin is None:
            raise RuntimeError("Plugin stdin unavailable")
        self._session.process.stdin.write(json.dumps(payload) + "\n")
        self._session.process.stdin.flush()

    def _read_stdout(self, session: SubprocessPluginSession) -> None:
        stream = session.process.stdout
        if stream is None:
            return
        for line in stream:
            if session.shutdown:
                break
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            with session.queue_lock:
                session.request_queue.append(message)

    def _pending_requests(self) -> bool:
        if self._session is None:
            return False
        with self._session.queue_lock:
            return bool(self._session.request_queue)

    def _wait_for_request(self, *, timeout_seconds: float) -> dict[str, Any] | None:
        if self._session is None:
            return None
        deadline = timeout_seconds
        import time

        start = time.monotonic()
        while time.monotonic() - start < deadline:
            with self._session.queue_lock:
                if self._session.request_queue:
                    return self._session.request_queue.pop(0)
            if self._session.process.poll() is not None:
                with self._session.queue_lock:
                    if self._session.request_queue:
                        return self._session.request_queue.pop(0)
                return None
            time.sleep(0.02)
        return None


def default_bootstrap_path() -> Path:
    return Path(__file__).resolve().parents[3] / "plugin-sdk" / "ipc" / "bootstrap.py"
