from __future__ import annotations

import time
from collections.abc import Callable

from backend.domain.dev_db.checks import is_tcp_port_listening


def wait_for_mysql_ready(
    host: str,
    port: int,
    *,
    timeout_seconds: float = 60.0,
    poll_interval: float = 1.0,
    is_listening: Callable[[str, int], bool] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> tuple[bool, bool]:
    """Return (container_assumed_running, mysql_reachable) after bounded TCP polling."""
    listen = is_listening or is_tcp_port_listening
    wait = sleep or time.sleep
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if listen(host, port):
            return True, True
        wait(poll_interval)
    return False, False
