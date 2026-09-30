"""Backfill `scan_scope` on runs from before the column - brief v3 step I.

`0032` added the column and the chooser has written it since, but every run
on the operator's database predates it, so `scan_scope` was NULL on all of
them and the dashboard fell back to the tier: any non-T1 run was taken as
site-wide. A T2 run of 2026-09-02 that fetched the navigation set - twenty
pages - stood as the latest site-wide crawl, and the record marked 207 of
227 pages "not in latest crawl" on every group.

The crawl's own page count says what the run was, so that is what is
written: one page fetched is a page scan; up to twenty-five pages on a run
that was not T3 is a navigation scan; anything else is left NULL, where the
readers' shared rule (`runs.scope_of`) decides by count at read time. Only
audits: a verification or a refresh is narrow by kind already.
"""

import json

from clauditseo.persistence.runs import kind_in_site_reading_kinds

MAX_NAV_PATHS = 25


def apply(conn) -> None:
    rows = conn.execute(
        "SELECT id, tier, crawled_paths FROM audit_runs"
        f" WHERE {kind_in_site_reading_kinds()} AND scan_scope IS NULL AND crawled_paths IS NOT NULL"
    ).fetchall()
    for row in rows:
        try:
            n = len(json.loads(row[2]))
        except (TypeError, ValueError):
            continue
        scope = ("page" if n == 1
                 else "nav" if 1 < n <= MAX_NAV_PATHS and row[1] != "T3"
                 else None)
        if scope:
            conn.execute("UPDATE audit_runs SET scan_scope=? WHERE id=?", (scope, row[0]))
