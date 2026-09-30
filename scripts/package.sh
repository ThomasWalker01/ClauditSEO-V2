#!/usr/bin/env bash
# Build the distributable from git, so .gitignore is the single source of
# truth about what ships. Zipping the working directory shipped .venv (a 92 MB
# node.exe inside playwright's driver), node_modules, the .git object store,
# and 475 generated reports - four of them named for a real client, which is a
# data-exposure problem quite apart from the size.
set -euo pipefail
cd "$(dirname "$0")/.."
version=$(python -c "import clauditseo; print(clauditseo.__version__)")
out="clauditseo-${version}.zip"
git archive --format=zip --prefix="clauditseo/" -o "$out" HEAD
# List first, then match. Piping into `grep -q` under `pipefail` is a trap:
# grep exits on the first hit, unzip dies of SIGPIPE, the pipeline reports
# failure, and `if` reads that as "nothing found" — the guard passes loudest
# exactly when it should fail.
# Drop `unzip -l`'s own `Archive:  <name>` header before matching. It names
# the archive being listed, which is not an entry in it — and once the leak
# pattern learned to catch a nested `clauditseo-*.zip`, the header matched
# itself and the script failed on every clean build.
listing=$(unzip -l "$out" | grep -v '^Archive:')
if leaks=$(printf '%s\n' "$listing" \
           | grep -E "\.venv|node_modules|reports/out|\.pytest_cache|benchmarks\.zip|clauditseo-.*\.zip"); then
  echo "packaging leak detected in $out:" >&2
  printf '%s\n' "$leaks" >&2
  exit 1
fi
echo "$out clean ($(du -h "$out" | cut -f1))"
