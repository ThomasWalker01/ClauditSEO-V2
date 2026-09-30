"""Item 239 step 1: The Latest View - one record per site, updated by each
finished run under the write rules, and rebuilt from the runs by a replay.

The fixture is twenty22's history at small scale, in its order: a one-page
T1 over every dimension; a T3 over every dimension, images weighed; a
one-page ONP refresh; a T2 over ONP only, no images. The rulings' guard for
step 1, asserted:

  - TEC and LNK blocks are T3's; image weights are T3's;
  - ONP page fields on pages T2 fetched are T2's;
  - the refresh changed only its one page's ONP fields and no block;
  - rebuilding twice gives an identical record, and the rebuild equals what
    the runs wrote as they finished;
  - deleting T2 gives the record built from T1, T3 and the refresh alone;
    an operator's accept made before the delete survives it; the delete
    writes no regression; its dry run changes nothing.
"""

from __future__ import annotations

import json

from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.engine.core import AuditResult
from clauditseo.engine.types import Finding, Severity, Site, Tier
from clauditseo.persistence import latest_view, repo, runs

BASE = "https://latest.test"
ALL = ["TEC", "ONP", "A11Y", "PRF", "CNT", "OFP", "LOC", "AIS", "LNK", "SEC"]
PATHS = [f"/p{n}/" for n in range(60)]


def _page(path, title, imaged=False):
    return {"url": BASE + path, "status": 200, "content_type": "text/html",
            "title": title, "meta_description": f"About {path}", "h1": title,
            "a11y": {"issues": 0}, "canonical": BASE + path,
            "click_depth": 1, "outlinks": [],
            "image_inventory": [{"src": "hero.jpg", "alt": "x",
                                 **({"weight_kb": 300} if imaged else {})}]}


def _finding(check, path, dim="ONP"):
    return Finding(dimension=dim, check_id=check, severity=Severity.MEDIUM,
                   summary=f"{check} on {path}", subject=f"{check}:{path}",
                   affected_urls=[BASE + path])


def _run(conn, site, label, dims, paths, *, kind="audit", imaged=False, findings=()):
    run = runs.create_run(conn, site, dims, label.split()[0], kind=kind,
                          scan_scope="site" if kind == "audit" and len(paths) > 1 else "page")
    runs.store_evidence(conn, run, {"start_url": BASE + "/",
                                    "pages": [_page(p, f"{label} {p}", imaged) for p in paths]})
    runs.complete_run(conn, run, AuditResult(
        site=Site(domain=BASE + "/"), tier=Tier.T2, dimensions=dims, findings=list(findings),
        composite_score=70.0 if kind == "audit" else None,
        crawled_paths=set(paths), imaged_paths=set(paths) if imaged else set()))
    return run


def _history(tmp_path, name, with_t2=True):
    conn = connect(tmp_path / f"{name}.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site = repo.create_site(conn, repo.create_client(conn, op, "C"), "latest.test")
    ids = {}
    ids[_run(conn, site, "T1 home", ALL, ["/p0/"])] = "T1"
    ids[_run(conn, site, "T3 full", ALL, PATHS, imaged=True,
             findings=[_finding("title-missing", "/p1/"), _finding("inlinks-low", "/p2/", "LNK")])] = "T3"
    ids[_run(conn, site, "T3 refresh", ["ONP"], ["/p5/"], kind="refresh",
             findings=[_finding("title-missing", "/p1/")])] = "refresh"
    if with_t2:
        ids[_run(conn, site, "T2 onp", ["ONP"], PATHS[:40],
                 findings=[_finding("meta-desc-missing", "/p3/")])] = "T2"
    return conn, site, ids


def _labelled(snap, ids):
    """A snapshot with run ids replaced by labels, so two databases compare."""
    name = lambda r: ids.get(r, r)  # noqa: E731
    items = {}
    for (kind, key), (value, rid) in snap["items"].items():
        if kind == "page":
            value = {f: {**c, "run_id": name(c["run_id"]), "at": None,
                         "value": c["value"] if f != "title" else "-"}
                     for f, c in value.items()}
        elif kind == "presence":
            # Item 243: which dimensions saw the page and which call it gone,
            # without the dates - the two histories are built a second or
            # two apart by the clock, which is not a difference in the record.
            value = {k: sorted(v) for k, v in value.items()}
        else:
            value = {k: (name(v) if k == "run_id" else v)
                     for k, v in value.items() if k not in ("at", "crawl_at")}
        items[(kind, key)] = (value, name(rid))
    states = {fp: (st, name(r), a) for fp, (st, r, a) in snap["states"].items()}
    return {"items": items, "states": states}


def test_each_item_comes_from_the_run_that_last_measured_it(tmp_path):
    conn, site, ids = _history(tmp_path, "h")
    t3, t2 = (next(r for r, n in ids.items() if n == lbl) for lbl in ("T3", "T2"))
    view = latest_view.snapshot(conn, site)["items"]
    assert view[("block", "TEC")][1] == t3 and view[("block", "LNK")][1] == t3
    assert view[("block", "ONP")][1] == t2
    page_t2, page_t3_only = view[("page", "/p3/")][0], view[("page", "/p50/")][0]
    assert page_t2["title"]["run_id"] == t2           # ONP, and T2 fetched it
    assert page_t2["status"]["run_id"] == t3          # TEC: T2 did not measure it
    assert page_t2["image_weights"]["run_id"] == t3   # T2 weighed no images
    assert page_t3_only["title"]["run_id"] == t3      # T2 did not fetch it
    assert view[("composite", "current")][1] == t3    # T2 measured ONP only


def test_the_refresh_changed_only_its_pages_onp_fields(tmp_path):
    conn, site, ids = _history(tmp_path, "r", with_t2=False)
    refresh = next(r for r, n in ids.items() if n == "refresh")
    items = latest_view.snapshot(conn, site)["items"]
    owned = {(k, f) for (kind, k), (v, _r) in items.items() if kind == "page"
             for f, c in v.items() if c["run_id"] == refresh}
    assert owned and {k for k, _f in owned} == {"/p5/"}, owned
    assert {f for _k, f in owned} <= set(latest_view.PAGE_FIELDS["ONP"]), owned
    assert not [k for (kind, k), (_v, r) in items.items() if kind == "block" and r == refresh]


def test_a_rebuild_is_what_the_runs_wrote_and_is_stable(tmp_path):
    conn, site, ids = _history(tmp_path, "b")
    live = latest_view.snapshot(conn, site)
    first = latest_view.rebuild(conn, site, "test")
    second = latest_view.rebuild(conn, site, "test")
    assert first == second
    assert first == live


def test_deleting_a_run_is_the_record_without_it(tmp_path):
    conn, site, ids = _history(tmp_path, "d")
    without, _site2, ids2 = _history(tmp_path, "w", with_t2=False)
    t3 = next(r for r, n in ids.items() if n == "T3")
    t2 = next(r for r, n in ids.items() if n == "T2")
    accepted = conn.execute("SELECT fingerprint FROM findings WHERE run_id=? AND check_id='inlinks-low'",
                            (t3,)).fetchone()[0]
    runs.set_state(conn, site, accepted, "accepted-risk")
    runs.set_state(without, _site2, accepted, "accepted-risk")

    before = latest_view.snapshot(conn, site)
    effect = latest_view.delete_effect(conn, t2)
    assert latest_view.snapshot(conn, site) == before, "the dry run changed the record"
    assert effect["blocks_returned"] == ["ONP"] and effect["pages_returned"] == 40, effect

    runs.delete_run(conn, t2)
    got = _labelled(latest_view.snapshot(conn, site), ids)
    want = _labelled(latest_view.snapshot(without, _site2), ids2)
    assert got == want
    assert got["states"][accepted][0] == "accepted-risk"
    assert not [s for s, _r, _a in got["states"].values() if s == "regressed"]
    log = conn.execute("SELECT reason FROM latest_view_log WHERE site_id=?", (site,)).fetchall()
    assert [r[0] for r in log] == [f"rebuilt after deleting run {t2}"]


def test_an_operators_judgement_is_an_event():
    """A state the operator sets is logged, so a replay can apply it; one a
    run writes is not an operator's."""
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        conn, site, ids = _history(Path(d), "e", with_t2=False)
        fp = conn.execute("SELECT fingerprint FROM finding_states WHERE site_id=? LIMIT 1",
                          (site,)).fetchone()[0]
        runs.set_state(conn, site, fp, "withdrawn")
        runs.mark_attempt(conn, site, fp, "tried")
        events = [(r["kind"], r["to_state"]) for r in conn.execute(
            "SELECT kind, to_state FROM state_events WHERE site_id=? ORDER BY id", (site,))]
        conn.close()
    assert events == [("state", "withdrawn"), ("attempt", "marked")], events
    _ = json
