from __future__ import annotations

import sys
import types

import pytest


@pytest.fixture(autouse=True)
def isolate_baked_sentry_dsn() -> None:
    """Block gitignored build_config_generated.py from leaking a real DSN into tests."""
    module = types.ModuleType("backend.infrastructure.build_config_generated")
    module.BAKED_SENTRY_DSN = ""
    sys.modules["backend.infrastructure.build_config_generated"] = module
    yield
    sys.modules.pop("backend.infrastructure.build_config_generated", None)
