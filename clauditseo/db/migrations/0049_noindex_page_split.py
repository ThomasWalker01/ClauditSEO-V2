"""Re-home stored `noindex-page` findings into the split checks (item 137,
brief v18 step BA).

`noindex-page` was one HIGH blocker on any page whose meta robots said noindex,
with a summary that asserted "internally linked" without ever counting inlinks.
Step BA splits it by what is actually true of the page:

  - `noindex-linked` — noindex AND linked from >= 3 pages — HIGH, and the
    blocker (the real problem: a page you point at and tell Google to drop);
  - `noindex-in-sitemap` — noindex AND declared in the sitemap — LOW;
  - a noindex page that is neither is retired: it was the false HIGH the split
    exists to remove.

This migration reclassifies each stored `noindex-page` finding the same way the
new sweep does, from its own run's crawl evidence, and carries `finding_states`
so the standing reconciles. The classification reads the identical inputs as
`tec.TechnicalModule.run` — `evidence.inlinks` (page.outlinks, self excluded)
and sitemap membership by `tec._norm_path` — so a row this moves and a row the
next run stores land on the same check and the same fingerprint.

**The fingerprint changes because the check id does.** Identity is
`sha256("TEC:<check>:<subject>")[:24]`; the subject (the page path) does not
change, so the new id is reproducible and the inverse is the map read backwards.
A row is only rewritten when the stored fingerprint is the one
`fingerprint("TEC", "noindex-page", path)` reproduces from the row's own URL —
the guard that the subject derivation matches what the recorder used.

**Severity moves with the check** (HIGH stays HIGH for linked; a sitemap-only
row drops to LOW), because a stored severity is what the score reads. The
summary is refreshed too, so a re-homed row does not display the old
"internally linked" claim it never verified.
"""

import json
import logging

LOG = logging.getLogger(__name__)


def apply(conn) -> None:
    from urllib.parse import urlsplit

    from clauditseo.crawler.evidence import inlinks as ev_inlinks
    from clauditseo.engine.types import fingerprint
    from clauditseo.linksuggest import MIN_INLINKS
    from clauditseo.modules.tec import _norm_path

    rows = conn.execute(
        "SELECT f.id, f.run_id, f.fingerprint, f.affected_urls, a.site_id"
        " FROM findings f JOIN audit_runs a ON a.id = f.run_id"
        " WHERE f.dimension='TEC' AND f.check_id='noindex-page'"
        "   AND f.source='deterministic'").fetchall()

    # Cache each run's inlink graph and sitemap set — several findings can share
    # a run.
    run_cache: dict[str, tuple[dict, set]] = {}

    def _run_data(run_id):
        if run_id not in run_cache:
            row = conn.execute("SELECT crawl_evidence FROM audit_runs WHERE id=?",
                               (run_id,)).fetchone()
            ev = {}
            if row and row["crawl_evidence"]:
                try:
                    ev = json.loads(row["crawl_evidence"])
                except (TypeError, ValueError):
                    ev = {}
            graph = ev_inlinks(ev)
            sm = {_norm_path(u) for u in ev.get("sitemap_entries", [])}
            run_cache[run_id] = (graph, sm)
        return run_cache[run_id]

    linked = insitemap = retired = skipped = 0
    fp_map: dict[tuple[str, str], str | None] = {}
    for r in rows:
        urls = json.loads(r["affected_urls"] or "[]")
        if not urls:
            skipped += 1
            continue
        url = urls[0]
        subj = urlsplit(url).path or "/"
        if fingerprint("TEC", "noindex-page", subj) != r["fingerprint"]:
            LOG.warning("0049: finding %s fingerprint not reproduced from its URL; "
                        "left as noindex-page", r["id"])
            skipped += 1
            continue

        graph, sm = _run_data(r["run_id"])
        sources = {s for s in graph.get(url, []) if s != url}
        path = subj if subj == "/" else subj.rstrip("/")

        if len(sources) >= MIN_INLINKS:
            new_check, sev = "noindex-linked", "high"
            summary = (f"{subj} carries a noindex directive but is linked from "
                       f"{len(sources)} pages — confirm this is intentional.")
            linked += 1
        elif _norm_path(url) in sm:
            new_check, sev = "noindex-in-sitemap", "low"
            summary = (f"{subj} is declared in the sitemap but carries a noindex "
                       "directive — the sitemap invites indexing the page refuses.")
            insitemap += 1
        else:
            # Neither linked nor in the sitemap: the false HIGH the split removes.
            conn.execute("DELETE FROM findings WHERE id=?", (r["id"],))
            fp_map[(r["site_id"], r["fingerprint"])] = None
            retired += 1
            continue

        new_fp = fingerprint("TEC", new_check, subj)
        conn.execute(
            "UPDATE findings SET check_id=?, severity=?, fingerprint=?, summary=? WHERE id=?",
            (new_check, sev, new_fp, summary, r["id"]))
        fp_map[(r["site_id"], r["fingerprint"])] = new_fp

    for (site_id, old_fp), new_fp in fp_map.items():
        if new_fp is None:
            conn.execute("DELETE FROM finding_states WHERE site_id=? AND fingerprint=?",
                         (site_id, old_fp))
        else:
            conn.execute(
                "UPDATE OR REPLACE finding_states SET fingerprint=?"
                " WHERE site_id=? AND fingerprint=?", (new_fp, site_id, old_fp))

    LOG.info("0049: split %d noindex-page findings — %d -> noindex-linked, "
             "%d -> noindex-in-sitemap, %d retired, %d left in place",
             len(rows), linked, insitemap, retired, skipped)
