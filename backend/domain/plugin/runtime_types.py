from __future__ import annotations

from enum import StrEnum


class PluginRuntimeStatus(StrEnum):
    STARTING = "starting"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"
    CRASHED = "crashed"
    TIMED_OUT = "timed_out"


class CapabilityCallDecision(StrEnum):
    GRANTED = "granted"
    DENIED = "denied"
    UNKNOWN = "unknown"


class CapabilityCallOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DENIED = "denied"
    ERROR = "error"


PLUGIN_STARTUP_TIMEOUT_SECONDS = 5.0
PLUGIN_CALL_TIMEOUT_SECONDS = 10.0
PLUGIN_HANG_KILL_TIMEOUT_SECONDS = 3.0


SUBPROCESS_HONEST_LIMIT = (
    "Subprocess isolation prevents the plugin from reading Atlas process memory, importing around the "
    "capability ledger, or calling Atlas internals directly. It does NOT confine the plugin to less than "
    "the user's OS privileges: the plugin subprocess can still access filesystem and network the OS permits "
    "unless further OS-level sandboxing is applied (out of scope for M9b)."
)
