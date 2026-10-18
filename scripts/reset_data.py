"""Reset the stored audit data, keeping the record (brief v11 step AK).

The check set, the severities, the row unit and the source column changed
under brief v11, so stored findings, reports and deliverables no longer
match the structures that read them. This resets rather than migrates:
every run and everything keyed on one goes, and a verified snapshot is
taken first so nothing is lost.

    python scripts/reset_data.py             # report only
    python scripts/reset_data.py --backup    # snapshot, then reset

Removed: audit_runs, findings, finding_states, expert_reports, the
deliverables (reports), prechecks, metric_snapshots, and any other table
carrying a run_id column. Kept: sites with their local-SEO record,
clients, operators, Admin settings (app_prefs, brand), brief defaults
(brief_models, tier_models), prices, fx rates, schedules and notes. The
analyst cache is keyed on the prompt bundle, not a run, and stays: the
rewritten prompts never hit it.

Not a migration and must not become one - see reset_audit_data.py.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clauditseo.config import settings                      # noqa: E402
from clauditseo.db.connection import connect                # noqa: E402
from clauditseo.persistence import backup                   # noqa: E402

#: Named by the brief. Child-first: the schema has real foreign keys.
NAMED = ("finding_states", "expert_reports", "findings", "reports",
         "prechecks", "metric_snapshots", "audit_runs")

#: Typed in or configured by a person; nothing derives them again.
KEPT = ("operators", "clients", "sites", "tool_schedules", "notes", "app_prefs",
        "brand", "brief_models", "tier_models", "model_prices", "fx_rates",
        "analyst_cache", "schema_migrations")


def run_keyed(conn: sqlite3.Connection) -> list[str]:
    """Every table with a run_id column, whatever migration added it."""
    found = []
    for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"
                                " AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({name})")}
        if "run_id" in cols and name not in NAMED:
            found.append(name)
    return found


def counts(conn, tables) -> dict[str, int]:
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backup", action="store_true",
                    help="take a verified snapshot under data/backups, then reset")
    ap.add_argument("--db", help="database path (default: configured)")
    args = ap.parse_args()

    db = Path(args.db) if args.db else settings().db_path
    conn = connect(db)
    going_tables = run_keyed(conn) + list(NAMED)
    going = counts(conn, going_tables)
    staying = counts(conn, [t for t in KEPT
                            if conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (t,)).fetchone()])

    print(f"{db}\n")
    print("  removed (a crawl and a brief produce these again):")
    for t, n in going.items():
        print(f"    {n:7}  {t}")
    print("\n  kept (the record and the configuration):")
    for t, n in staying.items():
        print(f"    {n:7}  {t}")

    if not args.backup:
        print("\nReport only. Re-run with --backup to snapshot and reset.")
        return 0

    snap = backup.create_backup(conn, db)
    if snap.get("status") != "ok":
        print(f"\nBackup failed, nothing removed: {snap}")
        return 1
    print(f"\n  backup: {snap['path']} ({snap['bytes']} bytes, integrity {snap['integrity']})")

    with conn:
        for table in going_tables:
            conn.execute(f"DELETE FROM {table}")
    conn.execute("VACUUM")
    left = counts(conn, going_tables)
    assert not any(left.values()), f"not empty: {left}"
    print(f"\nReset. {sum(going.values())} row(s) removed across {len(going_tables)} tables;"
          f" {sum(staying.values())} row(s) of record and configuration untouched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
