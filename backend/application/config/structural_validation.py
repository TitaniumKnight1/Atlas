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


def run_structural_validation(*, root: Path, filesystem: Any, secret_scanner: Any) -> StructuralValidationResult:
    return run_config_validation(root=root, filesystem=filesystem, secret_scanner=secret_scanner)


def enrich_validation_payload(result: StructuralValidationResult, *, root_path: str | None = None) -> dict[str, Any]:
    payload = result.to_dict()
    findings = result.findings
    payload["fix_prompts"] = {item.finding_id: build_fix_prompt(item, server_root_hint=root_path) for item in findings}
    payload["all_issues_prompt"] = build_all_issues_prompt(list(findings), server_root_hint=root_path)
    return payload


def not_run_validation() -> dict[str, Any]:
    return {
        "status": StructuralValidationStatus.NOT_RUN.value,
        "finding_count": 0,
        "findings": [],
        "server_cfg_path": None,
        "prompts_available": False,
    }
