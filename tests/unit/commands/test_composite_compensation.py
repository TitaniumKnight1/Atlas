from __future__ import annotations

from pathlib import Path

from backend.application.commands import CommandContext, CompositeCompensation
from backend.application.config.service import RestoreConfigFileCompensation
from backend.application.git.service import RemoveClonedRepositoryCompensation


class _FakeFilesystem:
    def __init__(self) -> None:
        self.files: dict[str, str] = {}

    def read_text(self, path: Path) -> str | None:
        return self.files.get(str(path))

    def write_text(self, path: Path, content: str) -> None:
        self.files[str(path)] = content


def test_composite_compensation_reverses_in_inverse_order(tmp_path: Path) -> None:
    resource_dir = tmp_path / "new-resource"
    resource_dir.mkdir()
    (resource_dir / "fxmanifest.lua").write_text("fx_version 'cerulean'", encoding="utf-8")
    server_cfg = tmp_path / "server.cfg"
    server_cfg.write_text("ensure gamma\n", encoding="utf-8")
    filesystem = _FakeFilesystem()
    filesystem.files[str(server_cfg)] = server_cfg.read_text(encoding="utf-8")
    filesystem.write_text(server_cfg, "ensure gamma\nensure new-resource\n")

    composite = CompositeCompensation(
        (
            RemoveClonedRepositoryCompensation(str(resource_dir)),
            RestoreConfigFileCompensation(str(server_cfg), "ensure gamma\n", filesystem),
        )
    )
    composite.apply(CommandContext(uow=object()))  # type: ignore[arg-type]

    assert not resource_dir.exists()
    assert filesystem.files[str(server_cfg)] == "ensure gamma\n"
