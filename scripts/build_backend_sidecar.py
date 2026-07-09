from __future__ import annotations

import os
import platform
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC_FILE = ROOT / "scripts" / "atlas-backend.spec"
BINARIES_DIR = ROOT / "src-tauri" / "binaries"
STALE_ROOT_SPEC = ROOT / "atlas-backend.spec"
RUNTIME_REQUIREMENTS = ROOT / "backend" / "requirements.txt"
SIDECAR_VENV = ROOT / "build" / "sidecar-venv"


def resolve_target_triple() -> str:
    """Return the Tauri/Cargo target triple for the sidecar being bundled."""
    for env_var in ("TAURI_TARGET_TRIPLE", "CARGO_BUILD_TARGET"):
        value = os.environ.get(env_var, "").strip()
        if value:
            return value

    try:
        completed = subprocess.run(
            ["rustc", "--print", "host-tuple"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return _fallback_host_triple()


def sidecar_binary_path(target_triple: str | None = None) -> Path:
    triple = target_triple or resolve_target_triple()
    extension = ".exe" if sys.platform == "win32" else ""
    return BINARIES_DIR / f"atlas-backend-{triple}{extension}"


def _sidecar_venv_python() -> Path:
    if sys.platform == "win32":
        return SIDECAR_VENV / "Scripts" / "python.exe"
    return SIDECAR_VENV / "bin" / "python"


def _ensure_sidecar_build_env() -> Path:
    """Create an isolated venv with Atlas runtime deps + PyInstaller only."""
    python = _sidecar_venv_python()
    if not python.is_file():
        print(f"Creating isolated sidecar build venv at {SIDECAR_VENV}")
        SIDECAR_VENV.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([sys.executable, "-m", "venv", str(SIDECAR_VENV)], cwd=ROOT, check=True)

    subprocess.run(
        [str(python), "-m", "pip", "install", "--upgrade", "pip"],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "-r",
            str(RUNTIME_REQUIREMENTS),
            "pyinstaller>=6.11.0",
            "pyinstaller-hooks-contrib>=2024.10",
        ],
        cwd=ROOT,
        check=True,
    )
    print(f"Sidecar build uses isolated venv: {python}")
    return python


def _install_sidecar_for_local_targets(built_binary: Path) -> None:
    """Mirror the sidecar next to local Cargo outputs for `tauri dev`."""
    extension = ".exe" if sys.platform == "win32" else ""
    target_root = ROOT / "src-tauri" / "target"
    if not target_root.is_dir():
        return

    for profile in ("debug", "release"):
        profile_dir = target_root / profile
        if not profile_dir.is_dir():
            continue
        dest_dir = profile_dir / "binaries"
        dest = dest_dir / f"atlas-backend{extension}"
        _atomic_install_binary(built_binary, dest)


def _atomic_install_binary(source: Path, destination: Path) -> None:
    """Install a built sidecar, replacing an in-use binary when possible (Windows dev runs)."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_name(destination.name + ".new")
    if staging.exists():
        staging.unlink()
    shutil.copy2(source, staging)

    last_error: OSError | None = None
    for attempt in range(12):
        try:
            os.replace(staging, destination)
            return
        except PermissionError as error:
            last_error = error
            if attempt == 0:
                _try_stop_locked_sidecar()
            time.sleep(0.5)

    if staging.exists():
        try:
            staging.unlink()
        except OSError:
            pass

    raise RuntimeError(
        f"Could not install sidecar at {destination} because the file is in use. "
        "Close Atlas (and any atlas-backend.exe processes), then re-run `npm run sidecar:build`."
    ) from last_error


def _try_stop_locked_sidecar() -> None:
    if sys.platform != "win32":
        return
    print("Stopping running atlas-backend sidecar so the new build can be installed...")
    subprocess.run(
        ["taskkill", "/F", "/IM", "atlas-backend.exe", "/T"],
        capture_output=True,
        text=True,
        check=False,
    )


def _load_release_env() -> None:
    """Load maintainer-only release secrets from .env.release if present."""
    release_env = ROOT / ".env.release"
    if not release_env.is_file():
        return
    for line in release_env.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _write_build_config(dsn: str) -> None:
    generated = ROOT / "backend" / "infrastructure" / "build_config_generated.py"
    generated.write_text(
        '"""AUTO-GENERATED by scripts/build_backend_sidecar.py — DO NOT COMMIT."""\n'
        f"BAKED_SENTRY_DSN = {dsn!r}\n",
        encoding="utf-8",
    )


def main() -> None:
    if not SPEC_FILE.is_file():
        raise RuntimeError(f"Missing PyInstaller spec: {SPEC_FILE}")
    if not RUNTIME_REQUIREMENTS.is_file():
        raise RuntimeError(f"Missing runtime requirements: {RUNTIME_REQUIREMENTS}")

    target_triple = resolve_target_triple()
    output_path = sidecar_binary_path(target_triple)

    BINARIES_DIR.mkdir(parents=True, exist_ok=True)
    if STALE_ROOT_SPEC.exists():
        STALE_ROOT_SPEC.unlink()

    _load_release_env()
    build_dsn = os.environ.get("ATLAS_SENTRY_DSN", "").strip()
    _write_build_config(build_dsn)
    if build_dsn:
        print("Baked maintainer Sentry DSN into sidecar build config.")
    else:
        print("No ATLAS_SENTRY_DSN in build environment; sidecar will have no baked DSN.")

    build_python = _ensure_sidecar_build_env()

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)

    subprocess.run(
        [
            str(build_python),
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            str(SPEC_FILE),
        ],
        cwd=ROOT,
        env=env,
        check=True,
    )

    built_binary = ROOT / "dist" / f"atlas-backend{'.exe' if sys.platform == 'win32' else ''}"
    _atomic_install_binary(built_binary, output_path)
    _install_sidecar_for_local_targets(built_binary)
    if sys.platform != "win32":
        output_path.chmod(output_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    print(f"Built backend sidecar for {target_triple}: {output_path}")


def _fallback_host_triple() -> str:
    machine = platform.machine().lower()
    is_arm64 = machine in {"arm64", "aarch64"}

    if sys.platform == "win32":
        return "aarch64-pc-windows-msvc" if is_arm64 else "x86_64-pc-windows-msvc"
    if sys.platform == "darwin":
        return "aarch64-apple-darwin" if is_arm64 else "x86_64-apple-darwin"
    if sys.platform.startswith("linux"):
        return "aarch64-unknown-linux-gnu" if is_arm64 else "x86_64-unknown-linux-gnu"

    raise RuntimeError("Unable to infer Tauri sidecar target triple")


if __name__ == "__main__":
    main()
