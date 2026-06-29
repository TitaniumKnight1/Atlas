"""Unit tests for Pathway 2 join-team wizard step derivation."""

from backend.domain.pathway2.wizard import build_wizard_status, derive_active_step


def _adopt_status(
    *,
    origin: str | None = "adopted",
    normalized: bool = False,
    secrets_substituted: bool = False,
    dev_transformed: bool = False,
    run_ready: bool = False,
    unset_dev_slots: list[str] | None = None,
    run_blocked_reason: str | None = None,
    looks_like_fivem: bool = True,
) -> dict:
    return {
        "project_id": "proj-1",
        "structure_scorecard": {"looks_like_fivem_server": looks_like_fivem},
        "pathway2_state": {
            "origin": origin,
            "normalized": normalized,
            "secrets_substituted": secrets_substituted,
            "dev_transformed": dev_transformed,
            "run_ready": run_ready,
        },
        "unset_dev_slots": unset_dev_slots or [],
        "run_blocked_reason": run_blocked_reason,
    }


def test_derive_active_step_fresh_adopt() -> None:
    assert derive_active_step(
        origin=None,
        normalized=False,
        secrets_substituted=False,
        dev_transformed=False,
        run_ready=False,
        unset_dev_slots=[],
    ) == "adopt"


def test_derive_active_step_resume_normalize() -> None:
    assert derive_active_step(
        origin="adopted",
        normalized=False,
        secrets_substituted=False,
        dev_transformed=False,
        run_ready=False,
        unset_dev_slots=[],
    ) == "normalize"


def test_derive_active_step_resume_secrets_unset_dev_slots() -> None:
    assert derive_active_step(
        origin="adopted",
        normalized=True,
        secrets_substituted=True,
        dev_transformed=False,
        run_ready=False,
        unset_dev_slots=["dev_license"],
    ) == "secrets"


def test_derive_active_step_resume_tuning() -> None:
    assert derive_active_step(
        origin="adopted",
        normalized=True,
        secrets_substituted=True,
        dev_transformed=False,
        run_ready=True,
        unset_dev_slots=[],
    ) == "tuning"


def test_derive_active_step_resume_run() -> None:
    assert derive_active_step(
        origin="adopted",
        normalized=True,
        secrets_substituted=True,
        dev_transformed=True,
        run_ready=True,
        unset_dev_slots=[],
    ) == "run"


def test_derive_active_step_done_after_server_started() -> None:
    assert derive_active_step(
        origin="adopted",
        normalized=True,
        secrets_substituted=True,
        dev_transformed=True,
        run_ready=True,
        unset_dev_slots=[],
        server_started=True,
    ) == "done"


def test_wizard_run_blocked_until_dev_secrets_filled() -> None:
    wizard = build_wizard_status(
        adopt_status=_adopt_status(
            normalized=True,
            secrets_substituted=True,
            run_ready=False,
            unset_dev_slots=["dev_license"],
            run_blocked_reason="Set your dev license before running.",
        )
    )
    assert wizard["active_step"] == "secrets"
    assert wizard["gates"]["run"] is False
    assert "dev license" in wizard["blockers"]["run"].lower()


def test_wizard_run_blocked_until_server_started() -> None:
    wizard = build_wizard_status(
        adopt_status=_adopt_status(
            normalized=True,
            secrets_substituted=True,
            dev_transformed=True,
            run_ready=True,
        )
    )
    assert wizard["active_step"] == "run"
    assert wizard["gates"]["run"] is True
    assert "start your server" in wizard["blockers"]["run"].lower()


def test_wizard_run_complete_after_server_started() -> None:
    status = _adopt_status(
        normalized=True,
        secrets_substituted=True,
        dev_transformed=True,
        run_ready=True,
    )
    status["pathway2_state"]["server_started"] = True
    wizard = build_wizard_status(adopt_status=status)
    assert wizard["active_step"] == "done"
    assert wizard["gates"]["done"] is True
    assert "run" not in wizard["blockers"] or "start your server" not in wizard["blockers"].get("run", "").lower()


def test_wizard_return_blocked_by_contamination_gate() -> None:
    wizard = build_wizard_status(
        adopt_status=_adopt_status(
            normalized=True,
            secrets_substituted=True,
            dev_transformed=True,
            run_ready=True,
        ),
        return_path={
            "contamination_report": {
                "allowed": False,
                "gate_status": "BLOCKED",
                "findings": [
                    {
                        "path": "resources/foo.cfg",
                        "line": 12,
                        "secret_type": "license_key",
                        "redacted_preview": "****",
                    }
                ],
                "summary_lines": [],
            }
        },
    )
    assert wizard["gates"]["return"] is False
    assert "resources/foo.cfg" in wizard["blockers"]["return"]


def test_wizard_fivem_gate_blocks_normalize() -> None:
    wizard = build_wizard_status(
        adopt_status=_adopt_status(origin="adopted", looks_like_fivem=False),
    )
    assert wizard["gates"]["adopt"] is False
    assert "FiveM server" in wizard["blockers"]["normalize"]
