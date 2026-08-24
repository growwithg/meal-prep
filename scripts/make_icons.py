#!/usr/bin/env python3
"""Render the app icons. Hand-rolled PNG writer so the build needs no image library."""
import zlib, struct, math
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "app" / "icons"


def png(path, size, pixels):
    raw = b"".join(b"\x00" + bytes(pixels[y * size * 4:(y + 1) * size * 4]) for y in range(size))
    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b""))


def mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def coverage(d, edge=1.2):
    """Signed distance -> antialiased alpha. Negative distance is inside."""
    return max(0.0, min(1.0, 0.5 - d / edge))


def over(dst, src, alpha):
    return tuple(round(src[i] * alpha + dst[i] * (1 - alpha)) for i in range(3))


def render(size):
    s = size
    top, bottom = (0x34, 0xC7, 0x59), (0x0A, 0x84, 0xC1)   # green -> blue
    r = s * 0.2237                                          # iOS squircle-ish corner
    cx = s / 2
    px = bytearray(s * s * 4)

    bowl_cy, bowl_r = s * 0.615, s * 0.270
    rim_hw, rim_hh = bowl_r * 1.10, s * 0.020
    rim_cy = bowl_cy - s * 0.010
    # three staggered steam strokes rising off the bowl
    steam = [(cx - s * 0.135, s * 0.300, s * 0.155),
             (cx,             s * 0.245, s * 0.205),
             (cx + s * 0.135, s * 0.300, s * 0.155)]
    steam_w = s * 0.028

    for y in range(s):
        for x in range(s):
            fx, fy = x + 0.5, y + 0.5
            # rounded-square mask
            qx, qy = abs(fx - cx) - (s / 2 - r), abs(fy - cx) - (s / 2 - r)
            d = math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - r
            a = coverage(d)
            if a <= 0:
                continue

            col = mix(top, bottom, fy / s)
            # specular sheen across the upper third, the "glass" cue
            sheen = max(0.0, 1 - abs(fy - s * 0.24) / (s * 0.30)) * max(0.0, 1 - abs(fx - cx) / (s * 0.75))
            col = mix(col, (255, 255, 255), sheen * 0.28)

            # bowl: the lower half of a disc
            if fy >= rim_cy:
                db = math.hypot(fx - cx, fy - bowl_cy) - bowl_r
                col = over(col, (255, 255, 255), coverage(db) * 0.97)
            # flat rim across the top of the bowl, corners rounded
            rq = math.hypot(max(abs(fx - cx) - (rim_hw - rim_hh), 0),
                            max(abs(fy - rim_cy) - 0, 0)) - rim_hh
            col = over(col, (255, 255, 255), coverage(rq) * 0.97)

            # steam
            for sx, sy, sh in steam:
                sq = math.hypot(max(abs(fx - sx) - 0, 0),
                                max(abs(fy - (sy + sh / 2)) - (sh / 2 - steam_w), 0)) - steam_w
                al = coverage(sq)
                if al > 0:
                    col = over(col, (255, 255, 255), al * 0.80)

            i = (y * s + x) * 4
            px[i:i + 4] = bytes((*col, round(a * 255)))
    return px


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, size in (("icon-192.png", 192), ("icon-512.png", 512), ("apple-touch-icon.png", 180)):
        png(OUT / name, size, render(size))
        print("wrote", (OUT / name).relative_to(OUT.parent.parent))


if __name__ == "__main__":
    main()
