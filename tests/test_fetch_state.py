"""`useFetch` must not answer for a request it is no longer making.

WF-13 and UX-13, first named at audit 011 and carried in
`audits/DISPOSITIONS.md`'s engineering set for eleven rounds. One hook, two
harms, and both are the same omission: the effect started a new request
without saying anything about the state left over from the old one.

- **The error is never cleared.** `setError` was called and nothing ever
  called `setError(null)`, so the first dropped request poisoned the hook for
  the life of the component. Every screen reads `if (error) return
  <ErrorNote/>` before it reads `data`, and `App.tsx` mounts
  `SiteDetailView` unkeyed — so a 503 on one site put an error on screen that
  navigating to a *different, healthy* site could not clear. The operator's
  only recovery was a full reload, and nothing on the screen said so. That is
  WF-13's "no disclosed recovery path", asserted here the way it actually
  failed: not by unit-testing the hook, but by breaking one site and walking
  to another.

- **The previous path's data outlives the path.** `live` dropped a superseded
  *reply*; nothing dropped the superseded *state*. So between a site change
  and its response, the screen rendered the previous site's tab counts under
  the new site's URL — a number that is not about the thing the address bar
  names. That is UX-13.

**Why the third test is here and not somewhere smaller.** `loading` and
`retry` are new fields on a hook that renders nothing, and this repository
has just spent a round (CQ-23, twelve rounds carried) on a stored figure with
a writer and no reader. A field no screen reads is that defect in a new
place, so the reader ships with the writer and is asserted from the screen.

**This has to be a browser test.** Every part is correct in isolation: the
fetch resolves, the component renders what it is given, the router routes.
The defect is state outliving the request it describes, which only exists
once a real app has mounted, fetched and been navigated — and the navigation
must be in-app, since a reload remounts the component and takes the stale
state with it.

Requests are stalled rather than delayed. A `time.sleep` inside a sync
Playwright route handler blocks the browser and serialises the race it is
meant to create — DISCIPLINE rule 1 records that exact mistake costing UX-09
its first guard. A handler that returns without calling `continue_`,
`fulfill` or `abort` leaves the request pending, which is the intermediate
state this file needs to look at.

Skips rather than fails without Playwright or a built dashboard, matching
`test_a11y_rendered.py` and `test_site_switch.py` — a bare
`pip install -e .[dev]` still runs green.

**`scripts/prove_fail.py` cannot answer for this file**, for the reason
`test_site_switch.py` records: it reverts `dashboard/src` without rebuilding
`dashboard/dist`, which is what these tests load, so its answer would be
about the bundle on disk rather than about the parent commit. Rule 1 was
satisfied by hand instead — built from the unfixed source, watched the first
two tests fail and the third fail on a missing control, fixed, rebuilt,
watched all three pass. The counts are in the fix commit. `NEEDS_BUILD` was
left alone deliberately, for the reason that file gives: a hand-kept list
standing in for a derived population is the defect, and adding to it is not
the fix. It has since been replaced by a derived one, so this file is refused
by name and the hand proof above is history rather than standing practice.
"""

from __future__ import annotations

from tests.last_resort import on_the_layout_of_last_resort
import re
import socket
import threading
import time
from pathlib import Path

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

HTML = ("<html lang=en><head><title>t</title></head><body><main><h1>h</h1>"
        "<h4>skipped</h4><img src=/i.png><p>Short.</p></main></body></html>")

#: Alpha is audited so its screen carries non-zero tab counts; beta is bare so
#: its own counts are all zero. A count that survives the walk from one to the
#: other is therefore alpha's by construction, not by inference — the two
#: sites cannot produce the same number.
PATHS = ("/", "/one", "/two")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _routes():
    out = {"/robots.txt": (200, {"Content-Type": "text/plain"},
                           "User-agent: *\nAllow: /\n")}
    for p in PATHS:
        out[p] = (200, {}, HTML)
    out["/"] = (200, {}, HTML + "".join(
        f"<a href='{p}'>x</a>" for p in PATHS if p != "/"))
    return out


@pytest.fixture(scope="module")
def served(tmp_path_factory):
    """One client, one audited site, one bare site."""
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

    db = tmp_path_factory.mktemp("fetchstate") / "clauditseo.db"
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
    client = httpx.post(f"{base}/api/clients", json={"name": "acme"},
                        timeout=30).json()
    dims = ["ONP", "A11Y"]

    fixture = FixtureSite(_routes()).start()
    try:
        alpha = httpx.post(f"{base}/api/clients/{client['id']}/sites",
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
    # Twice: a finding seen once is a candidate, and the counts on the tabs
    # read the standing position rather than the candidate set.
    for _ in range(2):
        runs.complete_run(conn, runs.create_run(conn, alpha["id"], dims, "T2"),
                          result)
    conn.close()

    # Never crawled and never audited, so every count on its screen is zero
    # and it can never be mistaken for alpha.
    beta = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                      json={"domain": "https://beta.example.org/"},
                      timeout=30).json()

    try:
        yield base, {"alpha": alpha["id"], "beta": beta["id"]}
    finally:
        server.should_exit = True


def _counts(page) -> list[str]:
    """Every rendered reference count on the site screen — the Pages and
    Notes chips, which are what the tab counts became when the tab row was
    retired (site-screen plan, step 5)."""
    return page.eval_on_selector_all(
        ".ref-n", "els => els.map(e => e.textContent.trim())")


def test_the_previous_site_s_counts_do_not_render_under_the_new_site_s_url(served):
    """UX-13, asserted on a number that can only have come from the old site.

    Beta's own reply is held open for the whole assertion, so nothing beta
    could have rendered has arrived. Any non-zero count on screen at that
    moment is alpha's, under beta's address.
    """
    from playwright.sync_api import sync_playwright

    base, ids = served

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        on_the_layout_of_last_resort(page)
        try:
            page.goto(f"{base}/#/sites/{ids['alpha']}", wait_until="networkidle")
            page.wait_for_selector(".refs", timeout=15000)
            alpha = _counts(page)
            assert any(c not in ("", "0") for c in alpha), (
                f"alpha's screen carries no non-zero count to detect: {alpha}")

            # Held, not delayed: the handler returns without continuing, so
            # the request stays pending and the browser stays responsive.
            page.route(f"**/api/sites/{ids['beta']}", lambda route: None)
            page.evaluate(
                f"window.location.hash = '#/sites/{ids['beta']}'")
            page.wait_for_timeout(1500)

            assert page.locator(".ref-n").count() == 0, (
                "the previous site's counts are still on screen under the "
                f"new site's URL: {_counts(page)} (alpha's were {alpha}, and "
                "beta's reply has not been delivered)")
            assert page.locator("p[role=status]").count() > 0, (
                "nothing on screen says a request is in flight")
        finally:
            browser.close()


def test_a_page_change_marks_the_evidence_stale_and_keeps_the_picker(served):
    """UX-13 on the one screen where blanking is the wrong remedy.

    `AnatomyView`'s screen is labelled by the site; its page filter is a
    control on that screen. Blanking on every path change would unmount the
    picker between keystrokes — the regression `2ed927a` fixed by removing
    the blanking outright, at the cost of leaving the previous page's counts
    on screen under the new page's name. Reports 025 and 030 name the remedy
    for this screen and it is neither: keep what is rendered and say it is
    the previous page's.

    So both halves are asserted together, because either one alone is a
    state the product has already shipped and had a finding raised about.
    """
    from playwright.sync_api import sync_playwright

    base, ids = served
    held: list = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        on_the_layout_of_last_resort(page)
        try:
            page.goto(f"{base}/#/sites/{ids['alpha']}", wait_until="networkidle")
            page.wait_for_selector(ANATOMY_READY, timeout=15000)
            assert page.locator(".stale-note").count() == 0, (
                "a settled screen claims to be loading something")

            paths = page.eval_on_selector_all(
                "#anat-pages option", "els => els.map(e => e.value)")
            assert paths, "no page to narrow to"

            page.route("**/anatomy?page=*", lambda route: held.append(route))
            open_page_filter(page)
            page.fill(".page-find", paths[-1])
            page.dispatch_event(".page-find", "change")
            page.wait_for_timeout(1500)

            assert held, (
                "narrowing sent no request, so nothing was in flight and this "
                "test proves nothing about the state during one")
            assert page.locator(".stale-note").count() == 1, (
                "the counts and evidence on screen are the previous page's "
                "and the screen does not say so")
            assert page.locator(".page-find").count() == 1, (
                "the picker was unmounted while the page it chose loaded — "
                "the operator cannot correct a mistyped path")
            assert page.locator(".anat-pane, .cl-landing").count() > 0, (
                "the whole screen was taken away rather than marked")
        finally:
            browser.close()


def test_an_error_on_one_site_does_not_survive_the_walk_to_another(served):
    """WF-13's first half: `setError(null)` was never called.

    Beta's request is left untouched and succeeds. Under the unfixed hook the
    error raised on alpha is still the first thing every screen checks, so
    beta renders alpha's failure instead of beta.
    """
    from playwright.sync_api import sync_playwright

    base, ids = served
    served_once = {"n": 0}

    def fail_alpha_once(route):
        if served_once["n"] == 0:
            served_once["n"] += 1
            route.fulfill(status=503, content_type="application/json",
                          body='{"detail": "alpha is unavailable"}')
        else:
            route.continue_()

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        on_the_layout_of_last_resort(page)
        try:
            page.route(f"**/api/sites/{ids['alpha']}", fail_alpha_once)
            page.goto(f"{base}/#/sites/{ids['alpha']}",
                      wait_until="domcontentloaded")
            page.wait_for_selector("p.error", timeout=15000)
            assert "alpha is unavailable" in page.inner_text("p.error")

            page.evaluate(f"window.location.hash = '#/sites/{ids['beta']}'")
            page.wait_for_timeout(2000)

            assert page.locator("p.error").count() == 0, (
                "a healthy site renders the previous site's error: "
                f"{page.inner_text('p.error')}")
            assert page.locator(".refs").count() > 0, (
                "the healthy site never rendered")
        finally:
            browser.close()


def test_the_error_offers_a_retry_and_says_when_it_is_trying(served):
    """WF-13's second half, and the reader for `loading` and `retry`.

    A hook renders nothing, so a `loading` flag and a `retry` callback that
    no screen reads would be CQ-23's defect in a new place — a writer with no
    reader — which is why this asserts from the rendered control rather than
    from the hook's return value.

    The retry is driven while the reply is held open, so the "trying" state
    is observed as a state and not as a flicker between two settled ones.

    **Where the busy word lives, and why this test used to say the opposite.**
    Until relay 126 the clause below read `"trying" in retry.inner_text()` —
    the busy word inside the button's own text, which is exactly UX-66: a
    button's label is its accessible name, so a name that changes mid-press is
    announced as a different control appearing. `ErrorNote` was the last of
    the twenty-nine controls in that class and the only one held back, because
    this assertion and the finding could not both hold and DISCIPLINE rule 6
    makes that the operator's call. `QUESTIONS.md` Q-43, answered *fix the
    control and re-point the test*. So the three clauses now assert strictly
    more than the one they replaced: the name is the same before and during
    the press, `aria-busy` carries the state the label stopped carrying, and
    "trying" is still on screen — in the `<p role="alert">` the button sits
    inside, which re-announces on change.

    This control could not take the `role="status"` region the other
    twenty-seven took: a region nested inside `role="alert"` is a live region
    inside a live region, and a `<div>` inside a `<p>` is invalid besides.
    That is why the words are read from `p.error` and not from a sibling.

    **The handler switches mode rather than counting requests**, because
    `/api/sites/<id>` has two independent callers on this screen: the view's
    own `useFetch` and `SelectionProvider` (`selection.tsx:127`), which fetches
    the same URL to fill the picker. Counting invocations attributed the
    retry's request to the wrong caller and answered it — the first version of
    this test passed the click and then found the whole screen rendered. The
    phase the test is in is something the test knows; which component asked is
    not.
    """
    from playwright.sync_api import sync_playwright

    base, ids = served
    mode = {"v": "fail"}
    held: list = []

    def alpha(route):
        if mode["v"] == "fail":
            route.fulfill(status=503, content_type="application/json",
                          body='{"detail": "alpha is unavailable"}')
        else:
            held.append(route)          # pending, deliberately

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        on_the_layout_of_last_resort(page)
        try:
            page.route(f"**/api/sites/{ids['alpha']}", alpha)
            page.goto(f"{base}/#/sites/{ids['alpha']}",
                      wait_until="domcontentloaded")
            page.wait_for_selector("p.error", timeout=15000)

            retry = page.locator("button.retry")
            assert retry.count() == 1, (
                "the failure offers no way to try again — the operator's only "
                "recovery is a reload, and nothing on screen says so")
            assert not retry.is_disabled(), (
                "a settled failure offers a control that cannot be pressed")
            settled_name = retry.inner_text()
            assert settled_name.strip(), (
                "the retry control has no caption at all, so the comparison "
                "below would hold two empty strings equal and assert nothing")

            mode["v"] = "hold"
            retry.click()
            page.wait_for_timeout(1200)

            assert held, "the retry sent no request"
            assert page.locator("p.error").count() == 1, (
                "the failure the operator is acting on vanished the moment "
                "they acted on it")
            assert retry.is_disabled(), (
                "the retry control is still offering an action it is already "
                "performing")
            assert retry.get_attribute("aria-busy") == "true", (
                "the control is disabled and says nothing about why; "
                "`aria-busy` is what carries the state once the busy word is "
                "out of the label. Read: "
                f"{retry.get_attribute('aria-busy')!r}")
            assert retry.inner_text() == settled_name, (
                "the control renamed itself under the press — the operator "
                "who pressed one button is told a different control appeared. "
                f"Before: {settled_name!r}, during: {retry.inner_text()!r}")
            said = page.inner_text("p.error")
            assert "trying" in said.lower(), (
                f"nothing on screen says it is trying: {said!r}")
        finally:
            browser.close()


def _open_a_category_with_ticks(page) -> None:
    """Click category leaves until one shows a tickable finding.

    The findings table lives inside an opened category (`selected` starts
    `""` at `anatomy.tsx:1351`) and only findings that name a page carry a
    tick — round 066 made `names_a_page` required on `Markable` precisely so
    the control is withheld where the server would refuse the verification.
    So neither "the first leaf" nor "any leaf" is guaranteed to serve, and a
    test that assumed one would fail for a reason that has nothing to do with
    what it is asserting.
    """
    # Parts are opened through the address since the sidebar's retirement
    # (brief v24 step BO).
    keys = page.evaluate(_PART_KEYS_JS)
    for key in keys:
        open_part_key(page, key)
        page.wait_for_timeout(200)
        # Instances stand under their causes since brief v2 step E; open
        # every cause so a tick, if the part has one, is on screen.
        for j in range(page.locator("table.causes .group-toggle").count()):
            page.locator("table.causes .group-toggle").nth(j).click()
        page.wait_for_timeout(100)
        if page.locator(".fix-chk").count() > 0:
            return
        open_part_key(page, "")        # close it again before trying the next
        page.wait_for_timeout(100)
    raise AssertionError(
        "no category on this screen offers a tick, so no refresh can be "
        "driven without spending money")


def test_a_refresh_that_is_not_a_page_change_does_not_claim_one(served):
    """UX-56: the banner states a cause that did not occur.

    `stale` was `loading && Boolean(data)`, and `loading` goes true for any
    re-run of the effect that keeps the payload — which is every bump of
    `tick`: a fix-loop verification (`anatomy.tsx:1421`), a **paid** triage
    purchase (`:1499`), a section run (`:1535`) and a page refresh (`:1870`).
    In all four the screen printed, and `role="status"` announced, "Loading
    the page you chose — the counts and evidence below are still the previous
    page's." No page was chosen and the counts below were the same page's,
    one refresh old.

    The hook could not have answered this. `FetchState` recorded `for` — the
    identity key, which `AnatomyView` deliberately sets to `siteId` so the
    picker survives a page change — and never the path the payload came from,
    so there was nothing for the screen to compare against and it inferred a
    cause from a flag that cannot carry one.

    **Driven through the fix loop rather than through triage**, which is the
    same code path one bump over and does not spend. The two POSTs it makes
    are fulfilled rather than served: `verify` re-crawls, and the fixture's
    site is stopped by the time this runs, so a real verification would fail
    for a reason unrelated to the assertion. What must be real is the GET the
    bump provokes, and that one is held.
    """
    from playwright.sync_api import sync_playwright

    base, ids = served
    held: list = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        on_the_layout_of_last_resort(page)
        try:
            page.goto(f"{base}/#/sites/{ids['alpha']}", wait_until="networkidle")
            page.wait_for_selector(ANATOMY_READY, timeout=15000)
            # Item 174: site mode draws no filter at all; drawn, it is empty.
            assert (page.locator(".page-find").count() == 0
                    or page.input_value(".page-find") == ""), (
                "a page filter is already set, so this is not the state the "
                "finding is about")
            assert page.locator(".stale-note").count() == 0, (
                "a settled screen claims to be loading something")

            _open_a_category_with_ticks(page)

            page.route("**/attempt", lambda route: route.fulfill(
                status=200, content_type="application/json", body="{}"))
            page.route("**/verify", lambda route: route.fulfill(
                status=200, content_type="application/json",
                body='{"outcomes": []}'))
            # No `?page=` — the whole point is that the subject did not move.
            # The request carries the picker's run since brief v6 step V1.
            page.route(re.compile(r"/anatomy(\?run_id=[^&]*)?$"), lambda route: held.append(route))

            page.locator(".fix-chk").first.check()
            page.wait_for_timeout(300)
            run = page.locator(".mark-bar .mark-verify")
            assert run.count() == 1, (
                "ticking offered no verification, so no refresh can be driven")
            run.click()
            page.wait_for_timeout(1500)

            assert held, (
                "the verification provoked no refetch, so nothing was in "
                "flight and this test proves nothing about the state during one")
            assert page.locator(".stale-note").count() == 0, (
                "the screen says the operator chose a page and that the "
                "counts belong to a different one. Neither happened: this is "
                "the same page, one refresh old. Rendered text says "
                f"{page.locator('.stale-note').first.inner_text()!r}")
        finally:
            browser.close()


def test_clearing_the_page_filter_is_not_reported_as_choosing_a_page(served):
    """UX-56's fifth case: a path change with no page chosen.

    Widening back to All pages really does leave the previous page's counts
    on screen while the site-wide reply is in flight, so silence would be
    UX-13 again — but the sentence the screen had names a choice the operator
    did not make. The banner must survive and stop claiming the wrong cause,
    which is why this asserts on the text rather than on the count.
    """
    from playwright.sync_api import sync_playwright

    base, ids = served
    held: list = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        on_the_layout_of_last_resort(page)
        try:
            page.goto(f"{base}/#/sites/{ids['alpha']}", wait_until="networkidle")
            page.wait_for_selector(ANATOMY_READY, timeout=15000)

            paths = page.eval_on_selector_all(
                "#anat-pages option", "els => els.map(e => e.value)")
            assert paths, "no page to narrow to"

            open_page_filter(page)
            page.fill(".page-find", paths[-1])
            page.dispatch_event(".page-find", "change")
            page.wait_for_selector(".cur-filter-note", timeout=15000)
            page.wait_for_timeout(500)

            # The request carries the picker's run since brief v6 step V1.
            page.route(re.compile(r"/anatomy(\?run_id=[^&]*)?$"), lambda route: held.append(route))
            open_page_filter(page)
            page.fill(".page-find", "")
            page.dispatch_event(".page-find", "change")
            page.wait_for_timeout(1500)

            assert held, (
                "clearing the filter sent no request, so nothing was in "
                "flight and this test proves nothing about the state during one")
            note = page.locator(".stale-note")
            assert note.count() == 1, (
                "the counts on screen are one page's and the reply in flight "
                "is the whole site's, and the screen does not say so")
            text = note.first.inner_text()
            assert "page you chose" not in text, (
                "the operator cleared the filter and chose no page; the "
                f"screen says they chose one: {text!r}")
        finally:
            browser.close()


_PART_KEYS_JS = """async () => {
  const m = location.hash.match(/#\\/sites\\/([^?/]+)/);
  const cats = (await (await fetch(`/api/sites/${m[1]}/anatomy`)).json()).categories;
  return cats.filter((c) => c.group !== 'workflow').map((c) => c.key);
}"""


def open_part_key(page, key: str) -> None:
    page.evaluate("""(key) => {
      const [path, query = ''] = location.hash.split('?');
      const q = new URLSearchParams(query);
      if (!q.get('tab')) q.set('tab', 'findings');
      if (key) q.set('part', key); else q.delete('part');
      location.hash = path + '?' + q.toString();
    }""", key)
