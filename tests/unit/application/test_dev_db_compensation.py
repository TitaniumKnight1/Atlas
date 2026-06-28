from __future__ import annotations

from unittest.mock import MagicMock

from backend.application.dev_db.compensation import ClearDevDatabaseSettingsCompensation
from backend.domain.dev_db.types import DevDatabaseEngine, DevDatabasePlan


def test_remove_compensation_default_does_not_remove_volume() -> None:
    plan = DevDatabasePlan(
        project_id="proj",
        engine=DevDatabaseEngine.MYSQL,
        image="mysql:8.0",
        container_name="atlas-dev-mysql-proj",
        volume_name="atlas-dev-mysql-proj",
        host="127.0.0.1",
        port=3306,
        database="atlas_dev",
        user="atlas_dev",
        password="atlas_dev",
        connection_string="mysql://atlas_dev:atlas_dev@127.0.0.1:3306/atlas_dev",
        publish_host_port="127.0.0.1:3306:3306",
    )
    port = MagicMock()
    port.remove.return_value = {"removed_container": True, "removed_volume": False}

    port.remove(plan, remove_volume=False)
    port.remove.assert_called_with(plan, remove_volume=False)

    port.remove(plan, remove_volume=True)
    assert port.remove.call_args.kwargs["remove_volume"] is True


def test_clear_settings_compensation_describe() -> None:
    compensation = ClearDevDatabaseSettingsCompensation("proj-1")
    assert compensation.describe()["action_type"] == "clear_dev_database_settings"
