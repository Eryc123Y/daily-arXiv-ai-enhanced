"""Build the derived brand assets from litscout-mark.svg (the hand-drawn source).

    uv run --with fonttools --with pillow python assets/brand/build.py

Needs rsvg-convert (brew install librsvg) and STIX Two Text (a macOS system
font). Writes the mono mark, wordmark, favicon, PNG exports and social preview
next to this file. concepts.png is built separately by concepts.py because it
needs the Codex concept images from .cache/brand/.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

HERE = Path(__file__).parent
FONT = "/System/Library/Fonts/Supplemental/STIXTwoText.ttf"
NAVY = "#1c2430"
PAPER_INK = "#f1eef8"

MARK = (HERE / "litscout-mark.svg").read_text()
DEFS = re.search(r"<defs>.*?</defs>", MARK, re.S).group(0)
GLYPH_SHAPES = re.search(r'<g id="spyglass".*?</g>', MARK, re.S).group(0)
TILE_RX = 14


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
        tpen = TransformPen(pen, (scale, 0, 0, -scale, cursor, baseline))
        glyphs[name].draw(tpen)
        cursor += glyphs[name].width * scale
    return pen.getCommands(), cursor


def write(name: str, text: str) -> None:
    (HERE / name).write_text(text)


def tile(rx: int = TILE_RX) -> str:
    return MARK.replace(f'rx="{TILE_RX}"', f'rx="{rx}"')


def render(svg: str, png: str, width: int, height: int | None = None) -> None:
    height = height or width
    subprocess.run(
        ["rsvg-convert", "-w", str(width), "-h", str(height), str(HERE / svg), "-o", str(HERE / png)],
        check=True,
    )


def mono() -> None:
    # One copy, one colour: the stereo pair collapses into a single silhouette.
    body = GLYPH_SHAPES.replace('id="spyglass"', 'id="spyglass" fill="currentColor" stroke="currentColor"')
    write(
        "litscout-mark-mono.svg",
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-label="LitScout">\n'
        "  <!-- One colour (currentColor), no tile: the stereo pair becomes a single silhouette. -->\n"
        f"  {body}\n</svg>\n",
    )


def wordmark() -> None:
    font = stix(600)
    size = 40
    d, end = outline(font, "LitScout", size, 64 + 14, 45)
    width = round(end + 4)
    write(
        "litscout-wordmark.svg",
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} 64" role="img" aria-label="LitScout">\n'
        "  <!-- Wordmark: STIX Two Text SemiBold converted to outlines, so no font is needed. -->\n"
        "  <style>.word{fill:#1c2430}@media (prefers-color-scheme:dark){.word{fill:#f1eef8}}</style>\n"
        f"  {DEFS}\n"
        f'  <rect width="64" height="64" rx="{TILE_RX}" fill="{NAVY}"/>\n'
        '  <use href="#spyglass" fill="#e8424a" stroke="#e8424a" transform="translate(-2.6 0)"/>\n'
        '  <use href="#spyglass" fill="#2fd0dd" stroke="#2fd0dd" transform="translate(2.6 0)"/>\n'
        f'  <path class="word" d="{d}"/>\n</svg>\n',
    )


def favicon() -> None:
    write("favicon.svg", tile().replace('role="img" aria-label="LitScout"', ""))
    render("favicon.svg", "favicon-32.png", 32)
    # Apple rounds the corners itself, so the touch icon is a full-bleed square.
    write("_touch.svg", tile(0))
    render("_touch.svg", "apple-touch-icon.png", 180)
    (HERE / "_touch.svg").unlink()


def social() -> None:
    w, h = 1280, 640
    title, tagline = stix(600), stix(400)
    td, _ = outline(title, "LitScout", 150, 450, 335)
    gd, _ = outline(tagline, "Daily papers from arXiv and top venues, summarised", 31, 452, 412)
    write(
        "_social.svg",
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">\n'
        f'  <rect width="{w}" height="{h}" fill="{NAVY}"/>\n'
        f"  {DEFS}\n"
        '  <g transform="translate(57 150) scale(5.4)">\n'
        '    <use href="#spyglass" fill="#e8424a" stroke="#e8424a" transform="translate(-2.6 0)"/>\n'
        '    <use href="#spyglass" fill="#2fd0dd" stroke="#2fd0dd" transform="translate(2.6 0)"/>\n'
        "  </g>\n"
        f'  <path fill="{PAPER_INK}" d="{td}"/>\n'
        f'  <path fill="#aab4c3" d="{gd}"/>\n</svg>\n',
    )
    render("_social.svg", "social-preview.png", w, h)
    (HERE / "_social.svg").unlink()


if __name__ == "__main__":
    mono()
    wordmark()
    favicon()
    social()
    print("built:", ", ".join(sorted(p.name for p in HERE.iterdir() if p.suffix in (".svg", ".png"))))
