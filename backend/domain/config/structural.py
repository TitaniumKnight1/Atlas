from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ConfigFindingType(StrEnum):
    DANGLING_RESOURCE_REFERENCE = "DANGLING_RESOURCE_REFERENCE"
    MISSING_MANIFEST = "MISSING_MANIFEST"
    ABSOLUTE_PATH = "ABSOLUTE_PATH"
    INLINE_SECRET = "INLINE_SECRET"


class StructuralValidationStatus(StrEnum):
    NOT_RUN = "not_run"
    VALIDATED = "validated"
    SKIPPED_NO_SERVER_CFG = "skipped_no_server_cfg"


class AutoFixKind(StrEnum):
    COMMENT_OUT_ENSURE = "comment_out_ensure"
    REWRITE_ABSOLUTE_PATH = "rewrite_absolute_path"


@dataclass(frozen=True, slots=True)
class ConfigFindingRemediation:
    auto_fix_available: bool
    auto_fix_kind: str | None = None
    prompt_exportable: bool = True
    requires_confirmation: bool = False


@dataclass(frozen=True, slots=True)
class ConfigFinding:
    finding_id: str
    type: ConfigFindingType
    severity: str
    path: str
    line: int | None
    message: str
    remediation: ConfigFindingRemediation
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "type": self.type.value,
            "severity": self.severity,
            "path": self.path,
            "line": self.line,
            "message": self.message,
            "remediation": {
                "auto_fix_available": self.remediation.auto_fix_available,
                "auto_fix_kind": self.remediation.auto_fix_kind,
                "prompt_exportable": self.remediation.prompt_exportable,
                "requires_confirmation": self.remediation.requires_confirmation,
            },
            "context": dict(self.context),
        }


@dataclass(frozen=True, slots=True)
class StructuralValidationResult:
    status: StructuralValidationStatus
    findings: tuple[ConfigFinding, ...]
    server_cfg_path: str | None = None

    @property
    def finding_count(self) -> int:
        return len(self.findings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "finding_count": self.finding_count,
            "server_cfg_path": self.server_cfg_path,
            "findings": [item.to_dict() for item in self.findings],
            "prompts_available": True,
        }

    def warning_summary(self) -> list[str]:
        if self.status == StructuralValidationStatus.NOT_RUN:
            return ["Config not yet validated"]
        if self.status == StructuralValidationStatus.SKIPPED_NO_SERVER_CFG:
            return ["No server.cfg found — structural validation skipped"]
        if not self.findings:
            return []
        errors = sum(1 for item in self.findings if item.severity == "error")
        warnings = sum(1 for item in self.findings if item.severity == "warning")
        parts: list[str] = []
        if errors:
            parts.append(f"{errors} error{'s' if errors != 1 else ''}")
        if warnings:
            parts.append(f"{warnings} warning{'s' if warnings != 1 else ''}")
        info = sum(1 for item in self.findings if item.severity == "info")
        if info and not errors and not warnings:
            parts.append(f"{info} info")
        label = ", ".join(parts) if parts else str(len(self.findings))
        return [f"{len(self.findings)} structural config issue{'s' if len(self.findings) != 1 else ''} ({label})"]
