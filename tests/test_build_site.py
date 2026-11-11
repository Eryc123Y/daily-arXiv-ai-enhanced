"""The Cloudflare build: scripts/build_site.py copies an allowlist of public page files into dist/."""

import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ("summaries/", "tests/", "daily_arxiv/", "docs/", "scripts/")
REFERENCE = re.compile(r"""(?:src|href)\s*=\s*["']([^"']+)["']""")
CSS_URL = re.compile(r"""url\(\s*["']?([^"')]+)["']?\s*\)""")


def load_build():
    spec = importlib.util.spec_from_file_location("build_site", ROOT / "scripts" / "build_site.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def local(ref):
    """The site-relative path a reference points at, or None for remote, inline and in-page ones."""
    if re.match(r"^(?:[a-z]+:|//|#)", ref, re.IGNORECASE):
        return None
    path = re.split(r"[?#]", ref, maxsplit=1)[0]
    if path in ("", "./", "."):
        return "index.html"
    return path[2:] if path.startswith("./") else path


@pytest.fixture(scope="module")
def dist(tmp_path_factory):
    out = tmp_path_factory.mktemp("dist")
    load_build().build(ROOT, out)
    return out


def built(dist):
    return sorted(p.relative_to(dist).as_posix() for p in dist.rglob("*") if p.is_file())


def test_every_local_file_the_pages_load_is_copied(dist):
    missing = []
    for page in dist.rglob("*.html"):
        for ref in REFERENCE.findall(page.read_text(encoding="utf-8")):
            path = local(ref)
            if path and not (dist / path).is_file():
                missing.append(f"{page.name}: {ref}")
    for sheet in dist.rglob("*.css"):
        for ref in CSS_URL.findall(sheet.read_text(encoding="utf-8")):
            path = local(ref)
            if path and not (sheet.parent / path).is_file():
                missing.append(f"{sheet.name}: {ref}")
    assert not missing, f"the build leaves out files the page loads: {missing}"


def test_the_build_copies_only_public_page_files(dist):
    files = built(dist)
    assert "index.html" in files
    assert not [f for f in files if f.startswith(PRIVATE)], files
    assert not [f for f in files if any(part.startswith(".") for part in f.split("/"))], files
    assert not [f for f in files if f.endswith((".py", ".md", ".jsonl"))], files


def test_every_extra_page_is_linked_from_the_reading_page(dist):
    links = {local(ref) for ref in REFERENCE.findall((dist / "index.html").read_text(encoding="utf-8"))}
    pages = [f for f in built(dist) if f.endswith(".html") and f != "index.html"]
    assert all(page in links for page in pages), pages


def test_the_build_starts_from_an_empty_folder(tmp_path):
    out = tmp_path / "dist"
    (out / "old").mkdir(parents=True)
    (out / "old" / "stale.txt").write_text("left over", encoding="utf-8")
    load_build().build(ROOT, out)
    assert not (out / "old").exists()
    assert (out / "index.html").is_file()


def test_a_missing_allowlisted_file_fails_the_build(tmp_path):
    source = tmp_path / "repo"
    source.mkdir()
    (source / "index.html").write_text("<html></html>", encoding="utf-8")
    with pytest.raises(SystemExit, match="css"):
        load_build().build(source, tmp_path / "dist")


def wrangler():
    text = (ROOT / "wrangler.jsonc").read_text(encoding="utf-8")
    without_comments = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("//"))
    return json.loads(re.sub(r",(\s*[}\]])", r"\1", without_comments))


def test_the_worker_serves_the_build_output_on_the_custom_domain():
    config = wrangler()
    assert config["name"] == "litscout-daily"
    assert config["assets"]["directory"] == "./dist"
    assert "main" not in config, "static assets only, no Worker script"
    assert config["workers_dev"] is False
    assert config["routes"] == [{"pattern": "litscout.turing2234.com", "custom_domain": True}]
    assert load_build().OUTPUT == "dist"
