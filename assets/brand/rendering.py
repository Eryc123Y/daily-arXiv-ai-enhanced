"""PNG rendering for the brand SVGs.

rsvg-convert ignores mix-blend-mode, so the red and cyan copies of a mark are
rendered as separate layers and screen-blended here, which is what browsers do
with the blend in the SVG itself.
"""
from __future__ import annotations

import io
import re
import subprocess
from pathlib import Path

from PIL import Image, ImageChops

HERE = Path(__file__).parent
RED, CYAN = "#e8424a", "#2fd0dd"


def rsvg(svg: str, width: int, height: int | None = None) -> Image.Image:
    out = subprocess.run(
        ["rsvg-convert", "-w", str(width), "-h", str(height or width), "-f", "png"],
        input=svg.encode(), capture_output=True, check=True,
    ).stdout
    return Image.open(io.BytesIO(out)).convert("RGBA")


def screen(base: Image.Image, layer: Image.Image) -> Image.Image:
    """Screen-blend an RGBA layer onto an RGB base, weighted by the layer's alpha."""
    blended = ImageChops.screen(base, layer.convert("RGB"))
    return Image.composite(blended, base, layer.getchannel("A"))


def split(svg: str) -> tuple[str, str, str]:
    """(base, red layer, cyan layer) of a tile-plus-two-copies mark."""
    lines = svg.splitlines()
    uses = [i for i, ln in enumerate(lines) if "<use" in ln]
    red = next(i for i in uses if RED in lines[i])
    cyan = next(i for i in uses if CYAN in lines[i])
    base = "\n".join(ln for i, ln in enumerate(lines) if i not in (red, cyan))
    no_tile = [ln for ln in lines if not re.match(r"\s*<rect width=", ln)]
    layer = lambda keep: "\n".join(ln for ln in no_tile if "<use" not in ln or ln == lines[keep])
    return base, layer(red), layer(cyan)


def compose(base: Image.Image, *layers: Image.Image) -> Image.Image:
    img = base.convert("RGB")
    for layer in layers:
        img = screen(img, layer)
    return img


def mark_png(svg: str, size: int, rx: int | None = None) -> Image.Image:
    """RGBA render of a tile mark; rx overrides the corner radius (0 = full bleed)."""
    if rx is not None:
        svg = re.sub(r'(<rect width="64" height="64" rx=")\d+', rf"\g<1>{rx}", svg)
    base, red, cyan = split(svg)
    tile = rsvg(base, size)
    out = compose(tile, rsvg(red, size), rsvg(cyan, size)).convert("RGBA")
    out.putalpha(tile.getchannel("A"))
    return out
