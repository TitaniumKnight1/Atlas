from __future__ import annotations

from backend.domain.pathway2.substitution import (
    AUTO_LOCAL_DB_DEFAULT,
    DEV_LICENSE_PLACEHOLDER,
    SecretHandlingClass,
    classify_slot,
    compute_run_gate,
    plan_overlay_substitution,
)


def test_classify_database_auto_local_and_license_dev_supplied() -> None:
    assert classify_slot(secret_type="database_connection_string", convar_key="mysql_connection_string") == SecretHandlingClass.AUTO_LOCAL
    assert classify_slot(secret_type="cfx_license_key", convar_key="sv_licenseKey") == SecretHandlingClass.DEV_SUPPLIED
    assert classify_slot(secret_type=None, convar_key="unknown_integration") == SecretHandlingClass.DEV_SUPPLIED


def test_plan_overlay_substitution_auto_local_has_no_prod_fragments() -> None:
    overlay = (
        'sv_licenseKey "CHANGE_ME"\n'
        'set mysql_connection_string "CHANGE_ME"\n'
        'set discord_webhook "CHANGE_ME"\n'
    )
    proposed, slots, _meta = plan_overlay_substitution(overlay)
    assert "CHANGE_ME" not in proposed
    assert AUTO_LOCAL_DB_DEFAULT in proposed
    assert "DEV_LICENSE_KEY_SET_ME" in proposed
    assert "DEV_WEBHOOK_IGNORE_ME" in proposed
    assert any(slot.handling_class == SecretHandlingClass.AUTO_LOCAL for slot in slots)


def test_compute_run_gate_open_only_without_dev_supplied_placeholders() -> None:
    ready, unset = compute_run_gate('sv_licenseKey "DEV_LICENSE_KEY_SET_ME"\n')
    assert ready is False
    assert DEV_LICENSE_PLACEHOLDER in unset

    ready, unset = compute_run_gate('sv_licenseKey "cfxk_real_dev_key"\n')
    assert ready is True
    assert unset == []
