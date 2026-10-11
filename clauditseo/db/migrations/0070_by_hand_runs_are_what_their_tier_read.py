"""Record a by-hand run as what its tier read, not as `full` (item 253).

The launch route recorded every audit that named no scope as `full`: a
by-hand T1 (one page), a by-hand T2 (the site sample) and the adaptive pulse
alike. A `full` run is a reading of the site, so a one-page run replaced the
Latest View's crawl-relative blocks, became a reference run, and its silence
cleared cross-page findings it never looked for.

The route derives the scope from the tier now. This repairs the rows it
already wrote, and only those: an audit stored as `full` with no depth is a
run that named neither (the chooser always names both; a caller that posted
`scope: full` runs at T3 and stays `full` under the same map). Each row it
relabels is marked `scope_source = derived-from-tier`, the marker the route
writes from now on. The depth is written where it is a fact - no analyst is
Quick - and left NULL where a model ran, because which model is not on the
row.

It also fills `known_paths` (0069) for every run with stored evidence: the
page floor's denominator, from the run's own sitemaps or its own crawl.

Then the Latest View of every site with a run is rebuilt, because which run
may write a block is a write rule - the label and the floor both - and a
change to a write rule ships with a rebuild rather than a hand patch.
Idempotent: a repaired row no longer matches, a filled count is not
refilled, and a site where neither happened is not rebuilt.
"""

import logging

log = logging.getLogger(__name__)

SCOPE_FOR_TIER = {"T1": "page", "T2": "site", "T3": "full"}


def apply(conn) -> None:
    from clauditseo.persistence import runs

    sites: set[str] = set()
    rows = conn.execute(
        "SELECT id, site_id, tier, analyst_enabled FROM audit_runs"
        f" WHERE {runs.kind_in_site_reading_kinds()} AND scan_scope='full'"
        " AND scan_depth IS NULL").fetchall()
    for run_id, site_id, tier, analyst in rows:
        scope = SCOPE_FOR_TIER.get(tier)
        if scope is None:
            continue
        conn.execute("UPDATE audit_runs SET scan_scope=?, scope_source=?,"
                     " scan_depth=COALESCE(scan_depth, ?) WHERE id=?",
                     (scope, runs.SCOPE_DERIVED, None if analyst else "quick", run_id))
        sites.add(site_id)

    for run_id, site_id in conn.execute(
            "SELECT id, site_id FROM audit_runs"
            " WHERE known_paths IS NULL AND crawled_paths IS NOT NULL").fetchall():
        try:
            known = runs.known_paths_of(runs.get_evidence(conn, run_id))
        except Exception:                                    # noqa: BLE001
            known = None
        if known is not None:
            conn.execute("UPDATE audit_runs SET known_paths=? WHERE id=?", (known, run_id))
            sites.add(site_id)

    if not sites or not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='latest_view'").fetchone():
        return
    from clauditseo.persistence import latest_view
    for site_id in sorted(sites):
        before = latest_view.snapshot(conn, site_id)["items"]
        after = latest_view.rebuild(
            conn, site_id, "0070: by-hand runs recorded as what their tier read,"
                           " and the page floor")["items"]
        moved = sorted(key for (kind, key), (_, run) in after.items()
                       if kind == "block" and before.get((kind, key), (None, None))[1] != run)
        log.info("0070: site %s rebuilt; blocks with a new reference run: %s",
                 site_id, ", ".join(moved) or "none")
