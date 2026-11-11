# LitScout brand: design brief

Written before drawing anything, so the marks on `concepts.png` can be judged against it.

## What LitScout is

A quiet daily reading page for researchers: new papers from arXiv and, later, top journals and conferences, each with a short AI summary, sorted by what the reader cares about. The same name is also an MCP search tool for scholarly literature. The page reads like a well-set preprint (STIX Two Text for headings, Atkinson Hyperlegible Next for the interface), not like an app.

## Attributes to aim for

Scholarly, calm, precise, trustworthy, a little editorial. A researcher should feel they are being handed the right page, not being sold something. Not playful, not "AI", not tech-startup.

Aesthetic direction: **marginalia**. The mark behaves like a mark a careful reader leaves in a margin, such as a tick, a bracket or a blaze painted on a tree: one deliberate, slightly unexpected gesture in solid shapes, with plenty of white around it. Everything else stays quiet.

## Where the mark lives

- 16 px browser tab favicon, and 32 px.
- 28 px in the page header, beside "LitScout Daily" set in STIX Two Text SemiBold.
- GitHub social preview (1280 by 640) and the top of the README.
- Later: the MCP server's own repository and listings, so it must stand alone and next to a wordmark.

## Constraints

- One colour first: it must work in pure black on white and pure white on black before any colour is added.
- A strong silhouette that survives at 16 px: two or three solid shapes on a simple grid.
- No gradients, no 3D, no outline-on-outline effects, no stereo or anaglyph effect (the earlier red and cyan idea is dropped), no text inside the mark.
- The brand colour must not be arXiv red (#b31b1b) now that the site reads more than arXiv, and must reach at least 3:1 (the WCAG threshold for graphics) on white and on the Lilac dark background (#1d1c26).

## Clichés to avoid, or treat in an unexpected way

Plain magnifying glass, open book, graduation cap, brain, sparkles, a literal telescope icon, a document with a lens over it, an eye. If one of these ideas is used, it has to be reduced to a gesture that only suggests it.

## Exploration and critique

Four directions, three variants each, generated with Codex image generation (solid black on white, no colour, no effects). The raw images are in `.cache/brand/` (git-ignored); `concepts.png` is the decision board.

| Direction (best variant) | Reads at 16 px | Distinctive | Fits the serif wordmark and editorial page | One colour | Suits the MCP tool too |
|---|---|---|---|---|---|
| 1 Monogram, serif L on a rule (1a) | Fair: the thin rule and serifs blur | Fair: a letter, but the rule gives it a point of view | Best: it is the wordmark's own face | Yes | Yes |
| 2 Focus pictogram (2a ring of text lines, 2c viewfinder) | Yes | No: reads as a list icon or a camera | Weak: UI icon language, not editorial | Yes | Weak |
| 3 Reading mark, bookmark that is also an L (3a) | Yes: one solid shape | Yes: bookmark and letter in one | Good: geometric but calm, sits beside serif type | Yes | Yes: "saved result" reads naturally |
| 4 Seal or stamp (4a to 4c) | Fair | No: reads as a battery, a hat or a "G" | Weak: the ID-stamp echo needs text, which the mark may not contain | Yes | Weak |

**Shortlist: 3a as mark A (bookmark L) and 1a as mark B (serif L on a rule).** They are different kinds of answer to the same brief: A is a pictogram that carries an idea, B is typography that carries the voice. A is the recommendation: it is the more distinctive and the stronger at 16 px.

## The two marks and their colours

Both are redrawn by hand on a 64 grid from the Codex sketches, solid shapes only, in `marks/`.

- **A, bookmark L** (`marks/a-bookmark.svg`): one polygon. Stem 18 wide, foot to the right, a swallowtail notch on the centre line. Colour **verdigris #1f8f7a**, the green of aged copper on library roofs and old instruments: calm, scholarly, and not used by any of the page's five themes (Preprint red, Lilac, Lamplight amber, Anaglyph cyan, Graphite cobalt), nor arXiv red.
- **B, serif L on a rule** (`marks/b-serif-l.svg`, generated from STIX Two Text Bold by `build.py`): the L stands on a ruled line like a line of text. Colour **ink blue #2f7fd1**, the fountain-pen blue of marginal notes, and a lighter blue than the Graphite theme's cobalt.

Contrast of the colour against white / Lilac page #1d1c26 / the five theme surfaces: verdigris 4.0 / 4.2 / at least 3.8; ink blue 4.1 / 4.1 / at least 3.6. Mid-tones cannot reach 4.5:1 on both a white and a dark ground, so the target is the 3:1 that WCAG sets for graphics, which both pass everywhere the header can be.

## Files

| File | What |
|---|---|
| `marks/a-bookmark.svg`, `marks/b-serif-l.svg` | The two hand-drawn marks (source of truth) |
| `litscout-mark.svg`, `litscout-mark-mono.svg` | The chosen mark in colour and in `currentColor` |
| `litscout-wordmark.svg` | Mark plus "LitScout" in STIX Two Text SemiBold outlines (no font needed; text turns light in dark mode) |
| `favicon.svg`, `favicon-32.png`, `apple-touch-icon.png` | Favicons (the mark needs no simplification at 16 px); the touch icon is a white mark on a colour square |
| `social-preview.png` | 1280 by 640 for GitHub's social preview (upload by hand in repository settings) |
| `concepts.png` | The decision board |
| `preview/` | Header screenshots, light and dark, desktop and 375 px |

## Swapping the mark

```bash
uv run --with fonttools --with pillow python assets/brand/build.py --mark b   # or a
uv run --with fonttools --with pillow python assets/brand/concepts.py          # only to refresh the board
```

`build.py` rewrites every top-level file above from the chosen mark; `index.html` and the README point to those file names and need no change. Needs `rsvg-convert` (`brew install librsvg`) and STIX Two Text (a macOS system font). `concepts.py` also needs the Codex images in `.cache/brand/`.
