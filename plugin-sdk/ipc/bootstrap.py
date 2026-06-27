"""Atlas plugin subprocess bootstrap — stdlib only; never imports Atlas backend."""

from __future__ import annotations

import importlib.util
import json
import sys
import uuid
from pathlib import Path
from typing import Any


class PluginIpcClient:
    def __init__(self) -> None:
        self._counter = 0

    def request_capability(self, capability: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._counter += 1
        request_id = f"req-{self._counter}-{uuid.uuid4().hex[:8]}"
        message = {
            "ipc_version": "1",
            "type": "capability_request",
            "request_id": request_id,
            "capability": capability,
            "params": params or {},
        }
        sys.stdout.write(json.dumps(message) + "\n")
        sys.stdout.flush()
        line = sys.stdin.readline()
        if not line:
            raise RuntimeError("Host closed IPC channel")
        return json.loads(line)

    def shutdown(self) -> None:
        sys.stdout.write(json.dumps({"ipc_version": "1", "type": "shutdown"}) + "\n")
        sys.stdout.flush()

    def contribution_result(self, contribution_id: str, result: dict[str, Any] | None = None) -> None:
        sys.stdout.write(
            json.dumps(
                {
                    "ipc_version": "1",
                    "type": "contribution_result",
                    "contribution_id": contribution_id,
                    "result": result or {},
                }
            )
            + "\n"
        )
        sys.stdout.flush()


def main() -> None:
    if len(sys.argv) < 3:
        raise SystemExit("usage: bootstrap.py <plugin_script> <mode>")
    plugin_script = Path(sys.argv[1]).resolve()
    mode = sys.argv[2]
    line = sys.stdin.readline()
    if not line:
        raise SystemExit("missing host_ready message")
    config = json.loads(line)
    client = PluginIpcClient()
    spec = importlib.util.spec_from_file_location("atlas_plugin_entry", plugin_script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load plugin script: {plugin_script}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "run"):
        raise RuntimeError("Plugin script must define run(client, mode)")
    module.run(client, mode=mode)
    client.shutdown()


if __name__ == "__main__":
    main()
