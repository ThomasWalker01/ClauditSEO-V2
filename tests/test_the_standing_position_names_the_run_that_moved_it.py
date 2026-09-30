"""UX-92: "Where it stands" is stamped with a run that did not move it.

Reproduced on the operator's own database before this guard was written, at
`#/sites/2537f69f...?tab=record`. The pane reads `2026-08-23 · site-wide` over
`1085 OUTSTANDING · 31 REGRESSED · 20 FIXED TO DATE`. Those counts are a
`GROUP BY state` over the whole of `finding_states`, whatever moved each row —
and the newest run to have moved any of them is a **verify** of 2026-08-24
that moved ten:

    2026-08-24T04:01:00  verify  71f0fad2  moved 10
    2026-08-23T11:17:41  audit   fe97cc61  moved 59
    2026-08-23T01:00:11  verify  b0331ff9  moved  8

The stamp came from `current_state`'s `latest`, which selects `AND
kind='audit'`. So the date over the counts named a run that is not the one the
counts were last moved by, and the operator had no way to tell — a day's
difference reads as "nothing has happened since", which is exactly wrong when
a verification moved ten rows in between.

**`last_audit` is not the defect and is deliberately left alone.** Three other
readers want precisely "the last full audit" and are correct today:

  * *"Last audit ... opened N, closed N and reopened N"* is run-scoped by
    construction — it reports `moved`, which is counted against that same run;
  * the site's `last ran` line, which is about audits;
  * `useFixLoop`'s `judged` gate, whose whole rule is that a verification
    looking at a handful of pages may NOT settle a mark it never covered.

Adding a second fact is therefore the fix, not redirecting the first. The two
answer different questions, and this pane was asking the second one with the
first one's answer.

**Why `last_move` is decided by whether a row exists rather than by a status.**
A run that wrote a `finding_states` row moved the standing position; the row
is the evidence for that claim. Filtering on `status` instead would be
structure standing in for evidence — DISCIPLINE rule 4 — and would be wrong in
the direction that matters, since a run can reach a terminal status without
touching a single row.
"""

from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import pytest

import clauditseo.modules  # noqa: F401  (registers the dimensions)
from clauditseo import axe
from clauditseo.persistence import runs
from tests.conftest import FixtureSite
from tests.test_a11y_rendered import DIST
from tests.test_heading_fault import browser_page  # noqa: F401  (reused fixture)
from tests.test_verify import GOOD, _routes, _seeded


def _audit_then_verify(tmp: Path, site: FixtureSite):
    """A site whose standing position was last moved by a `verify`.

    The verify is driven through the route rather than written by hand: the
    finding under test is about which run `finding_states.changed_by_run`
    names, and a fixture that set that column itself would be evidence drawn
    from the thing it is checking.
    """
    from fastapi.testclient import TestClient

    from clauditseo.api.app import create_app

    db, conn, site_id, fps = _seeded(tmp, site)
    # The seed audit is backdated a day. Without this both runs are stamped
    # inside the same second, `started_at` is second-resolution, and the two
    # dates the pane could show are the same string — so the guard passes on
    # the broken tree for a reason that has nothing to do with the defect.
    # It is also the real shape: the audit was yesterday and the operator
    # verified a fix today, which is precisely when the stale stamp misleads.
    with conn:
        conn.execute(
            "UPDATE audit_runs SET started_at = datetime(started_at, '-1 day'),"
            " created_at = datetime(created_at, '-1 day')"
            " WHERE site_id=? AND kind='audit'", (site_id,))
        conn.execute(
            "UPDATE finding_states SET updated_at = datetime(updated_at, '-1 day')"
            " WHERE site_id=?", (site_id,))
    site.routes["/"] = (200, {}, GOOD)          # the operator's fix
    client = TestClient(create_app(db_path=db))
    resp = client.post(f"/api/sites/{site_id}/verify",
                       json={"fingerprints": sorted(fps)})
    assert resp.status_code == 200, resp.text
    assert resp.json()["cleared"] >= 1, (
        "the verification cleared nothing, so it moved no row and this "
        "fixture cannot express the defect")
    return db, conn, site_id, resp.json()["run_id"]


def _runs_that_moved_a_row(conn, site_id: str):
    return conn.execute(
        "SELECT r.id, r.kind, r.started_at FROM audit_runs r"
        " WHERE r.site_id=? AND EXISTS ("
        "   SELECT 1 FROM finding_states fs"
        "   WHERE fs.site_id=r.site_id AND fs.changed_by_run=r.id)"
        " ORDER BY r.started_at DESC, r.rowid DESC", (site_id,)).fetchall()


# --- on the wire ------------------------------------------------------------

def test_the_payload_says_which_run_last_moved_the_standing_position(tmp_path):
    """The screen cannot work this out for itself: it is a fact about which
    run wrote which row, and only the server can see it."""
    site = FixtureSite(_routes()).start()
    try:
        _db, conn, site_id, verify_run = _audit_then_verify(tmp_path, site)
        moved = _runs_that_moved_a_row(conn, site_id)
        assert moved and moved[0]["id"] == verify_run, (
            "the verify is not the newest run to have moved a row, so this "
            f"fixture cannot express the defect: {[dict(r) for r in moved]}")

        current = runs.current_state(conn, site_id)

        # The population check, and it is the whole reproduction: with the two
        # runs identical this guard would pass on the broken tree.
        assert current["last_audit"] != moved[0]["started_at"], (
            "the last audit IS the run that last moved the position in this "
            "fixture, so the stamp cannot be caught naming the wrong one")

        assert current.get("last_move"), (
            "the payload does not say which run last moved the standing "
            "position — the screen is given only `last_audit`, which in this "
            f"fixture is {current['last_audit']!r} while the row was moved "
            f"by a {moved[0]['kind']} at {moved[0]['started_at']!r}")
        assert current["last_move"]["at"] == moved[0]["started_at"]
        assert current["last_move"]["kind"] == "verify", (
            "the stamp does not name the kind of run that moved it: "
            f"{current['last_move']!r}")
    finally:
        site.stop()


def test_the_last_audit_the_other_three_readers_want_is_unchanged(tmp_path):
    """The counter-assertion. `moved` is counted against `last_audit`, so
    redirecting that field would silently re-point three correct readers at a
    two-page crawl — including the one whose rule is that a verification may
    not settle a mark it never covered.
    """
    site = FixtureSite(_routes()).start()
    try:
        _db, conn, site_id, _verify_run = _audit_then_verify(tmp_path, site)
        current = runs.current_state(conn, site_id)
        audit = conn.execute(
            "SELECT id, started_at FROM audit_runs WHERE site_id=?"
            " AND kind='audit' ORDER BY started_at DESC LIMIT 1",
            (site_id,)).fetchone()
        assert current["last_audit"] == audit["started_at"], (
            "`last_audit` no longer names the last full audit")
        assert current["last_audit"] != (current.get("last_move") or {}).get("at"), (
            "the two facts collapsed back into one")
        # Coverage notes excluded, by the predicate `standing_by_state` applies
        # to the same table (audit F1, 2026-09-18). This clause counted the raw
        # rows and so asserted the defect: on the operator's database the
        # landing rendered "First audit +36 -0" beside its own "It found 32
        # findings in this audit. 4 coverage notes not counted." What it is
        # here to hold is that `moved` is counted against the run `last_audit`
        # names, and that survives the narrower population.
        moved_by_audit = conn.execute(
            f"SELECT COUNT(*) FROM finding_states fs"
            f" JOIN findings f ON f.rowid = ({runs._latest_finding()})"
            f" WHERE fs.site_id=? AND fs.changed_by_run=?"
            f" AND NOT {runs.coverage_note_sql()}",
            (site_id, audit["id"])).fetchone()[0]
        assert (current["moved"]["opened"] + current["moved"]["fixed"]
                + current["moved"]["regressed"]) == moved_by_audit, (
            "`moved` is no longer counted against the run `last_audit` names")
    finally:
        site.stop()


# --- on the screen, in a browser --------------------------------------------

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def live(fn):
    fn = pytest.mark.skipif(
        not (DIST / "index.html").is_file(),
        reason="dashboard not built (npm run build in dashboard/)")(fn)
    return pytest.mark.skipif(
        not axe.available(),
        reason="needs clauditseo[render] and `playwright install chromium`")(fn)


@pytest.fixture(scope="module")
def served_after_a_verify():
    """Its own server, on the precedent
    `test_the_sweep_forecast_states_the_population_it_priced.py` set and for
    its reason: `test_a11y_rendered.py`'s `served` seed is asserted on by
    several files for its run count, and adding a verify run to it to prove
    something about this pane is how a shared fixture stops being readable.
    """
    import tempfile

    import uvicorn

    from clauditseo.api.app import create_app

    tmp = Path(tempfile.mkdtemp(prefix="standing"))
    site = FixtureSite(_routes()).start()
    try:
        db, conn, site_id, _verify_run = _audit_then_verify(tmp, site)
        moved = [dict(r) for r in _runs_that_moved_a_row(conn, site_id)]
        conn.close()

        app = create_app(db_path=db)
        port = _free_port()
        config = uvicorn.Config(app, host="127.0.0.1", port=port,
                                log_level="warning")
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        deadline = time.time() + 30
        while not server.started and time.time() < deadline:
            time.sleep(0.05)
        if not server.started:
            pytest.fail("server did not start")
        try:
            yield f"http://127.0.0.1:{port}", site_id, moved[0]
        finally:
            server.should_exit = True
            thread.join(timeout=10)
    finally:
        site.stop()


@live
def test_the_pane_is_stamped_with_the_run_that_moved_it(
        served_after_a_verify, browser_page):  # noqa: F811
    """Read off the rendered pane, because the stamp is the finding.

    `.cur-when` is the class the stamp renders under, so this asks the screen
    the same question the payload was asked above rather than matching prose
    that can be reworded.
    """
    base, site_id, mover = served_after_a_verify
    # The stamp heads the Waiting lane on the landing since brief v24 step BM.
    browser_page.goto(f"{base}/#/sites/{site_id}", wait_until="load")
    browser_page.wait_for_selector(".cur-when", timeout=20_000)
    stamp = browser_page.eval_on_selector(".cur-when", "el => el.innerText")

    assert mover["started_at"][:10] in stamp, (
        f"the pane is stamped {stamp!r}; the run that last moved the counts "
        f"beside it is a {mover['kind']} of {mover['started_at'][:10]}")
    # Rendered text, not a `title` — a stated limitation on a displayed value
    # has to reach a keyboard, which is the provenance invariant's frame
    # clause.
    assert "verif" in stamp.lower(), (
        "the stamp does not name the kind of run that moved the position: "
        f"{stamp!r}")


@live
def test_the_stamped_run_can_be_opened_from_the_pane(
        served_after_a_verify, browser_page):  # noqa: F811
    """UX-94: the pane names a run, so the pane opens it.

    `last_move` is built as an at, a kind and a run id
    (`clauditseo/persistence/runs.py`), and the aside rendered the first two
    and discarded the third — a screen naming an object it will not open,
    which is the affordance invariant's own wording. The route the link uses
    is the one four other places in `anatomy.tsx` already use for a run.

    Driven rather than read from source, because the source clause in
    `tests/test_eight_findings_at_ten_reports_are_recorded_not_invisible.py`
    can only see that `run_id` appears in the block. Whether the browser
    renders something a keyboard can reach, pointing at the run that actually
    moved the counts, is a question only the running product answers — and
    DISCIPLINE rule 12 says that is where it has to be asked.
    """
    base, site_id, mover = served_after_a_verify
    # The stamp heads the Waiting lane on the landing since brief v24 step BM.
    browser_page.goto(f"{base}/#/sites/{site_id}", wait_until="load")
    browser_page.wait_for_selector(".cur-when", timeout=20_000)

    tag = browser_page.eval_on_selector(".cur-when", "el => el.tagName")
    assert tag == "A", (
        "the standing-position stamp names a run and is not an anchor, so "
        f"the run it names cannot be opened: rendered as <{tag.lower()}>")

    href = browser_page.eval_on_selector(
        ".cur-when", "el => el.getAttribute('href')")
    assert href == f"#/runs/{mover['id']}", (
        "the stamp links somewhere other than the run that moved the counts. "
        f"Linked {href!r}; the mover is {mover['id']!r}")
