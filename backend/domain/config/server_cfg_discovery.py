from __future__ import annotations

import re
from pathlib import Path

EXEC_LINE = re.compile(r"^\s*exec\s+", re.IGNORECASE)


def find_server_cfg(root: Path) -> Path | None:
    resolved = root.expanduser().resolve()
    for candidate in (resolved / "server.cfg", resolved / "server-data" / "server.cfg"):
        if candidate.is_file():
            return candidate
    return None
