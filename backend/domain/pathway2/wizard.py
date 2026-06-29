"""Pathway 2 join-team wizard step derivation (view over pathway2 state machine)."""

from __future__ import annotations

from typing import Any, Literal

from backend.domain.pathway2.secrets_step import derive_secrets_step_guidance

WizardStepId = Literal["adopt", "normalize", "secrets", "tuning", "run", "return", "done"]
WizardStepStatus = Literal["upcoming", "active", "complete", "failed"]

WIZARD_STEP_DEFS: tuple[tuple[WizardStepId, str], ...] = (
    ("adopt", "Clone & adopt"),
    ("normalize", "Normalize"),
    ("secrets", "Dev secrets"),
    ("tuning", "Dev tuning"),
    ("run", "Run locally"),
    ("return", "Return work"),
    ("done", "Done"),
)


def derive_active_step(
    *,
    origin: str | None,
    normalized: bool,
    secrets_substituted: bool,
    dev_transformed: bool,
    run_ready: bool,
    unset_dev_slots: list[str],
) -> WizardStepId:
    if not origin:
        return "adopt"
    if not normalized:
        return "normalize"
    if not secrets_substituted or unset_dev_slots or not run_ready:
        return "secrets"
    if not dev_transformed:
        return "tuning"
    return "run"


def _step_complete(
    step_id: WizardStepId,
    *,
    origin: str | None,
    normalized: bool,
    secrets_substituted: bool,
    dev_transformed: bool,
    run_ready: bool,
    commit_gate_passed: bool,
) -> bool:
    if step_id == "adopt":
        return bool(origin)
    if step_id == "normalize":
        return normalized
    if step_id == "secrets":
        return secrets_substituted and run_ready
    if step_id == "tuning":
        return dev_transformed
    if step_id == "return":
        return commit_gate_passed
    return False


def build_wizard_status(
    *,
    adopt_status: dict[str, Any],
    return_path: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state = adopt_status.get("pathway2_state") or {}
    scorecard = adopt_status.get("structure_scorecard") or {}
    unset_dev_slots = list(adopt_status.get("unset_dev_slots") or [])
    run_blocked_reason = adopt_status.get("run_blocked_reason")

    origin = state.get("origin")
    normalized = bool(state.get("normalized"))
    secrets_substituted = bool(state.get("secrets_substituted"))
    dev_transformed = bool(state.get("dev_transformed"))
    run_ready = bool(state.get("run_ready"))
    looks_like_fivem = bool(scorecard.get("looks_like_fivem_server"))

    contamination = (return_path or {}).get("contamination_report") or {}
    commit_allowed = bool(contamination.get("allowed"))
    commit_gate_passed = contamination.get("gate_status") == "PASS"

    active_step = derive_active_step(
        origin=origin,
        normalized=normalized,
        secrets_substituted=secrets_substituted,
        dev_transformed=dev_transformed,
        run_ready=run_ready,
        unset_dev_slots=unset_dev_slots,
    )

    steps: list[dict[str, str]] = []
    for step_id, label in WIZARD_STEP_DEFS:
        if step_id == active_step:
            status: WizardStepStatus = "active"
        elif _step_complete(
            step_id,
            origin=origin,
            normalized=normalized,
            secrets_substituted=secrets_substituted,
            dev_transformed=dev_transformed,
            run_ready=run_ready,
            commit_gate_passed=commit_gate_passed,
        ):
            status = "complete"
        elif step_id == "adopt" and not origin:
            status = "upcoming"
        elif step_id in {"normalize", "secrets", "tuning", "run", "return", "done"} and not origin:
            status = "upcoming"
        else:
            status = "complete" if _step_index(step_id) < _step_index(active_step) else "upcoming"
        steps.append({"id": step_id, "label": label, "status": status})

    blockers = _build_blockers(
        origin=origin,
        normalized=normalized,
        secrets_substituted=secrets_substituted,
        run_ready=run_ready,
        run_blocked_reason=run_blocked_reason,
        unset_dev_slots=unset_dev_slots,
        looks_like_fivem=looks_like_fivem,
        contamination=contamination,
        return_path=return_path,
    )

    gates = {
        "adopt": looks_like_fivem and bool(origin),
        "normalize": normalized,
        "secrets": secrets_substituted and run_ready,
        "tuning": True,
        "run": run_ready,
        "return": commit_allowed,
        "done": bool(origin) and normalized and run_ready,
    }

    substitution_slots = list(adopt_status.get("substitution_slots") or [])
    secrets_step = derive_secrets_step_guidance(
        normalized=normalized,
        secrets_substituted=secrets_substituted,
        run_ready=run_ready,
        unset_dev_slots=unset_dev_slots,
        run_blocked_reason=run_blocked_reason,
        substitution_slot_count=len(substitution_slots),
    )
    if secrets_step["phase"] not in {"ready"}:
        blockers["secrets"] = secrets_step["detail"]

    return {
        "active_step": active_step,
        "steps": steps,
        "gates": gates,
        "blockers": blockers,
        "next_step": _next_enabled_step(active_step, gates),
        "secrets_step": secrets_step,
    }


def _step_index(step_id: WizardStepId) -> int:
    for index, (candidate, _) in enumerate(WIZARD_STEP_DEFS):
        if candidate == step_id:
            return index
    return 0


def _next_enabled_step(active_step: WizardStepId, gates: dict[str, bool]) -> WizardStepId | None:
    order = [step_id for step_id, _ in WIZARD_STEP_DEFS]
    try:
        start = order.index(active_step) + 1
    except ValueError:
        start = 0
    for step_id in order[start:]:
        if step_id == "tuning":
            return step_id
        if gates.get(step_id):
            return step_id
        if step_id in {"normalize", "secrets", "run", "return"}:
            return step_id
    return "done"


def _build_blockers(
    *,
    origin: str | None,
    normalized: bool,
    secrets_substituted: bool,
    run_ready: bool,
    run_blocked_reason: str | None,
    unset_dev_slots: list[str],
    looks_like_fivem: bool,
    contamination: dict[str, Any],
    return_path: dict[str, Any] | None,
) -> dict[str, str]:
    blockers: dict[str, str] = {}
    if origin and not looks_like_fivem:
        blockers["normalize"] = "Atlas must detect a FiveM server (server.cfg and resources) before normalization."
    if normalized and not secrets_substituted:
        blockers["secrets"] = "Apply secret substitution to move production values into the gitignored overlay."
    if secrets_substituted and (unset_dev_slots or not run_ready):
        reason = run_blocked_reason or "Set dev-supplied secrets in server.cfg.local before running."
        blockers["secrets"] = reason
        blockers["run"] = reason
    elif not run_ready and run_blocked_reason:
        blockers["run"] = run_blocked_reason
    if return_path and not contamination.get("allowed"):
        summary = contamination.get("summary_lines") or []
        findings = contamination.get("findings") or []
        if findings:
            first = findings[0]
            blockers["return"] = (
                f"Remove the secret in {first.get('path')}:{first.get('line')} "
                f"({first.get('secret_type')}) before committing."
            )
        elif summary:
            blockers["return"] = str(summary[0])
        else:
            blockers["return"] = "Return-path secret gate blocked this commit."
    return blockers
