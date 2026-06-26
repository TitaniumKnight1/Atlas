from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path

from git import Repo
from sqlalchemy import func, select

from backend.adapters.persistence.models import AuditEventRecord, TelemetryQueueRecord, TelemetryRejectionRecord
from backend.domain.shared_kernel import ProjectId
from backend.infrastructure.di import create_application_container
from backend.infrastructure.streams import StreamTopic


def test_clone_commit_branch_status_and_diff(tmp_path: Path) -> None:
    container, project_id, bare_path = _fixture_project(tmp_path)
    service = container.create_git_service()
    clone_dest = tmp_path / "cloned-repo"
    try:
        result = service.execute_clone_repository(
            project_id=project_id,
            remote_url=str(bare_path),
            destination_path=str(clone_dest),
        )
        repo_id = result.result["git_repository_id"]
        (clone_dest / "README.md").write_text("hello atlas\n", encoding="utf-8")
        service.execute_create_commit(project_id=project_id, git_repository_id=repo_id, message="Add readme")
        service.execute_create_branch(project_id=project_id, git_repository_id=repo_id, branch_name="feature/test")
        status = service.get_worktree_status(project_id, repo_id)
        assert status["is_dirty"] is False
        refs = service.list_refs(project_id, repo_id)
        assert any(item["ref_name"] == "feature/test" for item in refs)
        head = status["head_commit_sha"]
        diff = service.get_diff_summary(project_id, repo_id, f"{head}~1", head)
        assert diff["files"]
    finally:
        container.close()


def test_clone_undo_removes_directory(tmp_path: Path) -> None:
    container, project_id, bare_path = _fixture_project(tmp_path)
    service = container.create_git_service()
    clone_dest = tmp_path / "undo-clone"
    try:
        result = service.execute_clone_repository(project_id=project_id, remote_url=str(bare_path), destination_path=str(clone_dest))
        assert clone_dest.exists()
        assert result.undo_plan is not None
        service.undo(result.undo_plan)
        assert not clone_dest.exists()
    finally:
        container.close()


def test_commit_undo_soft_resets(tmp_path: Path) -> None:
    container, project_id, bare_path = _fixture_project(tmp_path)
    service = container.create_git_service()
    clone_dest = tmp_path / "commit-repo"
    try:
        result = service.execute_clone_repository(project_id=project_id, remote_url=str(bare_path), destination_path=str(clone_dest))
        repo_id = result.result["git_repository_id"]
        before = service.get_worktree_status(project_id, repo_id)["head_commit_sha"]
        (clone_dest / "change.txt").write_text("x", encoding="utf-8")
        commit = service.execute_create_commit(project_id=project_id, git_repository_id=repo_id, message="track change")
        assert commit.undo_plan is not None
        service.undo(commit.undo_plan)
        after = service.get_worktree_status(project_id, repo_id)["head_commit_sha"]
        assert after == before
    finally:
        container.close()


def test_pull_preview_warns_on_dirty_tree(tmp_path: Path) -> None:
    container, project_id, bare_path = _fixture_project(tmp_path)
    service = container.create_git_service()
    clone_dest = tmp_path / "dirty-repo"
    try:
        result = service.execute_clone_repository(project_id=project_id, remote_url=str(bare_path), destination_path=str(clone_dest))
        repo_id = result.result["git_repository_id"]
        (clone_dest / "dirty.txt").write_text("uncommitted", encoding="utf-8")
        preview = service.preview_pull_repository(project_id=project_id, git_repository_id=repo_id)
        assert preview.preview["reversible"] is False
        assert preview.warnings
    finally:
        container.close()


def test_delete_branch_preview_warns_irreversible(tmp_path: Path) -> None:
    container, project_id, bare_path = _fixture_project(tmp_path)
    service = container.create_git_service()
    clone_dest = tmp_path / "branch-repo"
    try:
        result = service.execute_clone_repository(project_id=project_id, remote_url=str(bare_path), destination_path=str(clone_dest))
        repo_id = result.result["git_repository_id"]
        service.execute_create_branch(project_id=project_id, git_repository_id=repo_id, branch_name="temp-branch")
        preview = service.preview_delete_branch(project_id=project_id, git_repository_id=repo_id, branch_name="temp-branch")
        assert preview.preview["reversible"] is False
        assert preview.warnings
    finally:
        container.close()


def test_clone_publishes_op_progress_events(tmp_path: Path) -> None:
    container, project_id, bare_path = _fixture_project(tmp_path)
    service = container.create_git_service()
    clone_dest = tmp_path / "progress-repo"
    received: list[dict] = []
    subscriber = container.stream_hub.subscribe(str(project_id), {StreamTopic.OP_PROGRESS})
    stop = threading.Event()

    def consume() -> None:
        while not stop.is_set():
            event = subscriber.wait_next(0.2)
            if event is not None:
                received.append(event.to_sse_data())

    thread = threading.Thread(target=consume, daemon=True)
    thread.start()
    time.sleep(0.1)
    try:
        service.execute_clone_repository(project_id=project_id, remote_url=str(bare_path), destination_path=str(clone_dest))
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if any(item.get("event_type") == "OperationProgress" for item in received):
                break
            time.sleep(0.05)
        stop.set()
        thread.join(timeout=2)
        assert any(item.get("event_type") == "OperationProgress" for item in received)
        assert all("supersecret" not in json.dumps(item) for item in received)
    finally:
        container.close()


def test_remote_url_redacted_in_preview_storage_and_audit(tmp_path: Path) -> None:
    container, project_id, bare_path = _fixture_project(tmp_path)
    service = container.create_git_service()
    secret_url = "https://user:supersecret@example.com/org/repo.git"
    preview = service.preview_clone_repository(project_id=project_id, remote_url=secret_url, destination_path=str(tmp_path / "redact-repo"))
    assert "supersecret" not in json.dumps(preview.preview)
    clone_dest = tmp_path / "redact-repo"
    try:
        result = service.execute_clone_repository(project_id=project_id, remote_url=str(bare_path), destination_path=str(clone_dest))
        repos = service.list_git_repositories(project_id)
        assert repos
        assert "supersecret" not in json.dumps(repos)
        with container.session_factory() as session:
            audits = session.execute(select(AuditEventRecord)).scalars().all()
            assert audits
            assert "supersecret" not in json.dumps([record.details_json for record in audits])
            assert int(session.scalar(select(func.count()).select_from(TelemetryQueueRecord)) or 0) == 0
            assert int(session.scalar(select(func.count()).select_from(TelemetryRejectionRecord)) or 0) == 0
        assert result.undo_plan is not None
    finally:
        container.close()


def test_project_isolation_blocks_foreign_repo(tmp_path: Path) -> None:
    container, first_project_id, bare_path = _fixture_project(tmp_path, name="alpha")
    second_project_id = ProjectId(container.create_project_service().execute_import_project(root_path=_project_root(tmp_path, "beta")).result["project_id"])
    service = container.create_git_service()
    clone_dest = tmp_path / "alpha-clone"
    try:
        result = service.execute_clone_repository(project_id=first_project_id, remote_url=str(bare_path), destination_path=str(clone_dest))
        repo_id = result.result["git_repository_id"]
        try:
            service.get_git_repository(second_project_id, repo_id)
        except Exception as error:  # noqa: BLE001
            assert "not found" in str(error).lower()
        else:
            raise AssertionError("cross-project git access was allowed")
    finally:
        container.close()


def _fixture_project(tmp_path: Path, name: str = "git-project"):
    container = create_application_container(tmp_path / "app-data")
    bare_path = _init_bare_repo_with_commit(tmp_path / "bare-origin")
    root = _project_root(tmp_path, name)
    project_id = ProjectId(container.create_project_service().execute_import_project(root_path=root).result["project_id"])
    return container, project_id, bare_path


def _project_root(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    root.mkdir(parents=True)
    return root


def _init_bare_repo_with_commit(bare_path: Path) -> Path:
    bare_path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "--bare", str(bare_path)], check=True, capture_output=True)
    work = bare_path.parent / "seed-work"
    work.mkdir(exist_ok=True)
    repo = Repo.init(str(work))
    readme = work / "README.md"
    readme.write_text("seed\n", encoding="utf-8")
    repo.index.add([str(readme)])
    repo.index.commit("seed commit")
    branch = repo.active_branch.name
    repo.create_remote("origin", str(bare_path))
    repo.remotes.origin.push(refspec=f"{branch}:{branch}")
    return bare_path
