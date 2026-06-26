from __future__ import annotations

import hashlib
import shutil
import sqlite3
import zipfile
from pathlib import Path


class BackupArchiveAdapter:
    """Local zip archives only — stdlib compression, no external deps."""

    def create_zip_archive(self, source_dir: Path, archive_path: Path) -> int:
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        total = 0
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(source_dir.rglob("*")):
                if path.is_file():
                    arcname = path.relative_to(source_dir).as_posix()
                    archive.write(path, arcname)
                    total += path.stat().st_size
        return total

    def extract_zip_archive(self, archive_path: Path, destination: Path) -> list[str]:
        destination.mkdir(parents=True, exist_ok=True)
        extracted: list[str] = []
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                target = (destination / member.filename).resolve()
                if not str(target).startswith(str(destination.resolve())):
                    raise ValueError("archive member escapes destination")
                archive.extract(member, destination)
                if target.is_file():
                    extracted.append(str(target.relative_to(destination)))
        return extracted

    def sha256_file(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def snapshot_tree(self, source: Path, snapshot: Path) -> None:
        if snapshot.exists():
            shutil.rmtree(snapshot)
        shutil.copytree(source, snapshot)

    def copy_tree_into(self, source: Path, destination: Path, *, exclude_names: set[str] | None = None) -> list[dict[str, object]]:
        exclude = exclude_names or set()
        items: list[dict[str, object]] = []
        destination.mkdir(parents=True, exist_ok=True)
        for path in sorted(source.rglob("*")):
            if any(part in exclude for part in path.relative_to(source).parts):
                continue
            if path.is_file():
                relative = path.relative_to(source)
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
                items.append({"relative_path": relative.as_posix(), "size_bytes": path.stat().st_size})
        return items

    def sqlite_backup_file(self, source_db: Path, destination_db: Path) -> None:
        """Consistent SQLite copy via backup API — never copies Atlas app DB path."""
        destination_db.parent.mkdir(parents=True, exist_ok=True)
        if destination_db.exists():
            destination_db.unlink()
        source = sqlite3.connect(f"file:{source_db}?mode=ro", uri=True)
        try:
            dest = sqlite3.connect(str(destination_db))
            try:
                source.backup(dest)
            finally:
                dest.close()
        finally:
            source.close()
