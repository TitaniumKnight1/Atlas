"""Unit tests for Dev secrets wizard step guidance."""

from backend.domain.pathway2.secrets_step import derive_secrets_step_guidance
from backend.domain.pathway2.substitution import DEV_LICENSE_PLACEHOLDER
from backend.domain.pathway2.wizard import build_wizard_status


def test_guidance_apply_substitution_when_slots_pending() -> None:
    guidance = derive_secrets_step_guidance(
        normalized=True,
        secrets_substituted=False,
        run_ready=False,
        unset_dev_slots=[],
        run_blocked_reason=None,
        substitution_slot_count=2,
    )
    assert guidance["phase"] == "apply_substitution"
    assert guidance["show_substitution_command"] is True
    assert guidance["show_dev_entry_form"] is False
    assert "2 slot" in guidance["detail"]


def test_guidance_set_dev_license_after_substitution() -> None:
    guidance = derive_secrets_step_guidance(
        normalized=True,
        secrets_substituted=True,
        run_ready=False,
        unset_dev_slots=[DEV_LICENSE_PLACEHOLDER],
        run_blocked_reason=f"Set dev values for: {DEV_LICENSE_PLACEHOLDER}",
        substitution_slot_count=1,
    )
    assert guidance["phase"] == "set_dev_license"
    assert guidance["show_substitution_command"] is False
    assert guidance["show_dev_entry_form"] is True
    assert DEV_LICENSE_PLACEHOLDER in guidance["detail"]
    assert "cfxk_" in guidance["detail"]


def test_guidance_no_contradiction_when_zero_slots() -> None:
    guidance = derive_secrets_step_guidance(
        normalized=True,
        secrets_substituted=False,
        run_ready=False,
        unset_dev_slots=[],
        run_blocked_reason=None,
        substitution_slot_count=0,
    )
    assert guidance["phase"] == "overlay_missing_placeholders"
    assert guidance["show_substitution_command"] is False
    assert "CHANGE_ME" in guidance["detail"]
    assert "Apply secret substitution" not in guidance["title"]


def test_guidance_ready_when_run_gate_passes() -> None:
    guidance = derive_secrets_step_guidance(
        normalized=True,
        secrets_substituted=True,
        run_ready=True,
        unset_dev_slots=[],
        run_blocked_reason=None,
        substitution_slot_count=1,
    )
    assert guidance["phase"] == "ready"
    assert guidance["show_substitution_command"] is False
    assert guidance["show_dev_entry_form"] is False


def test_wizard_status_includes_secrets_step_guidance() -> None:
    wizard = build_wizard_status(
        adopt_status={
            "project_id": "proj-1",
            "structure_scorecard": {"looks_like_fivem_server": True},
            "pathway2_state": {
                "origin": "adopted",
                "normalized": True,
                "secrets_substituted": True,
                "dev_transformed": False,
                "run_ready": False,
            },
            "unset_dev_slots": [DEV_LICENSE_PLACEHOLDER],
            "run_blocked_reason": f"Set dev values for: {DEV_LICENSE_PLACEHOLDER}",
            "substitution_slots": [{"slot_id": "sv_licenseKey"}],
        }
    )
    secrets_step = wizard["secrets_step"]
    assert secrets_step["phase"] == "set_dev_license"
    assert wizard["blockers"]["secrets"] == secrets_step["detail"]
    assert "Dev secrets required" not in secrets_step["title"]
