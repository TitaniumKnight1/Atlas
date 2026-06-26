"""Generate minimal placeholder icons required by Tauri on Windows."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ICONS_DIR = ROOT / "src-tauri" / "icons"


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)


def write_png(path: Path, width: int, height: int, rgb: tuple[int, int, int] = (68, 111, 255)) -> None:
    raw = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))
    compressed = zlib.compress(raw, 9)
    png = b"\x89PNG\r\n\x1a\n"
    png += _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += _png_chunk(b"IDAT", compressed)
    png += _png_chunk(b"IEND", b"")
    path.write_bytes(png)


def write_ico_from_png(path: Path, png_bytes: bytes) -> None:
    # ICO container with a single PNG image (supported on modern Windows).
    header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(png_bytes), 22)
    path.write_bytes(header + entry + png_bytes)


def main() -> None:
    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    write_png(ICONS_DIR / "32x32.png", 32, 32)
    write_png(ICONS_DIR / "128x128.png", 128, 128)
    write_png(ICONS_DIR / "128x128@2x.png", 256, 256)
    icon_png = (ICONS_DIR / "32x32.png").read_bytes()
    write_ico_from_png(ICONS_DIR / "icon.ico", icon_png)
    print(f"Generated Tauri icons in {ICONS_DIR}")


if __name__ == "__main__":
    main()
