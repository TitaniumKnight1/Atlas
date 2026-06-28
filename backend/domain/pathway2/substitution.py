from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from backend.adapters.config.validator import unified_diff
from backend.domain.pathway2.normalization import (
    LICENSE_LINE,
    OVERLAY_FILENAME,
    PLACEHOLDER,
    SET_LINE,
    redact_config_text,
    redact_unified_diff,
)

DEV_LICENSE_PLACEHOLDER = "DEV_LICENSE_KEY_SET_ME"
DEV_API_KEY_PLACEHOLDER = "DEV_API_KEY_SET_ME"
DEV_WEBHOOK_PLACEHOLDER = "DEV_WEBHOOK_IGNORE_ME"
DEV_GENERIC_PLACEHOLDER = "DEV_EXTERNAL_KEY_SET_ME"

DEV_SUPPLIED_MARKERS = (
    DEV_LICENSE_PLACEHOLDER,
    DEV_API_KEY_PLACEHOLDER,
    DEV_GENERIC_PLACEHOLDER,
)

AUTO_LOCAL_DB_DEFAULT = 'mysql://atlas_dev:atlas_dev@127.0.0.1:3306/atlas_dev'
AUTO_LOCAL_POSTGRES_DEFAULT = "postgresql://atlas_dev:atlas_dev@127.0.0.1:5432/atlas_dev"


class SecretHandlingClass(StrEnum):
    AUTO_LOCAL = "auto_local"
    DEV_SUPPLIED = "dev_supplied"
    DEV_IRRELEVANT = "dev_irrelevant"


@dataclass(frozen=True, slots=True)
class SubstitutionSlot:
    slot_id: str
    line_number: int
    convar_key: str | None
    secret_type: str | None
    handling_class: SecretHandlingClass
    current_line: str
    replacement_line: str
    masked_source: str = "[REDACTED]"


def classify_slot(*, secret_type: str | None, convar_key: str | None) -> SecretHandlingClass:
    key_lower = (convar_key or "").lower()
    if secret_type == "database_connection_string" or any(
        token in key_lower for token in ("mysql", "postgres", "mariadb", "mongodb", "connection_string", "database", "dsn")
    ):
        return SecretHandlingClass.AUTO_LOCAL
    if secret_type == "discord_webhook_url" or (convar_key and "webhook" in key_lower):
        return SecretHandlingClass.DEV_IRRELEVANT
    if secret_type == "cfx_license_key" or convar_key == "sv_licenseKey":
        return SecretHandlingClass.DEV_SUPPLIED
    if secret_type in {"discord_token", "api_key", "credential_assignment", "license_identifier"}:
        return SecretHandlingClass.DEV_SUPPLIED
    if secret_type == "credential_url":
        return SecretHandlingClass.DEV_IRRELEVANT
    return SecretHandlingClass.DEV_SUPPLIED


def infer_secret_type(*, convar_key: str | None, line: str) -> str | None:
    if LICENSE_LINE.match(line) or convar_key == "sv_licenseKey":
        return "cfx_license_key"
    if convar_key:
        key_lower = convar_key.lower()
        if "webhook" in key_lower:
            return "discord_webhook_url"
        if any(token in key_lower for token in ("mysql", "postgres", "mariadb", "mongodb", "connection", "database", "dsn")):
            return "database_connection_string"
        if "token" in key_lower or "api" in key_lower or "secret" in key_lower or "password" in key_lower:
            return "api_key"
    return None


def parse_overlay_slot(line: str, line_number: int) -> SubstitutionSlot | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith("endpoint_add_"):
        return None
    convar_key = _convar_key_from_line(line)
    if convar_key is None:
        return None
    if PLACEHOLDER not in line and not _is_dev_supplied_placeholder_line(line):
        return None
    secret_type = infer_secret_type(convar_key=convar_key, line=line)
    handling = classify_slot(secret_type=secret_type, convar_key=convar_key)
    replacement = _replacement_line(handling, convar_key=convar_key, secret_type=secret_type)
    return SubstitutionSlot(
        slot_id=_slot_id(convar_key),
        line_number=line_number,
        convar_key=convar_key,
        secret_type=secret_type,
        handling_class=handling,
        current_line=line,
        replacement_line=replacement,
    )


def plan_overlay_substitution(overlay_content: str) -> tuple[str, list[SubstitutionSlot], dict[str, Any]]:
    lines = overlay_content.splitlines()
    output_lines: list[str] = []
    slots: list[SubstitutionSlot] = []
    for index, line in enumerate(lines, start=1):
        slot = parse_overlay_slot(line, index)
        if slot is None:
            output_lines.append(line)
            continue
        slots.append(slot)
        output_lines.append(slot.replacement_line)
    proposed = "\n".join(output_lines).rstrip() + ("\n" if output_lines else "")
    meta = {
        "slot_count": len(slots),
        "auto_local_count": sum(1 for item in slots if item.handling_class == SecretHandlingClass.AUTO_LOCAL),
        "dev_supplied_count": sum(1 for item in slots if item.handling_class == SecretHandlingClass.DEV_SUPPLIED),
        "dev_irrelevant_count": sum(1 for item in slots if item.handling_class == SecretHandlingClass.DEV_IRRELEVANT),
    }
    return proposed, slots, meta


def build_substitution_preview(slots: list[SubstitutionSlot]) -> list[dict[str, Any]]:
    return [
        {
            "slot_id": slot.slot_id,
            "line_number": slot.line_number,
            "convar_key": slot.convar_key,
            "secret_type": slot.secret_type,
            "handling_class": slot.handling_class.value,
            "masked_source": slot.masked_source,
            "replacement_line": _preview_replacement_line(slot),
        }
        for slot in slots
    ]


def build_substitution_diff(*, current: str, proposed: str) -> str:
    return redact_unified_diff(unified_diff(current, proposed, OVERLAY_FILENAME))


def compute_run_gate(overlay_content: str) -> tuple[bool, list[str]]:
    unset: list[str] = []
    for marker in DEV_SUPPLIED_MARKERS:
        if marker in overlay_content:
            unset.append(marker)
    return len(unset) == 0, unset


def apply_dev_value_to_overlay(*, overlay_content: str, slot_id: str, dev_value: str) -> str:
    if not dev_value.strip():
        raise ValueError("dev value cannot be empty")
    lines = overlay_content.splitlines()
    updated: list[str] = []
    replaced = False
    for line in lines:
        slot = parse_overlay_slot(line, 0)
        if slot is not None and slot.slot_id == slot_id and slot.handling_class == SecretHandlingClass.DEV_SUPPLIED:
            updated.append(_dev_supplied_line(slot.convar_key, dev_value))
            replaced = True
            continue
        if _line_matches_slot(line, slot_id) and _is_dev_supplied_placeholder_line(line):
            convar_key = _convar_key_from_line(line)
            updated.append(_dev_supplied_line(convar_key, dev_value))
            replaced = True
            continue
        updated.append(line)
    if not replaced:
        raise ValueError(f"slot not found or not dev-supplied: {slot_id}")
    return "\n".join(updated).rstrip() + "\n"


def slot_preview_for_dev_value(*, slot_id: str, dev_value: str) -> dict[str, Any]:
    return {
        "slot_id": slot_id,
        "replacement_preview": redact_config_text(_dev_supplied_line(_slot_convar_key(slot_id), dev_value)),
        "masked_value": _masked_dev_value(dev_value),
    }


def _preview_replacement_line(slot: SubstitutionSlot) -> str:
    if slot.handling_class == SecretHandlingClass.AUTO_LOCAL:
        return slot.replacement_line
    return slot.replacement_line


def _replacement_line(handling: SecretHandlingClass, *, convar_key: str | None, secret_type: str | None) -> str:
    if handling == SecretHandlingClass.AUTO_LOCAL:
        if secret_type == "database_connection_string" and convar_key and "postgres" in convar_key.lower():
            return f'set {convar_key} "{AUTO_LOCAL_POSTGRES_DEFAULT}"'
        if secret_type == "database_connection_string" or (convar_key and "connection" in convar_key.lower()):
            key = convar_key or "mysql_connection_string"
            value = AUTO_LOCAL_DB_DEFAULT if "postgres" not in key.lower() else AUTO_LOCAL_POSTGRES_DEFAULT
            return f"set {key} \"{value}\""
        return f'set {convar_key or "local_convar"} "127.0.0.1"'
    if handling == SecretHandlingClass.DEV_IRRELEVANT:
        key = convar_key or "webhook_url"
        return f'set {key} "{DEV_WEBHOOK_PLACEHOLDER}"'
    if convar_key == "sv_licenseKey":
        return f'sv_licenseKey "{DEV_LICENSE_PLACEHOLDER}"'
    key = convar_key or "external_key"
    placeholder = DEV_API_KEY_PLACEHOLDER if "token" in key.lower() or "api" in key.lower() else DEV_GENERIC_PLACEHOLDER
    return f'set {key} "{placeholder}"'


def _dev_supplied_line(convar_key: str | None, dev_value: str) -> str:
    escaped = dev_value.replace('"', '\\"')
    if convar_key == "sv_licenseKey":
        return f'sv_licenseKey "{escaped}"'
    return f'set {convar_key} "{escaped}"'


def _convar_key_from_line(line: str) -> str | None:
    if LICENSE_LINE.match(line):
        return "sv_licenseKey"
    match = SET_LINE.match(line)
    if match:
        return match.group(1)
    return None


def _slot_id(convar_key: str | None) -> str:
    return convar_key or "unknown"


def _slot_convar_key(slot_id: str) -> str:
    return slot_id


def _is_dev_supplied_placeholder_line(line: str) -> bool:
    return any(marker in line for marker in DEV_SUPPLIED_MARKERS)


def _line_matches_slot(line: str, slot_id: str) -> bool:
    convar_key = _convar_key_from_line(line)
    return convar_key == slot_id


def _masked_dev_value(value: str) -> str:
    if len(value) <= 8:
        return "[REDACTED]"
    return f"{value[:4]}...[REDACTED]"
