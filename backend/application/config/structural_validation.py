from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from backend.domain.config import (
    StructuralValidationResult,
    StructuralValidationStatus,
    build_all_issues_prompt,
    build_fix_prompt,
    run_config_validation,
)
from backend.domain.pathway2.normalization import redact_config_text

DEFAULT_RESPONSE_FINDING_CAP = 100


def run_structural_validation(*, root: Path, filesystem: Any, secret_scanner: Any) -> StructuralValidationResult:
    return run_config_validation(root=root, filesystem=filesystem, secret_scanner=secret_scanner)


def enrich_validation_payload(
    result: StructuralValidationResult,
    *,
    root_path: str | None = None,
    for_response: bool = False,
    max_findings_in_response: int = DEFAULT_RESPONSE_FINDING_CAP,
) -> dict[str, Any]:
    findings = list(result.findings)
    payload = result.to_dict()
    payload["finding_count"] = len(findings)
    payload["counts_by_type"] = dict(Counter(item.type.value for item in findings))
    payload["counts_by_severity"] = dict(Counter(item.severity for item in findings))

    include_all = not for_response or len(findings) <= max_findings_in_response
    visible = findings if include_all else findings[:max_findings_in_response]
    payload["findings_truncated"] = not include_all
    payload["findings"] = [_audit_safe_finding_dict(item.to_dict()) for item in visible]
    payload["fix_prompts"] = {
        item.finding_id: _redact_validation_text(build_fix_prompt(item, server_root_hint=root_path)) for item in visible
    }
    if include_all:
        payload["all_issues_prompt"] = _redact_validation_text(build_all_issues_prompt(findings, server_root_hint=root_path))
    else:
        payload["all_issues_prompt"] = _redact_validation_text(
            _truncated_issues_prompt(findings, server_root_hint=root_path, visible_count=len(visible))
        )
    return payload


def _truncated_issues_prompt(findings: list[Any], *, server_root_hint: str | None, visible_count: int) -> str:
    summary = build_all_issues_prompt(findings[:visible_count], server_root_hint=server_root_hint)
    return (
        f"{summary}\n\n"
        f"Note: {len(findings) - visible_count} additional finding(s) omitted from this response. "
        "Re-fetch project status for the full list or fix issues in batches."
    )


def _redact_validation_text(value: str) -> str:
    return redact_config_text(value)


def _audit_safe_finding_dict(finding: dict[str, Any]) -> dict[str, Any]:
    safe = dict(finding)
    context = dict(safe.get("context") or {})
    for key, value in list(context.items()):
        if isinstance(value, str):
            context[key] = _redact_validation_text(value)
    safe["context"] = context
    if isinstance(safe.get("message"), str):
        safe["message"] = _redact_validation_text(safe["message"])
    return safe


def not_run_validation() -> dict[str, Any]:
    return {
        "status": StructuralValidationStatus.NOT_RUN.value,
        "finding_count": 0,
        "findings": [],
        "server_cfg_path": None,
        "prompts_available": False,
    }
