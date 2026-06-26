from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.adapters.telemetry.sanitizer import IDENTIFIER_RULES, SECRET_RULES

REDACTION_PREFIX = "[REDACTED:"
REDACTION_SUFFIX = "]"

# Shared M2 vocabulary — export-only extensions for credential URLs and uncertainty.
EXPORT_EXTRA_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "credential_url",
        re.compile(r"://[^:@\s/]+:[^@\s/]+@", re.IGNORECASE),
    ),
    (
        "player_identifier",
        re.compile(r"\b(?:player[_-]?(?:id|name|license)|citizenid)[=:\s\"']+[^\s\"']+", re.IGNORECASE),
    ),
)

# Err toward redaction: high-entropy secret-shaped tokens not matched above.
_UNCERTAIN_SECRET = re.compile(r"\b[A-Za-z0-9._~-]{28,}\b")


@dataclass(frozen=True, slots=True)
class ExportSanitizationResult:
    sanitized_markdown: str
    redaction_count: int
    categories: dict[str, int] = field(default_factory=dict)
    rules_applied: tuple[str, ...] = ()


def sanitize_export_markdown(markdown: str) -> ExportSanitizationResult:
    """Pure redact-in-place sanitizer for outbound incident Markdown exports."""
    sanitized = markdown
    categories: dict[str, int] = {}
    rules_applied: set[str] = set()

    all_rules = (*SECRET_RULES, *IDENTIFIER_RULES, *EXPORT_EXTRA_RULES)
    for rule_name, pattern in all_rules:
        sanitized, count = _replace_with_marker(sanitized, pattern, rule_name)
        if count:
            rules_applied.add(rule_name)
            categories[rule_name] = categories.get(rule_name, 0) + count

    sanitized, uncertain_count = _replace_uncertain(sanitized)
    if uncertain_count:
        rules_applied.add("unknown_secret")
        categories["unknown_secret"] = categories.get("unknown_secret", 0) + uncertain_count

    total = sum(categories.values())
    return ExportSanitizationResult(
        sanitized_markdown=sanitized,
        redaction_count=total,
        categories=dict(sorted(categories.items())),
        rules_applied=tuple(sorted(rules_applied)),
    )


def redaction_marker(category: str) -> str:
    return f"{REDACTION_PREFIX} {category}{REDACTION_SUFFIX}"


def _replace_with_marker(text: str, pattern: re.Pattern[str], category: str) -> tuple[str, int]:
    marker = redaction_marker(category)
    return pattern.subn(marker, text)


def _replace_uncertain(text: str) -> tuple[str, int]:
    count = 0

    def replacer(match: re.Match[str]) -> str:
        nonlocal count
        value = match.group(0)
        if value.startswith(REDACTION_PREFIX):
            return value
        count += 1
        return redaction_marker("unknown_secret")

    sanitized = _UNCERTAIN_SECRET.sub(replacer, text)
    return sanitized, count
