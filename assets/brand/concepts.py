"""Build concepts.png: the three Codex concepts next to the final mark at 16, 32 and 128 px.

    uv run --with pillow python assets/brand/concepts.py

The Codex images live in .cache/brand/ (git-ignored); only the sheet is committed.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from rendering import mark_png

HERE = Path(__file__).parent
CONCEPTS = HERE.parent.parent / ".cache" / "brand"
FONT = "/System/Library/Fonts/Helvetica.ttc"
INK = "#1c2430"
GROUND = [("#ffffff", "white"), ("#e8ebef", "Preprint chrome"), ("#1c2430", "navy"), ("#262533", "Lilac surface")]
W, H = 1500, 1000


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT, size, index=1 if bold else 0)


def main() -> None:
    sheet = Image.new("RGB", (W, H), "#f6f7f9")
    d = ImageDraw.Draw(sheet)
    d.text((40, 28), "LitScout mark: three Codex concepts, and the chosen one redrawn as SVG", font=font(28, True), fill=INK)
    names = [
        ("concept-a-spyglass.png", "A  Spyglass (chosen)"),
        ("concept-b-lens-page.png", "B  Lens over a page"),
        ("concept-c-eye-lines.png", "C  Eye over text lines"),
    ]
    for i, (file, label) in enumerate(names):
        x = 40 + i * 480
        img = Image.open(CONCEPTS / file).convert("RGB").resize((420, 420), Image.LANCZOS)
        sheet.paste(img, (x, 90))
        d.text((x, 520), label, font=font(22, True), fill=INK)
    d.text((40, 580), "Final mark (A, hand-drawn SVG) at 16, 32 and 128 px, on the grounds it has to work on", font=font(22, True), fill=INK)
    full, fav = (HERE / "litscout-mark.svg").read_text(), (HERE / "favicon.svg").read_text()
    # What ships: the heavier favicon at 16 and 32 px, the full mark from 28 px up.
    shown = [(fav, 16), (fav, 32), (full, 32), (full, 128)]
    renders = [mark_png(svg, size) for svg, size in shown]
    pw = 344
    for i, (colour, name) in enumerate(GROUND):
        x = 40 + i * (pw + 14)
        panel = Image.new("RGB", (pw, 300), colour)
        sheet.paste(panel, (x, 625))
        light = colour in ("#ffffff", "#e8ebef")
        cx = x + 24
        for m in renders:
            sheet.paste(m, (cx, 625 + 40 + (128 - m.width) // 2), m)
            cx += m.width + 16
        muted = "#5f6773" if light else "#a5a1bf"
        d.text((x + 16, 625 + 190), "favicon 16, 32 | mark 32, 128", font=font(14), fill=muted)
        d.text((x + 16, 625 + 218), name, font=font(16), fill=muted)
        # the 16 px favicon magnified 4x so the pixels can be judged
        mag = renders[0].resize((64, 64), Image.NEAREST)
        sheet.paste(mag, (x + pw - 80, 625 + 218 - 8), mag)
    d.text((40, 950), "Codex image generation made A, B and C; the final SVG is redrawn by hand (strokes only, no raster). Lower right of each panel: the 16 px favicon at 4x.", font=font(15), fill="#5f6773")
    sheet.save(HERE / "concepts.png", optimize=True)


if __name__ == "__main__":
    main()
