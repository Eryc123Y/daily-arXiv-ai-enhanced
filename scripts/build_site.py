"""Copy the public reading-page files into dist/ for Cloudflare: `python3 scripts/build_site.py`.

Only the files listed here are published, never the repository root, so the
pipeline code, tests, docs and dot-files stay out of the Worker's assets. The
page reads its data from the `data` branch on raw.githubusercontent.com, so
nothing here depends on the data. Standard library only; Cloudflare Workers
Builds runs it as the build command before `npx wrangler deploy`.
"""

import shutil
import sys
from pathlib import Path

OUTPUT = "dist"

# Pages: the reading page and the keyword-trends page it links to.
PAGES = ("index.html", "statistic.html")

# Folders copied whole: stylesheets and browser scripts.
FOLDERS = ("css", "js")

# Single files the pages load: icons and logos.
FILES = (
    "assets/brand/favicon.svg",
    "assets/brand/favicon-32.png",
    "assets/brand/apple-touch-icon.png",
    "assets/brand/litscout-mark.svg",
    "assets/logo.svg",
    "assets/logo2-removebg-preview.png",
)


def _public(path):
    return not any(part.startswith(".") for part in path.parts)


def site_files(root):
    """Paths, relative to root, of every file the site publishes; exits if one is missing."""
    root = Path(root)
    missing = [name for name in (*PAGES, *FOLDERS, *FILES) if not (root / name).exists()]
    if missing:
        raise SystemExit(f"build_site: missing {', '.join(missing)} under {root}")
    found = [Path(name) for name in (*PAGES, *FILES)]
    for folder in FOLDERS:
        found += [p.relative_to(root) for p in sorted((root / folder).rglob("*")) if p.is_file()]
    return [p for p in found if _public(p)]


def build(root, out):
    """Replace out with a fresh copy of the site files; return their relative paths."""
    root, out = Path(root), Path(out)
    files = site_files(root)
    if out.exists():
        shutil.rmtree(out)
    for rel in files:
        target = out / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, target)
    return [p.as_posix() for p in files]


def main():
    root = Path(__file__).resolve().parents[1]
    files = build(root, root / OUTPUT)
    print(f"build_site: copied {len(files)} files to {OUTPUT}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
