from __future__ import annotations

import time
from unittest.mock import patch

from backend.domain.dev_db.readiness import wait_for_mysql_ready


def test_wait_for_mysql_ready_succeeds_when_port_opens() -> None:
    with patch("backend.domain.dev_db.readiness.is_tcp_port_listening", side_effect=[False, True]):
        running, reachable = wait_for_mysql_ready("127.0.0.1", 3306, timeout_seconds=2, poll_interval=0.01, sleep=time.sleep)

    assert running is True
    assert reachable is True


def test_wait_for_mysql_ready_times_out() -> None:
    with patch("backend.domain.dev_db.readiness.is_tcp_port_listening", return_value=False):
        running, reachable = wait_for_mysql_ready("127.0.0.1", 3306, timeout_seconds=0.05, poll_interval=0.01, sleep=time.sleep)

    assert running is False
    assert reachable is False
