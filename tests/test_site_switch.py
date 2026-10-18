"""Nothing on the client screen may survive a change of client.

The operator switched from one client to another and the screen kept the
first one's state: the page filter still held a URL belonging to the previous
site, so every category on the new client read 0 and the screen said a site
with five hundred open findings was clean; and the open brief still held the
previous client's report, so one company's entity graph sat under another
company's name in the header.

The filter was the worse half because it concealed itself. A `<select>`
cannot display a value that is not among its options, so the control fell
back to showing "All pages" while React still held the old URL and still sent
it with every request. The screen was filtered and said it was not.

This has to be a browser test. The bug is not in a query or a component in
isolation — every part was correct on its own — it is in state outliving the
thing it describes, which only exists once a real app has mounted, fetched,
and been navigated. Both halves are asserted the way they actually failed:
the request must carry no stale filter, and the report must be gone.

`test_a_site_added_in_the_app_is_offered_by_the_picker` is the same provider's
other half, and the same shape of bug: state that outlives what it describes.
There the selection survived a switch it should not have; here the list of
things that can be selected does not survive an addition it should.
`SelectionProvider` fetched `/api/sites` once on mount, so a site created
after the tab was opened was invisible to every screen that picks a target
until a reload — B-20, WF-14 and KI-34, one defect held in three registers.

`test_the_remembered_client_is_the_one_the_app_opens` is WF-99, and it is the
same provider a third time — the *remembered* selection rather than the live
one. It is here rather than in a file of its own because it needs what this
module's fixture already builds and no other fixture has: **two** clients with
distinct ids, which is what makes "the remembered one was opened" separable
from "the first one was". It is ordered before the picker test for that
fixture's own stated reason — that test adds a third site, and everything
above it is written against the two the fixture seeds.

The tests are named rather than numbered above because they were numbered, and
a test inserted between them left the numbering false — CQ-216's shape, in the
commit that closed CQ-216.

Skips rather than fails without Playwright or a built dashboard, matching
`test_a11y_rendered.py` — a bare `pip install -e .[dev]` still runs green.

**`scripts/prove_fail.py` could not answer for this file and did not say
so** — true when this was written, repaired since; `needs_build` now derives
the refused set from the import graph and refuses this file by name.
Its own caveat is the reason: it reverts `dashboard/src` and does not rebuild
`dashboard/dist`, which is what these tests load, so the answer would be about
the bundle on disk rather than about the parent commit. It refuses such tests
through `NEEDS_BUILD`, a hand-kept tuple holding `tests/test_a11y_rendered.py`
alone — this file is equally a bundle test and is absent from it, so the
script would have answered confidently and wrongly. Rule 1 was satisfied by
hand instead: built from the unfixed source, watched the third test fail,
fixed, rebuilt, watched it pass. The counts are in the fix commit. Widening
`NEEDS_BUILD` was left alone deliberately — a hand-kept list standing in for a
derived population is the defect, and adding a second element to it is not
the fix. That argument is what CQ-164 was eventually taken on: the tuple is
gone and the property is computed.
"""

from __future__ import annotations

from tests.last_resort import on_the_layout_of_last_resort
import socket
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from clauditseo import axe
from tests.parts import ANATOMY_READY, open_page_filter

DIST = Path(__file__).resolve().parents[1] / "dashboard" / "dist"

pytestmark = [
    pytest.mark.skipif(not axe.available(),
                       reason="needs clauditseo[render] and `playwright install chromium`"),
    pytest.mark.skipif(not (DIST / "index.html").is_file(),
                       reason="dashboard not built (npm run build in dashboard/)"),
]

#: Different paths per site, so a filter carried across cannot accidentally
#: match and pass. This is the real-world case: one client's URL is never a
#: URL of another's.
PAGES = {
    "alpha": ("/", "/alpha-one", "/alpha-two"),
    "beta": ("/", "/beta-one", "/beta-two"),
}

HTML = ("<html lang=en><head><title>t</title></head><body><main><h1>h</h1>"
        "<h4>skipped</h4><img src=/i.png><p>Short.</p></main></body></html>")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _routes(paths):
    out = {"/robots.txt": (200, {"Content-Type": "text/plain"},
                           "User-agent: *\nAllow: /\n")}
    for p in paths:
        body = HTML if p == "/" else HTML.replace(
            "<p>Short.</p>", f"<p>Short.</p><a href='{p}'>x</a>")
        out[p] = (200, {}, body)
    out["/"] = (200, {}, HTML + "".join(
        f"<a href='{p}'>x</a>" for p in paths if p != "/"))
    return out


@pytest.fixture(scope="module")
def served(tmp_path_factory):
    """A server holding two clients, each with its own audited site."""
    import httpx
    import uvicorn

    from clauditseo.api.app import create_app
    from clauditseo.crawler.crawl import crawl
    from clauditseo.crawler.types import TierBudget
    from clauditseo.db.connection import connect
    from clauditseo.engine.core import run_audit
    from clauditseo.engine.types import Site, Tier
    from clauditseo.persistence import runs
    from tests.conftest import FixtureSite

    db = tmp_path_factory.mktemp("switch") / "clauditseo.db"
    app = create_app(db_path=db)
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
                                           log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    deadline = time.time() + 30
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:
        pytest.fail("server did not start")

    base = f"http://127.0.0.1:{port}"
    dims = ["ONP", "A11Y"]
    ids = {}
    for name, paths in PAGES.items():
        client = httpx.post(f"{base}/api/clients", json={"name": name},
                            timeout=30).json()
        fixture = FixtureSite(_routes(paths)).start()
        try:
            site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                              json={"domain": fixture.base_url + "/"},
                              timeout=30).json()
            crawled = crawl(fixture.base_url + "/", Tier.T2,
                            budget=TierBudget(max_pages=20, request_timeout_s=5,
                                              wall_clock_s=30, delay_s=0))
            result = run_audit(Site(domain=fixture.base_url + "/"), crawled,
                               dims, Tier.T2)
        finally:
            fixture.stop()
        conn = connect(db)
        # Twice: a finding seen once is a candidate, and the tree counts only
        # what is open.
        last = None
        for _ in range(2):
            last = runs.create_run(conn, site["id"], dims, "T2")
            runs.complete_run(conn, last, result)
        # A stored brief, because without one this fixture cannot express the
        # thing the report clause is about. `analysed_by` is what puts a
        # `read <tool>` button in `.cat-run`, and it is filled from
        # `expert_reports` — a sweep-only audit leaves it empty, there is no
        # panel to open, and the clause below skipped itself for want of a
        # subject. It had done so since the day it was written (`dccbc71`,
        # 12 August): the fixture has always run `run_audit` with two sweep
        # dimensions and stored nothing else.
        #
        # That skip is not free. `test_site_switch.py` is named in CI's
        # `axe over every screen` job, whose whole point is that these
        # clauses may skip in the job without a browser precisely because
        # they may not skip in the one with it — so the job greps its own
        # log for `N skipped` and fails. One silent skip here was failing
        # that job for every commit.
        runs.store_expert_report(
            conn, last, "indexability",
            {"model": "fixture",
             "report": "## Findings\n\nA brief ran here.",
             "findings": [], "figures_to_verify": []})
        conn.close()
        ids[name] = site["id"]

    try:
        yield base, ids
    finally:
        server.should_exit = True


def test_switching_client_drops_the_previous_one_s_page_filter(served):
    """Asserted on the request, not the control.

    The control is exactly what lied: it read "All pages" throughout. Only
    the URL the app actually asked for shows whether a filter was still
    applied, which is why this watches the network rather than the DOM.
    """
    from playwright.sync_api import sync_playwright

    base, ids = served
    asked: list[str] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        on_the_layout_of_last_resort(page)
        page.on("request", lambda r: asked.append(r.url)
                if "/anatomy" in r.url else None)
        try:
            page.goto(f"{base}/#/sites/{ids['alpha']}", wait_until="networkidle")
            page.wait_for_selector(ANATOMY_READY, timeout=15000)

            # Narrow to one of alpha's pages. The control is a typeahead
            # over a datalist rather than a select — on a hundred-page site a
            # select was a scroll — so the page is chosen by typing its path,
            # which is also what an operator does.
            paths = page.eval_on_selector_all(
                "#anat-pages option",
                "els => els.map(e => e.value)")
            assert paths, "no page to narrow to"
            open_page_filter(page)
            page.fill(".page-find", paths[0])
            page.dispatch_event(".page-find", "change")
            page.wait_for_timeout(1200)
            filtered = [u for u in asked if "page=" in u]
            assert filtered, "narrowing sent no filtered request"

            # Now the other client.
            asked.clear()
            page.goto(f"{base}/#/sites/{ids['beta']}", wait_until="networkidle")
            page.wait_for_selector(ANATOMY_READY, timeout=15000)
            page.wait_for_timeout(1200)

            beta = [u for u in asked if f"/sites/{ids['beta']}/anatomy" in u]
            assert beta, "the new client's anatomy was never requested"
            carried = [u for u in beta
                       if parse_qs(urlsplit(u).query).get("page")]
            assert not carried, (
                "the previous client's page filter was still being sent: "
                f"{carried[0]}")

            # And the consequence the operator actually saw: a site with open
            # findings reading zero everywhere.
            # The landing's waiting lane counts what is open since the
            # sidebar's retirement (brief v24 step BO).
            page.wait_for_selector(".lane-waiting .cl-entry", timeout=15000)
            total = page.eval_on_selector_all(
                ".lane-waiting .cl-entry dd",
                "els => els.map(e => e.textContent.trim())"
                ".filter(t => /^\\d+$/.test(t)).reduce((a, b) => a + (+b), 0)")
            assert total > 0, "every category read zero after the switch"
        finally:
            browser.close()


def test_switching_client_closes_the_previous_one_s_report(served):
    """A brief belongs to the site it was run for. Left open across a switch
    it is not merely stale — it is attributed to whoever the header now
    names."""
    from playwright.sync_api import sync_playwright

    base, ids = served
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        on_the_layout_of_last_resort(page)
        try:
            page.goto(f"{base}/#/sites/{ids['alpha']}", wait_until="networkidle")
            page.wait_for_selector(ANATOMY_READY, timeout=15000)
            # Walk the leaves until one offers a readable brief, rather than
            # clicking the first non-zero one and hoping. Which category
            # carries a report is a property of the fixture and of the
            # catalogue, and hard-coding either makes this clause skip the
            # day a tool is retired — which is exactly what happened: it
            # skipped from the day it was written and nobody saw, because a
            # skip reads as green everywhere except the one CI job that
            # greps for it.
            from tests.test_fetch_state import _PART_KEYS_JS, open_part_key
            opened = False
            for key in page.evaluate(_PART_KEYS_JS):
                open_part_key(page, key)
                page.wait_for_timeout(250)
                opened = page.evaluate(
                    "() => { const b = [...document.querySelectorAll('.cat-run "
                    ".tone')].find(x => /^(read|open) /.test(x.textContent));"
                    " if (!b) return false; b.click(); return true; }")
                if opened:
                    break
            assert opened, (
                "no category offered a readable brief, so this clause has "
                "nothing to open and cannot test that the panel dies with "
                "the client. The fixture stores one against "
                "`indexability`; if that tool leaves the catalogue, or that "
                "category gains a part page, store one for a tool that is in "
                "the catalogue and whose category still renders `.cat-run` "
                "rather than letting this skip.")
            page.wait_for_timeout(1200)

            page.goto(f"{base}/#/sites/{ids['beta']}", wait_until="networkidle")
            page.wait_for_selector(ANATOMY_READY, timeout=15000)
            page.wait_for_timeout(900)
            assert page.query_selector(".sec-report") is None, (
                "the previous client's brief was still on screen under the "
                "new client's name")
        finally:
            browser.close()


#: The key `SelectionProvider` remembers the operator's client in
#: (`dashboard/src/selection.tsx`). Spelled out here rather than imported
#: because there is nothing to import it from, and checked against the source
#: below so the two cannot drift apart silently.
REMEMBERED_KEY = "clauditseo:site"


def test_the_key_this_file_writes_is_the_key_the_app_reads():
    """Non-vacuity for the drive below, and cheap enough to run without a
    browser. A test that seeded some *other* key would drive the default-
    selection path while claiming to drive the remembered one, and would pass
    for as long as both clients happened to resolve the same way."""
    source = (Path(__file__).resolve().parents[1] / "dashboard" / "src"
              / "selection.tsx").read_text(encoding="utf-8")
    assert f'const KEY = "{REMEMBERED_KEY}"' in source, (
        f"selection.tsx no longer remembers the selection in "
        f"{REMEMBERED_KEY!r}, so the drive below seeds a key nothing reads")


def _client_the_app_opens(browser, base: str, remembered: str) -> str:
    """Which client the app opens at `#/reports`, having been told to remember
    `remembered` **before the document loads**.

    `add_init_script` rather than a write after `goto`, and that is the whole
    point of WF-99: `SelectionProvider` reads the key once, inside the
    `/api/sites` effect, so a drive that writes it afterwards cannot reach the
    remembered path at all — the read has already happened. A drive of exactly
    that shape is on the record as KI-54, and it retired WF-98 on evidence
    that could not tell *"the remembered id was used"* from *"the remembered
    id was never read"*, because both paint the same screen.

    `#/reports` is the observable, because `ToSelectedSite` redirects it to
    `#/sites/<the selection>/reports` — so the selection is in the URL rather
    than inferred from what a screen drew.
    """
    page = browser.new_page()
    on_the_layout_of_last_resort(page)
    try:
        page.add_init_script(
            f"localStorage.setItem({REMEMBERED_KEY!r}, {remembered!r})")
        page.goto(f"{base}/#/reports", wait_until="networkidle")
        page.wait_for_function(
            "() => location.hash.startsWith('#/sites/')", timeout=15000)
        return urlsplit(page.url).fragment.split("/")[2]
    finally:
        page.close()


def test_the_remembered_client_is_the_one_the_app_opens(served):
    """WF-99. Both clients are driven, and that pair is the evidence.

    Asserting one alone cannot separate the two outcomes: the app falls back
    to `s[0]?.id` when nothing is remembered, so a single drive that opened
    the remembered client would also have passed had the key never been read
    and that client merely happened to be first. Seeding each in turn and
    getting a *different* answer each time is only possible if the remembered
    value is what decided — which is the discrimination KI-54 lacked.
    """
    from playwright.sync_api import sync_playwright

    base, ids = served
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            opened = {name: _client_the_app_opens(browser, base, ids[name])
                      for name in ("alpha", "beta")}
        finally:
            browser.close()

    assert opened["alpha"] != opened["beta"], (
        "the app opened the same client whichever one was remembered "
        f"({opened['alpha']}), so the remembered id was never read and the "
        "selection came from the site list's own order")
    for name in ("alpha", "beta"):
        assert opened[name] == ids[name], (
            f"with {name} remembered before the document loaded, the app "
            f"opened {opened[name]} instead")


#: Distinctive enough that a substring test cannot match either fixture site,
#: both of which are `127.0.0.1:<port>`.
ADDED_DOMAIN = "picker-refresh.example"


def _picker_options(page) -> list[str]:
    """What the global site picker is offering, read from the datalist.

    The datalist is the list itself. The `<input>` beside it shows the current
    selection and would read the same whether the list behind it were fresh or
    a year old, so asserting on the input would assert on the wrong element —
    the same trap the page-filter test above records, where a control read
    "All pages" while the state behind it said otherwise.
    """
    return page.eval_on_selector_all(
        "#site-search-list option", "els => els.map(e => e.value)")


def test_a_site_added_in_the_app_is_offered_by_the_picker(served):
    """Driven through the app's own form, because that is where it happened.

    An out-of-band `POST /api/clients/{id}/sites` from the test would prove
    something weaker and different — that the provider polls — which is not
    the fix and not the complaint. The operator added the site on Home and
    went to Tools to audit it; the path under test is the one their click
    takes.

    Ordered last in the file on purpose: it adds a third site to a
    module-scoped fixture, and the two tests above assert against specific
    site ids that an extra row does not disturb.
    """
    from playwright.sync_api import TimeoutError as PWTimeout
    from playwright.sync_api import sync_playwright

    base, _ids = served

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        on_the_layout_of_last_resort(page)
        try:
            page.goto(f"{base}/#/", wait_until="networkidle")
            # `state="attached"`, not the default. An `<option>` inside a
            # `<datalist>` is never rendered — the browser paints the dropdown
            # itself — so Playwright's visibility wait can never be satisfied
            # here. The first version of this line timed out after fifteen
            # seconds having already resolved both options, and reported the
            # timeout rather than the defect under test.
            page.wait_for_selector("#site-search-list option", timeout=15000,
                                   state="attached")

            before = _picker_options(page)
            # The guard has to be able to disagree with itself: if the picker
            # already offered this domain, everything below would pass without
            # the fetch under test ever running.
            assert len(before) == 2, f"expected the two fixture sites, got {before}"
            assert not [o for o in before if ADDED_DOMAIN in o], (
                f"the domain under test was already on offer: {before}")

            page.click(".home-add-open")  # item 176: an action in Home's head
            page.wait_for_selector("input[aria-label='new site domain']",
                                   timeout=10000)
            page.select_option("select[aria-label='client for the new site']",
                               label="alpha")
            page.fill("input[aria-label='new site domain']", ADDED_DOMAIN)
            page.click(".add-forms button:has-text('Add site')")

            # The row must exist server-side before the picker can be blamed
            # for not showing it — otherwise a rejected POST reads as a stale
            # list, and the test would name the wrong defect.
            page.wait_for_function(
                "d => fetch('/api/sites').then(r => r.json())"
                ".then(s => s.some(x => (x.domain || '').includes(d)))",
                arg=ADDED_DOMAIN, timeout=15000)

            try:
                page.wait_for_function(
                    "d => [...document.querySelectorAll('#site-search-list option')]"
                    ".some(o => o.value.includes(d))",
                    arg=ADDED_DOMAIN, timeout=8000)
            except PWTimeout:
                pass

            after = _picker_options(page)
            assert [o for o in after if ADDED_DOMAIN in o], (
                "a site added through the app is stored but not offered: the "
                "picker still lists only what existed when the tab was opened, "
                f"so it cannot be selected without a reload. offering {after}")
        finally:
            browser.close()
