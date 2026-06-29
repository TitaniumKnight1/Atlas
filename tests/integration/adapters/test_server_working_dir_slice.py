"""Integration: resolve server working dir for adopted prevailrp-shape repos."""

from __future__ import annotations

from pathlib import Path

from backend.domain.shared_kernel import ProjectId
from backend.infrastructure.di import create_application_container


def test_resolve_server_working_directory_for_root_server_cfg(tmp_path: Path) -> None:
    container = create_application_container(tmp_path / "app-data")
    root = tmp_path / "team-server"
    root.mkdir()
    resources = root / "resources"
    resources.mkdir()
    (resources / "demo").mkdir()
    (resources / "demo" / "fxmanifest.lua").write_text("fx_version 'cerulean'\n", encoding="utf-8")
    (root / "server.cfg").write_text('endpoint_add_tcp "0.0.0.0:30120"\nensure demo\n', encoding="utf-8")
    try:
        adopt = container.create_adopt_service().execute_adopt_repository(root_path=root)
        project_id = ProjectId(str(adopt.result["project_id"]))
        resolved = container.create_setup_service().resolve_server_working_directory(project_id=project_id)
        assert resolved["working_directory"] == str(root.resolve())
        assert resolved["server_cfg_relative"] == "server.cfg"
        assert Path(resolved["server_cfg_path"]).is_file()
    finally:
        container.close()
