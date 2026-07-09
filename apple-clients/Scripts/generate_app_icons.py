#!/usr/bin/env python3
"""Generate the Apple app-icon assets for AstralDeep from a single square master.

Feature 053. Zero third-party dependencies (Constitution V): resampling is done by
the Apple toolchain (`sips`); PNG decode/encode, alpha stripping, and the macOS
squircle mask are pure-stdlib.

Why each platform differs (see specs/053-apple-production-release/research.md D15/D17):

* iOS / watchOS  — a SINGLE 1024x1024 square PNG. The system masks the corners
  (rounded-rect on iOS, circle on watchOS), so the artwork must be full-bleed and
  must NOT bake in rounding. It MUST be fully opaque: an alpha channel fails App
  Store validation with ITMS-90717 ("The App Store Icon ... can't be transparent
  nor contain an alpha channel").

* macOS — the classic `AppIcon.appiconset` workflow does NOT mask. Each of the ten
  slots (16/32/128/256/512 at @1x and @2x) must therefore supply the rounded-rect
  shape itself, inset inside a transparent gutter. Apple's macOS icon grid puts an
  824x824 body on the 1024 canvas (a ~100px gutter on each side) with a ~185.4px
  continuous-corner radius. Transparency is expected here and is not an ITMS-90717
  violation (that rule governs the iOS/watchOS App Store icon slot).

Usage:
    python3 apple-clients/Scripts/generate_app_icons.py [--master PATH] [--check]

`--check` verifies the emitted assets satisfy the invariants (sizes, and that the
iOS/watch 1024 icons carry no alpha channel) and exits non-zero on violation.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import struct
import subprocess
import sys
import tempfile
import zlib

REPO = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_MASTER = REPO / "android-client" / "Android Raw Assets" / "AppIcon.png"
APP_ICONSET = REPO / "apple-clients/AstralApp/AstralApp/Assets.xcassets/AppIcon.appiconset"
WATCH_ICONSET = REPO / "apple-clients/AstralWatch/Assets.xcassets/AppIcon.appiconset"

# Apple macOS icon grid, expressed on the 1024 canvas.
MAC_CANVAS = 1024
MAC_BODY = 824
MAC_RADIUS = 185.4
# Continuous-corner ("squircle") exponent. n=2 is a circular corner; Apple's
# continuous corners sit near 4-5. 4.0 tracks the shipped shape closely.
SQUIRCLE_N = 4.0

# (size, scale) -> emitted pixel size, for the ten classic macOS slots.
MAC_SLOTS = [
    (16, 1, 16), (16, 2, 32),
    (32, 1, 32), (32, 2, 64),
    (128, 1, 128), (128, 2, 256),
    (256, 1, 256), (256, 2, 512),
    (512, 1, 512), (512, 2, 1024),
]


# ---------------------------------------------------------------- PNG codec

def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def read_png(path: pathlib.Path) -> tuple[int, int, int, bytearray]:
    """Return (width, height, channels, pixel bytes). Channels is 3 (RGB) or 4 (RGBA)."""
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path}: not a PNG")
    pos, idat = 8, b""
    width = height = depth = ctype = None
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        ctag = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        if ctag == b"IHDR":
            width, height, depth, ctype = struct.unpack(">IIBB", chunk[:10])
        elif ctag == b"IDAT":
            idat += chunk
        elif ctag == b"IEND":
            break
        pos += 12 + length
    if depth != 8 or ctype not in (2, 6):
        raise ValueError(f"{path}: need 8-bit RGB/RGBA, got depth={depth} colortype={ctype}")
    channels = 4 if ctype == 6 else 3
    raw = zlib.decompress(idat)
    stride = width * channels
    out = bytearray(stride * height)
    prev = bytearray(stride)
    pos = 0
    for y in range(height):
        filt = raw[pos]; pos += 1
        line = bytearray(raw[pos:pos + stride]); pos += stride
        if filt:
            for i in range(stride):
                a = line[i - channels] if i >= channels else 0
                b = prev[i]
                c = prev[i - channels] if i >= channels else 0
                if filt == 1:
                    line[i] = (line[i] + a) & 0xFF
                elif filt == 2:
                    line[i] = (line[i] + b) & 0xFF
                elif filt == 3:
                    line[i] = (line[i] + ((a + b) >> 1)) & 0xFF
                elif filt == 4:
                    line[i] = (line[i] + _paeth(a, b, c)) & 0xFF
                else:
                    raise ValueError(f"{path}: bad filter {filt}")
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return width, height, channels, out


def write_png(path: pathlib.Path, width: int, height: int, channels: int, px: bytearray) -> None:
    ctype = 6 if channels == 4 else 2
    stride = width * channels
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter: none
        raw += px[y * stride:(y + 1) * stride]

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, ctype, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


def sips_resize(src: pathlib.Path, dst: pathlib.Path, size: int) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["sips", "-s", "format", "png", "--resampleHeightWidth", str(size), str(size),
         str(src), "--out", str(dst)],
        check=True, capture_output=True,
    )


# ---------------------------------------------------------------- transforms

def strip_alpha(width: int, height: int, channels: int, px: bytearray) -> bytearray:
    """Drop the alpha channel. Refuses to silently composite real transparency."""
    if channels == 3:
        return px
    alphas = px[3::4]
    if min(alphas) != 255:
        raise ValueError(
            "master has real transparency; flatten onto an opaque background first "
            f"(min alpha={min(alphas)}). The App Store icon must be fully opaque (ITMS-90717)."
        )
    return bytearray(b for i, b in enumerate(px) if i % 4 != 3)


def _coverage(dx: float, dy: float, r: float, n: float, samples: int = 4) -> float:
    """Antialiased superellipse coverage for a corner pixel at (dx, dy) from the corner centre."""
    hit = 0
    step = 1.0 / samples
    for sy in range(samples):
        yy = dy + (sy + 0.5) * step
        for sx in range(samples):
            xx = dx + (sx + 0.5) * step
            if xx <= 0 or yy <= 0:
                hit += 1
                continue
            if (xx / r) ** n + (yy / r) ** n <= 1.0:
                hit += 1
    return hit / (samples * samples)


def squircle_alpha(size: int, radius: float, n: float) -> bytearray:
    """Alpha mask (0..255) for a `size` square with continuous-corner rounding."""
    mask = bytearray(b"\xff" * (size * size))
    r = radius
    for y in range(size):
        # distance into the corner band, vertically
        if y < r:
            cy = r - y - 0.5
        elif y >= size - r:
            cy = y - (size - r) + 0.5
        else:
            continue  # middle band: fully opaque row
        for x in range(size):
            if x < r:
                cx = r - x - 0.5
            elif x >= size - r:
                cx = x - (size - r) + 0.5
            else:
                continue  # middle band: fully opaque
            cov = _coverage(cx - 0.5, cy - 0.5, r, n)
            mask[y * size + x] = int(round(cov * 255))
    return mask


def build_mac_canvas(body_png: pathlib.Path) -> tuple[int, int, int, bytearray]:
    """Place the masked 824 body, centred, on a transparent 1024 canvas."""
    bw, bh, bch, bpx = read_png(body_png)
    if (bw, bh) != (MAC_BODY, MAC_BODY):
        raise ValueError(f"expected {MAC_BODY}x{MAC_BODY} body, got {bw}x{bh}")
    mask = squircle_alpha(MAC_BODY, MAC_RADIUS, SQUIRCLE_N)
    canvas = bytearray(MAC_CANVAS * MAC_CANVAS * 4)  # zeroed => transparent
    off = (MAC_CANVAS - MAC_BODY) // 2
    for y in range(MAC_BODY):
        drow = ((y + off) * MAC_CANVAS + off) * 4
        srow = y * MAC_BODY * bch
        mrow = y * MAC_BODY
        for x in range(MAC_BODY):
            s = srow + x * bch
            d = drow + x * 4
            canvas[d] = bpx[s]
            canvas[d + 1] = bpx[s + 1]
            canvas[d + 2] = bpx[s + 2]
            canvas[d + 3] = mask[mrow + x]
    return MAC_CANVAS, MAC_CANVAS, 4, canvas


# ---------------------------------------------------------------- catalogs

def write_app_contents() -> None:
    images = [
        {"filename": "AppIcon-1024.png", "idiom": "universal", "platform": "ios", "size": "1024x1024"},
        {"appearances": [{"appearance": "luminosity", "value": "dark"}],
         "filename": "AppIcon-1024-dark.png", "idiom": "universal", "platform": "ios",
         "size": "1024x1024"},
    ]
    for size, scale, px in MAC_SLOTS:
        images.append({
            "filename": f"mac-{size}x{size}@{scale}x.png",
            "idiom": "mac", "scale": f"{scale}x", "size": f"{size}x{size}",
        })
    (APP_ICONSET / "Contents.json").write_text(
        json.dumps({"images": images, "info": {"author": "xcode", "version": 1}}, indent=2) + "\n"
    )


def write_watch_contents() -> None:
    payload = {
        "images": [{"filename": "AppIcon-1024.png", "idiom": "universal",
                    "platform": "watchos", "size": "1024x1024"}],
        "info": {"author": "xcode", "version": 1},
    }
    WATCH_ICONSET.mkdir(parents=True, exist_ok=True)
    (WATCH_ICONSET / "Contents.json").write_text(json.dumps(payload, indent=2) + "\n")
    root = WATCH_ICONSET.parent / "Contents.json"
    if not root.exists():
        root.write_text(json.dumps({"info": {"author": "xcode", "version": 1}}, indent=2) + "\n")


# ---------------------------------------------------------------- driver

def generate(master: pathlib.Path) -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)

        # --- iOS + watchOS: one opaque, full-bleed 1024 square (system masks it).
        base = tmp / "base-1024.png"
        sips_resize(master, base, 1024)
        w, h, ch, px = read_png(base)
        rgb = strip_alpha(w, h, ch, px)
        for target in (APP_ICONSET / "AppIcon-1024.png",
                       APP_ICONSET / "AppIcon-1024-dark.png",
                       WATCH_ICONSET / "AppIcon-1024.png"):
            write_png(target, w, h, 3, rgb)
        print(f"  ios/watch  1024x1024 opaque  -> 3 files")

        # --- macOS: rounded-rect body inside a transparent gutter, ten slots.
        body = tmp / "body-824.png"
        sips_resize(master, body, MAC_BODY)
        cw, chh, cch, cpx = build_mac_canvas(body)
        mac1024 = tmp / "mac-1024.png"
        write_png(mac1024, cw, chh, cch, cpx)
        for size, scale, pxsize in MAC_SLOTS:
            out = APP_ICONSET / f"mac-{size}x{size}@{scale}x.png"
            if pxsize == MAC_CANVAS:
                write_png(out, cw, chh, cch, cpx)
            else:
                sips_resize(mac1024, out, pxsize)
        print(f"  macOS      squircle + gutter -> {len(MAC_SLOTS)} files")

    write_app_contents()
    write_watch_contents()
    print("  Contents.json wired for AstralApp + AstralWatch")


def check() -> int:
    problems: list[str] = []
    for p, size in [(APP_ICONSET / "AppIcon-1024.png", 1024),
                    (APP_ICONSET / "AppIcon-1024-dark.png", 1024),
                    (WATCH_ICONSET / "AppIcon-1024.png", 1024)]:
        if not p.exists():
            problems.append(f"missing {p}")
            continue
        w, h, ch, _ = read_png(p)
        if (w, h) != (size, size):
            problems.append(f"{p.name}: {w}x{h} != {size}x{size}")
        if ch != 3:
            problems.append(f"{p.name}: has an alpha channel (ITMS-90717); must be opaque RGB")
    for size, scale, pxsize in MAC_SLOTS:
        p = APP_ICONSET / f"mac-{size}x{size}@{scale}x.png"
        if not p.exists():
            problems.append(f"missing {p}")
            continue
        w, h, ch, _ = read_png(p)
        if (w, h) != (pxsize, pxsize):
            problems.append(f"{p.name}: {w}x{h} != {pxsize}x{pxsize}")
        if ch != 4:
            problems.append(f"{p.name}: macOS slot must keep its transparent gutter (RGBA)")
    for msg in problems:
        print(f"  FAIL {msg}", file=sys.stderr)
    if problems:
        return 1
    print("  OK: sizes correct; iOS/watch icons opaque; macOS slots retain the gutter")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--master", type=pathlib.Path, default=DEFAULT_MASTER)
    ap.add_argument("--check", action="store_true", help="verify emitted assets, don't regenerate")
    args = ap.parse_args()
    if args.check:
        return check()
    if not args.master.exists():
        print(f"master not found: {args.master}", file=sys.stderr)
        return 2
    print(f"master: {args.master}")
    generate(args.master)
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
