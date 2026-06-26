from __future__ import annotations

import shutil
import zipfile
from pathlib import Path


class LocalSetupFilesystem:
    def ensure_directory(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)

    def extract_zip(self, archive_path: Path, destination: Path) -> list[Path]:
        destination.mkdir(parents=True, exist_ok=True)
        extracted: list[Path] = []
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                target = (destination / member.filename).resolve()
                if not str(target).startswith(str(destination.resolve())):
                    raise ValueError("archive member escapes destination")
                archive.extract(member, destination)
                extracted.append(target)
        return extracted

    def remove_path(self, path: Path) -> None:
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()

    def read_text(self, path: Path) -> str | None:
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def write_text(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def touch_file(self, path: Path) -> bool:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            return False
        path.touch()
        return True
