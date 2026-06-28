from __future__ import annotations

import os


def _load_baked_sentry_dsn() -> str:
    try:
        from backend.infrastructure.build_config_generated import BAKED_SENTRY_DSN
    except ImportError:
        return ""
    return str(BAKED_SENTRY_DSN).strip()


def resolve_sentry_dsn() -> str:
    """Resolve the Sentry DSN: baked build constant, then env override, else none."""
    baked = _load_baked_sentry_dsn()
    if baked:
        return baked
    return os.environ.get("ATLAS_SENTRY_DSN", "").strip()
