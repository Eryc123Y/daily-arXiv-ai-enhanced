"""Build the derived brand assets from litscout-mark.svg (the hand-drawn source).

    uv run --with fonttools --with pillow python assets/brand/build.py

Needs rsvg-convert (brew install librsvg) and STIX Two Text (a macOS system
font). Writes the mono mark, wordmark, PNG exports and social preview next to
this file; favicon.svg is hand-drawn, only favicon-32.png comes from it. PNGs
screen-blend the red and cyan layers themselves (see rendering.py). concepts.png is built separately by concepts.py because it
needs the Codex concept images from .cache/brand/.
"""
from __future__ import annotations

import re
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from rendering import CYAN, RED, compose, mark_png, rsvg

HERE = Path(__file__).parent
FONT = "/System/Library/Fonts/Supplemental/STIXTwoText.ttf"
NAVY = "#1c2430"
PAPER_INK = "#f1eef8"

MARK = (HERE / "litscout-mark.svg").read_text()
DEFS = re.search(r"<defs>.*?</defs>", MARK, re.S).group(0)
GLYPH_SHAPES = re.search(r'<g id="spyglass".*?</g>', MARK, re.S).group(0)
USES = "\n".join(ln for ln in MARK.splitlines() if "<use" in ln)
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


def mono() -> None:
    # One copy, one colour: the stereo pair collapses into a single silhouette.
    body = GLYPH_SHAPES.replace('id="spyglass"', 'id="spyglass" stroke="currentColor"')
    write(
        "litscout-mark-mono.svg",
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-label="LitScout">\n'
        "  <!-- One colour (currentColor), no tile: one copy of the strokes, no stereo pair. -->\n"
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
        f"{USES}\n"
        f'  <path class="word" d="{d}"/>\n</svg>\n',
    )


def favicon() -> None:
    # favicon.svg is hand-drawn like the mark (heavier strokes for 16 and 32 px).
    fav = (HERE / "favicon.svg").read_text()
    mark_png(fav, 32).save(HERE / "favicon-32.png")
    # Apple rounds the corners itself, so the touch icon is a full-bleed square of the full mark.
    mark_png(MARK, 180, rx=0).convert("RGB").save(HERE / "apple-touch-icon.png")


def social() -> None:
    w, h = 1280, 640
    title, tagline = stix(600), stix(400)
    td, _ = outline(title, "LitScout", 150, 450, 335)
    gd, _ = outline(tagline, "Daily papers from arXiv and top venues, summarised", 31, 452, 412)

    def scene(*, background: bool, use: str | None) -> str:
        parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">', DEFS]
        if background:
            parts += [
                f'<rect width="{w}" height="{h}" fill="{NAVY}"/>',
                f'<path fill="{PAPER_INK}" d="{td}"/>',
                f'<path fill="#aab4c3" d="{gd}"/>',
            ]
        if use:
            parts.append(f'<g transform="translate(57 150) scale(5.4)">{use}</g>')
        return "\n".join(parts + ["</svg>"])

    red, cyan = (next(ln for ln in USES.splitlines() if colour in ln) for colour in (RED, CYAN))
    base = rsvg(scene(background=True, use=None), w, h)
    img = compose(base, rsvg(scene(background=False, use=red), w, h), rsvg(scene(background=False, use=cyan), w, h))
    img.save(HERE / "social-preview.png")


if __name__ == "__main__":
    mono()
    wordmark()
    favicon()
    social()
    print("built:", ", ".join(sorted(p.name for p in HERE.iterdir() if p.suffix in (".svg", ".png"))))
