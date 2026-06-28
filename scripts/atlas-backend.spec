# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Atlas FastAPI sidecar.

Built via scripts/build_backend_sidecar.py. Keeps analysis scoped to the M0a
backend only and excludes unrelated globally-installed packages (e.g. Django)
that can break or bloat the one-file executable on developer machines.
"""

from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent

block_cipher = None

a = Analysis(
    [str(ROOT / "backend" / "atlas_backend" / "__main__.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=[
        "backend",
        "backend.adapters.persistence.sqlite_smoke",
        "backend.api.routers.health",
        "backend.api.schemas.health",
        "backend.atlas_backend.app",
        "backend.infrastructure.build_config_generated",
        "backend.infrastructure.sentry_dsn",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "django",
        "psycopg2",
        "matplotlib",
        "numpy",
        "pandas",
        "PIL",
        "tkinter",
    ],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="atlas-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
