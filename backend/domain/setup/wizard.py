"""Pathway 1 new-server setup wizard step derivation."""

from __future__ import annotations

from typing import Any, Literal

SetupWizardStepId = Literal["project", "artifact", "install", "config", "dependencies", "database", "validate"]
SetupWizardStepStatus = Literal["upcoming", "active", "complete", "failed"]

SETUP_WIZARD_STEP_DEFS: tuple[tuple[SetupWizardStepId, str], ...] = (
    ("project", "Project"),
    ("artifact", "Artifact"),
    ("install", "Install"),
    ("config", "server.cfg"),
    ("dependencies", "Dependencies"),
    ("database", "Database"),
    ("validate", "Validate"),
)


def derive_active_step(
    *,
    has_artifact_pin: bool,
    fxserver_installed: bool,
    server_cfg_written: bool,
    dependency_checks_run: bool,
    database_prepared: bool,
    server_started: bool,
) -> SetupWizardStepId:
    if server_started:
        return "validate"
    if database_prepared:
        return "validate"
    if dependency_checks_run:
        return "database"
    if server_cfg_written:
        return "dependencies"
    if fxserver_installed:
        return "config"
    if has_artifact_pin:
        return "install"
    return "artifact"


def _step_complete(
    step_id: SetupWizardStepId,
    *,
    has_artifact_pin: bool,
    fxserver_installed: bool,
    server_cfg_written: bool,
    dependency_checks_run: bool,
    database_prepared: bool,
    server_started: bool,
) -> bool:
    if step_id == "project":
        return True
    if step_id == "artifact":
        return has_artifact_pin
    if step_id == "install":
        return fxserver_installed
    if step_id == "config":
        return server_cfg_written
    if step_id == "dependencies":
        return dependency_checks_run
    if step_id == "database":
        return database_prepared
    if step_id == "validate":
        return server_started
    return False


def build_wizard_status(
    *,
    has_artifact_pin: bool,
    fxserver_installed: bool,
    server_cfg_written: bool,
    dependency_checks_run: bool,
    database_prepared: bool,
    server_started: bool,
) -> dict[str, Any]:
    active_step = derive_active_step(
        has_artifact_pin=has_artifact_pin,
        fxserver_installed=fxserver_installed,
        server_cfg_written=server_cfg_written,
        dependency_checks_run=dependency_checks_run,
        database_prepared=database_prepared,
        server_started=server_started,
    )

    steps: list[dict[str, str]] = []
    for step_id, label in SETUP_WIZARD_STEP_DEFS:
        if step_id == active_step:
            status: SetupWizardStepStatus = "active"
        elif _step_complete(
            step_id,
            has_artifact_pin=has_artifact_pin,
            fxserver_installed=fxserver_installed,
            server_cfg_written=server_cfg_written,
            dependency_checks_run=dependency_checks_run,
            database_prepared=database_prepared,
            server_started=server_started,
        ):
            status = "complete"
        elif _step_index(step_id) < _step_index(active_step):
            status = "complete"
        else:
            status = "upcoming"
        steps.append({"id": step_id, "label": label, "status": status})

    gates = {
        "artifact": has_artifact_pin,
        "install": fxserver_installed,
        "config": server_cfg_written,
        "dependencies": dependency_checks_run,
        "database": database_prepared,
        "validate": server_started,
    }

    return {
        "active_step": active_step,
        "steps": steps,
        "gates": gates,
        "complete": server_started,
    }


def _step_index(step_id: SetupWizardStepId) -> int:
    for index, (candidate, _) in enumerate(SETUP_WIZARD_STEP_DEFS):
        if candidate == step_id:
            return index
    return 0
