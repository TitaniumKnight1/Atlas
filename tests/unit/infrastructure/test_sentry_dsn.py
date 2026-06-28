from __future__ import annotations

import sys
import types

import pytest

from backend.infrastructure.sentry_dsn import resolve_sentry_dsn


@pytest.fixture(autouse=True)
def clear_generated_module() -> None:
    sys.modules.pop("backend.infrastructure.build_config_generated", None)
    yield
    sys.modules.pop("backend.infrastructure.build_config_generated", None)


def test_resolve_returns_none_without_baked_or_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ATLAS_SENTRY_DSN", raising=False)
    assert resolve_sentry_dsn() == ""


def test_resolve_uses_env_when_no_baked_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_SENTRY_DSN", "https://env@example.com/1")
    assert resolve_sentry_dsn() == "https://env@example.com/1"


def test_resolve_prefers_baked_dsn_over_env(monkeypatch: pytest.MonkeyPatch) -> None:
    module = types.ModuleType("backend.infrastructure.build_config_generated")
    module.BAKED_SENTRY_DSN = "https://baked@example.com/1"
    sys.modules["backend.infrastructure.build_config_generated"] = module
    monkeypatch.setenv("ATLAS_SENTRY_DSN", "https://env@example.com/2")
    assert resolve_sentry_dsn() == "https://baked@example.com/1"
