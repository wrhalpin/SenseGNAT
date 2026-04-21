#!/usr/bin/env python3
"""Generate the SenseGNAT logo kit from the source PNG.

Usage
-----
    python scripts/generate_logo_kit.py

Reads  : SenseGNAT-logo.png (repo root)
Writes : docs/assets/images/  (created if absent)

Output files
------------
    sensegnat-logo-512.png   — 512 × 512  full-colour square
    sensegnat-logo-256.png   — 256 × 256
    sensegnat-logo-128.png   — 128 × 128
    favicon-48.png           — 48 × 48
    favicon-32.png           — 32 × 32
    favicon-16.png           — 16 × 16
    apple-touch-icon.png     — 180 × 180  (iOS home-screen icon)
    favicon.ico              — multi-size bundle (16 / 32 / 48)
    social-card.png          — 1200 × 630 (Open Graph / Twitter card)

Requires Pillow:
    uv pip install --system Pillow   # or: pip install Pillow
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow is required.  Install it with: pip install Pillow")

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE = REPO_ROOT / "SenseGNAT-logo.png"
OUT_DIR = REPO_ROOT / "docs" / "assets" / "images"

# Dark-ink background colour used for the social card canvas (#111321)
CARD_BG = (17, 19, 33, 255)
CARD_SIZE = (1200, 630)


def _resize(img: Image.Image, size: int) -> Image.Image:
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    if not SOURCE.exists():
        sys.exit(f"Source logo not found: {SOURCE}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    img = Image.open(SOURCE).convert("RGBA")
    w, h = img.size
    print(f"Source : {SOURCE.name}  ({w}×{h})")
    print(f"Output : {OUT_DIR.relative_to(REPO_ROOT)}/\n")

    variants: list[tuple[str, int | None]] = [
        ("sensegnat-logo-512.png", 512),
        ("sensegnat-logo-256.png", 256),
        ("sensegnat-logo-128.png", 128),
        ("favicon-48.png",          48),
        ("favicon-32.png",          32),
        ("favicon-16.png",          16),
        ("apple-touch-icon.png",   180),
    ]

    for name, size in variants:
        out = OUT_DIR / name
        frame = _resize(img, size)
        frame.save(out, "PNG", optimize=True)
        print(f"  {name:<35s} {size}×{size}")

    # ICO bundle
    ico_sizes = [16, 32, 48]
    frames = [_resize(img, s) for s in ico_sizes]
    ico_path = OUT_DIR / "favicon.ico"
    frames[0].save(
        ico_path,
        format="ICO",
        sizes=[(s, s) for s in ico_sizes],
        append_images=frames[1:],
    )
    print(f"  {'favicon.ico':<35s} {'/'.join(str(s) for s in ico_sizes)} (bundled)")

    # Social card — centred logo on dark-ink canvas
    card = Image.new("RGBA", CARD_SIZE, CARD_BG)
    logo = _resize(img, 560)
    x = (CARD_SIZE[0] - 560) // 2
    y = (CARD_SIZE[1] - 560) // 2
    card.paste(logo, (x, y), logo)
    card_path = OUT_DIR / "social-card.png"
    card.convert("RGB").save(card_path, "PNG", optimize=True)
    print(f"  {'social-card.png':<35s} {CARD_SIZE[0]}×{CARD_SIZE[1]}")

    print("\nDone.")


if __name__ == "__main__":
    main()
