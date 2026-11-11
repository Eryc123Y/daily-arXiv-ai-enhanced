"""Shared helpers for the LitScout brand build: marks, outlined text, rendering."""
from __future__ import annotations

import io
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from PIL import Image

HERE = Path(__file__).parent
MARKS = HERE / "marks"
FONT = "/System/Library/Fonts/Supplemental/STIXTwoText.ttf"
NAVY = "#1c2430"
LILAC_BG = "#1d1c26"
LILAC_SURFACE = "#262533"
INK_DARK = "#f1eef8"
FILES = {"a": "a-bookmark.svg", "b": "b-serif-l.svg"}
RECOMMENDED = "a"


@dataclass(frozen=True)
class Mark:
    key: str
    d: str
    colour: str

    def svg(self, *, fill: str | None = None, attrs: str = 'viewBox="0 0 64 64"') -> str:
        return f'<svg xmlns="http://www.w3.org/2000/svg" {attrs}><path fill="{fill or self.colour}" d="{self.d}"/></svg>'

    def at(self, x: float, y: float, scale: float, fill: str | None = None) -> str:
        """The mark as a <g> in a larger scene (its 64 grid mapped by scale, origin at x, y)."""
        return f'<g transform="translate({x} {y}) scale({scale})"><path fill="{fill or self.colour}" d="{self.d}"/></g>'


def load_mark(key: str) -> Mark:
    text = (MARKS / FILES[key]).read_text()
    return Mark(key, re.search(r' d="([^"]+)"', text).group(1), re.search(r'fill="(#[0-9a-fA-F]{6})"', text).group(1))


def stix(weight: int) -> TTFont:
    return instantiateVariableFont(TTFont(FONT), {"wght": weight}, inplace=False)


def outline(font: TTFont, text: str, size: float, x: float, baseline: float) -> tuple[str, float]:
    """Path data for `text` as outlines, and the x where it ends."""
    glyphs = font.getGlyphSet()
    cmap = font.getBestCmap()
    scale = size / font["head"].unitsPerEm
    pen = SVGPathPen(glyphs)
    cursor = x
    for ch in text:
        name = cmap[ord(ch)]
        glyphs[name].draw(TransformPen(pen, (scale, 0, 0, -scale, cursor, baseline)))
        cursor += glyphs[name].width * scale
    return pen.getCommands(), cursor


def rsvg(svg: str, width: int, height: int | None = None) -> Image.Image:
    out = subprocess.run(
        ["rsvg-convert", "-w", str(width), "-h", str(height or width), "-f", "png"],
        input=svg.encode(), capture_output=True, check=True,
    ).stdout
    return Image.open(io.BytesIO(out)).convert("RGBA")


def paste(base: Image.Image, img: Image.Image, xy: tuple[int, int]) -> None:
    base.paste(img, xy, img)


def make_serif_l_source() -> None:
    """Write marks/b-serif-l.svg: STIX Two Text Bold 'L' over a rule, on the 64 grid."""
    font = stix(700)
    glyphs = font.getGlyphSet()
    scale = 42 / 657  # cap height 42 grid units
    width = (631 - 34) * scale
    x0 = 32 - width / 2 - 34 * scale
    pen = SVGPathPen(glyphs, ntos=lambda v: f"{v:.2f}".rstrip("0").rstrip("."))
    glyphs[font.getBestCmap()[ord("L")]].draw(TransformPen(pen, (scale, 0, 0, -scale, x0, 48)))
    left, right = 32 - width / 2, 32 + width / 2
    rule = f"M{left:.2f} 53H{right:.2f}V58H{left:.2f}Z"
    (MARKS / FILES["b"]).write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-label="LitScout">\n'
        "  <!-- B: STIX Two Text Bold L (the wordmark's own face) standing on a ruled line. 64 grid: cap height 42, rule 5 thick. -->\n"
        f'  <path fill="#2f7fd1" d="{pen.getCommands()}{rule}"/>\n</svg>\n'
    )
