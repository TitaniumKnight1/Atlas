from __future__ import annotations

import json
import pytest

from backend.adapters.telemetry.sanitizer import DeterministicTelemetrySanitizer, TelemetrySanitizationError
from backend.domain.shared_kernel import Severity
from backend.domain.telemetry import SanitizationState, TelemetryEventCandidate, TelemetryRejectionReason, TelemetrySubsystem

def _candidate(payload: dict, event_type="atlas.backend.unhandled_exception") -> TelemetryEventCandidate:
    return TelemetryEventCandidate(
        event_type=event_type,
        subsystem=TelemetrySubsystem.BACKEND,
        severity=Severity.ERROR,
        payload=payload,
    )

def test_adversarial_secret_leaks():
    sanitizer = DeterministicTelemetrySanitizer()
    
    # A) SECRET LEAKS (redaction)
    # API keys, DB connection strings, Discord tokens/webhooks, IPv4/IPv6, Steam/Rockstar/FiveM identifiers, credential URLs, Windows/Unix paths.
    
    payload = {
        "message": "Error connecting to db",
        "exception": {
            "type": "RuntimeError", 
            "value": "Failed with token mfa.abcdefghijklmnopqrstuvw.abcdef.abcdefghijklmnopqrst", 
            "module": "backend"
        },
        "stacktrace": [
            {
                "filename": "C:\\Users\\Ryan\\Atlas\\backend\\app.py", 
                "function": "boom", 
                "module": "backend", 
                "lineno": 7,
                "abs_path": "/home/user/Atlas/backend/app.py"
            }
        ],
        "breadcrumbs": [
            {
                "category": "backend", 
                "message": "connect mysql://user:pass%20word@10.0.0.8:3306/db?ssl=true", 
                "level": "error",
                "timestamp": "2023-01-01T00:00:00Z",
                "type": "default"
            },
            {
                "category": "backend",
                "message": "discord webhook https://discordapp.com/api/webhooks/123456789012345678/abcdef-12345_67890~",
                "level": "error",
                "timestamp": "2023-01-01T00:00:00Z",
                "type": "default"
            },
            {
                "category": "backend",
                "message": "steam id steam:110000100000000 and rockstar:abcdef1234567890 and fivem:123456",
                "level": "error",
                "timestamp": "2023-01-01T00:00:00Z",
                "type": "default"
            },
            {
                "category": "backend",
                "message": "ipv6 2001:db8::1 and ipv4 192.168.1.1",
                "level": "error",
                "timestamp": "2023-01-01T00:00:00Z",
                "type": "default"
            },
            {
                "category": "backend",
                "message": "api_key=sk-1234567890abcdef1234567890abcdef and ghp_1234567890abcdef1234567890abcdef123456",
                "level": "error",
                "timestamp": "2023-01-01T00:00:00Z",
                "type": "default"
            },
            {
                "category": "backend",
                "message": "cfxk_1234567890abcdef1234567890abcdef and license:abcdefabcdefabcdefabcdefabcdefabcdefabcd",
                "level": "error",
                "timestamp": "2023-01-01T00:00:00Z",
                "type": "default"
            },
            {
                "category": "backend",
                "message": "http://user:pass@example.com/api?token=sk-1234567890abcdef1234567890abcdef",
                "level": "error",
                "timestamp": "2023-01-01T00:00:00Z",
                "type": "default"
            }
        ],
        "contexts": {
            "backend": {
                "component": "api"
            }
        },
        "tags": {
            "backend_subsystem": "backend"
        }
    }
    
    result = sanitizer.sanitize(_candidate(payload))
    assert result.state == SanitizationState.REDACTED
    
    serialized = json.dumps(result.sanitized_payload)
    
    # Assertions for leaks
    leaks = []
    if "mfa.abcdefghijklmnopqrstuvw.abcdef.abcdefghijklmnopqrst" in serialized: leaks.append("discord token")
    if "C:\\Users\\Ryan\\Atlas" in serialized: leaks.append("windows path")
    if "/home/user/Atlas" in serialized: leaks.append("unix path")
    if "mysql://user:pass%20word@10.0.0.8:3306/db?ssl=true" in serialized: leaks.append("db connection string")
    if "https://discordapp.com/api/webhooks/123456789012345678/abcdef-12345_67890~" in serialized: leaks.append("discord webhook")
    if "steam:110000100000000" in serialized: leaks.append("steam id")
    if "rockstar:abcdef1234567890" in serialized: leaks.append("rockstar id")
    if "fivem:123456" in serialized: leaks.append("fivem id")
    if "2001:db8::1" in serialized: leaks.append("ipv6")
    if "192.168.1.1" in serialized: leaks.append("ipv4")
    if "sk-1234567890abcdef1234567890abcdef" in serialized: leaks.append("sk- api key")
    if "ghp_1234567890abcdef1234567890abcdef123456" in serialized: leaks.append("ghp_ api key")
    if "cfxk_1234567890abcdef1234567890abcdef" in serialized: leaks.append("cfxk license")
    if "license:abcdefabcdefabcdefabcdefabcdefabcdefabcd" in serialized: leaks.append("license identifier")
    if "user:pass@example.com" in serialized: leaks.append("credential url")
    
    assert not leaks, f"Secrets leaked: {leaks}"

def test_adversarial_project_data_bypass():
    sanitizer = DeterministicTelemetrySanitizer()
    
    # B) PROJECT-DATA REJECT BYPASS (fail-closed)
    # server.cfg, txData/resources paths, FXServer/txAdmin log lines, SQL dumps, player data, sensitive key names
    
    bypasses = []
    
    # 1. Obfuscated paths / alternate separators
    try:
        result = sanitizer.sanitize(_candidate({"message": "Error in C:/servers/rp/resources/bank/server.cfg"}))
        if result.state != SanitizationState.REJECTED: bypasses.append("resources path with forward slashes")
    except Exception:
        pass
        
    try:
        result = sanitizer.sanitize(_candidate({"message": "Error in txdata\\default"}))
        if result.state != SanitizationState.REJECTED: bypasses.append("txData case variant")
    except Exception:
        pass

    try:
        result = sanitizer.sanitize(_candidate({"message": "Error in SERVER.CFG"}))
        if result.state != SanitizationState.REJECTED: bypasses.append("server.cfg case variant")
    except Exception:
        pass

    try:
        result = sanitizer.sanitize(_candidate({"message": "Player dropped: Alice"}))
        if result.state != SanitizationState.REJECTED: bypasses.append("player dropped case variant")
    except Exception:
        pass

    try:
        result = sanitizer.sanitize(_candidate({"message": "insert into users (id) values (1)"}))
        if result.state != SanitizationState.REJECTED: bypasses.append("sql dump case variant")
    except Exception:
        pass

    try:
        result = sanitizer.sanitize(_candidate({"message": "safe", "tags": {"Player_ID": "123"}}))
        if result.state != SanitizationState.REJECTED: bypasses.append("sensitive key name bypass (Player_ID)")
    except Exception:
        pass

    try:
        result = sanitizer.sanitize(_candidate({"message": "safe", "contexts": {"backend": {"my_secret_token": "abc"}}}))
        if result.state != SanitizationState.REJECTED: bypasses.append("sensitive key name bypass (my_secret_token)")
    except Exception:
        pass

    try:
        result = sanitizer.sanitize(_candidate({"message": "Error in url encoded resources%2Fbank%2Fserver.cfg"}))
        if result.state != SanitizationState.REJECTED: bypasses.append("url encoded resources path")
    except Exception:
        pass

    try:
        result = sanitizer.sanitize(_candidate({"message": "Error in url encoded txdata%5Cdefault"}))
        if result.state != SanitizationState.REJECTED: bypasses.append("url encoded txData path")
    except Exception:
        pass

    assert not bypasses, f"Project data bypasses: {bypasses}"

def test_adversarial_allowlist_evasion():
    sanitizer = DeterministicTelemetrySanitizer()
    
    evasions = []
    
    # Non-atlas event type
    try:
        result = sanitizer.sanitize(_candidate({"message": "safe"}, event_type="fivem.server.crash"))
        if result.state != SanitizationState.REJECTED: evasions.append("non-atlas event type")
    except Exception:
        pass
        
    # Extra payload keys
    try:
        result = sanitizer.sanitize(_candidate({"message": "safe", "extra_key": "value"}))
        if result.state != SanitizationState.REJECTED: evasions.append("extra payload key")
    except Exception:
        pass
        
    # Nested structures smuggling data
    try:
        result = sanitizer.sanitize(_candidate({"message": "safe", "contexts": {"backend": {"smuggled": {"nested": "value"}}}}))
        if result.state != SanitizationState.REJECTED: evasions.append("nested structure in contexts")
    except Exception:
        pass

    assert not evasions, f"Allowlist evasions: {evasions}"

def test_legitimate_event_passes():
    sanitizer = DeterministicTelemetrySanitizer()
    payload = {
        "message": "Connection timeout",
        "exception": {"type": "TimeoutError", "value": "Timeout connecting to backend", "module": "asyncio"},
        "tags": {"backend_subsystem": "backend"},
        "contexts": {"backend": {"component": "api"}}
    }
    result = sanitizer.sanitize(_candidate(payload))
    assert result.state == SanitizationState.ALLOWED
    assert result.sanitized_payload is not None
