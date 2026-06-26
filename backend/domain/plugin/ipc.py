from __future__ import annotations

from typing import Any

IPC_VERSION = "1"

MESSAGE_HOST_READY = "host_ready"
MESSAGE_CAPABILITY_REQUEST = "capability_request"
MESSAGE_CAPABILITY_RESPONSE = "capability_response"
MESSAGE_SHUTDOWN = "shutdown"
MESSAGE_PLUGIN_LOG = "plugin_log"


def host_ready_message(*, plugin_id: str, granted_capabilities: list[str], mode: str, plugin_script: str) -> dict[str, Any]:
    return {
        "ipc_version": IPC_VERSION,
        "type": MESSAGE_HOST_READY,
        "plugin_id": plugin_id,
        "granted_capabilities": granted_capabilities,
        "mode": mode,
        "plugin_script": plugin_script,
    }


def capability_request_message(*, request_id: str, capability: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "ipc_version": IPC_VERSION,
        "type": MESSAGE_CAPABILITY_REQUEST,
        "request_id": request_id,
        "capability": capability,
        "params": params or {},
    }


def capability_response_message(
    *,
    request_id: str,
    granted: bool,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "ipc_version": IPC_VERSION,
        "type": MESSAGE_CAPABILITY_RESPONSE,
        "request_id": request_id,
        "granted": granted,
        "result": result or {},
        "error": error,
    }
