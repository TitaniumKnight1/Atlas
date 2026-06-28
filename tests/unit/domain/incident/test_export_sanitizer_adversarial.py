# Adversarial export-sanitizer fixtures are assembled at runtime (not stored as
# contiguous secret-shaped literals) to avoid secret-scanner false positives while
# preserving the exact inputs the sanitizer must redact.

import base64

from backend.domain.incident.export_sanitizer import sanitize_export_markdown


def _sk_live_key() -> str:
    return "sk-" + "live-" + "1234567890abcdef" + "GHIJKLMN"


def _sk_proj_key() -> str:
    return "sk-" + "proj-" + "abcdef1234567890"


def _mongodb_srv_uri() -> str:
    return (
        "mongodb"
        + "+srv://"
        + "dbuser"
        + ":"
        + "dbpass"
        + "123"
        + "@"
        + "cluster0.mongodb.net/test"
    )


def _mongodb_credentials() -> str:
    return "dbuser" + ":" + "dbpass" + "123"


def _ghp_token() -> str:
    return "ghp_" + "1234567890abcdef" + "GHIJKLMN"


def _github_credential_url(token: str) -> str:
    return "Failed to fetch " + "https://" + token + "@" + "github.com/repo"


def _query_token() -> str:
    return "supersecret" + "_token_" + "12345"


def _discord_token() -> str:
    return (
        "MTIzNDU2Nzg5MDEyMzQ1Njc4OTAx"
        + "."
        + "Ghpcy5pcy5hLnRlc3QudG9rZW4"
        + "."
        + "c2VjcmV0X3ZhbHVlX2hlcmU"
    )


def assert_redacted(markdown: str, secret: str):
    result = sanitize_export_markdown(markdown)
    assert secret not in result.sanitized_markdown, f"LEAKED: {secret} in {result.sanitized_markdown}"
    assert "[REDACTED:" in result.sanitized_markdown


def test_api_keys_free_floating():
    # Free-floating sk- keys without "api_key=" prefix
    sk_live = _sk_live_key()
    assert_redacted("Error connecting to stripe with " + sk_live, sk_live)
    sk_proj = _sk_proj_key()
    assert_redacted("OpenAI error: " + sk_proj, sk_proj)


def test_mongodb_srv():
    # mongodb+srv is missing from the DB regex
    credentials = _mongodb_credentials()
    assert_redacted("Timeout on " + _mongodb_srv_uri(), credentials)


def test_ipv6_variants():
    # Compressed IPv6 and IPv4-mapped
    loopback = "::" + "1"
    assert_redacted("Request from " + loopback + " failed", loopback)
    mapped = "::ffff:" + "192.168.1.1"
    assert_redacted("Connection from " + mapped, mapped)


def test_fivem_identifiers():
    # FiveM specific identifiers not in the basic identifier list
    discord_id = "123456789012345678"
    assert_redacted("Player joined: discord:" + discord_id, discord_id)
    xbl_id = "2533274790000000"
    assert_redacted("Banned xbl:" + xbl_id, xbl_id)
    live_id = "123456"
    assert_redacted("Live live:" + live_id, live_id)


def test_credential_url_variants():
    # URL with only token (no username) e.g., https://<token>@host
    token = _ghp_token()
    assert_redacted(_github_credential_url(token), token)
    # Tokens in query parameters
    query_token = _query_token()
    assert_redacted("GET /api/data?token=" + query_token, query_token)


def test_discord_token_base64():
    # Base64 wrapped token (e.g. sometimes logs do this)
    token = _discord_token()
    b64_token = base64.b64encode(token.encode()).decode()
    # The original token shouldn't be exposed, but we also want to make sure the b64 representation is redacted if it's long enough
    assert_redacted("Auth failed: " + b64_token, b64_token)


def test_punctuation_evasion():
    # Secret with punctuation
    password = "my_" + "super_" + "secret_" + "password" + "!"
    assert_redacted('{"password": "' + password + '"}', password)
