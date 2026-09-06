"""Generate FunkBot.ico (and .png) — the app icon for the Windows build.

Pure Python: no Pillow, no ImageMagick, no network. Draws the FunkBot mark —
HUD ring, dark visor well, glowing green eye — supersampled 4x, then writes a
PNG and wraps it in an ICO (Vista+ ICOs may hold PNG payloads directly).

    python make_icon.py            -> FunkBot.ico + FunkBot.png
"""

from __future__ import annotations

import math
import pathlib
import struct
import zlib

SIZE = 256
SS = 4                      # supersampling factor
GREEN = (43, 255, 158)
PURPLE = (160, 108, 255)
WELL = (10, 13, 18)

ROOT = pathlib.Path(__file__).resolve().parent

# Ring arcs: (radius, thickness, colour, start°, sweep°)
ARCS = [
    (0.92, 0.030, GREEN,  200, 120), (0.92, 0.030, GREEN, 340, 90),
    (0.92, 0.030, GREEN,   80,  60),
    (0.80, 0.018, PURPLE, 150,  70), (0.80, 0.018, PURPLE, 300, 55),
    (0.70, 0.045, GREEN,   20,  40),
]


def _blend(dst: list[int], i: int, rgb: tuple[int, int, int], a: float) -> None:
    for c in range(3):
        dst[i + c] = int(dst[i + c] * (1 - a) + rgb[c] * a)
    dst[i + 3] = int(dst[i + 3] + (255 - dst[i + 3]) * a)


def render() -> bytes:
    """RGBA bytes, SIZE x SIZE."""
    px = [0] * (SIZE * SIZE * 4)
    centre = SIZE / 2
    step = 1.0 / SS
    weight = 1.0 / (SS * SS)

    for y in range(SIZE):
        for x in range(SIZE):
            idx = (y * SIZE + x) * 4
            hits: dict[tuple, float] = {}

            for sy in range(SS):
                for sx in range(SS):
                    px_x = x + (sx + 0.5) * step - centre
                    px_y = y + (sy + 0.5) * step - centre
                    r = math.hypot(px_x, px_y) / centre
                    ang = math.degrees(math.atan2(px_y, px_x)) % 360

                    if r < 0.60:                                   # visor well
                        hits[WELL] = hits.get(WELL, 0) + weight
                    if 0.58 < r < 0.62:                            # well rim
                        hits[GREEN] = hits.get(GREEN, 0) + weight * 0.5

                    for rad, thick, colour, start, sweep in ARCS:
                        if abs(r - rad) < thick and \
                                ((ang - start) % 360) <= sweep:
                            hits[colour] = hits.get(colour, 0) + weight

                    # the eye: bright core, soft halo, sitting right of centre
                    ex, ey = px_x - centre * 0.22, px_y + centre * 0.06
                    er = math.hypot(ex, ey) / centre
                    if er < 0.055:
                        hits[(240, 255, 246)] = hits.get((240, 255, 246), 0) + weight
                    elif er < 0.115:
                        hits[GREEN] = hits.get(GREEN, 0) + weight
                    elif er < 0.175:
                        hits[GREEN] = hits.get(GREEN, 0) + weight * 0.30

            for colour, alpha in hits.items():
                _blend(px, idx, colour, min(1.0, alpha))

    return bytes(px)


def write_png(rgba: bytes, path: pathlib.Path) -> bytes:
    rows = b"".join(b"\x00" + rgba[y * SIZE * 4:(y + 1) * SIZE * 4] for y in range(SIZE))

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", SIZE, SIZE, 8, 6, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(rows, 9))
           + chunk(b"IEND", b""))
    path.write_bytes(png)
    return png


def write_ico(png: bytes, path: pathlib.Path) -> None:
    # ICONDIR + one ICONDIRENTRY pointing at the PNG payload.
    header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(png), 6 + 16)
    path.write_bytes(header + entry + png)


def main() -> None:
    rgba = render()
    png = write_png(rgba, ROOT / "FunkBot.png")
    write_ico(png, ROOT / "FunkBot.ico")
    print(f"wrote FunkBot.png and FunkBot.ico ({len(png)} bytes, {SIZE}x{SIZE})")


if __name__ == "__main__":
    main()
