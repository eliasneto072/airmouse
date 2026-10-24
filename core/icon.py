# core/icon.py
"""App icon drawn with Pillow: used for the tray (coloured by mode) and the shortcuts (.ico)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

BACKGROUND = "#1d1f24"
MODE_COLORS = {
    "classic": "#4c8dff",
    "disarmed": "#8a8f98",
    "move": "#4c8dff",
    "scroll": "#3fbf7f",
    "shortcuts": "#f2a33a",
    "media": "#a970ff",
    "windows": "#2bb3c0",
    "paused": "#5a5f68",
}

# Mouse-pointer arrow, in unit coordinates (0..1)
_ARROW = [(0.35, 0.24), (0.35, 0.74), (0.47, 0.62), (0.56, 0.80), (0.64, 0.76), (0.55, 0.58), (0.71, 0.58)]


def draw_icon(color: str = MODE_COLORS["move"], size: int = 64, paused: bool = False) -> Image.Image:
    """Dark rounded tile with a coloured ring and a white pointer (two bars when paused)."""
    scale = 4  # draw large, then downsample for smooth edges
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, s - 1, s - 1), radius=s // 5, fill=BACKGROUND)
    ring = max(2, s // 14)
    pad = s // 9
    d.ellipse((pad, pad, s - pad, s - pad), outline=color, width=ring)
    if paused:
        bar_w, bar_h = s // 9, s // 2.6
        cx, cy = s / 2, s / 2
        for dx in (-bar_w * 0.9, bar_w * 0.9):
            d.rounded_rectangle(
                (cx + dx - bar_w / 2, cy - bar_h / 2, cx + dx + bar_w / 2, cy + bar_h / 2),
                radius=bar_w // 3,
                fill="white",
            )
    else:
        d.polygon([(x * s, y * s) for x, y in _ARROW], fill="white")
    return img.resize((size, size), Image.LANCZOS)


def save_ico(path: str | Path, color: str = MODE_COLORS["move"]) -> Path:
    """Write a multi-resolution .ico (for shortcuts)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    draw_icon(color, 256).save(path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return path
