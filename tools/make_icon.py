"""Regenerate icon.ico (exe + installer icon) and docs/logo.png from the logo
drawing code in ui_icons.render_logo, so every rendition of the logo comes
from one source.

    python tools/make_icon.py

icon.ico holds every LOGO_SIZES rendition: 32-bit BMP entries below 256px
(what Explorer and the shell prefer for small sizes) and a PNG entry at 256.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import QBuffer, QIODevice  # noqa: E402
from PyQt6.QtGui import QGuiApplication, QImage  # noqa: E402

from ui_icons import LOGO_SIZES, render_logo  # noqa: E402


def _png_bytes(img: QImage) -> bytes:
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def _bmp_entry(img: QImage) -> bytes:
    """ICO-style DIB: BITMAPINFOHEADER with doubled height, bottom-up BGRA
    pixels, then the 1-bpp AND mask (set where fully transparent)."""
    img = img.convertToFormat(QImage.Format.Format_ARGB32)  # BGRA in memory
    w, h = img.width(), img.height()
    raw = img.constBits().asstring(img.sizeInBytes())
    stride = img.bytesPerLine()
    rows = [raw[y * stride: y * stride + w * 4] for y in range(h)]
    mask_stride = ((w + 31) // 32) * 4
    mask_rows = []
    for row in rows:
        bits = bytearray(mask_stride)
        for x in range(w):
            if row[x * 4 + 3] == 0:
                bits[x // 8] |= 0x80 >> (x % 8)
        mask_rows.append(bytes(bits))
    pixels = b"".join(reversed(rows))
    mask = b"".join(reversed(mask_rows))
    header = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0,
                         len(pixels) + len(mask), 0, 0, 0, 0)
    return header + pixels + mask


def build_ico(sizes=LOGO_SIZES) -> bytes:
    images = []
    for size in sizes:
        img = render_logo(size)
        data = _png_bytes(img) if size >= 256 else _bmp_entry(img)
        images.append((size, data))
    out = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for size, data in images:
        dim = 0 if size >= 256 else size  # 0 means 256 in ICONDIRENTRY
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32,
                               len(data), offset)
        blobs += data
        offset += len(data)
    return out + entries + blobs


def main() -> int:
    _app = QGuiApplication(sys.argv)  # noqa: F841 — QPainter needs one
    ico = ROOT / "icon.ico"
    ico.write_bytes(build_ico())
    logo = ROOT / "docs" / "logo.png"
    logo.parent.mkdir(exist_ok=True)
    render_logo(256).save(str(logo), "PNG")
    print(f"wrote {ico} and {logo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
