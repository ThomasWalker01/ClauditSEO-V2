"""Links files one finding per page, and the stored runs are brought to the
same shape (item 251 step 4, channel answer 20261002-1215).

`LinksModule` filed each graph check once, with every page in
`affected_urls`. So the part page's PAGES was a union of two shapes with the
analysis's per-page rows, "superseded on" could never fire, a page leaving
the orphan list closed nothing, and `orphan` on eight pages was rated the
same as on one (`scoring.subscore` rates a check on its number of findings).

The score move is intended and named: ENGINE_VERSION is 0.29.0.
"""

from __future__ import annotations

import json

from clauditseo import ENGINE_VERSION
from clauditseo.db import migrate as migrate_mod
from clauditseo.db.connection import connect
from clauditseo.db.migrate import applied, migrate
from clauditseo.engine import scoring
from clauditseo.engine.types import fingerprint
from clauditseo.persistence import repo, runs
from clauditseo.persistence.repo import create_id
from tests.test_links_on_the_page import BASE, _by_check, _page, _run

SPLIT = "0073_links_findings_per_page.py"


def _site():
    """Home links to /a; /b, /c and /d are linked by nothing."""
    return [_page("/", "<a href='/a'>Read about A in full</a>"),
            _page("/a", "<p>a</p>"), _page("/b", "<p>b</p>"),
            _page("/c", "<p>c</p>"), _page("/d", "<p>d</p>")]


def test_each_page_gets_its_own_finding_about_that_page():
    got = _by_check(_run(*_site()))
    orphans = got["orphan"]
    assert sorted(f.subject for f in orphans) == ["/b", "/c", "/d"]
    for f in orphans:
        assert f.affected_urls == [BASE + f.subject], f.affected_urls
        assert f.summary == f"No other page links to {f.subject}.", f.summary
    # Three identities, each its page's own.
    assert len({f.fingerprint for f in orphans}) == 3
    assert orphans[0].fingerprint == fingerprint("LNK", "orphan", orphans[0].subject)


def test_no_graph_check_is_filed_under_its_own_name_any_more():
    for f in _run(*_site()):
        if f.check_id == "hub-unlinked":
            continue                    # per entity, as it always was
        assert f.subject != f.check_id, (f.check_id, f.subject)
        assert len(f.affected_urls) == 1, (f.check_id, f.affected_urls)


def test_a_per_page_finding_is_rated_by_pages_and_not_as_a_flat_site_deduction():
    """The score move, stated. A finding is page-scoped when its subject is
    a path (`scoring.subscore`). Filed under the check's own id, a Links
    finding was a SITE finding and deducted a flat amount whatever it covered:
    `orphan` on one page of 45 cost 10 points, and on forty pages cost 10.
    Per page it is rated on the share of pages, like every other dimension's
    checks, so the Links score moves - up where a check is rare, down where it
    is widespread. That is why the engine version moved with it."""
    three = [f for f in _run(*_site()) if f.check_id == "orphan"]
    sub = scoring.subscore("LNK", three, 1.0, None)
    assert sub.detail["per_check"]["orphan"]["affected"] == 3, sub.detail

    import dataclasses
    as_it_was = dataclasses.replace(three[0], subject="orphan",
                                    affected_urls=[u for f in three for u in f.affected_urls])
    flat = scoring.subscore("LNK", [as_it_was], 1.0, None)
    assert "orphan" not in flat.detail["per_check"], "a check-level finding was rated by page"
    assert flat.detail["deduction"] == scoring.SITE_DEDUCTION[as_it_was.severity]
    assert ENGINE_VERSION == "0.29.0", "a score move without a version move is not comparable"


# ---- the stored runs ------------------------------------------------------------

def _before_the_split(db):
    conn = connect(db)
    applied(conn)
    for path in migrate_mod._files():
        if path.name == SPLIT:
            continue
        with conn:
            if path.suffix == ".py":
                migrate_mod._apply_python(path, conn)
            else:
                conn.executescript(path.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migrations (filename) VALUES (?)", (path.name,))
    return conn


def _old_finding(conn, run_id, check, urls, at):
    fp = fingerprint("LNK", check, check)
    conn.execute(
        "INSERT INTO findings (id, run_id, dimension, check_id, severity, source, summary,"
        " affected_urls, affected_total, evidence, recommendation, fingerprint, created_at)"
        " VALUES (?, ?, 'LNK', ?, 'medium', 'deterministic', ?, ?, ?, '{}', 'rec', ?, ?)",
        (create_id(), run_id, check, f"{len(urls)} pages no other page links to",
         json.dumps(urls), len(urls), fp, at))
    return fp


def _old_run(conn, site_id, at, orphans):
    run_id = runs.create_run(conn, site_id, ["LNK"], "T2", scan_scope="site")
    pages = [BASE + "/"] + orphans
    runs.store_evidence(conn, run_id, {"start_url": BASE + "/",
                                       "pages": [{"url": u, "status": 200} for u in pages]})
    conn.execute("UPDATE audit_runs SET status='complete', started_at=?, finished_at=?,"
                 " created_at=?, crawled_paths=?, composite_score=81.5 WHERE id=?",
                 (at, at, at, json.dumps(["/" + u.split("/", 3)[3] for u in pages]), run_id))
    fp = _old_finding(conn, run_id, "orphan", orphans, at)
    conn.commit()
    return run_id, fp


def test_the_stored_runs_are_split_per_page_and_the_record_follows(tmp_path):
    conn = _before_the_split(tmp_path / "old.db")
    op = repo.ensure_default_operator(conn)
    site = repo.create_site(conn, repo.create_client(conn, op, "Links Co"), "links.test")
    b, c, d = BASE + "/b", BASE + "/c", BASE + "/d"
    first, old_fp = _old_run(conn, site, "2026-09-18T00:00:00+00:00", [b, c, d])
    second, _ = _old_run(conn, site, "2026-09-25T00:00:00+00:00", [b, c])     # /d was fixed
    # The operator accepted the finding between the two audits: all three
    # pages it named at the time.
    conn.execute("INSERT INTO state_events (site_id, fingerprint, kind, from_state, to_state,"
                 " note, by_operator, at) VALUES (?, ?, 'state', 'open', 'accepted-risk',"
                 " NULL, NULL, '2026-09-20T00:00:00+00:00')", (site, old_fp))
    conn.commit()

    assert migrate(conn) == [SPLIT]

    rows = conn.execute("SELECT run_id, summary, affected_urls, fingerprint, severity,"
                        " recommendation, evidence FROM findings WHERE dimension='LNK'").fetchall()
    assert len(rows) == 5, "three pages in the first run and two in the second"
    assert not conn.execute("SELECT 1 FROM findings WHERE fingerprint=?", (old_fp,)).fetchone()
    for r in rows:
        (url,) = json.loads(r["affected_urls"])
        path = "/" + url.split("/", 3)[3]
        assert r["fingerprint"] == fingerprint("LNK", "orphan", path)
        assert r["summary"] == f"No other page links to {path}.", r["summary"]
        assert r["severity"] == "medium" and r["recommendation"] == "rec"
        assert json.loads(r["evidence"])["split_from"] == old_fp
    in_first = {json.loads(r["affected_urls"])[0] for r in rows if r["run_id"] == first}
    assert in_first == {b, c, d}, "a split row left the run it was raised in"

    # The judgement applies to every page the finding named when it was made,
    # with its date; the original event is kept.
    events = conn.execute("SELECT fingerprint, to_state, at FROM state_events WHERE site_id=?"
                          " ORDER BY id", (site,)).fetchall()
    assert events[0]["fingerprint"] == old_fp, "history was rewritten, not added to"
    carried = {e["fingerprint"] for e in events[1:]}
    assert carried == {fingerprint("LNK", "orphan", p) for p in ("/b", "/c", "/d")}, carried
    assert {(e["to_state"], e["at"]) for e in events[1:]} == {
        ("accepted-risk", "2026-09-20T00:00:00+00:00")}

    # The record, rebuilt after the split: /b and /c keep the operator's
    # answer; /d was fixed by the second audit and nothing reads as new.
    state = {r["fingerprint"]: r["state"] for r in conn.execute(
        "SELECT fingerprint, state FROM finding_states WHERE site_id=?", (site,))}
    assert old_fp not in state
    assert state[fingerprint("LNK", "orphan", "/b")] == "accepted-risk"
    assert state[fingerprint("LNK", "orphan", "/c")] == "accepted-risk"
    reason = conn.execute("SELECT reason FROM latest_view_log WHERE site_id=?"
                          " ORDER BY rowid DESC LIMIT 1", (site,)).fetchone()
    assert reason and reason[0].startswith("0073"), reason

    # Stored scores stand as they were computed.
    assert {r[0] for r in conn.execute("SELECT composite_score FROM audit_runs")} == {81.5}
    assert migrate(conn) == [], "the split ran twice"
    conn.close()
