"""Build concepts.png: the three Codex concepts next to the final mark at 16, 32 and 128 px.

    uv run --with pillow python assets/brand/concepts.py

The Codex images live in .cache/brand/ (git-ignored); only the sheet is committed.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
CONCEPTS = HERE.parent.parent / ".cache" / "brand"
FONT = "/System/Library/Fonts/Helvetica.ttc"
INK = "#1c2430"
GROUND = [("#ffffff", "white"), ("#e8ebef", "Preprint chrome"), ("#1c2430", "navy"), ("#262533", "Lilac surface")]
W, H = 1500, 1000


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT, size, index=1 if bold else 0)


def mark(size: int, tmp: Path) -> Image.Image:
    out = tmp / f"m{size}.png"
    subprocess.run(["rsvg-convert", "-w", str(size), "-h", str(size), str(HERE / "litscout-mark.svg"), "-o", str(out)], check=True)
    return Image.open(out).convert("RGBA")


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
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        sizes = {s: mark(s, tmp) for s in (16, 32, 128)}
    pw = 344
    for i, (colour, name) in enumerate(GROUND):
        x = 40 + i * (pw + 14)
        panel = Image.new("RGB", (pw, 300), colour)
        sheet.paste(panel, (x, 625))
        light = colour in ("#ffffff", "#e8ebef")
        cx = x + 24
        for s in (16, 32, 128):
            m = sizes[s]
            sheet.paste(m, (cx, 625 + 40 + (128 - s) // 2), m)
            cx += s + 28
        d.text((x + 16, 625 + 218), name, font=font(16), fill="#5f6773" if light else "#a5a1bf")
        # 16 px and 32 px magnified so the pixels can be judged
        mag = sizes[16].resize((64, 64), Image.NEAREST)
        sheet.paste(mag, (x + pw - 80, 625 + 218 - 8), mag)
    d.text((40, 950), "Codex image generation made A, B and C; the final SVG is redrawn by hand (flat shapes, no raster). Rightmost thumbnail in each panel: the 16 px render at 4x.", font=font(15), fill="#5f6773")
    sheet.save(HERE / "concepts.png", optimize=True)


if __name__ == "__main__":
    main()
