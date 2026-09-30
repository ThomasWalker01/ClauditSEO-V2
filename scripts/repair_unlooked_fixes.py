"""Reopen findings a run marked fixed on pages it never fetched.

The bug this repairs is closed — `_apply_states` now requires a finding's page
to be in the run's crawl before it may be cleared — but the damage it did is
still in the record and nothing back-dated fixes it.

The shape of it: a 20-page nav crawl of a 100-page site marked every open
finding it did not see again as fixed, including 356 on the 80 pages it never
requested. "We looked and it is gone" and "we did not look" are different
statements, and only the first may clear a finding.

Left alone this compounds. The next full crawl finds all 356 again and, because
the record says they were fixed, calls them REGRESSED — a wave of alarms
describing a return that never happened, on top of a repair that never
happened.

So they go back to `open`, not to `regressed` and not to `fixed`:

  - `open` is what is actually known. The finding was raised, nothing has
    since looked at its page, so it stands.
  - `regressed` would assert a fix and a relapse, neither evidenced.
  - the exact prior state is unrecoverable — `finding_states` keeps one row
    per finding with no history — so a finding that had genuinely regressed
    before this comes back as `open`. That loses a nuance rather than
    inventing one.

`attempted_at` and `attempt_note` are carried through untouched: the operator's
"I have fixed this" is their claim, and this script is correcting the crawler's
claim, not theirs.

`changed_by_run` is cleared, because no run judged these — saying "run X
decided this" would be the same kind of false attribution being repaired.

Reopening is the whole job. What is actually true of those pages *now* is a
question for a crawl, so follow this with a verification (or any full audit)
and let the evidence decide. Doing it in that order matters: verify first and
every reappearance is recorded as a regression.

Usage, from the repo root:

    python scripts/repair_unlooked_fixes.py                 # report only
    python scripts/repair_unlooked_fixes.py --apply         # write
    python scripts/repair_unlooked_fixes.py --site <id>     # one site

Back the database up first; this rewrites rows.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clauditseo.config import settings                      # noqa: E402
from clauditseo.db.connection import connect                # noqa: E402
from clauditseo.persistence import runs                     # noqa: E402
from clauditseo.persistence.repo import now_iso             # noqa: E402


def crawled_paths(conn, run_id: str) -> set[str]:
    """The paths a run actually fetched, from its own stored evidence."""
    row = conn.execute("SELECT crawl_evidence FROM audit_runs WHERE id=?",
                       (run_id,)).fetchone()
    try:
        blob = json.loads(row["crawl_evidence"]) if row else {}
    except (TypeError, ValueError):
        return set()
    return {urlsplit(p["url"]).path or "/" for p in (blob or {}).get("pages") or []}


def unlooked(conn, site_id: str | None = None) -> list[dict]:
    """Findings sitting at `fixed` whose clearing run never fetched their page.

    Deliberately the same test `_apply_states` now applies, stated the same
    way — a finding that names no page is site-scoped, so the dimension having
    run *is* the whole test and its clearing stands.
    """
    where = "fs.state='fixed' AND fs.changed_by_run IS NOT NULL"
    args: tuple = ()
    if site_id:
        where += " AND fs.site_id=?"
        args = (site_id,)
    rows = conn.execute(
        f"""SELECT fs.site_id, fs.fingerprint, fs.changed_by_run, fs.attempted_at,
                   f.check_id, f.dimension, f.affected_urls
            FROM finding_states fs
            JOIN findings f ON f.rowid = ({runs._latest_finding()})
            WHERE {where}""", args).fetchall()

    cache: dict[str, set[str]] = {}
    out = []
    for r in rows:
        run_id = r["changed_by_run"]
        if run_id not in cache:
            cache[run_id] = crawled_paths(conn, run_id)
        crawled = cache[run_id]
        if not crawled:
            # No evidence stored at all. That is a different unknown — it may
            # be an imported crawl — so it is left alone rather than reopened
            # on a guess.
            continue
        urls = json.loads(r["affected_urls"] or "[]")
        pages = {urlsplit(u).path or "/" for u in urls if u.startswith("http")}
        if pages and not (pages & crawled):
            out.append(dict(r))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="write the changes (default is to report only)")
    ap.add_argument("--site", help="limit to one site id")
    ap.add_argument("--db", help="database path (default: configured)")
    args = ap.parse_args()

    db = Path(args.db) if args.db else settings().db_path
    conn = connect(db)
    found = unlooked(conn, args.site)

    if not found:
        print(f"{db}: nothing to repair.")
        return 0

    from collections import Counter
    by_site = Counter(r["site_id"] for r in found)
    by_run = Counter(r["changed_by_run"] for r in found)
    by_check = Counter(r["check_id"] for r in found)

    print(f"{db}")
    print(f"{len(found)} finding(s) marked fixed by a run that never fetched "
          f"their page.\n")
    for site, n in by_site.most_common():
        dom = conn.execute("SELECT domain FROM sites WHERE id=?",
                           (site,)).fetchone()
        print(f"  site {dom['domain'] if dom else site}: {n}")
    print("\n  by clearing run:")
    for run_id, n in by_run.most_common():
        row = conn.execute("SELECT tier, started_at FROM audit_runs WHERE id=?",
                           (run_id,)).fetchone()
        print(f"    {run_id[:8]} {row['tier']} {row['started_at'][:19]}  {n}")
    print("\n  by check:")
    for check, n in by_check.most_common(15):
        print(f"    {n:5}  {check}")
    kept = sum(1 for r in found if r["attempted_at"])
    print(f"\n  {kept} of these carry an operator's fix attempt; it is kept.")

    if not args.apply:
        print("\nReport only. Re-run with --apply to reopen them.")
        return 0

    stamp = now_iso()
    with conn:
        conn.executemany(
            "UPDATE finding_states SET state='open', changed_by_run=NULL,"
            " updated_at=? WHERE site_id=? AND fingerprint=?",
            [(stamp, r["site_id"], r["fingerprint"]) for r in found])
    print(f"\nReopened {len(found)}. Now crawl those pages — a verification or "
          "a full audit — and let it decide what is actually still there.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
