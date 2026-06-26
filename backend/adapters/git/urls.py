from __future__ import annotations

from urllib.parse import urlparse, urlunparse


REDACTED_CREDENTIAL = "[REDACTED]"


def redact_remote_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if not parsed.username and not parsed.password:
        return url
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    netloc = f"{REDACTED_CREDENTIAL}@{host}"
    return urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))


def sanitize_git_payload(value: object) -> object:
    if isinstance(value, dict):
        sanitized: dict[str, object] = {}
        for key, item in value.items():
            if key in {"remote_url", "url"} and isinstance(item, str):
                sanitized[key] = redact_remote_url(item)
            else:
                sanitized[key] = sanitize_git_payload(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_git_payload(item) for item in value]
    return value
