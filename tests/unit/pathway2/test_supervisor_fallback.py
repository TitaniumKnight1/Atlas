from __future__ import annotations

from backend.domain.pathway2.supervisor_fallback import (
    build_plus_set_arguments,
    mask_launch_arguments,
    resolve_plus_set_overrides,
)


DEV_LICENSE = "cfxk_dev_personal_key_for_local_only"


def test_plus_set_onesync_from_overlay() -> None:
    overlay = "# Atlas P2-3 dev transform\nset onesync on\n"
    overrides = resolve_plus_set_overrides(overlay_content=overlay, base_content="")
    keys = [item.key for item in overrides]
    assert "onesync" in keys


def test_plus_set_license_only_when_base_resists_overlay() -> None:
    overlay = f'sv_licenseKey "{DEV_LICENSE}"\nset onesync on\n'
    base = 'sv_licenseKey GetConvar("sv_licenseKey", "changeme")\n'
    overrides = resolve_plus_set_overrides(overlay_content=overlay, base_content=base)
    license_items = [item for item in overrides if item.key == "sv_licenseKey"]
    assert len(license_items) == 1
    assert license_items[0].is_secret is True
    assert license_items[0].value == DEV_LICENSE


def test_plus_set_license_skipped_for_normal_base() -> None:
    overlay = f'sv_licenseKey "{DEV_LICENSE}"\nset onesync on\n'
    base = 'sv_licenseKey "CHANGE_ME"\n'
    overrides = resolve_plus_set_overrides(overlay_content=overlay, base_content=base)
    assert all(item.key != "sv_licenseKey" for item in overrides)


def test_mask_launch_arguments_hides_secret_plus_set_value() -> None:
    args = ["+exec", "server.cfg", "+set", "sv_licenseKey", DEV_LICENSE, "+set", "onesync", "on"]
    masked = mask_launch_arguments(args)
    assert DEV_LICENSE not in masked
    assert "[REDACTED]" in masked
    assert "+set" in masked
    assert "on" in masked
