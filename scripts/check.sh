#!/bin/sh
# Every check before merging: both type checkers, the linter, and both test
# suites. Stops at the first failure. No CI runs them (see AGENTS.md).
set -e
cd "$(dirname "$0")/.."

echo '== tsc (js/, JSDoc with checkJs)'
npx -y -p typescript@7.0.2 tsc -p .
echo '== pyright'
uv run pyright
echo '== ruff'
uv run ruff check
echo '== node tests'
node --test tests/js/*.test.js
echo '== pytest'
uv run pytest -q
