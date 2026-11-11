"""One-command setup for a fork: `uv run python -m summaries setup`.

Sets the repository variables (the local crawl reads CATEGORIES), enables
Actions for the test workflow and GitHub Pages' builds, enables Pages, and
prints what is left to do. The crawl and summaries run on your machine. It
uses the logged-in `gh` CLI and never asks for, reads or stores an API key.
"""

import subprocess

from summaries import github
from summaries.providers import KEY_ENV

DEFAULT_CATEGORIES = "cs.CV, cs.AI, cs.LG, cs.CL, stat.ML"


def _try(*args):
    """Run gh; return None on success or the error text."""
    try:
        github.gh(*args)
        return None
    except subprocess.CalledProcessError as error:
        return (error.stderr or str(error)).strip()


def cmd_setup(args):
    slug = github.repo_slug(args.repo)
    variables = {"CATEGORIES": args.categories, "LANGUAGE": args.language, "SUMMARY_MODE": args.mode}
    if args.provider:
        variables["SUMMARY_PROVIDER"] = args.provider
    if args.model:
        variables["SUMMARY_MODEL"] = args.model
    if args.commit_name and args.commit_email:
        variables.update(COMMIT_NAME=args.commit_name, COMMIT_EMAIL=args.commit_email)
    for name, value in variables.items():
        github.gh("variable", "set", name, "-R", slug, "--body", value)
    notes = [f"Set {', '.join(variables)} on {slug}."]

    if _try("workflow", "enable", "tests.yml", "-R", slug):
        notes.append(
            f"Actions is off on this fork, so GitHub Pages cannot build: open https://github.com/{slug}/actions "
            "and click 'I understand my workflows, go ahead and enable them' (no workflow runs on a schedule)."
        )

    pages = _try("api", "-X", "POST", f"repos/{slug}/pages", "-f", "build_type=legacy", "-f", "source[branch]=main", "-f", "source[path]=/")
    if pages is None:
        notes.append("Enabled GitHub Pages from the main branch.")
    elif "409" in pages or "already" in pages.lower():
        notes.append("GitHub Pages was already enabled.")
    else:
        notes.append(f"Could not enable GitHub Pages ({pages}); set Settings > Pages > Deploy from a branch: main, /.")

    key = KEY_ENV.get(args.provider or "anthropic")
    print("\n".join(notes))
    print(
        f"""
Your page: {github.site_url(slug)}

Crawl today's papers on this machine (and backfill missed days):
  uv run python -m summaries ensure-day

Summaries (pick one):
  Local coding agent: uv run python -m summaries run-local --client claude|codex|antigravity
    Schedule both with cron or launchd; for a Claude Code scheduled task see docs/claude-code-task.md.
  API: export {key} in the scheduled job's environment, then uv run python -m summaries api --days 3

Your interests: edit js/interest-presets.js, or use Keywords & authors on the page."""
    )
    return 0


def add_parser(sub):
    setup = sub.add_parser("setup", help="configure this fork on GitHub (variables, Pages)")
    setup.add_argument("--categories", default=DEFAULT_CATEGORIES, help="comma-separated arXiv categories")
    setup.add_argument("--language", default="English", help="language of the summaries")
    setup.add_argument("--mode", default="claude-code", choices=["claude-code", "api"])
    setup.add_argument("--provider", choices=sorted(KEY_ENV), help="API provider for api mode and the fallback")
    setup.add_argument("--model", help="model for the API provider (required for openai and gemini)")
    setup.add_argument("--commit-name", help="name for data commits (default: the github-actions bot)")
    setup.add_argument("--commit-email", help="email for data commits, e.g. your GitHub noreply address")
    setup.set_defaults(func=cmd_setup)
