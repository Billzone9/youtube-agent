"""Optional title card — Pillow renders a transparent PNG (the Mac's ffmpeg has no `drawtext`), which
`overlay` composites over the opening. Off by default (the lion spec's `title_card` is null); purely
additive — never required for a render.
"""
from __future__ import annotations

import os


def render_card(text: str, target, dst_png: str, style: dict | None = None) -> str:
    """Render centered title text to a transparent PNG at the target frame size."""
    from PIL import Image, ImageDraw, ImageFont

    style = style or {}
    img = Image.new("RGBA", (target.w, target.h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    size = int(style.get("font_px", target.h // 12))
    try:
        font = ImageFont.truetype(style.get("font", "/System/Library/Fonts/Supplemental/Georgia.ttf"), size)
    except Exception:  # noqa: BLE001 — fall back to the bundled default if the font is absent
        font = ImageFont.load_default()
    lines = text.split("\n")
    _, _, _, lh = draw.textbbox((0, 0), "Ag", font=font)
    total = lh * len(lines)
    y = (target.h - total) // 2
    for line in lines:
        w = draw.textbbox((0, 0), line, font=font)[2]
        draw.text(((target.w - w) // 2, y), line, font=font,
                  fill=tuple(style.get("color", [255, 255, 255, 255])))
        y += lh
    tmp = f"{dst_png}.tmp.png"
    img.save(tmp)
    os.replace(tmp, dst_png)
    return dst_png


def overlay_fragment(png_input_index: int, start_s: float, duration: float, fade: float = 1.0) -> str:
    """A filter fragment overlaying the title PNG for [start, start+duration] with fades."""
    return (
        f"[{png_input_index}:v]format=rgba,fade=t=in:st={start_s}:d={fade}:alpha=1,"
        f"fade=t=out:st={start_s + duration - fade}:d={fade}:alpha=1[title]"
    )
