from __future__ import annotations

import json
from pathlib import Path


class LocalTxAdminDetector:
    def detect(self, server_data_path: Path) -> dict[str, object] | None:
        txdata = server_data_path / "txData"
        if not txdata.exists():
            return None
        metadata: dict[str, object] = {"txdata_path": str(txdata)}
        settings = txdata / "default" / "settings.json"
        if settings.exists():
            try:
                payload = json.loads(settings.read_text(encoding="utf-8"))
                metadata["settings_present"] = True
                metadata["profile_name"] = payload.get("profileName")
            except json.JSONDecodeError:
                metadata["settings_present"] = False
        return metadata
