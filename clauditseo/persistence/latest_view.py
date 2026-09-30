"""The Latest View: the site's one current record (item 239, the operator's
ruling of 2026-09-24).

> "Rather than stitch together a report, the report can run independently,
> then just update a complete record that is 'The Latest View'. This way it
> is the reference point that can always be counted on."

Runs stay independent and complete; a run's own record is the history view.
The Latest View is ONE record per site that a finished run updates, under
write rules, and that screens and reports read in the current view. It is
derived, never the only copy: `rebuild` replays it from the site's runs and
the operator's judgements (`state_events`) in time order, and a change to a
write rule ships with a rebuild rather than a hand patch.

Two halves:

- **The ledger** is `finding_states`, as it always was. A run's step of it is
  `runs._advance_states`, which the live completion and this replay both
  call, so the two cannot drift; item 240's `runs.measured` decides what a
  run may clear. The analyses' own walks run after, as live.
- **The items** are `latest_view` rows, each with the run that measured it
  and when:

    page       key = path. Page-intrinsic fields, each written only by a run
               whose dimensions include the field's owner and which read the
               page (`PAGE_FIELDS`); the trace by a run that traced it; image
               weights by a run that weighed them. Merged per field: a newer
               run that measured a field replaces it, one that did not leaves
               it.
    block      key = dimension. The dimension's reference crawl: the newest
               reading of the whole site that measured it. Crawl-relative
               facts (the link graph, depth, duplicates, sitemap coverage, the
               URL pattern table, template speed) are read whole from that
               run, never merged page by page. Two more keys for a block that
               needs an instrument as well as a dimension (amendment 4):
               `images`, the newest site reading that weighed images, and
               `trace`, the newest that traced. Twenty22's ONP reference is an
               ONP-only T2 that weighed nothing; its images block is T3's.
    analysis   key = tool. The newest run of each analysis.
    composite  key = "current". The reference audit's composite: the newest
               site reading whose dimensions cover the current one's. Never
               synthesised across runs.

Nothing here draws a screen yet (step 1): the operator is shown the rebuilt
record for twenty22 before any screen reads it.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from . import runs
from .repo import now_iso

#: Which dimension measures each page-intrinsic field of the crawl evidence
#: (amendment 3 of item 239). A field is written by a run whose dimensions
#: include its owner and which read the page. Crawl-relative page fields -
#: `click_depth`, `outlinks`, `links`, `discovered_via` - are not here: they
#: are the reference crawl's (`block`), never merged per page.
PAGE_FIELDS: dict[str, tuple[str, ...]] = {
    "ONP": ("title", "meta_description", "h1", "headings", "heading_levels",
            "heading_total", "outline", "main_region", "schema_inventory",
            "schema_types", "jsonld_blocks", "jsonld_raw", "profile_links",
            "lang", "hreflang", "images", "image_inventory", "image_total"),
    "TEC": ("status", "canonical", "link_header_canonical", "meta_robots",
            "x_robots_tag", "redirect_chain", "redirect_statuses", "headers",
            "viewport_tags", "content_type", "indexability", "elapsed_ms"),
    "A11Y": ("a11y",),
    "CNT": ("word_count", "content_dates", "opening", "content_hash"),
    "LOC": ("nap_mentions", "local_schema"),
    # What the page links to is the page's own; who links to it is not.
    "LNK": ("links", "outlinks"),
}
#: The fields a fetch measures whatever became of it: a page that answered
#: an error was still read for its status, its redirects and its headers,
#: and a page record that forgot them would say nothing about why it failed.
FETCH_FIELDS = ("status", "redirect_chain", "redirect_statuses", "headers", "content_type")
#: What the browser image pass adds to an inventory row. Written as
#: `image_weights` only by a run that weighed that page's images; the markup
#: half of the row is ONP's `image_inventory`.
IMAGE_MEASURED_KEYS = ("rendered", "intrinsic_w", "intrinsic_h", "weight_kb",
                       "lcp_candidate", "above_fold", "css_aspect_ratio", "top_pct",
                       "weight_source")


def _j(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _put(conn: sqlite3.Connection, site_id: str, kind: str, key: str, value: Any,
         run_id: str | None, at: str | None) -> None:
    conn.execute(
        "INSERT INTO latest_view (site_id, kind, key, value, run_id, measured_at)"
        " VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(site_id, kind, key) DO UPDATE SET"
        " value=excluded.value, run_id=excluded.run_id, measured_at=excluded.measured_at",
        (site_id, kind, key, _j(value), run_id, at))


def _get(conn: sqlite3.Connection, site_id: str, kind: str, key: str) -> dict | None:
    row = conn.execute("SELECT value FROM latest_view WHERE site_id=? AND kind=? AND key=?",
                       (site_id, kind, key)).fetchone()
    return json.loads(row[0]) if row else None


def _run_row(conn: sqlite3.Connection, run_id: str):
    return conn.execute(
        "SELECT id, site_id, kind, status, tier, dimensions, composite_score,"
        " started_at, finished_at, scan_scope, crawled_paths FROM audit_runs WHERE id=?",
        (run_id,)).fetchone()


def apply_run(conn: sqlite3.Connection, run_id: str) -> None:
    """Write what one finished run measured into its site's Latest View.
    The caller holds the transaction (or none; each statement is its own)."""
    row = _run_row(conn, run_id)
    if row is None or row["status"] not in runs.AUDITED_STATUSES or row["status"] == "blocked":
        return
    reading = runs.Reading.of_stored(conn, run_id)
    if reading is None:
        return
    site_id, at = row["site_id"], row["finished_at"] or row["started_at"]
    from urllib.parse import urlsplit

    from clauditseo.crawler.types import stored_page_is_eligible
    evidence = runs.get_evidence(conn, run_id) or {}
    # An import measures no dimension and carries the page facts it carries:
    # an empty dimension list is read as every page field's owner.
    dims = reading.dimensions or frozenset(PAGE_FIELDS)
    for page in evidence.get("pages") or []:
        if not isinstance(page, dict) or not page.get("url"):
            continue
        path = urlsplit(page["url"]).path or "/"
        if not stored_page_is_eligible(page):
            # Read, and failed: its fetch fields only, under TEC's rule.
            if "TEC" in dims:
                written = {f: page[f] for f in FETCH_FIELDS if f in page}
                if written:
                    current = _get(conn, site_id, "page", path) or {}
                    for f, value in written.items():
                        current[f] = {"value": value, "run_id": run_id, "at": at}
                    _put(conn, site_id, "page", path, current, run_id, at)
            continue
        if path not in reading.crawled:
            continue
        written: dict[str, Any] = {}
        for dim, fields in PAGE_FIELDS.items():
            if dim in dims:
                for f in fields:
                    if f in page:
                        value = page[f]
                        if f == "image_inventory":
                            value = [{k: v for k, v in (i or {}).items()
                                      if k not in IMAGE_MEASURED_KEYS} for i in (value or [])]
                        written[f] = value
        if "PRF" in reading.dimensions and path in reading.traced and page.get("perf"):
            written["perf"] = page["perf"]
        if path in reading.imaged:
            # Keyed by the file (item 246): by `src`, every lazy image's
            # weight was filed under one shared `data:` placeholder, and the
            # page card read one image's weight for all of them.
            written["image_weights"] = {
                (i or {}).get("lazy_src") or (i or {}).get("src") or "":
                    {k: i[k] for k in IMAGE_MEASURED_KEYS if k in i}
                for i in (page.get("image_inventory") or []) if isinstance(i, dict)}
        if not written:
            continue
        current = _get(conn, site_id, "page", path) or {}
        for f, value in written.items():
            current[f] = {"value": value, "run_id": run_id, "at": at}
        _put(conn, site_id, "page", path, current, run_id, at)

    # Crawl-relative blocks: only a reading of the whole site, whole.
    if reading.site_reading and row["status"] in runs.SCORED_STATUSES:
        block = {"run_id": run_id, "at": at, "tier": row["tier"], "kind": row["kind"],
                 "pages": len(reading.crawled)}
        for dim in sorted(reading.dimensions):
            _put(conn, site_id, "block", dim, block, run_id, at)
        if reading.imaged:
            _put(conn, site_id, "block", "images", block, run_id, at)
        if reading.traced:
            _put(conn, site_id, "block", "trace", block, run_id, at)
        _presence(conn, site_id, run_id, at, reading, evidence)
        # The reference composite: the newest site reading whose dimensions
        # cover the current reference's (amendment 8). A narrower audit keeps
        # its own composite, shown only in the history view.
        if row["composite_score"] is not None and row["kind"] == "audit":
            held = _get(conn, site_id, "composite", "current")
            if held is None or set(reading.dimensions) >= set(held["dimensions"]):
                _put(conn, site_id, "composite", "current",
                     {"run_id": run_id, "at": at, "tier": row["tier"],
                      "score": row["composite_score"],
                      "dimensions": sorted(reading.dimensions)}, run_id, at)


def _listed(evidence: dict) -> frozenset[str] | None:
    """The paths a crawl's sitemaps listed, or None where their silence about
    a page is not evidence: no sitemap answered, or the list was capped."""
    from urllib.parse import urlsplit
    if not any((s or {}).get("status") == 200 for s in evidence.get("sitemaps") or []):
        return None
    entries = [u for u in evidence.get("sitemap_entries") or [] if isinstance(u, str)]
    if (evidence.get("sitemap_entry_total") or 0) > len(entries):
        return None
    return frozenset(urlsplit(u).path or "/" for u in entries)


def _presence(conn: sqlite3.Connection, site_id: str, run_id: str, at: str,
              reading: runs.Reading, evidence: dict) -> None:
    """Whether each page is still on the site, per dimension (item 243, 239
    amendment 6). One `presence` item per path:

        seen   dim -> when a reference crawl of dim last fetched the page
        gone   dim -> that date, where the newest reference crawl of dim
                      did not fetch the page, an earlier one did, and the
                      newest crawl's sitemap does not list it

    A gone page keeps its last reading and says "not seen since", rather than
    ageing towards "out of date" like a page nobody re-checked. Nothing is
    cleared: its findings keep their states until the operator moves them.

    A crawl that stopped short (`truncated_by`) or could not read a sitemap
    says nothing about the pages it did not reach, so it marks nothing gone.
    Written by the replay exactly as live, so a rebuild derives the same."""
    listed = None if evidence.get("truncated_by") else _listed(evidence)
    known = {r["key"]: json.loads(r["value"]) for r in conn.execute(
        "SELECT key, value FROM latest_view WHERE site_id=? AND kind='presence'", (site_id,))}
    for path in set(known) | set(reading.crawled):
        item = known.get(path) or {"seen": {}, "gone": {}}
        before = _j(item)
        for dim in reading.dimensions:
            if path in reading.crawled:
                item["seen"][dim] = at
                item["gone"].pop(dim, None)
            elif dim in item["seen"] and listed is not None and path not in listed:
                item["gone"].setdefault(dim, item["seen"][dim])
            else:
                item["gone"].pop(dim, None)
        if path not in known or _j(item) != before:
            _put(conn, site_id, "presence", path, item, run_id, at)


def gone(conn: sqlite3.Connection, site_id: str, dimension: str | None = None) -> dict[str, str]:
    """Path -> "not seen since" date, for pages that have left the site as
    `dimension`'s reference crawls saw it; any dimension where None."""
    out: dict[str, str] = {}
    for r in conn.execute("SELECT key, value FROM latest_view WHERE site_id=? AND kind='presence'",
                          (site_id,)):
        g = json.loads(r["value"]).get("gone") or {}
        dates = [g[dimension]] if dimension in g else ([] if dimension else list(g.values()))
        if dates:
            out[r["key"]] = min(dates)
    return out


def reference(conn: sqlite3.Connection, site_id: str, key: str) -> dict | None:
    """The run a block names - a dimension's reference crawl, or `images` /
    `trace` - with its date and tier; None where nothing has measured it.
    What every crawl-relative section reads in the current view (step 2)."""
    block = _get(conn, site_id, "block", key)
    if not block:
        return None
    row = _run_row(conn, block["run_id"])
    if row is None:
        return None
    return {"run_id": row["id"], "at": row["started_at"], "tier": row["tier"],
            "dimensions": json.loads(row["dimensions"] or "[]"), "kind": row["kind"]}


def reference_run(conn: sqlite3.Connection, site_id: str, *keys: str) -> str | None:
    """The first of `keys` that names a run. A block whose instrument never
    ran still has something to say - "no trace was taken", "nobody weighed
    these images" - and it says it from the newest reading that could have:
    Speed asks `trace`, then PRF's reference, then TEC's."""
    for key in keys:
        ref = reference(conn, site_id, key)
        if ref:
            return ref["run_id"]
    return None


def field_run(conn: sqlite3.Connection, site_id: str, url: str, field: str) -> str | None:
    """The run that last measured one field of one page (step 3): what a
    page-scope block drawn from that field's instrument reads."""
    from urllib.parse import urlsplit
    item = _get(conn, site_id, "page", urlsplit(url).path or "/") or {}
    cell = item.get(field)
    return cell["run_id"] if cell else None


def newest_reading(conn: sqlite3.Connection, site_id: str) -> dict | None:
    """The newest reading of the whole site, of any dimension: what the site
    as a whole was last measured by (`_latest_sweep` with no dimension)."""
    newest = None
    for r in conn.execute("SELECT key, value FROM latest_view WHERE site_id=? AND kind='block'",
                          (site_id,)):
        v = json.loads(r["value"])
        if newest is None or (v.get("at") or "") > (newest.get("at") or ""):
            newest = v
    return reference(conn, site_id, _key_of(conn, site_id, newest["run_id"])) if newest else None


def _key_of(conn: sqlite3.Connection, site_id: str, run_id: str) -> str:
    row = conn.execute("SELECT key FROM latest_view WHERE site_id=? AND kind='block' AND run_id=?"
                       " LIMIT 1", (site_id, run_id)).fetchone()
    return row["key"]


def apply_analysis(conn: sqlite3.Connection, run_id: str, tool_id: str) -> None:
    """The newest run of an analysis is its item (amendment 10): dated by when
    it ran, and by the crawl it read."""
    er = conn.execute(
        "SELECT er.created_at, er.model_id, er.cost, r.site_id, r.finished_at, r.started_at"
        " FROM expert_reports er JOIN audit_runs r ON r.id = er.run_id"
        " WHERE er.run_id=? AND er.tool_id=? ORDER BY er.created_at DESC LIMIT 1",
        (run_id, tool_id)).fetchone()
    if er is None:
        return
    held = _get(conn, er["site_id"], "analysis", tool_id)
    if held and (held.get("at") or "") > (er["created_at"] or ""):
        return
    _put(conn, er["site_id"], "analysis", tool_id,
         {"run_id": run_id, "at": er["created_at"], "model": er["model_id"],
          "cost": er["cost"], "crawl_at": er["finished_at"] or er["started_at"]},
         run_id, er["created_at"])


def part_range(conn: sqlite3.Connection, site_id: str, dimension: str | None,
               ref: dict | None) -> dict | None:
    """The dates a part's items were measured on (item 239 rule 3, step 6):
    its reference crawl, and the pages whose fields of the part's dimension
    another run measured since - "Measured 18 Sept to 23 Sept · one page
    re-checked 23 Sept". None where the part has no reference crawl."""
    if not dimension or not ref:
        return None
    fields = PAGE_FIELDS.get(dimension, ())
    ref_at, ref_run = ref.get("at") or "", ref.get("run_id")
    newer, newest, oldest = 0, None, None
    # A page that has left the site is not an old reading of the site (item
    # 243): it says "not seen since" on its own and is no part of the range.
    left = gone(conn, site_id, dimension)
    for r in conn.execute("SELECT key, value FROM latest_view WHERE site_id=? AND kind='page'",
                          (site_id,)):
        if r["key"] in left:
            continue
        cells = [c for f, c in json.loads(r["value"]).items()
                 if f in fields and c.get("run_id") != ref_run and c.get("at")]
        if not cells:
            continue
        top = max(c["at"] for c in cells)
        if top > ref_at:
            newer += 1
            newest = max(newest or top, top)
        low = min(c["at"] for c in cells)
        if low < ref_at:
            oldest = min(oldest or low, low)
    return {"from": oldest or ref_at, "to": newest or ref_at, "reference_at": ref_at,
            "rechecked_pages": newer, "rechecked_at": newest}


def frozen_copy(conn: sqlite3.Connection, site_id: str) -> dict:
    """The Latest View as a client report carries it (item 239 step 7):
    taken at generation, stored with the report, never changed afterwards.
    Every item keeps the run that measured it and when; the findings are the
    ledger's open ones, dated the same way; `hold` is the open Critical and
    High in this copy, which is what holds the report."""
    items: dict[str, dict] = {}
    for r in conn.execute("SELECT kind, key, value FROM latest_view WHERE site_id=?"
                          " ORDER BY kind, key", (site_id,)):
        items.setdefault(r["kind"], {})[r["key"]] = json.loads(r["value"])
    findings = [{k: f.get(k) for k in ("fingerprint", "dimension", "check_id", "severity",
                                       "source", "state", "run_id", "measured_at",
                                       "affected_urls", "summary")}
                for f in runs.ledger_findings(conn, site_id)]
    dates = sorted(f["measured_at"] for f in findings if f["measured_at"])
    return {"taken_at": now_iso(),
            "composite": items.get("composite", {}).get("current"),
            "blocks": items.get("block", {}), "analyses": items.get("analysis", {}),
            "pages": items.get("page", {}), "findings": findings,
            "measured_from": dates[0] if dates else None,
            "measured_to": dates[-1] if dates else None,
            "hold": runs.open_severe(conn, site_id)}


def analyses(conn: sqlite3.Connection, site_id: str) -> dict[str, dict]:
    """The newest run of each analysis tool on this site (amendment 10, step
    4): what a part's pills and the rows beneath them both read, so the two
    cannot name different runs."""
    return {r["key"]: json.loads(r["value"]) for r in conn.execute(
        "SELECT key, value FROM latest_view WHERE site_id=? AND kind='analysis'", (site_id,))}


def _scope_statements(conn: sqlite3.Connection, run_id: str) -> tuple[set[str], set[str]]:
    """A stored run's re-emitted fingerprints and its scope statements, as
    `_apply_states` read them off the live result. The flag rides in the
    evidence since item 239; a row stored before it falls back to the
    coverage-note rule, which is what nearly every scope statement is."""
    current, about = set(), set()
    for f in conn.execute("SELECT fingerprint, check_id, severity, evidence FROM findings"
                          " WHERE run_id=? AND source='deterministic'", (run_id,)):
        current.add(f["fingerprint"])
        try:
            ev = json.loads(f["evidence"] or "{}")
        except ValueError:
            ev = {}
        flagged = ev.get("scope_statement") if isinstance(ev, dict) else None
        if flagged or (flagged is None and runs.is_coverage_note(f["check_id"], f["severity"])):
            about.add(f["fingerprint"])
    return current, about


def _apply_event(conn: sqlite3.Connection, site_id: str, ev) -> None:
    """An operator judgement, replayed. One on a finding no remaining run
    raised has no state row to act on; it stays in the log, shown as judged,
    finding no longer raised."""
    if ev["kind"] == "state":
        conn.execute("UPDATE finding_states SET state=?, changed_by_run=NULL, updated_at=?"
                     " WHERE site_id=? AND fingerprint=?",
                     (ev["to_state"], ev["at"], site_id, ev["fingerprint"]))
    elif ev["kind"] == "attempt":
        if ev["to_state"] == "marked":
            conn.execute("UPDATE finding_states SET attempted_at=?, attempt_note=?"
                         " WHERE site_id=? AND fingerprint=?",
                         (ev["at"], ev["note"] or "", site_id, ev["fingerprint"]))
        else:
            conn.execute("UPDATE finding_states SET attempted_at=NULL, attempt_note=NULL"
                         " WHERE site_id=? AND fingerprint=?", (site_id, ev["fingerprint"]))


def _replay(conn: sqlite3.Connection, site_id: str) -> None:
    """Rebuild the ledger and the items from the runs that exist, in order.
    No transaction of its own: `rebuild` and `delete_effect` hold one."""
    conn.execute("DELETE FROM latest_view WHERE site_id=?", (site_id,))
    conn.execute("DELETE FROM finding_states WHERE site_id=?", (site_id,))
    timeline: list[tuple[str, int, Any]] = []
    # Runs in the order they finished; a tie (two runs stamped in one second)
    # falls back to the order they were created in, which is the order the
    # live completion took them. Events after runs at the same instant.
    for r in conn.execute("SELECT rowid AS n, id, status, finished_at, started_at FROM audit_runs"
                          f" WHERE site_id=? AND {runs.status_in(runs.AUDITED_STATUSES)}",
                          (site_id,)):
        timeline.append((r["finished_at"] or r["started_at"] or "", 0, r["n"], r))
    for e in conn.execute("SELECT * FROM state_events WHERE site_id=? ORDER BY at, id", (site_id,)):
        timeline.append((e["at"], 1, e["id"], e))
    timeline.sort(key=lambda t: t[:3])
    for at, what, _n, item in timeline:
        if what == 1:
            _apply_event(conn, site_id, item)
            continue
        reading = runs.Reading.of_stored(conn, item["id"])
        if reading is None:
            continue
        current, about = _scope_statements(conn, item["id"])
        runs._advance_states(conn, site_id, item["id"], at, current=current,
                             about_the_run=about, reading=reading,
                             blocked=item["status"] == "blocked")
        apply_run(conn, item["id"])
    # The analyses' own walks, as the live completion runs them: each from its
    # tool's whole history, respecting the operator's states now in place.
    tools = conn.execute(
        "SELECT er.tool_id, MAX(er.contract IS NOT NULL) AS contract FROM expert_reports er"
        " JOIN audit_runs r ON r.id = er.run_id WHERE r.site_id=? GROUP BY er.tool_id",
        (site_id,)).fetchall()
    for t in tools:
        if t["contract"]:
            runs.recompute_contract_states(conn, site_id, t["tool_id"])
        else:
            runs.recompute_expert_states(conn, site_id, t["tool_id"])
    for er in conn.execute("SELECT er.run_id, er.tool_id FROM expert_reports er"
                           " JOIN audit_runs r ON r.id = er.run_id WHERE r.site_id=?"
                           " ORDER BY er.created_at", (site_id,)).fetchall():
        apply_analysis(conn, er["run_id"], er["tool_id"])


def snapshot(conn: sqlite3.Connection, site_id: str) -> dict:
    """The record as a comparable value: the ledger (state, the run that moved
    it, the attempt mark) and every item. Timestamps of the rebuild itself are
    left out, so two rebuilds of one history compare equal."""
    states = {r["fingerprint"]: (r["state"], r["changed_by_run"], r["attempted_at"] is not None)
              for r in conn.execute("SELECT fingerprint, state, changed_by_run, attempted_at"
                                    " FROM finding_states WHERE site_id=?", (site_id,))}
    items = {(r["kind"], r["key"]): (json.loads(r["value"]), r["run_id"])
             for r in conn.execute("SELECT kind, key, value, run_id FROM latest_view"
                                   " WHERE site_id=?", (site_id,))}
    return {"states": states, "items": items}


def rebuild(conn: sqlite3.Connection, site_id: str, reason: str,
            counts: dict | None = None) -> dict:
    """Replay the site's Latest View from its runs and events, and record why."""
    with conn:
        _replay(conn, site_id)
        conn.execute("INSERT INTO latest_view_log (site_id, at, reason, counts) VALUES (?, ?, ?, ?)",
                     (site_id, now_iso(), reason, _j(counts or {})))
    return snapshot(conn, site_id)


def _delete_rows(conn: sqlite3.Connection, run_id: str, site_id: str, finished_at: str | None) -> None:
    """Everything a run wrote into the database (item 239's delete ruling):
    its findings, costs, trend point, analyses - and, via the rebuild after,
    every state it moved."""
    # The states it moved still name it; the replay after rewrites them.
    conn.execute("UPDATE finding_states SET changed_by_run=NULL WHERE changed_by_run=?", (run_id,))
    conn.execute("DELETE FROM findings WHERE run_id=?", (run_id,))
    conn.execute("DELETE FROM cost_entries WHERE run_id=?", (run_id,))
    conn.execute("DELETE FROM metric_snapshots WHERE run_id=?", (run_id,))
    conn.execute("DELETE FROM expert_reports WHERE run_id=?", (run_id,))
    if finished_at:
        conn.execute("DELETE FROM metric_snapshots WHERE site_id=? AND captured_at=?",
                     (site_id, finished_at))
    conn.execute("DELETE FROM audit_runs WHERE id=?", (run_id,))


def delete_effect(conn: sqlite3.Connection, run_id: str) -> dict | None:
    """What deleting a run would change, without changing it (the delete
    confirm's dry run): the replay without the run, inside a savepoint that
    is rolled back."""
    row = conn.execute("SELECT site_id, finished_at, tier, started_at FROM audit_runs WHERE id=?",
                       (run_id,)).fetchone()
    if row is None:
        return None
    site_id = row["site_id"]
    before = snapshot(conn, site_id)
    # On a copy in memory, never in a savepoint of the real database: the
    # analyses' walks commit as they go, which released the savepoint and
    # made the first cut of this "dry run" a real delete (found on a copy of
    # the live database before it shipped).
    scratch = sqlite3.connect(":memory:")
    scratch.row_factory = sqlite3.Row
    try:
        conn.backup(scratch)
        with scratch:
            _delete_rows(scratch, run_id, site_id, row["finished_at"])
        _replay(scratch, site_id)
        scratch.commit()
        after = snapshot(scratch, site_id)
    finally:
        scratch.close()
    return describe(before, after, run_id, row["tier"], row["finished_at"] or row["started_at"])


def describe(before: dict, after: dict, run_id: str, tier: str | None, at: str | None) -> dict:
    """The effect of a rebuild, in counts the confirm can say."""
    reopened = sum(1 for fp, (st, _r, _a) in after["states"].items()
                   if st == "open" and before["states"].get(fp, (None,))[0] not in ("open", None))
    gone = sum(1 for fp in before["states"] if fp not in after["states"])
    mine = [(kind, key) for (kind, key), (_v, rid) in before["items"].items() if rid == run_id]
    return {"run_id": run_id, "tier": tier, "at": at,
            "reopened": reopened, "findings_gone": gone,
            "pages_returned": sum(1 for kind, _k in mine if kind == "page"),
            "blocks_returned": sorted(k for kind, k in mine if kind == "block")}
