"""Unit tests for Pathway 1 setup wizard step derivation."""

from backend.domain.setup.wizard import build_wizard_status, derive_active_step


def test_derive_active_step_fresh_project() -> None:
    assert (
        derive_active_step(
            has_artifact_pin=False,
            fxserver_installed=False,
            server_cfg_written=False,
            dependency_checks_run=False,
            database_prepared=False,
            server_started=False,
        )
        == "artifact"
    )


def test_derive_active_step_resume_validate_when_server_started() -> None:
    assert (
        derive_active_step(
            has_artifact_pin=True,
            fxserver_installed=True,
            server_cfg_written=True,
            dependency_checks_run=True,
            database_prepared=True,
            server_started=True,
        )
        == "validate"
    )


def test_build_wizard_status_marks_prior_steps_complete() -> None:
    wizard = build_wizard_status(
        has_artifact_pin=True,
        fxserver_installed=True,
        server_cfg_written=False,
        dependency_checks_run=False,
        database_prepared=False,
        server_started=False,
    )
    assert wizard["active_step"] == "config"
    statuses = {step["id"]: step["status"] for step in wizard["steps"]}
    assert statuses["artifact"] == "complete"
    assert statuses["install"] == "complete"
    assert statuses["config"] == "active"
