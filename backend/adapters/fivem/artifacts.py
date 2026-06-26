from __future__ import annotations

import json
import re
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from urllib import request

from backend.domain.setup import ArtifactChannel, ArtifactPlatform, ArtifactVersion, DownloadProgress
from backend.domain.shared_kernel import StableIdentifier


RUNTIME_BASE_URLS = {
    ArtifactPlatform.WINDOWS: "https://runtime.fivem.net/artifacts/fivem/build_server_windows/master",
    ArtifactPlatform.LINUX: "https://runtime.fivem.net/artifacts/fivem/build_proot_linux/master",
}


class CfxArtifactClient:
    """Current Cfx.re runtime artifact adapter using the official runtime host."""

    def discover(self, platform: ArtifactPlatform, channel: ArtifactChannel | None = None) -> list[ArtifactVersion]:
        channels = [channel] if channel else [ArtifactChannel.RECOMMENDED, ArtifactChannel.LATEST, ArtifactChannel.OPTIONAL]
        artifacts: list[ArtifactVersion] = []
        for selected_channel in channels:
            artifacts.append(self._discover_channel(platform, selected_channel))
        return artifacts

    def download(
        self,
        artifact: ArtifactVersion,
        destination: Path,
        progress: Callable[[DownloadProgress], None] | None = None,
        operation_id: str | None = None,
    ) -> Path:
        if artifact.download_url is None:
            raise ValueError("artifact download_url is required")
        destination.parent.mkdir(parents=True, exist_ok=True)
        operation = operation_id or str(StableIdentifier.new())
        with request.urlopen(artifact.download_url, timeout=30) as response:
            total = int(response.headers.get("Content-Length", "0")) or artifact.size_bytes
            received = 0
            with destination.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 128)
                    if not chunk:
                        break
                    output.write(chunk)
                    received += len(chunk)
                    if progress:
                        progress(DownloadProgress(operation, received, total, "downloading FXServer artifact"))
        if progress:
            progress(DownloadProgress(operation, received, total, "download complete"))
        return destination

    def _discover_channel(self, platform: ArtifactPlatform, channel: ArtifactChannel) -> ArtifactVersion:
        base_url = RUNTIME_BASE_URLS[platform]
        url = f"{base_url}/{channel.value}.json"
        with request.urlopen(url, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
        build_number = str(payload.get("version") or payload.get("build") or payload.get("name") or channel.value)
        archive_name = "server.zip" if platform == ArtifactPlatform.WINDOWS else "fx.tar.xz"
        download_url = str(payload.get("downloadUrl") or payload.get("url") or f"{base_url}/{build_number}/{archive_name}")
        return ArtifactVersion(
            artifact_version_id=str(StableIdentifier.new()),
            platform=platform,
            channel=channel,
            build_number=_build_number(build_number),
            download_url=download_url,
            sha256=payload.get("sha256"),
            size_bytes=payload.get("size"),
            released_at=payload.get("released_at") or payload.get("date") or datetime.now(UTC).isoformat(),
            metadata={"source": url, "raw": payload},
        )


class LocalArtifactSource:
    """Test/local artifact source that avoids network access."""

    def __init__(self, artifact: ArtifactVersion, archive_path: Path) -> None:
        self._artifact = artifact
        self._archive_path = archive_path

    def discover(self, platform: ArtifactPlatform, channel: ArtifactChannel | None = None) -> list[ArtifactVersion]:
        _ = (platform, channel)
        return [self._artifact]

    def download(
        self,
        artifact: ArtifactVersion,
        destination: Path,
        progress: Callable[[DownloadProgress], None] | None = None,
        operation_id: str | None = None,
    ) -> Path:
        _ = artifact
        destination.parent.mkdir(parents=True, exist_ok=True)
        total = self._archive_path.stat().st_size
        operation = operation_id or str(StableIdentifier.new())
        shutil.copyfile(self._archive_path, destination)
        if progress:
            progress(DownloadProgress(operation, total, total, "download complete"))
        return destination


def _build_number(value: str) -> str:
    match = re.search(r"\d+", value)
    return match.group(0) if match else value
