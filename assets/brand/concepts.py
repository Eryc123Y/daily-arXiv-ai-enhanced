"""Build concepts.png, the decision board: four Codex directions, the two shortlisted marks, rationale.

    uv run --with fonttools --with pillow python assets/brand/concepts.py

The Codex images live in .cache/brand/ (git-ignored); only the board is committed.
"""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

from brandlib import HERE, INK_DARK, LILAC_BG, LILAC_SURFACE, load_mark, outline, paste, rsvg, stix

CACHE = HERE.parent.parent / ".cache" / "brand"
HELV = "/System/Library/Fonts/Helvetica.ttc"
INK, MUTED, PAGE = "#1c2430", "#5f6773", "#f6f7f9"
W, H, M = 1600, 1500, 40

DIRECTIONS = [
    ("1  Typographic monogram", "1a shortlisted (B). 1b is busy at 16 px, 1c is too thin.", ["1a", "1b", "1c"]),
    ("2  Focus or lookout pictogram", "Reads as stock UI: a list in a circle (2a), a camera frame (2c).", ["2a", "2b", "2c"]),
    ("3  Abstract reading mark", "3a shortlisted (A): bookmark and L in one. 3b is hairline, 3c a bottle.", ["3a", "3b", "3c"]),
    ("4  Seal or stamp", "Battery (4a), hat (4b) and a G (4c); the ID-stamp echo is lost without text.", ["4a", "4b", "4c"]),
]
SHORTLIST = {"3a": "A", "1a": "B"}


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(HELV, size, index=1 if bold else 0)


def wrap(d: ImageDraw.ImageDraw, text: str, f: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if d.textlength(trial, font=f) <= width:
            line = trial
        else:
            lines.append(line)
            line = word
    return lines + [line]


def header_strip(mark, dark: bool, width: int) -> Image.Image:
    """The page header as it renders: 28 px mark and 'LitScout Daily' in STIX Two Text SemiBold 22 px."""
    surface, ink = (LILAC_SURFACE, INK_DARK) if dark else ("#ffffff", INK)
    line = "#3a3850" if dark else "#dce1e7"
    text, _ = outline(stix(600), "LitScout Daily", 22, 24 + 28 + 10, 35.2)
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} 56">'
        f'<rect width="{width}" height="56" fill="{surface}"/><rect y="55" width="{width}" height="1" fill="{line}"/>'
        f'{mark.at(24, 14, 28 / 64)}<path fill="{ink}" d="{text}"/></svg>'
    )
    return rsvg(svg, width, 56)


def treatments(mark) -> list[tuple[str, str, str, str]]:
    return [
        ("black on white", "#ffffff", "#000000", MUTED),
        ("white on dark", LILAC_BG, "#ffffff", "#a5a1bf"),
        ("colour on white", "#ffffff", mark.colour, MUTED),
        ("colour on Lilac", LILAC_BG, mark.colour, "#a5a1bf"),
    ]


def mark_block(sheet: Image.Image, d: ImageDraw.ImageDraw, mark, x: int, y: int, width: int, title: str, chip: str) -> int:
    d.text((x, y), title, font=font(24, True), fill=INK)
    d.text((x, y + 34), chip, font=font(15), fill=MUTED)
    y += 66
    cw, ch, gap = (width - 12) // 2, 178, 12
    for i, (name, bg, fill, label) in enumerate(treatments(mark)):
        cx, cy = x + (i % 2) * (cw + gap), y + (i // 2) * (ch + gap)
        d.rectangle([cx, cy, cx + cw - 1, cy + ch - 1], fill=bg, outline="#dce1e7" if bg == "#ffffff" else None)
        px = cx + 18
        for size in (16, 32, 128):
            paste(sheet, rsvg(mark.svg(fill=fill), size), (px, cy + 18 + (128 - size) // 2 + 8))
            d.text((px, cy + ch - 24), f"{size}", font=font(13), fill=label)
            px += size + 26
        d.text((cx + cw - 12 - d.textlength(name, font=font(14)), cy + 12), name, font=font(14), fill=label)
    y += 2 * ch + gap + 14
    for dark in (False, True):
        paste(sheet, header_strip(mark, dark, width), (x, y))
        y += 56 + 10
    return y


def main() -> None:
    sheet = Image.new("RGB", (W, H), PAGE)
    d = ImageDraw.Draw(sheet)
    d.text((M, 30), "LitScout mark: four directions explored with Codex, two shortlisted", font=font(32, True), fill=INK)
    d.text((M, 78), "Solid shapes, one colour first, no stereo effect. Thumbnails are Codex output; marks A and B below are redrawn by hand.", font=font(16), fill=MUTED)

    gw, gg = (W - 2 * M - 3 * 24) // 4, 24
    for i, (title, verdict, keys) in enumerate(DIRECTIONS):
        gx = M + i * (gw + gg)
        d.text((gx, 122), title, font=font(18, True), fill=INK)
        tw = (gw - 2 * 12) // 3
        for j, key in enumerate(keys):
            tx = gx + j * (tw + 12)
            tile = Image.open(CACHE / f"m{key}.png").convert("RGB").resize((tw, tw), Image.LANCZOS)
            sheet.paste(tile, (tx, 152))
            if key in SHORTLIST:
                d.rectangle([tx - 3, 149, tx + tw + 2, 152 + tw + 2], outline="#1f8f7a", width=4)
                d.text((tx + 6, 152 + 4), SHORTLIST[key], font=font(20, True), fill="#1f8f7a")
            else:
                d.rectangle([tx, 152, tx + tw - 1, 152 + tw - 1], outline="#dce1e7")
                d.text((tx + 6, 152 + 4), key, font=font(13), fill=MUTED)
        for k, line in enumerate(wrap(d, verdict, font(14), gw)):
            d.text((gx, 152 + tw + 14 + k * 19), line, font=font(14), fill=MUTED)

    d.line([M, 372, W - M, 372], fill="#dce1e7", width=2)
    bw = (W - 2 * M - 40) // 2
    a, b = load_mark("a"), load_mark("b")
    ya = mark_block(sheet, d, a, M, 392, bw, "A  Bookmark L (recommended)", "Verdigris #1f8f7a: 4.0:1 on white, 4.2:1 on Lilac #1d1c26, 3.8:1 on the Lilac header")
    yb = mark_block(sheet, d, b, M + bw + 40, 392, bw, "B  Serif L on a rule", "Ink blue #2f7fd1: 4.1:1 on white, 4.1:1 on Lilac #1d1c26, 3.6:1 on the Lilac header")
    y = max(ya, yb) + 16
    d.line([M, y, W - M, y], fill="#dce1e7", width=2)
    notes = [
        "A is a bookmark that is also an L: 'you have found the right page' in two corners and one notch. The most distinctive and the strongest at 16 px; the colour is not arXiv's red.",
        "B is the wordmark's own face, an L standing on a ruled line like a line of text. The most editorial and the quietest, but it repeats the wordmark's L and its fine serifs blur at 16 px.",
    ]
    for i, note in enumerate(notes):
        for k, line in enumerate(wrap(d, note, font(16), bw)):
            d.text((M + i * (bw + 40), y + 18 + k * 22), line, font=font(16), fill=INK)
    sheet.crop((0, 0, W, y + 120)).save(HERE / "concepts.png", optimize=True)


if __name__ == "__main__":
    main()
