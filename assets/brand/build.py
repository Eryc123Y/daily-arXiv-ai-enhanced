"""Build the LitScout brand files from one of the two marks in marks/.

    uv run --with fonttools --with pillow python assets/brand/build.py [--mark a|b]

--mark picks which mark the top-level files use (default: the recommended one),
so swapping the brand mark is one command, then commit the regenerated files.
Needs rsvg-convert (brew install librsvg) and STIX Two Text (a macOS system font).
Writes litscout-mark.svg, litscout-mark-mono.svg, litscout-wordmark.svg,
favicon.svg, favicon-32.png, apple-touch-icon.png and social-preview.png here.
concepts.png (the decision board) is built by concepts.py.
"""
from __future__ import annotations

import argparse

from brandlib import HERE, INK_DARK, NAVY, RECOMMENDED, Mark, load_mark, make_serif_l_source, outline, rsvg, stix


def write(name: str, text: str) -> None:
    (HERE / name).write_text(text)


def colour_files(mark: Mark) -> None:
    label = 'role="img" aria-label="LitScout"'
    write("litscout-mark.svg", mark.svg(attrs=f'viewBox="0 0 64 64" {label}') + "\n")
    write("litscout-mark-mono.svg", mark.svg(fill="currentColor", attrs=f'viewBox="0 0 64 64" {label}') + "\n")
    # No simplification needed: both marks are two or three solid shapes, so the favicon is the mark.
    write("favicon.svg", mark.svg() + "\n")
    rsvg(mark.svg(), 32).save(HERE / "favicon-32.png")
    # Apple rounds the corners itself: full-bleed colour square, white mark at 72 percent.
    touch = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
        f'<rect width="64" height="64" fill="{mark.colour}"/>'
        f'<g transform="translate(32 32) scale(.72) translate(-32 -32)"><path fill="#ffffff" d="{mark.d}"/></g></svg>'
    )
    rsvg(touch, 180).convert("RGB").save(HERE / "apple-touch-icon.png")


def wordmark(mark: Mark) -> None:
    d, end = outline(stix(600), "LitScout", 40, 64 + 6, 44)
    width = round(end + 4)
    write(
        "litscout-wordmark.svg",
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} 64" role="img" aria-label="LitScout">\n'
        "  <!-- Wordmark: STIX Two Text SemiBold converted to outlines, so no font is needed. -->\n"
        "  <style>.word{fill:#1c2430}@media (prefers-color-scheme:dark){.word{fill:#f1eef8}}</style>\n"
        f'  <path fill="{mark.colour}" d="{mark.d}"/>\n'
        f'  <path class="word" d="{d}"/>\n</svg>\n',
    )


def social(mark: Mark) -> None:
    w, h = 1280, 640
    td, _ = outline(stix(600), "LitScout", 150, 470, 335)
    gd, _ = outline(stix(400), "Daily papers from arXiv and top venues, summarised", 31, 472, 412)
    scene = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}">'
        f'<rect width="{w}" height="{h}" fill="{NAVY}"/>'
        f"{mark.at(105, 120, 6.25)}"
        f'<path fill="{INK_DARK}" d="{td}"/><path fill="#aab4c3" d="{gd}"/></svg>'
    )
    rsvg(scene, w, h).convert("RGB").save(HERE / "social-preview.png")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mark", choices=["a", "b"], default=RECOMMENDED)
    key = parser.parse_args().mark
    make_serif_l_source()
    chosen = load_mark(key)
    colour_files(chosen)
    wordmark(chosen)
    social(chosen)
    print(f"built the top-level files from mark {key}")
