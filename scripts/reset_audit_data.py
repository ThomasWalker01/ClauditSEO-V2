"""Drop every stored audit artifact, keeping the configuration that produced it.

Findings, runs, scores and briefs are *derived* — a crawl can produce them
again. Clients, sites, operators, schedules and notes are typed in by hand and
cannot. So this clears the first and keeps the second.

Why it exists at all: the readers of stored runs had accumulated fallbacks for
runs written before some field was added — "if this run has no page count, use
the finding count instead". A substituted value is indistinguishable from a
measured one, which is how a table shipped "21 of 20 pages". Clearing the old
shapes is what makes it safe to delete those fallbacks, so this script and
that deletion belong to the same change.

It is not a migration and must not become one. If stored data ever matters,
the answer is a numbered migration under ``clauditseo/db/migrations/`` plus an
ENGINE_VERSION bump, not this.

    python scripts/reset_audit_data.py               # report only
    python scripts/reset_audit_data.py --apply       # do it

Back the database up first. `--apply` cannot be undone from inside the app.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clauditseo.config import settings                      # noqa: E402
from clauditseo.db.connection import connect                # noqa: E402

#: Derived from a crawl, so reproducible. Ordered child-first: the schema has
#: real foreign keys and deleting a run out from under its findings fails.
DERIVED = (
    "cost_entries",
    "expert_reports",
    "reports",
    "metric_snapshots",
    "findings",
    "finding_states",
    "audit_runs",
    "analyst_cache",
)

#: Typed in by a person. A crawl cannot recreate these, so they stay.
KEPT = ("operators", "clients", "sites", "tool_schedules", "notes")


def counts(conn, tables) -> dict[str, int]:
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in tables}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="actually delete (default is to report only)")
    ap.add_argument("--db", help="database path (default: configured)")
    args = ap.parse_args()

    db = Path(args.db) if args.db else settings().db_path
    conn = connect(db)

    going = counts(conn, DERIVED)
    staying = counts(conn, KEPT)

    print(f"{db}\n")
    print("  removed (a crawl can produce these again):")
    for t, n in going.items():
        print(f"    {n:7}  {t}")
    print("\n  kept (nothing can produce these again):")
    for t, n in staying.items():
        print(f"    {n:7}  {t}")

    spend = conn.execute(
        "SELECT COALESCE(SUM(actual_cost), 0) FROM cost_entries").fetchone()[0]
    if spend:
        print(f"\n  Note: the ledger holds {spend:.2f} of recorded spend. That "
              "history goes with it.")

    if not args.apply:
        print("\nReport only. Re-run with --apply.")
        return 0

    with conn:
        for table in DERIVED:
            conn.execute(f"DELETE FROM {table}")
    conn.execute("VACUUM")

    left = counts(conn, DERIVED)
    assert not any(left.values()), f"not empty: {left}"
    print(f"\nCleared. {sum(staying.values())} configuration row(s) untouched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
