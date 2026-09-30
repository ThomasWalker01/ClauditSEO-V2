"""What one synchronous verification is allowed to cost, and where it says so.

`audits/DISPOSITIONS.md`'s engineering cohort, one live row at eleven rounds:
**the verify crawl is synchronous and uncapped** — `clauditseo/api/app.py`
verify route. Raised at audit 011 as WF-07, carried as WF-06 through report
038, and then not re-found by any auditor from 039 to 067; the register is the
only place it survived, which is the chain break `audit-fix/SKILL.md` step 1
asks a report to name.

**The defect, in the reports' own words.** `POST /api/sites/{id}/verify` runs
inside the request and sized its crawl as `max_pages=max(len(target["urls"]), 1)`
off the untruncated `affected_urls` of every marked finding, with no ceiling.
`img-alt-missing` on a 400-page site is one tick and one 400-page blocking HTTP
request — behind a button whose only cost statement was `title="Re-crawls only
those pages and runs only their dimensions. Seconds, and no model tokens."`

Two halves, and they are one change or the fix is worse than the finding: a cap
the operator only discovers by pressing is a refusal with no disclosure, and a
disclosure with no cap is the sentence that was already there.

**Why the client is told the number rather than deriving it.** The same
argument `runs.names_a_page` records one function above `VERIFY_PAGE_CAP`, and
the one CQ-82 and CQ-134 were both raised for: a second implementation of one
rule drifts. The cap has one owner in `runs.py` and travels on both payloads
the two `MarkBar` call sites already read.

**Why the bar may still offer a verify the server refuses.** `pages` is exact
on the record tab and a *floor* on Current, where the anatomy payload truncates
each finding's URL list at ten. A floor above the cap is certainly above it and
the bar refuses; a floor below it may still be above, and there the bar offers
and the server answers — in rendered text, through `ErrorNote`, which is the
disclosure this finding is about. Claiming a total the screen cannot know is
how the bar came to say 10 above a column reading 12.

**Split across the two CI legs**, the convention `test_site_level_tick.py` and
`test_measured_share_on_screen.py` both record. The route half and the payload
half run everywhere; the half about what the browser painted drives a real
server with a real browser and runs in `rendered-a11y`, where a skip fails the
job.
"""

from __future__ import annotations

from tests.last_resort import on_the_layout_of_last_resort
import json
import socket
import threading
import time
from pathlib import Path

import pytest

import clauditseo.modules  # noqa: F401  (registers the dimensions)
from clauditseo.persistence import runs
from tests.conftest import FixtureSite
from tests.test_a11y_rendered import DIST
from tests.test_verify import _routes, _seeded
from tests.parts import open_part

NEEDS_BROWSER = pytest.mark.skipif(
    not DIST.exists(), reason="dashboard/dist not built")


def _widen(conn, fingerprint: str, n: int, prefix: str = "p") -> list[str]:
    """Give one finding `n` distinct crawlable pages.

    One finding naming many pages is the shape the finding was raised on —
    `img-alt-missing` across a whole site is one row and one tick — so the
    batch is widened the way the product widens it rather than by seeding `n`
    findings, which would test the wrong thing and cost an `n`-page crawl to
    set up.

    `prefix` keeps two widened findings disjoint. It matters only for the
    `floored` fixture below, where the two batches overlapping would let the
    server dedupe back under the cap and the refusal being tested would never
    fire.
    """
    urls = [f"https://fixture.test/{prefix}{i}" for i in range(n)]
    conn.execute(
        "UPDATE findings SET affected_urls=? WHERE rowid=("
        "  SELECT f.rowid FROM findings f WHERE f.fingerprint=?"
        "  ORDER BY f.rowid DESC LIMIT 1)",
        (json.dumps(urls), fingerprint))
    conn.commit()
    return urls


# --- the route ---------------------------------------------------------------

def test_a_batch_over_the_cap_is_refused_before_anything_is_crawled(tmp_path):
    """The cap is the finding. A refusal that has already spent the crawl is
    not one, so this asserts the run row too: the three refusals above it all
    fire before `create_run`, and this one has to join them rather than sit
    after the budget is built.
    """
    from fastapi.testclient import TestClient

    from clauditseo.api.app import create_app

    site = FixtureSite(_routes()).start()
    try:
        db, conn, site_id, fps = _seeded(tmp_path, site)
        _widen(conn, fps[0], runs.VERIFY_PAGE_CAP + 1)
        before = conn.execute("SELECT COUNT(*) n FROM audit_runs").fetchone()["n"]

        client = TestClient(create_app(db_path=db))
        resp = client.post(f"/api/sites/{site_id}/verify",
                           json={"fingerprints": [fps[0]]})

        assert resp.status_code == 422, resp.text
        detail = resp.json()["detail"]
        assert str(runs.VERIFY_PAGE_CAP + 1) in detail, (
            f"the refusal must name what was asked for: {detail!r}")
        assert str(runs.VERIFY_PAGE_CAP) in detail, (
            f"the refusal must name the ceiling: {detail!r}")
        after = conn.execute("SELECT COUNT(*) n FROM audit_runs").fetchone()["n"]
        assert after == before, (
            "a refused batch created a run row, so the refusal happens after "
            "the crawl was committed to rather than before it")
    finally:
        site.stop()


def test_a_batch_at_the_cap_is_still_accepted(tmp_path):
    """The counter-assertion. A guard that refuses the ordinary case is not a
    cap, it is an outage — and `>` against `>=` is exactly the slip this
    catches.
    """
    from fastapi.testclient import TestClient

    from clauditseo.api.app import create_app

    site = FixtureSite(_routes()).start()
    try:
        db, conn, site_id, fps = _seeded(tmp_path, site)
        _widen(conn, fps[0], runs.VERIFY_PAGE_CAP)
        client = TestClient(create_app(db_path=db))
        resp = client.post(f"/api/sites/{site_id}/verify",
                           json={"fingerprints": [fps[0]]})
        assert resp.status_code == 200, resp.text
    finally:
        site.stop()


def test_both_screens_are_told_the_cap_the_route_enforces(tmp_path):
    """One owner, checked at both readers.

    The two `MarkBar` call sites read two different payloads — `site_detail`
    on the record tab, `site_anatomy` on Current — so a cap carried on one and
    not the other is a screen that offers what the server refuses, which is the
    defect round 066 closed for the tick. Compared against the constant rather
    than against a literal, so the two cannot drift.
    """
    from fastapi.testclient import TestClient

    from clauditseo.api.app import create_app

    site = FixtureSite(_routes()).start()
    try:
        db, _conn, site_id, _fps = _seeded(tmp_path, site)
        client = TestClient(create_app(db_path=db))
        for path in (f"/api/sites/{site_id}",
                     f"/api/sites/{site_id}/anatomy"):
            body = client.get(path).json()
            assert body.get("verify_page_cap") == runs.VERIFY_PAGE_CAP, (
                f"{path} does not carry the verify cap the route enforces: "
                f"{body.get('verify_page_cap')!r}")
    finally:
        site.stop()


# --- the screen, as painted --------------------------------------------------

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


#: A finding the default fixture audit raises against a page, so it can be
#: marked and then widened past the cap.
PAGED = "TEC/robots-missing"


@pytest.fixture(scope="module")
def capped():
    """A real server holding one audit, with one marked finding widened past
    the cap.

    Its own server rather than `test_a11y_rendered.py`'s `served`, for that
    fixture's own stated reason: it is asserted on by several files for its run
    count and its trend, and adding state to it to prove something about
    another screen is how a shared fixture stops being readable.

    The mark is made through the route the operator's tick calls, so the bar
    reaches the marked state the way the product reaches it.
    """
    import tempfile

    import httpx
    import uvicorn

    from clauditseo.api.app import create_app
    from clauditseo.db.connection import connect
    from tests.test_coverage import DIMS, _Hub, _run

    tmp = Path(tempfile.mkdtemp(prefix="verifycap"))
    db = tmp / "clauditseo.db"
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

    base = f"http://127.0.0.1:{port}"
    try:
        client = httpx.post(f"{base}/api/clients",
                            json={"name": "Cap Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "cap.fixture"}, timeout=30).json()
        conn = connect(db)
        run_id = runs.create_run(conn, site["id"], DIMS, "T2")
        runs.complete_run(conn, run_id, _run(_Hub()))
        marks = {f"{s['dimension']}/{s['check_id']}": s["fingerprint"]
                 for s in runs.site_states(conn, site["id"])}
        assert PAGED in marks, (
            f"the fixture no longer raises {PAGED}; pick another paged finding")
        _widen(conn, marks[PAGED], runs.VERIFY_PAGE_CAP + 5)
        conn.close()
        httpx.post(
            f"{base}/api/sites/{site['id']}/states/{marks[PAGED]}/attempt",
            json={"note": ""}, timeout=30).raise_for_status()
        yield base, site["id"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def _record_bar(base: str, site_id: str) -> str:
    """The mark bar on the record tab, as a browser painted it."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        on_the_layout_of_last_resort(pg)
        try:
            pg.goto(f"{base}/#/sites/{site_id}", wait_until="load",
                    timeout=30_000)
            pg.wait_for_selector("a.seq-name", timeout=30_000)
            pg.click("a.seq-name:text-is('Record')")
            # The record opens on open + regressed (plan §4a);
            # this reads rows in every state.
            pg.click('[aria-label="state filter"] [data-state="all"]')
            # The record groups by check since brief step 6; these read instances.
            pg.select_option('select[aria-label="group by"]', "none")
            pg.wait_for_selector(".mark-bar", timeout=30_000)
            return pg.inner_text(".mark-bar")
        finally:
            browser.close()


@NEEDS_BROWSER
def test_the_bar_refuses_a_batch_over_the_cap_in_rendered_text(capped):
    """DISCIPLINE rule 12 — the tree is not where a screen counts.

    `inner_text`, not `inner_html`: a reason living in a `title` is the half of
    this finding that reports 013 to 038 kept naming, so an assertion a `title`
    would satisfy cannot be the guard for it.
    """
    base, site_id = capped
    text = _record_bar(base, site_id)

    assert "verify " not in text.lower(), (
        "the bar offers a verification for a batch the server would refuse "
        f"422: {text!r}")
    assert str(runs.VERIFY_PAGE_CAP) in text, (
        f"the bar withholds the verify without naming the ceiling: {text!r}")
    assert str(runs.VERIFY_PAGE_CAP + 5) in text, (
        f"the bar withholds the verify without naming what was asked for: "
        f"{text!r}")


@NEEDS_BROWSER
def test_the_bar_states_the_cost_of_a_verification_in_text(capped):
    """The other half. Whatever the bar says a verification costs, it says on
    the screen.

    Driven with the batch brought back under the cap, because the sentence
    being asserted is the one beside an offered button. The widened row is the
    one seeded as marked, so unticking it and ticking any other leaves a batch
    the server would accept.
    """
    from playwright.sync_api import sync_playwright

    base, site_id = capped
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        on_the_layout_of_last_resort(pg)
        try:
            pg.goto(f"{base}/#/sites/{site_id}", wait_until="load",
                    timeout=30_000)
            pg.wait_for_selector("a.seq-name", timeout=30_000)
            pg.click("a.seq-name:text-is('Record')")
            # The record opens on open + regressed (plan §4a);
            # this reads rows in every state.
            pg.click('[aria-label="state filter"] [data-state="all"]')
            # The record groups by check since brief step 6; these read instances.
            pg.select_option('select[aria-label="group by"]', "none")
            pg.wait_for_selector("input.fix-chk", timeout=30_000)
            pg.uncheck("input.fix-chk:checked")
            pg.check("input.fix-chk >> nth=0")
            pg.wait_for_selector(".mark-bar", timeout=30_000)
            text = pg.inner_text(".mark-bar")
        finally:
            browser.close()

    low = text.lower()
    assert "model token" in low or "while you wait" in low, (
        "the only statement of what a verification costs is still reachable "
        f"by hovering: {text!r}")


# --- the other screen, where the refusal has nowhere to land ------------------

#: Two findings the default fixture audit raises into one anatomy category
#: (`crawl`, "Crawl & sitemaps"), both naming a page. Two rather than one, and
#: the reason is the whole point of the case below — see `floored`.
FLOORED = ("TEC/sitemap-missing", "TEC/robots-missing")

#: How many pages each of the two gets. The anatomy payload sends at most ten
#: URLs per finding (`runs.py`, `"urls": urls[:10]`) with the true total beside
#: it, and `MarkBar` on Current takes `max(union-of-the-lists, largest total)`.
#: So the screen sees `2 x 10 = 20` and the server counts `2 x 15 = 30`: under
#: the cap on one side of the wire and over it on the other. The arithmetic is
#: asserted rather than trusted in the fixture below, because if the cap moves
#: these numbers stop straddling it and the test would pass by not reproducing.
FLOOR_PER_FINDING = 15


@pytest.fixture(scope="module")
def floored():
    """A batch the screen counts under the cap and the server counts over it.

    **The dead end this fixture exists to record.** The obvious reproduction —
    widen one finding past the cap, open Current, press verify — cannot work,
    and neither can the one report 068 named ("tick `title-duplicate`, 38
    pages against a cap of 25, press verify from the Current pane"). With one
    finding, `pages` on Current is the finding's own untruncated total, so
    `MarkBar`'s `over` is true and it *withholds the verify button entirely*
    rather than offering it — the branch `test_the_bar_refuses_a_batch_over_
    the_cap_in_rendered_text` above already proves. There is no press, so
    there is no 422, so nothing is proved about where a 422 would land.

    The floor is only a floor **across findings**: two truncated ten-URL lists
    cannot be deduped against each other, so the screen's count stops at 20
    however many pages the two findings really name. That is the case
    `useFixLoop`'s own comment calls "the backstop for the case a screen
    cannot see", and it is the only one that puts an error on this screen.
    """
    import tempfile

    import httpx
    import uvicorn

    from clauditseo.api.app import create_app
    from clauditseo.db.connection import connect
    from tests.test_coverage import DIMS, _Hub, _run

    screen_sees = 2 * 10           # two lists, truncated at ten each
    server_sees = 2 * FLOOR_PER_FINDING
    assert screen_sees <= runs.VERIFY_PAGE_CAP < server_sees, (
        f"the cap moved to {runs.VERIFY_PAGE_CAP} and this fixture no longer "
        f"straddles it: the screen would count {screen_sees} and the server "
        f"{server_sees}. Re-pick FLOOR_PER_FINDING so the screen is under and "
        f"the server is over, or this test passes without reproducing.")

    tmp = Path(tempfile.mkdtemp(prefix="floored"))
    db = tmp / "clauditseo.db"
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

    base = f"http://127.0.0.1:{port}"
    try:
        client = httpx.post(f"{base}/api/clients",
                            json={"name": "Floor Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "floor.fixture"}, timeout=30).json()
        conn = connect(db)
        run_id = runs.create_run(conn, site["id"], DIMS, "T2")
        runs.complete_run(conn, run_id, _run(_Hub()))
        marks = {f"{s['dimension']}/{s['check_id']}": s["fingerprint"]
                 for s in runs.site_states(conn, site["id"])}
        for i, check in enumerate(FLOORED):
            assert check in marks, (
                f"the fixture no longer raises {check}; the two findings must "
                f"sit in one anatomy category and both name a page")
            # Disjoint, by construction: overlapping pages would let the
            # server dedupe down under the cap and the refusal would not fire.
            _widen(conn, marks[check], FLOOR_PER_FINDING, prefix=f"f{i}")
        conn.close()
        for check in FLOORED:
            httpx.post(
                f"{base}/api/sites/{site['id']}/states/{marks[check]}/attempt",
                json={"note": ""}, timeout=30).raise_for_status()
        yield base, site["id"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@NEEDS_BROWSER
def test_the_current_pane_says_why_a_verification_was_refused(floored):
    """DISCIPLINE rule 12 again, on the screen that had no reader.

    `useFixLoop` stores every refusal in `error` and returns it; The record
    renders it and Current destructured four fields and not that one, so four
    422s and one 502 reached this pane as nothing at all — the button said
    "looking…", came back, and no sentence appeared.

    The button being offered at all is asserted first, and is not a
    convenience: it is the precondition that makes this the live case rather
    than a hypothetical. If `MarkBar` withholds here, the screen and the
    server agree about the count and there is no refusal to render.
    """
    from playwright.sync_api import sync_playwright

    base, site_id = floored
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        on_the_layout_of_last_resort(pg)
        try:
            pg.goto(f"{base}/#/sites/{site_id}?tab=findings", wait_until="load",
                    timeout=30_000)
            pg.wait_for_selector(".anat-layout", timeout=30_000)
            open_part(pg, 'Crawl & sitemaps')
            pg.wait_for_selector(".mark-bar", timeout=30_000)

            bar = pg.inner_text(".mark-bar")
            assert "verify " in bar.lower(), (
                "the bar withheld the verify, so the screen and the server "
                f"agree about the count and there is no refusal to land: "
                f"{bar!r}")

            pg.click(".mark-bar button.mark-verify")
            pg.wait_for_timeout(2_000)
            pane = pg.inner_text(".anat-pane, .anat-layout")
        finally:
            browser.close()

    server_sees = 2 * FLOOR_PER_FINDING
    assert str(server_sees) in pane and str(runs.VERIFY_PAGE_CAP) in pane, (
        "the verify route refused this batch 422 and the Current pane painted "
        f"nothing: neither {server_sees} nor {runs.VERIFY_PAGE_CAP} is on the "
        f"screen. The refusal reached `setError` and no reader: {pane!r}")
