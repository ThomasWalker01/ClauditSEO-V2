#!/usr/bin/env bash
# One-command bootstrap: venv, deps, migrations, demo data, dashboard build, serve.
# Usage: bash scripts/dev.sh [--no-serve]
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -d .venv ]; then
    python3 -m venv .venv
fi
./.venv/bin/python -m pip install --quiet -e ".[dev]"
./.venv/bin/python -m clauditseo migrate
./.venv/bin/python -m clauditseo seed

(cd dashboard && { [ -d node_modules ] || npm install --no-audit --no-fund; } && npm run build)

if [ "${1:-}" = "--no-serve" ]; then
    echo "Bootstrap complete (serve skipped)."
else
    ./.venv/bin/python -m clauditseo serve
fi
