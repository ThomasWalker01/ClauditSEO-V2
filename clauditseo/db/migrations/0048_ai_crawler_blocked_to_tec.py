"""Re-home `ai-crawler-blocked` from AIS to TEC (item 137, brief v18 step AZ).

A robots.txt rule blocking the AI retrieval agents is a crawl-access failure
by cause, so the check now scores under TEC — the technical subscore — beside
`robots-missing`, not under AIS whose subscore is the site's answer surface.
The 2026-09-09 split (596c9f4) filed it under the Crawl part page while keeping
its weight on AIS (file by cause, score by consequence); the operator completed
the re-home here and owns the score move: a site whose only AI-surface failing
was a blocked crawler scores better on AI surface, and worse on Technical,
without the site having changed.

**The fingerprint changes, and the standing moves with it.** A deterministic
finding's identity is `sha256("<dimension>:<check>:<subject>")[:24]`
(`engine.types.fingerprint`). The dimension changes AIS→TEC, so every moved row
gets a new id. `finding_states` is keyed on that id, so its row is renamed in
step — the open/accepted state, the attempt note and the history follow the
finding to its new identity, which is what "the standing position must
reconcile exactly" requires. The part page is unaffected: it buckets by check
id (`anatomy.categorise`), and the check id does not change — it was already
filed under Crawl by the 2026-09-09 split.

**Guarded, and reversible by computation.** The check's subject is always
`ai-crawler-access`, so the pre-move fingerprint is a single constant this
migration reproduces from `fingerprint('AIS', 'ai-crawler-blocked',
'ai-crawler-access')`. A row is rewritten only when its stored fingerprint is
that value — a row this cannot reproduce is left alone, so the move is exact
where it acts. The inverse is the same map read backwards:
`dimension='AIS'`, `fingerprint=fingerprint('AIS', 'ai-crawler-blocked',
'ai-crawler-access')`. Nothing is stored to undo it.
"""

import logging

LOG = logging.getLogger(__name__)


def apply(conn) -> None:
    from clauditseo.engine.types import fingerprint

    old_fp = fingerprint("AIS", "ai-crawler-blocked", "ai-crawler-access")
    new_fp = fingerprint("TEC", "ai-crawler-blocked", "ai-crawler-access")

    # Findings: only the deterministic AIS rows whose stored fingerprint is the
    # one this check's fixed subject reproduces. `check_id` does not change.
    rows = conn.execute(
        "SELECT f.id, a.site_id FROM findings f JOIN audit_runs a ON a.id = f.run_id"
        " WHERE f.dimension='AIS' AND f.check_id='ai-crawler-blocked'"
        "   AND f.source='deterministic' AND f.fingerprint=?", (old_fp,)
    ).fetchall()

    sites = set()
    for r in rows:
        conn.execute("UPDATE findings SET dimension='TEC', fingerprint=? WHERE id=?",
                     (new_fp, r["id"]))
        sites.add(r["site_id"])

    # finding_states: one row per (site, id) across runs. OR REPLACE for the
    # identity change; the new id is fresh (no TEC row carried this check before
    # this migration), so nothing is displaced.
    renamed = 0
    for site_id in sites:
        cur = conn.execute(
            "UPDATE OR REPLACE finding_states SET fingerprint=?"
            " WHERE site_id=? AND fingerprint=?", (new_fp, site_id, old_fp))
        renamed += cur.rowcount

    LOG.info("0048: re-homed %d ai-crawler-blocked findings AIS->TEC "
             "(%d finding_states renamed across %d site(s))",
             len(rows), renamed, len(sites))
