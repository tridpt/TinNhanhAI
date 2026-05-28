"""Generate PNG icons used by the PWA manifest.

The SVG at ``frontend/icons/icon.svg`` is the source of truth, but iOS and
some Android launchers want raster PNGs at fixed sizes. We render a tiny
look-alike with Pillow primitives so we never need a headless browser or
external rasterizer in the build chain.

Re-run with ``python scripts/generate_icons.py`` after editing the design.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT_DIR = Path(__file__).resolve().parent.parent / "frontend" / "icons"
SIZES = (192, 512)
TEAL = (15, 118, 110, 255)
TEAL_LIGHT = (13, 148, 136, 255)
WHITE = (255, 255, 255, 255)


def _radial_bg(size: int) -> Image.Image:
    """Solid teal square with rounded corners and a subtle diagonal gradient."""

    overlay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for y in range(size):
        ratio = y / max(size - 1, 1)
        r = int(TEAL[0] + (TEAL_LIGHT[0] - TEAL[0]) * ratio)
        g = int(TEAL[1] + (TEAL_LIGHT[1] - TEAL[1]) * ratio)
        b = int(TEAL[2] + (TEAL_LIGHT[2] - TEAL[2]) * ratio)
        draw.line([(0, y), (size, y)], fill=(r, g, b, 255))

    rounded = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    mask = Image.new("L", (size, size), 0)
    radius = int(size * 0.18)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size, size), radius=radius, fill=255)
    rounded.paste(overlay, (0, 0), mask)
    return rounded


def _draw_glyph(image: Image.Image) -> None:
    """Draw a stylized "TN" monogram on top of the gradient background."""

    size = image.width
    draw = ImageDraw.Draw(image)

    # Newspaper-like card outline.
    margin = int(size * 0.18)
    box = (margin, margin, size - margin, size - margin - int(size * 0.05))
    line_width = max(2, int(size * 0.022))
    draw.rounded_rectangle(box, radius=int(size * 0.06), outline=WHITE, width=line_width)

    # Three horizontal "text" lines.
    inner_left = box[0] + int(size * 0.07)
    inner_right = box[2] - int(size * 0.07)
    line_y = box[1] + int(size * 0.18)
    line_gap = int(size * 0.10)
    for i in range(3):
        end_x = inner_right - (i * int(size * 0.10))
        draw.line(
            [(inner_left, line_y + i * line_gap), (end_x, line_y + i * line_gap)],
            fill=WHITE,
            width=line_width,
        )

    # Bold "TN" stamped over the corner.
    text = "TN"
    try:
        font = ImageFont.truetype("arialbd.ttf", int(size * 0.28))
    except OSError:
        font = ImageFont.load_default()
    text_w, text_h = draw.textbbox((0, 0), text, font=font)[2:]
    draw.text(
        (size - text_w - int(size * 0.10), size - text_h - int(size * 0.10)),
        text,
        font=font,
        fill=WHITE,
    )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for size in SIZES:
        image = _radial_bg(size)
        _draw_glyph(image)
        target = OUT_DIR / f"icon-{size}.png"
        image.save(target, "PNG", optimize=True)
        print(f"wrote {target} ({size}x{size})")


if __name__ == "__main__":
    main()
