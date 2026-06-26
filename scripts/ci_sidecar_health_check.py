from __future__ import annotations

import json
import importlib.util
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib import error, request

ROOT = Path(__file__).resolve().parents[1]

READY_EVENT = "atlas.backend.ready"
STARTUP_TIMEOUT_SECONDS = 20
SHUTDOWN_TIMEOUT_SECONDS = 10


def _load_build_module():
    module_path = ROOT / "scripts" / "build_backend_sidecar.py"
    spec = importlib.util.spec_from_file_location("build_backend_sidecar", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load build_backend_sidecar module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    binary_path = _load_build_module().sidecar_binary_path()
    if not binary_path.is_file():
        raise SystemExit(f"Packaged sidecar binary not found: {binary_path}")

    with tempfile.TemporaryDirectory(prefix="atlas-ci-sidecar-") as temp_dir:
        app_data_dir = Path(temp_dir)
        process = subprocess.Popen(
            [
                str(binary_path),
                "--app-data-dir",
                str(app_data_dir),
                "--host",
                "127.0.0.1",
                "--port",
                "0",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        try:
            ready = _wait_for_ready(process)
            base_url = f"http://{ready['host']}:{ready['port']}"
            health = _request_json(f"{base_url}/api/v1/health")
            if health.get("ok") is not True:
                raise AssertionError(f"Health endpoint returned unexpected payload: {health}")

            data = health.get("data") or {}
            if data.get("status") != "ok":
                raise AssertionError(f"Health status was not ok: {data}")
            if data.get("transport") != "loopback-http":
                raise AssertionError(f"Unexpected transport: {data.get('transport')}")

            port = int(ready["port"])
            _shutdown_process(process)
            _assert_port_released("127.0.0.1", port)
            print(f"CI sidecar health round-trip succeeded via {base_url}")
        finally:
            if process.poll() is None:
                _force_kill_process(process)


def _wait_for_ready(process: subprocess.Popen[str]) -> dict:
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    assert process.stdout is not None

    while time.monotonic() < deadline:
        if process.poll() is not None:
            stderr = process.stderr.read() if process.stderr is not None else ""
            raise AssertionError(
                f"Sidecar exited before readiness (code={process.returncode}): {stderr}"
            )

        line = process.stdout.readline()
        if not line:
            time.sleep(0.05)
            continue

        try:
            payload = json.loads(line.strip())
        except json.JSONDecodeError:
            continue

        if payload.get("event") == READY_EVENT:
            return payload

    raise AssertionError("Timed out waiting for sidecar readiness handshake")


def _request_json(url: str) -> dict:
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            req = request.Request(url, headers={"Accept": "application/json"})
            with request.urlopen(req, timeout=2) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.URLError as exc:
            last_error = exc
            time.sleep(0.1)
    raise AssertionError(f"Health request failed: {last_error}")


def _shutdown_process(process: subprocess.Popen[str]) -> None:
    assert process.stdin is not None
    process.stdin.write("shutdown\n")
    process.stdin.flush()
    try:
        process.wait(timeout=SHUTDOWN_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        _force_kill_process(process)
        raise AssertionError("Sidecar did not exit after shutdown command") from exc

    if process.returncode is None:
        _force_kill_process(process)
        raise AssertionError("Sidecar process did not terminate")


def _force_kill_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return

    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            capture_output=True,
        )
    else:
        process.kill()

    process.wait(timeout=5)


def _assert_port_released(host: str, port: int) -> None:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.settimeout(0.5)
        result = probe.connect_ex((host, port))
        if result == 0:
            raise AssertionError(f"Loopback port {port} is still bound after shutdown")
    finally:
        probe.close()


if __name__ == "__main__":
    main()
