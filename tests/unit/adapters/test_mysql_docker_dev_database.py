from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

from backend.adapters.docker.mysql_dev_database import MySqlDockerDevDatabase
from backend.domain.dev_db.types import (
    DEV_DB_DATABASE,
    DEV_DB_PASSWORD,
    DEV_DB_USER,
    MYSQL_IMAGE,
    DevDatabaseLifecycleStatus,
)


def _completed(returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_build_plan_matches_p2_connection_coordinates() -> None:
    adapter = MySqlDockerDevDatabase()
    plan = adapter.build_plan("proj-123")

    assert plan.image == MYSQL_IMAGE
    assert plan.database == DEV_DB_DATABASE
    assert plan.user == DEV_DB_USER
    assert plan.password == DEV_DB_PASSWORD
    assert plan.host == "127.0.0.1"
    assert plan.port == 3306
    assert plan.publish_host_port == "127.0.0.1:3306:3306"
    assert plan.connection_string == "mysql://atlas_dev:atlas_dev@127.0.0.1:3306/atlas_dev"
    assert plan.container_name == "atlas-dev-mysql-proj-123"
    assert plan.volume_name == "atlas-dev-mysql-proj-123"


def test_provision_docker_run_args_match_exact_spec() -> None:
    adapter = MySqlDockerDevDatabase()
    plan = adapter.build_plan("proj-abc")

    inspect_payload = json.dumps({"Id": "cid-1", "State": {"Running": True, "Status": "running"}})

    seen_run = {"value": False}

    def side_effect(args, **kwargs):
        if args[:3] == ["docker", "inspect", "--format"]:
            if seen_run["value"]:
                return _completed(stdout=inspect_payload)
            return _completed(returncode=1, stderr="No such object")
        if args[:2] == ["docker", "volume"]:
            return _completed()
        if args[:2] == ["docker", "run"]:
            seen_run["value"] = True
            return _completed(stdout="container-id\n")
        return _completed()

    with patch("backend.adapters.docker.mysql_dev_database.subprocess.run", side_effect=side_effect) as run_mock:
        with patch("backend.adapters.docker.mysql_dev_database.is_tcp_port_listening", return_value=True):
            runtime = adapter.provision(plan, root_password="root-secret")

    run_args = next(call.args[0] for call in run_mock.call_args_list if call.args[0][:2] == ["docker", "run"])
    assert run_args[:3] == ["docker", "run", "-d"]
    assert "--name" in run_args and plan.container_name in run_args
    assert f"{plan.volume_name}:/var/lib/mysql" in run_args
    assert "MYSQL_DATABASE=atlas_dev" in run_args
    assert "MYSQL_USER=atlas_dev" in run_args
    assert "MYSQL_PASSWORD=atlas_dev" in run_args
    assert "MYSQL_ROOT_PASSWORD=root-secret" in run_args
    assert "127.0.0.1:3306:3306" in run_args
    assert run_args[-1] == MYSQL_IMAGE
    assert runtime.container_running is True
    assert runtime.mysql_reachable is True


def test_remove_tiered_volume_flag() -> None:
    adapter = MySqlDockerDevDatabase()
    plan = adapter.build_plan("proj-abc")
    inspect_payload = json.dumps({"Id": "cid-1", "State": {"Running": False, "Status": "exited"}})

    with patch(
        "backend.adapters.docker.mysql_dev_database.subprocess.run",
        side_effect=[
            _completed(stdout=inspect_payload),
            _completed(returncode=0),
            _completed(returncode=0),
        ],
    ) as run_mock:
        result = adapter.remove(plan, remove_volume=True)

    assert result["removed_container"] is True
    assert result["removed_volume"] is True
    assert any(call.args[0][:3] == ["docker", "rm", "-f"] for call in run_mock.call_args_list)
    assert ["docker", "volume", "rm", plan.volume_name] in [call.args[0] for call in run_mock.call_args_list]


def test_remove_default_keeps_volume() -> None:
    adapter = MySqlDockerDevDatabase()
    plan = adapter.build_plan("proj-abc")
    inspect_payload = json.dumps({"Id": "cid-1", "State": {"Running": False, "Status": "exited"}})

    with patch(
        "backend.adapters.docker.mysql_dev_database.subprocess.run",
        side_effect=[
            _completed(stdout=inspect_payload),
            _completed(returncode=0),
        ],
    ) as run_mock:
        result = adapter.remove(plan, remove_volume=False)

    assert result["removed_container"] is True
    assert result["removed_volume"] is False
    assert not any(call.args[0][:2] == ["docker", "volume"] for call in run_mock.call_args_list)


def test_inspect_absent_when_container_missing() -> None:
    adapter = MySqlDockerDevDatabase()
    plan = adapter.build_plan("missing")

    with patch("backend.adapters.docker.mysql_dev_database.subprocess.run", return_value=_completed(returncode=1, stderr="No such object")):
        runtime = adapter.inspect(plan)

    assert runtime.lifecycle == DevDatabaseLifecycleStatus.ABSENT
