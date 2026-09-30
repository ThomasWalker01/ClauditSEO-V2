"""One-shot: give every deliverable on disk a row in the `reports` register.

WF-75. `generate()` now writes the document and its row in one transaction, so
no new orphan can appear. This recovers the ones that already exist — measured
on the operator's instance on 21 August 2026 as 35 documents against 13 rows,
of which 9 orphans are client-facing comparison documents for a live client and
13 are `fixture-test-*` residue that predates the `OUT_DIR` redirect now in
`tests/conftest.py`.

Safe to run twice: a document that already has a row is left alone.

    .venv\\Scripts\\python.exe scripts\\adopt_reports.py [--dry-run]

**Read the outcome from the table, not from this script's output.** A pass that
prints "adopted 9" while writing rows whose `path` does not resolve looks
identical from the console, which is why `--dry-run` exists and why the closing
check below is a query rather than a tally of what was printed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from clauditseo.config import Settings  # noqa: E402
from clauditseo.db.connection import connect  # noqa: E402
from clauditseo.reporting.generate import OUT_DIR, adopt_orphans  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be adopted and change nothing")
    args = ap.parse_args()

    conn = connect(Settings().db_path)
    try:
        before = conn.execute("SELECT COUNT(1) FROM reports").fetchone()[0]
        on_disk = len(list(OUT_DIR.glob("*.md"))) if OUT_DIR.is_dir() else 0
        print(f"{on_disk} document(s) in {OUT_DIR}, {before} row(s) in `reports`")

        # `dry_run` is passed down rather than wrapped in a transaction here.
        # The first version of this script did the latter — BEGIN, adopt,
        # rollback — and it silently wrote: `adopt_orphans` commits per row,
        # so the rollback had nothing left to undo. It printed "nothing
        # written" while taking the live table from 13 rows to 22. Do not
        # reintroduce it; the reasoning is in `adopt_orphans`' docstring.
        result = adopt_orphans(conn, dry_run=args.dry_run)

        for row in result["adopted"]:
            runs = ", ".join(r[:8] for r in row["run_ids"])
            print(f"  adopt  {Path(row['path']).name}  "
                  f"{row['created_at']}  runs: {runs}")
        for row in result["skipped"]:
            # ASCII only: this prints to a Windows console at cp1252, where an
            # em dash arrives as a replacement character (KI-39's hazard, one
            # layer out). Observed on the first run of this script.
            print(f"  skip   {Path(row['path']).name}  - {row['reason']}")

        after = conn.execute("SELECT COUNT(1) FROM reports").fetchone()[0]
        missing = [r["path"] for r in conn.execute("SELECT path FROM reports")
                   if not Path(r["path"]).exists()]
        print(f"\nadopted {len(result['adopted'])}, "
              f"skipped {len(result['skipped'])}, "
              f"`reports` now holds {after} row(s)"
              + (" (dry run - nothing written)" if args.dry_run else ""))
        if missing:
            print(f"WARNING: {len(missing)} row(s) name a file that does not "
                  f"exist: {missing[:3]}")
            return 1
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
