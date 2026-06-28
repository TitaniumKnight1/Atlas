from __future__ import annotations

from pathlib import Path

from backend.domain.pathway2.normalization import plan_repo_normalization, redact_unified_diff
from backend.adapters.config.validator import unified_diff


def test_plan_repo_normalization_preserves_ensure_list() -> None:
    content = (
        'endpoint_add_udp "0.0.0.0:30120"\n'
        'endpoint_add_tcp "0.0.0.0:30120"\n'
        'sv_licenseKey "cfxk_test_key"\n'
        "ensure qb-core\n"
        "ensure qb-policejob\n"
    )
    normalized, overlay, meta = plan_repo_normalization(content)
    assert "ensure qb-core" in normalized
    assert "ensure qb-policejob" in normalized
    assert "endpoint_add_udp" not in normalized
    assert "endpoint_add_udp" in overlay
    assert meta["endpoints_moved"]
    assert "exec server.cfg.local" in normalized


def test_redact_unified_diff_masks_secret_values() -> None:
    before = 'sv_licenseKey "cfxk_test_production_key_value_123456"\n'
    after = 'sv_licenseKey "CHANGE_ME"\n'
    diff = redact_unified_diff(unified_diff(before, after, "server.cfg"))
    assert "cfxk_test_production_key_value_123456" not in diff
    assert "CHANGE_ME" in diff
