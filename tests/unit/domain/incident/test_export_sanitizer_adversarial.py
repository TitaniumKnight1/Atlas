import pytest
from backend.domain.incident.export_sanitizer import sanitize_export_markdown

def assert_redacted(markdown: str, secret: str):
    result = sanitize_export_markdown(markdown)
    assert secret not in result.sanitized_markdown, f"LEAKED: {secret} in {result.sanitized_markdown}"
    assert "[REDACTED:" in result.sanitized_markdown

def test_api_keys_free_floating():
    # Free-floating sk- keys without "api_key=" prefix
    assert_redacted("Error connecting to stripe with sk-live-1234567890abcdefGHIJKLMN", "sk-live-1234567890abcdefGHIJKLMN")
    assert_redacted("OpenAI error: sk-proj-abcdef1234567890", "sk-proj-abcdef1234567890")

def test_mongodb_srv():
    # mongodb+srv is missing from the DB regex
    assert_redacted("Timeout on mongodb+srv://dbuser:dbpass123@cluster0.mongodb.net/test", "dbuser:dbpass123")

def test_ipv6_variants():
    # Compressed IPv6 and IPv4-mapped
    assert_redacted("Request from ::1 failed", "::1")
    assert_redacted("Connection from ::ffff:192.168.1.1", "::ffff:192.168.1.1")

def test_fivem_identifiers():
    # FiveM specific identifiers not in the basic identifier list
    assert_redacted("Player joined: discord:123456789012345678", "123456789012345678")
    assert_redacted("Banned xbl:2533274790000000", "2533274790000000")
    assert_redacted("Live live:123456", "123456")

def test_credential_url_variants():
    # URL with only token (no username) e.g., https://<token>@host
    assert_redacted("Failed to fetch https://ghp_1234567890abcdefGHIJKLMN@github.com/repo", "ghp_1234567890abcdefGHIJKLMN")
    # Tokens in query parameters
    assert_redacted("GET /api/data?token=supersecret_token_12345", "supersecret_token_12345")

def test_discord_token_base64():
    # Base64 wrapped token (e.g. sometimes logs do this)
    import base64
    token = "MTIzNDU2Nzg5MDEyMzQ1Njc4OTAx.Ghpcy5pcy5hLnRlc3QudG9rZW4.c2VjcmV0X3ZhbHVlX2hlcmU"
    b64_token = base64.b64encode(token.encode()).decode()
    # The original token shouldn't be exposed, but we also want to make sure the b64 representation is redacted if it's long enough
    assert_redacted(f"Auth failed: {b64_token}", b64_token)

def test_punctuation_evasion():
    # Secret with punctuation
    assert_redacted('{"password": "my_super_secret_password!"}', "my_super_secret_password!")
