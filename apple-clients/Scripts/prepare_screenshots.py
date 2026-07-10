#!/usr/bin/env python3
"""Feature 053 - normalize captured screenshots into App Store Connect uploads.

App Store Connect is strict about screenshots in two ways that raw captures
violate:

  1. **No alpha.** Screenshots must be flattened RGB. Every capture macOS and
     the Simulator produce is RGBA (colour type 6), so ASC rejects them even
     though the alpha channel is uniformly opaque.
  2. **Exact pixel sizes.** Each device class accepts a small fixed set of
     dimensions. The Simulator captures already land on an accepted size; a Mac
     window capture lands on whatever the operator's display can render, which
     is essentially never one of the four accepted 16:10 Mac sizes.

So this script:

  * decodes each PNG (stdlib ``zlib`` only - no Pillow, Constitution V),
  * re-encodes it as colour type 2 (truecolour, **no alpha channel**),
  * for classes whose capture size ASC does not accept (Mac, iPhone),
     downscales the capture and centres it on an accepted canvas in a matte
     colour sampled from the capture itself (see MAC_MATTE / IPHONE_MATTE),
  * writes the results in listing order as ``NN-slug.png``, and
  * asserts the exact size / absence of alpha of everything it wrote.

Dropping the alpha channel is *pixel-exact*, not a lossy composite: the script
refuses to run if any source pixel is non-opaque, so "flatten" can never
silently change a colour. See ``--check``.

Usage
-----
    # Regenerate from the operator's capture folder.
    python3 apple-clients/Scripts/prepare_screenshots.py \
        --source "$HOME/Desktop/Work/Astral Screenshots"

    # Re-verify the committed outputs (no sources needed; safe for CI).
    python3 apple-clients/Scripts/prepare_screenshots.py --check
"""

from __future__ import annotations

import argparse
import pathlib
import struct
import subprocess
import sys
import tempfile
import unicodedata
import zlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT_ROOT = REPO_ROOT / "apple-clients" / "AppStore" / "screenshots"

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

# Colour chunks are copied through from the input so the exported pixels keep
# the meaning they were captured with. The Simulator tags sRGB; a Mac capture
# carries an embedded ICC profile (Display P3 on most Macs). Dropping the
# profile would reinterpret P3 pixels as sRGB and over-saturate the whole shot.
# Everything else (eXIf, pHYs, iTXt, iDOT) is capture metadata ASC has no use
# for, and eXIf in particular can carry an orientation flag we do not want.
COLOUR_CHUNKS = (b"iCCP", b"cICP", b"sRGB", b"gAMA", b"cHRM")

# The Mac captures are 2940x1912 (ratio 1.538); the Mac App Store accepts only
# 16:10. Downscaling to fit the 1800px height yields 2768x1800, which is then
# centred on a 2880x1800 canvas -- 56px of matte per side, 1.9% of the width.
#
# The matte is pure black because that is what the capture's own top band
# already is: sampling the resized image's edges gives #000000 across the
# entire top row, #101220 down both sides, #141725 along the bottom. Black
# therefore matches the top seamlessly and sits within ~0x20 of the side edges,
# which is imperceptible on a dark UI. Padding with the side colour instead
# would put a visible notch around the black title band.
MAC_MATTE = (0x00, 0x00, 0x00)

# The iPhone captures come from an iPhone 17 Pro Max (6.9", 1320x2868), but the
# App Store Connect page presents the 6.5" slot (1242x2688 / 1284x2778).
# Scaling to fit the 2778px height gives 1278x2778, centred with 3px of matte
# per side. #0f1221 is the app's own background: sampling both edge columns of
# every capture shows ~75% #0f1221 with a #1a1e2e band -- at 3px, invisible.
IPHONE_MATTE = (0x0F, 0x12, 0x21)


class Klass:
    """One App Store device class."""

    def __init__(self, slug, source_dir, size, inner=None, matte=None):
        self.slug = slug
        self.source_dir = source_dir
        self.size = size  # exact (w, h) ASC must receive
        self.inner = inner  # (w, h) the capture is scaled to before padding
        self.matte = matte  # padding colour when letterboxed

    @property
    def letterboxed(self):
        return self.inner is not None


CLASSES = [
    Klass("iphone-6.5", "iPhone", (1284, 2778), inner=(1278, 2778), matte=IPHONE_MATTE),
    Klass("ipad-13", "iPad", (2064, 2752)),
    Klass("mac", "MacOS", (2880, 1800), inner=(2768, 1800), matte=MAC_MATTE),
    Klass("watch", "Watch", (416, 496)),
]

# Listing order per class, keyed by the ``HH.MM.SS`` stamp in the capture's
# filename (stable across the U+202F narrow no-break space macOS puts before
# "PM", and across the operator renaming the folder).
MANIFEST = {
    "iphone-6.5": [
        ("13.33.56", "dashboard"),
        ("13.34.17", "insights"),
        ("13.35.20", "get-started"),
    ],
    "ipad-13": [
        ("13.39.03", "dashboard"),
        ("13.39.16", "insights"),
        ("13.37.45", "get-started"),
    ],
    "mac": [
        ("1.48.54", "dashboard"),
        ("1.52.07", "growth-plan"),
        ("1.49.20", "schedule"),
        ("1.48.28", "get-started"),
    ],
    "watch": [
        ("13.44.22", "conversations"),
        ("13.44.42", "dashboard"),
        ("13.45.18", "ask-and-speak"),
    ],
}

# Captures deliberately left out of the listing, and why. Kept here rather than
# deleted so the decision survives a re-run.
EXCLUDED = {
    "13.45.05": (
        "watch: shows the watchOS system dictation keyboard, not AstralDeep. "
        "Guideline 2.3.3 wants the app itself in the shot."
    ),
}


# --------------------------------------------------------------------------
# Minimal PNG codec (8-bit, non-interlaced, colour type 2 or 6)
# --------------------------------------------------------------------------


def _iter_chunks(blob):
    i = 8
    while i < len(blob):
        (length,) = struct.unpack(">I", blob[i : i + 4])
        yield blob[i + 4 : i + 8], blob[i + 8 : i + 8 + length]
        i += 12 + length


def read_png(path):
    """Return ``(width, height, rgb_rows, colour_chunks)``; alpha must be opaque."""
    blob = path.read_bytes()
    if blob[:8] != PNG_MAGIC:
        raise SystemExit(f"{path}: not a PNG")

    width, height, depth, colour, _comp, _filt, interlace = struct.unpack(
        ">IIBBBBB", blob[16:29]
    )
    if depth != 8 or colour not in (2, 6) or interlace != 0:
        raise SystemExit(
            f"{path}: unsupported PNG (depth={depth} colour={colour} "
            f"interlace={interlace}); expected 8-bit RGB/RGBA, non-interlaced"
        )

    bpp = 4 if colour == 6 else 3
    idat = b"".join(data for typ, data in _iter_chunks(blob) if typ == b"IDAT")
    colour_chunks = [
        (typ, data) for typ, data in _iter_chunks(blob) if typ in COLOUR_CHUNKS
    ]

    raw = zlib.decompress(idat)
    stride = width * bpp
    expected = height * (stride + 1)
    if len(raw) != expected:
        raise SystemExit(f"{path}: IDAT is {len(raw)} bytes, expected {expected}")

    rows = []
    prev = bytearray(stride)
    pos = 0
    for _y in range(height):
        ftype = raw[pos]
        pos += 1
        line = bytearray(raw[pos : pos + stride])
        pos += stride
        if ftype == 0:
            pass
        elif ftype == 1:
            for x in range(bpp, stride):
                line[x] = (line[x] + line[x - bpp]) & 0xFF
        elif ftype == 2:
            for x in range(stride):
                line[x] = (line[x] + prev[x]) & 0xFF
        elif ftype == 3:
            for x in range(stride):
                left = line[x - bpp] if x >= bpp else 0
                line[x] = (line[x] + ((left + prev[x]) >> 1)) & 0xFF
        elif ftype == 4:
            for x in range(stride):
                a = line[x - bpp] if x >= bpp else 0
                b = prev[x]
                c = prev[x - bpp] if x >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[x] = (line[x] + pred) & 0xFF
        else:
            raise SystemExit(f"{path}: bad filter type {ftype}")
        rows.append(bytes(line))
        prev = line

    if bpp == 3:
        return width, height, rows, colour_chunks

    # Refuse to guess at a background for translucent pixels: if the capture is
    # fully opaque (it always is), dropping the channel is lossless.
    for line in rows:
        if any(a != 255 for a in line[3::4]):
            raise SystemExit(
                f"{path}: has non-opaque pixels; flattening would change colours"
            )

    rgb = []
    for line in rows:
        out = bytearray(width * 3)
        out[0::3] = line[0::4]
        out[1::3] = line[1::4]
        out[2::3] = line[2::4]
        rgb.append(bytes(out))
    return width, height, rgb, colour_chunks


def _chunk(typ, data):
    return (
        struct.pack(">I", len(data))
        + typ
        + data
        + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
    )


def write_png_rgb(path, width, height, rows, colour_chunks=()):
    """Write colour type 2 (RGB, no alpha)."""
    # Filter 0 (None) on every scanline. The adaptive filters buy maybe 30% on
    # flat dark UI captures and cost a per-byte Python loop over ~15M bytes;
    # ASC does not care about file size and neither does the repo.
    raw = bytearray()
    for line in rows:
        raw.append(0)
        raw += line

    out = bytearray(PNG_MAGIC)
    out += _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    for typ, data in colour_chunks:
        out += _chunk(typ, data)
    out += _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    out += _chunk(b"IEND", b"")
    path.write_bytes(bytes(out))


def png_header(path):
    """Cheap ``(width, height, colour_type)`` probe - no pixel decode."""
    blob = path.read_bytes()
    if blob[:8] != PNG_MAGIC:
        raise SystemExit(f"{path}: not a PNG")
    width, height, _d, colour, _c, _f, _i = struct.unpack(">IIBBBBB", blob[16:29])
    return width, height, colour


# --------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------


def time_key(name):
    """``Screenshot 2026-07-09 at 1.48.54<U+202F>PM.png`` -> ``1.48.54``.

    NFKC folds the U+202F narrow no-break space macOS wedges in before "PM"
    into a plain space, so the stamp survives a naive split. The extension is
    stripped first, or ``13.33.56.png`` tokenizes into four parts, not three.
    """
    stem = unicodedata.normalize("NFKC", pathlib.PurePath(name).stem)
    for token in stem.replace("-", " ").split():
        parts = token.split(".")
        if len(parts) == 3 and all(p.isdigit() for p in parts):
            return token
    return ""


def pad_centre(rows, width, height, out_w, out_h, matte):
    if width > out_w or height > out_h:
        raise SystemExit(f"cannot pad {width}x{height} up to {out_w}x{out_h}")
    left = (out_w - width) // 2
    top = (out_h - height) // 2
    bar = bytes(matte) * out_w
    lpad = bytes(matte) * left
    rpad = bytes(matte) * (out_w - width - left)

    out = [bar] * top
    out += [lpad + line + rpad for line in rows]
    out += [bar] * (out_h - height - top)
    return out


def sips_resize(src, dst, width, height):
    subprocess.run(
        ["sips", "-z", str(height), str(width), str(src), "--out", str(dst)],
        check=True,
        capture_output=True,
    )


def build(source_root):
    if not source_root.is_dir():
        raise SystemExit(f"source folder not found: {source_root}")

    written = []
    for klass in CLASSES:
        src_dir = source_root / klass.source_dir
        if not src_dir.is_dir():
            raise SystemExit(f"missing capture folder: {src_dir}")

        by_key = {time_key(p.name): p for p in src_dir.glob("*.png")}
        by_key.pop("", None)

        planned = MANIFEST[klass.slug]
        unused = set(by_key) - {k for k, _ in planned}
        for key in sorted(unused):
            reason = EXCLUDED.get(key, "not referenced by MANIFEST")
            print(f"  skip {klass.slug}/{key}: {reason}")

        out_dir = OUT_ROOT / klass.slug
        out_dir.mkdir(parents=True, exist_ok=True)
        for stale in out_dir.glob("*.png"):
            stale.unlink()

        for index, (key, slug) in enumerate(planned, start=1):
            src = by_key.get(key)
            if src is None:
                raise SystemExit(
                    f"{klass.slug}: no capture matching '{key}' in {src_dir}"
                )
            dst = out_dir / f"{index:02d}-{slug}.png"

            if klass.letterboxed:
                with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
                    sips_resize(src, tmp.name, *klass.inner)
                    w, h, rows, colour = read_png(pathlib.Path(tmp.name))
                if (w, h) != klass.inner:
                    raise SystemExit(f"{src}: sips produced {w}x{h}, want {klass.inner}")
                rows = pad_centre(rows, w, h, *klass.size, klass.matte)
                write_png_rgb(dst, *klass.size, rows, colour)
            else:
                w, h, rows, colour = read_png(src)
                if (w, h) != klass.size:
                    raise SystemExit(
                        f"{src}: capture is {w}x{h}, but the {klass.slug} class "
                        f"must be exactly {klass.size[0]}x{klass.size[1]}"
                    )
                write_png_rgb(dst, w, h, rows, colour)

            written.append(dst)
            print(f"  {dst.relative_to(REPO_ROOT)}  {klass.size[0]}x{klass.size[1]}")
    return written


def check():
    """Verify the committed outputs. Needs no capture sources - CI-safe."""
    problems = []
    for klass in CLASSES:
        out_dir = OUT_ROOT / klass.slug
        planned = MANIFEST[klass.slug]
        found = sorted(out_dir.glob("*.png")) if out_dir.is_dir() else []

        if len(found) != len(planned):
            problems.append(
                f"{klass.slug}: {len(found)} screenshot(s), manifest lists {len(planned)}"
            )
        if not 1 <= len(found) <= 10:
            problems.append(f"{klass.slug}: ASC accepts 1-10 screenshots, found {len(found)}")

        for index, (_key, slug) in enumerate(planned, start=1):
            path = out_dir / f"{index:02d}-{slug}.png"
            if not path.is_file():
                problems.append(f"missing {path.relative_to(REPO_ROOT)}")
                continue
            width, height, colour = png_header(path)
            rel = path.relative_to(REPO_ROOT)
            if (width, height) != klass.size:
                problems.append(
                    f"{rel}: {width}x{height}, ASC requires "
                    f"{klass.size[0]}x{klass.size[1]} for {klass.slug}"
                )
            if colour != 2:
                problems.append(f"{rel}: colour type {colour}, ASC requires RGB with no alpha")

    if problems:
        print("Screenshot check FAILED:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    total = sum(len(v) for v in MANIFEST.values())
    print(f"Screenshot check OK: {total} screenshots across {len(CLASSES)} device classes")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=pathlib.Path, help="folder of raw captures")
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the committed screenshots instead of rebuilding them",
    )
    args = parser.parse_args()

    if args.check:
        return check()
    if not args.source:
        parser.error("--source is required unless --check is given")

    print(f"Reading captures from {args.source}")
    build(args.source)
    print()
    return check()


if __name__ == "__main__":
    sys.exit(main())
