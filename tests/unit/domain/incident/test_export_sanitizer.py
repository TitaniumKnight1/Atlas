from __future__ import annotations

from backend.domain.incident.export_sanitizer import redaction_marker, sanitize_export_markdown

# Representative planted secrets per M2/M4 vocabulary categories.
PLANTED_SECRETS: dict[str, str] = {
    "license_key": "cfxk_test123456789012345678901234",
    "discord_token": "MTIzNDU2Nzg5MDEyMzQ1Njc4OTAx.Ghpcy5pcy5hLnRlc3QudG9rZW4.c2VjcmV0X3ZhbHVlX2hlcmU",
    "webhook_url": "https://discord.com/api/webhooks/123456789012345678/abcdefghijklmnopqrstuvwxyz123456",
    "database_connection_string": "postgres://dbuser:supersecret@db.internal:5432/fivem",
    "api_key": "api_key=sk-live-supersecretvalue123456",
    "ipv4": "192.168.50.42",
    "ipv6": "2001:0db8:85a3:0000:0000:8a2e:0370:7334",
    "steam_id": "76561198000000000",
    "rockstar_id": "license:deadbeef0123456789abcdef01234567",
    "credential_url": "https://deploy:supersecret@github.com/org/private-repo.git",
    "player_identifier": 'player_id="steam:110000112345678"',
    "unknown_secret": "Zmx1ZmZ5X2Jhc2U2NF9zZWNyZXRfdG9rZW5fdmFsdWU",
}


def _markdown_with(secret_line: str) -> str:
    return (
        "# Atlas Incident Export\n\n"
        "## Summary\n"
        "- **Title:** Server process exited unexpectedly\n"
        "- **Category:** crash\n\n"
        "## Occurrence timeline\n"
        "### Occurrence `occ-1`\n"
        f"- **Message:** {secret_line}\n"
        "```text\n"
        f"{secret_line}\n"
        "Error: resource alpha failed to start\n"
        "```\n"
    )


def test_each_secret_category_is_redacted_with_visible_marker() -> None:
    for category, planted in PLANTED_SECRETS.items():
        result = sanitize_export_markdown(_markdown_with(planted))
        assert planted not in result.sanitized_markdown, f"{category} leaked"
        assert "[REDACTED:" in result.sanitized_markdown
        assert result.redaction_count >= 1
        assert "resource alpha failed" in result.sanitized_markdown


def test_debuggable_context_survives_redaction() -> None:
    planted = PLANTED_SECRETS["license_key"]
    result = sanitize_export_markdown(_markdown_with(planted))
    assert "Server process exited unexpectedly" in result.sanitized_markdown
    assert "resource alpha failed to start" in result.sanitized_markdown
    assert planted not in result.sanitized_markdown


def test_uncertain_secret_shaped_value_is_redacted() -> None:
    uncertain = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    result = sanitize_export_markdown(_markdown_with(uncertain))
    assert uncertain not in result.sanitized_markdown
    assert redaction_marker("unknown_secret") in result.sanitized_markdown


def test_redaction_summary_counts_categories() -> None:
    planted = f"{PLANTED_SECRETS['ipv4']} {PLANTED_SECRETS['license_key']}"
    result = sanitize_export_markdown(_markdown_with(planted))
    assert result.redaction_count >= 2
    assert result.categories
