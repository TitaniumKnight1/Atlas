from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class OccurrenceExportSection:
    occurrence_id: str
    occurred_at: str
    message: str
    source_type: str
    runtime: dict[str, Any]
    logs: dict[str, Any]
    fingerprint_components: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class IncidentExportReport:
    project_id: str
    incident_group_id: str
    title: str
    severity: str
    category: str
    status: str
    fingerprint: str
    fingerprint_components: dict[str, Any]
    occurrence_count: int
    first_seen_at: str
    last_seen_at: str
    related_groups: list[dict[str, Any]]
    occurrences: tuple[OccurrenceExportSection, ...]
    shared_runtime: dict[str, Any]
    resources: dict[str, Any]
    startup_order: dict[str, Any]
    config_excerpt: dict[str, Any]
    environment: dict[str, Any]
    exported_at: str


def build_incident_markdown_report(report: IncidentExportReport) -> str:
    lines: list[str] = [
        "# Atlas Incident Export",
        "",
        "> **Privacy notice:** This report will be sanitized before export. After export, review all "
        "`[REDACTED: category]` markers before pasting into an external AI (ChatGPT, Claude, Gemini, or a local LLM). "
        "Atlas does not send this report anywhere automatically.",
        "",
        "## Summary",
        f"- **Title:** {report.title}",
        f"- **Severity:** {report.severity}",
        f"- **Category:** {report.category}",
        f"- **Status:** {report.status}",
        f"- **Project ID:** {report.project_id}",
        f"- **Group ID:** {report.incident_group_id}",
        f"- **Occurrences:** {report.occurrence_count}",
        f"- **First seen:** {report.first_seen_at}",
        f"- **Last seen:** {report.last_seen_at}",
        f"- **Exported at:** {report.exported_at}",
        "",
        "## Fingerprint / Grouping",
        f"- **Fingerprint:** `{report.fingerprint}`",
    ]
    if report.fingerprint_components:
        lines.append("- **Fingerprint components:**")
        lines.append("```json")
        lines.append(json.dumps(report.fingerprint_components, indent=2, sort_keys=True))
        lines.append("```")
    if report.occurrence_count > 1:
        lines.extend(
            [
                "",
                "### Over-grouping review",
                "This group contains multiple occurrences sharing one fingerprint. Compare per-occurrence "
                "exit codes, messages, and log excerpts below — if they differ materially, M7b may have "
                "over-grouped distinct crashes.",
            ]
        )
    if report.related_groups:
        lines.extend(["", "## Related groups"])
        for item in report.related_groups:
            lines.append(
                f"- `{item.get('related_group_id')}` ({item.get('relation_type')}, confidence {item.get('confidence')}): "
                f"{item.get('title')}"
            )

    lines.extend(["", "## Occurrence timeline"])
    for occurrence in report.occurrences:
        lines.extend(
            [
                "",
                f"### Occurrence `{occurrence.occurrence_id}`",
                f"- **Occurred at:** {occurrence.occurred_at}",
                f"- **Source:** {occurrence.source_type}",
                f"- **Message:** {occurrence.message}",
            ]
        )
        if occurrence.fingerprint_components:
            lines.append(f"- **Per-occurrence exit code:** {occurrence.fingerprint_components.get('exit_code')}")
            lines.append(f"- **Log signature:** `{occurrence.fingerprint_components.get('log_signature', '')}`")
        runtime = occurrence.runtime or report.shared_runtime
        if runtime:
            lines.append(f"- **Process state:** {runtime.get('state')}")
            lines.append(f"- **Exit code:** {runtime.get('exit_code')}")
            lines.append(f"- **PID:** {runtime.get('pid')}")
        logs = occurrence.logs or {}
        lines.append("- **Log availability:** " + str(logs.get("availability", "unknown")))
        stdout = logs.get("stdout_tail") or []
        stderr = logs.get("stderr_tail") or []
        if stdout or stderr:
            lines.append("```text")
            for line in stderr[-10:]:
                lines.append(line)
            for line in stdout[-10:]:
                lines.append(line)
            lines.append("```")

    lines.extend(["", "## Environment snapshot"])
    if report.environment:
        lines.append("```json")
        lines.append(json.dumps(report.environment, indent=2, sort_keys=True))
        lines.append("```")

    lines.extend(["", "## Resources"])
    if report.resources:
        lines.append("```json")
        lines.append(json.dumps(report.resources, indent=2, sort_keys=True)[:8000])
        lines.append("```")

    lines.extend(["", "## Startup / ensure order"])
    if report.startup_order:
        lines.append("```json")
        lines.append(json.dumps(report.startup_order, indent=2, sort_keys=True))
        lines.append("```")

    lines.extend(["", "## Configuration references"])
    if report.config_excerpt:
        lines.append(
            "_Secret values are not included; only file metadata and open secret-finding references from M4a._"
        )
        lines.append("```json")
        lines.append(json.dumps(report.config_excerpt, indent=2, sort_keys=True))
        lines.append("```")

    return "\n".join(lines) + "\n"
