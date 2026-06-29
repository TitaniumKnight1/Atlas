"""Dev-secrets wizard step: single next-action guidance (no contradictory UI copy)."""

from __future__ import annotations

from typing import Any, Literal

from backend.domain.pathway2.substitution import DEV_LICENSE_PLACEHOLDER

SecretsStepPhase = Literal[
    "apply_substitution",
    "set_dev_license",
    "overlay_missing_placeholders",
    "ready",
    "blocked",
]


def derive_secrets_step_guidance(
    *,
    normalized: bool,
    secrets_substituted: bool,
    run_ready: bool,
    unset_dev_slots: list[str],
    run_blocked_reason: str | None,
    substitution_slot_count: int,
) -> dict[str, Any]:
    if not normalized:
        return _guidance(
            phase="blocked",
            title="Complete normalization first",
            detail="Finish the Normalize step before substituting dev secrets.",
            show_substitution_command=False,
            show_dev_entry_form=False,
            primary_action="Go back to Normalize",
        )

    if secrets_substituted and run_ready:
        return _guidance(
            phase="ready",
            title="Dev secrets ready",
            detail="Local overlay is configured. Continue to dev tuning or run the server when you are ready.",
            show_substitution_command=False,
            show_dev_entry_form=False,
            primary_action="Continue to dev tuning",
        )

    if secrets_substituted and unset_dev_slots:
        license_pending = DEV_LICENSE_PLACEHOLDER in unset_dev_slots or "sv_licenseKey" in unset_dev_slots
        if license_pending:
            detail = (
                f'Replace {DEV_LICENSE_PLACEHOLDER} in server.cfg.local with your personal Cfx.re dev license '
                '(starts with cfxk_). This file is gitignored — never commit the real key.'
            )
        else:
            detail = run_blocked_reason or f"Set dev values for: {', '.join(unset_dev_slots)}"
        return _guidance(
            phase="set_dev_license",
            title="Set your dev license key",
            detail=detail,
            show_substitution_command=False,
            show_dev_entry_form=True,
            primary_action="Save dev license, then continue",
        )

    if not secrets_substituted and substitution_slot_count > 0:
        return _guidance(
            phase="apply_substitution",
            title="Apply secret substitution",
            detail=(
                f"Preview substitution, then apply {substitution_slot_count} slot(s) to server.cfg.local. "
                "Atlas fills safe local defaults (e.g. local MySQL); you will set your dev license next."
            ),
            show_substitution_command=True,
            show_dev_entry_form=False,
            primary_action="Preview substitution, then apply",
        )

    if not secrets_substituted and substitution_slot_count == 0:
        return _guidance(
            phase="overlay_missing_placeholders",
            title="No secret placeholders in overlay",
            detail=(
                "server.cfg.local has no CHANGE_ME lines for Atlas to substitute. "
                "Re-run normalization (if server.cfg still has CHANGE_ME placeholders), or add "
                'sv_licenseKey "CHANGE_ME" and connection placeholders to server.cfg.local, then use Re-run changes.'
            ),
            show_substitution_command=False,
            show_dev_entry_form=False,
            primary_action="Re-run normalization or add CHANGE_ME to overlay",
        )

    return _guidance(
        phase="blocked",
        title="Dev secrets incomplete",
        detail=run_blocked_reason or "Complete secret substitution and dev license setup.",
        show_substitution_command=False,
        show_dev_entry_form=False,
        primary_action="Resolve blockers above",
    )


def _guidance(
    *,
    phase: SecretsStepPhase,
    title: str,
    detail: str,
    show_substitution_command: bool,
    show_dev_entry_form: bool,
    primary_action: str,
) -> dict[str, Any]:
    return {
        "phase": phase,
        "title": title,
        "detail": detail,
        "show_substitution_command": show_substitution_command,
        "show_dev_entry_form": show_dev_entry_form,
        "primary_action": primary_action,
    }
