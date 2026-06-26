from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from backend.domain.incident.signals import FingerprintSignals

FINGERPRINT_ALGORITHM_VERSION = "atlas-crash-v1"

_ISO_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?")
_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE)
_WINDOWS_PATH = re.compile(r"[A-Za-z]:\\(?:[^\\:\n\r\t]+\\)*[^\\:\n\r\t]*")
_UNIX_PATH = re.compile(r"(?:/(?:usr|var|home|tmp|opt|app|server|resources|citizen)[^\s:]*|~[^\s:]*)")
_PID = re.compile(r"\b(?:pid|process)[=:\s#-]*\d+\b", re.IGNORECASE)
_PORT = re.compile(r":\d{2,5}\b")
_HEX_HASH = re.compile(r"\b[0-9a-f]{16,}\b", re.IGNORECASE)
_IPV4 = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
_NUMERIC_ID = re.compile(r"\b\d{6,}\b")
_SECRET_URL = re.compile(r"://[^:@\s]+:[^@\s]+@", re.IGNORECASE)
_SECRET_ASSIGNMENT = re.compile(
    r"\b(?:discord_token|api[_-]?key|license[_-]?key|mysql_connection_string|password|secret)\s*[=:]\s*[\"']?[^\"'\s]+",
    re.IGNORECASE,
)
_BEARER_TOKEN = re.compile(r"\b(?:bearer|token|api[_-]?key|license|secret)[=:\s\"']+[^\s\"']+", re.IGNORECASE)
_EXIT_CODE_IN_MESSAGE = re.compile(r"\b(?:exit(?:ed)?|code)\s+\d+\b", re.IGNORECASE)
_RESOURCE_STOP = re.compile(r"(?:stopping|starting|failed|error in|couldn't start)\s+resource\s+['\"]?([a-zA-Z0-9_-]+)", re.IGNORECASE)
_RESOURCE_ENSURE = re.compile(r"(?:ensure|resource)\s+['\"]?([a-zA-Z0-9_-]+)['\"]?", re.IGNORECASE)
_PATH_LIKE = re.compile(r"(?:[A-Za-z]:\\|/)[^\s]+")


@dataclass(frozen=True, slots=True)
class FingerprintResult:
    fingerprint: str
    algorithm_version: str
    components: dict[str, object]


def compute_fingerprint(signals: FingerprintSignals) -> FingerprintResult:
    normalized_message = normalize_text(signals.normalized_message)
    normalized_logs = tuple(normalize_text(line) for line in signals.log_lines if line.strip())
    log_signature = _hash_lines(normalized_logs)
    resource_hint = signals.resource_hint or _extract_resource_hint(normalized_logs)
    components: dict[str, object] = {
        "algorithm": FINGERPRINT_ALGORITHM_VERSION,
        "category": signals.category,
        "severity": signals.severity,
        "source_type": signals.source_type,
        "exit_code": signals.exit_code,
        "exception_type": signals.exception_type,
        "normalized_message": normalized_message,
        "log_signature": log_signature,
        "resource_hint": resource_hint,
    }
    canonical = json.dumps(components, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return FingerprintResult(
        fingerprint=digest,
        algorithm_version=FINGERPRINT_ALGORITHM_VERSION,
        components=components,
    )


def _redact_assignment(match: re.Match[str]) -> str:
    token = match.group(0)
    key = token.split("=")[0].split(":")[0].strip()
    return f"{key}=<secret>"


def normalize_text(value: str) -> str:
    text = value.strip()
    if not text:
        return ""
    text = _SECRET_URL.sub("://[REDACTED]@", text)
    text = _SECRET_ASSIGNMENT.sub(_redact_assignment, text)
    text = _BEARER_TOKEN.sub("<secret>", text)
    text = _ISO_TIMESTAMP.sub("<timestamp>", text)
    text = _UUID.sub("<id>", text)
    text = _PATH_LIKE.sub("<path>", text)
    text = _WINDOWS_PATH.sub("<path>", text)
    text = _UNIX_PATH.sub("<path>", text)
    text = _PID.sub("pid<pid>", text)
    text = _PORT.sub(":port", text)
    text = _IPV4.sub("<ip>", text)
    text = _HEX_HASH.sub("<hash>", text)
    text = _NUMERIC_ID.sub("<id>", text)
    text = _EXIT_CODE_IN_MESSAGE.sub("exit code <code>", text)
    return text


def _hash_lines(lines: tuple[str, ...]) -> str:
    if not lines:
        return ""
    meaningful = [line for line in lines if line]
    tail = meaningful[-5:]
    payload = "\n".join(tail)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _extract_resource_hint(lines: tuple[str, ...]) -> str | None:
    for line in reversed(lines):
        match = _RESOURCE_STOP.search(line) or _RESOURCE_ENSURE.search(line)
        if match:
            return match.group(1).lower()
    return None


def is_placeholder_fingerprint(fingerprint: str) -> bool:
    return fingerprint.startswith("capture:")
