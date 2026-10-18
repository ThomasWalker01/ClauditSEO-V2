"""Split the stored check-level Links findings into one per page (item 251
step 4, channel answer 20261002-1215).

`LinksModule` filed each graph check once, with every page in
`affected_urls` and the check's own id as the subject. It files one finding
per page now, so a page leaving the orphan list closes its row and a page
joining it opens one, and the part's PAGES is one shape with the analysis's
per-page rows. This brings the stored runs to the same shape, so the Latest
View replays one history and nothing reads as fixed-then-new at the next
audit:

- each check-level row becomes one row per page it named, in the same run,
  with the same severity and recommendation and a summary that says what the
  check says about THAT page;
- an operator judgement recorded against the old fingerprint applies to every
  page the finding named at the time, so each page's fingerprint gets the
  same event with the same date. The original event is kept; history is
  added to, not rewritten;
- the Latest View of each site touched is rebuilt, after the split and only
  then.

Stored scores are not recomputed: a score from before engine 0.29.0 stands
as it was computed, and the trend's engine break says why the next differs.
`hub-unlinked` was already filed per entity and is left alone.

Idempotent: a row whose fingerprint is not the check-level one is skipped.
"""

import json
import logging
import uuid
from urllib.parse import urlsplit

log = logging.getLogger(__name__)

CHECKS = ("orphan", "inlinks-low", "anchor-generic", "anchor-duplicate-target",
          "nofollow-internal", "broken-internal", "redirect-chain", "depth-deep")

#: What each check says about one page. The stored row kept only the graph
#: sentence ("3 pages nothing links to"), so the per-page counts a fresh run
#: now states (how many body links, how many clicks) are not recoverable and
#: are not invented.
SUMMARY = {
    "orphan": "No other page links to {path}.",
    "inlinks-low": "{path} has too few internal links from body copy.",
    "anchor-generic": "Internal links on {path} have anchor text that says nothing "
                      "about the page they point at.",
    "anchor-duplicate-target": "{path} is linked with an anchor phrase that also points "
                               "at another page.",
    "nofollow-internal": "Internal links on {path} carry rel=nofollow.",
    "broken-internal": "{path} is linked internally and returns an error.",
    "redirect-chain": "{path} is linked internally and reached through more than one redirect.",
    "depth-deep": "{path} is too many clicks from the home page.",
}


def _path(url: str) -> str:
    try:
        return urlsplit(url).path or "/"
    except ValueError:
        return url


def apply(conn) -> None:
    from clauditseo.engine.types import fingerprint

    old_fp = {c: fingerprint("LNK", c, c) for c in CHECKS}
    marks = ", ".join("?" for _ in CHECKS)
    rows = conn.execute(
        "SELECT f.id, f.run_id, f.check_id, f.severity, f.source, f.model_id, f.confidence,"
        " f.affected_urls, f.evidence, f.recommendation, f.fingerprint, f.created_at,"
        " a.site_id, COALESCE(a.finished_at, a.started_at) AS run_at"
        " FROM findings f JOIN audit_runs a ON a.id = f.run_id"
        f" WHERE f.dimension='LNK' AND f.source='deterministic' AND f.check_id IN ({marks})",
        CHECKS).fetchall()
    # (site, old fingerprint) -> [(run date, [new fingerprints])], for the events.
    named: dict[tuple[str, str], list[tuple[str, list[str]]]] = {}
    sites: set[str] = set()
    split = 0
    for r in rows:
        (fid, run_id, check, severity, source, model_id, confidence, raw_urls, evidence,
         recommendation, fp, created_at, site_id, run_at) = r
        if fp != old_fp[check]:
            continue                                   # already one per page
        try:
            urls = json.loads(raw_urls or "[]")
        except ValueError:
            urls = []
        if not urls:
            continue                                   # names no page: nothing to split it into
        try:
            ev = json.loads(evidence or "{}")
        except ValueError:
            ev = {}
        new_fps = []
        for url in urls:
            path = _path(url)
            new_fp = fingerprint("LNK", check, path)
            new_fps.append(new_fp)
            conn.execute(
                "INSERT INTO findings (id, run_id, dimension, check_id, severity, source,"
                " model_id, confidence, summary, affected_urls, affected_total, evidence,"
                " recommendation, fingerprint, created_at)"
                " VALUES (?, ?, 'LNK', ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)",
                (uuid.uuid4().hex, run_id, check, severity, source, model_id, confidence,
                 SUMMARY[check].format(path=path), json.dumps([url]),
                 json.dumps({**(ev if isinstance(ev, dict) else {}), "split_from": fp}),
                 recommendation, new_fp, created_at))
        conn.execute("DELETE FROM findings WHERE id=?", (fid,))
        named.setdefault((site_id, fp), []).append((run_at or "", new_fps))
        sites.add(site_id)
        split += 1
    if not split:
        return

    has_events = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table'"
                              " AND name='state_events'").fetchone()
    carried = 0
    if has_events:
        for (site_id, fp), history in named.items():
            history.sort()
            for e in conn.execute(
                    "SELECT kind, from_state, to_state, note, by_operator, at FROM state_events"
                    " WHERE site_id=? AND fingerprint=? ORDER BY at, id", (site_id, fp)).fetchall():
                # The pages the finding named when the judgement was made: the
                # newest run at or before it, else the earliest there is.
                at_or_before = [fps for run_at, fps in history if run_at <= e[5]]
                for new_fp in (at_or_before[-1] if at_or_before else history[0][1]):
                    conn.execute(
                        "INSERT INTO state_events (site_id, fingerprint, kind, from_state,"
                        " to_state, note, by_operator, at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (site_id, new_fp, *e))
                    carried += 1
    # The check-level state rows have no findings behind them now; the rebuild
    # below writes each page's from the runs and the events.
    for (site_id, fp) in named:
        conn.execute("DELETE FROM finding_states WHERE site_id=? AND fingerprint=?", (site_id, fp))

    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table'"
                    " AND name='latest_view'").fetchone():
        from clauditseo.persistence import latest_view
        for site_id in sorted(sites):
            latest_view.rebuild(conn, site_id,
                                "0073: stored Links findings split one per page",
                                {"findings_split": split, "judgements_carried": carried})
    log.info("0073: %d check-level Links findings split per page; %d judgements carried",
             split, carried)
