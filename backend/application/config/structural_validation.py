from __future__ import annotations

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


def run_structural_validation(*, root: Path, filesystem: Any, secret_scanner: Any) -> StructuralValidationResult:
    return run_config_validation(root=root, filesystem=filesystem, secret_scanner=secret_scanner)


def enrich_validation_payload(result: StructuralValidationResult, *, root_path: str | None = None) -> dict[str, Any]:
    payload = result.to_dict()
    findings = result.findings
    payload["findings"] = [_audit_safe_finding_dict(item.to_dict()) for item in findings]
    payload["fix_prompts"] = {
        item.finding_id: _redact_validation_text(build_fix_prompt(item, server_root_hint=root_path)) for item in findings
    }
    payload["all_issues_prompt"] = _redact_validation_text(build_all_issues_prompt(list(findings), server_root_hint=root_path))
    return payload


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
