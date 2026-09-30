"""Each figure in "Where it stands" reaches the things it counts.

`FEATURES.md` F-11 states the rule for the Pages count on a finding:
wherever the product states a quantity of affected things, the operator can
reach those things in one action from where the quantity is stated. The
standing position's five headline figures — outstanding, regressed, fixed to
date, pages, seen once — stated their quantities on every pane and reached
nothing. The operator asked on 2026-09-02 that each point at what it
references.

Each finding count is now a link to the record filtered to the state it
counts (`?tab=all&state=…`). The page count is not: the reference row above
the pane is the same number reaching the same pane. No link where the list
would be empty — a control onto nothing is the affordance
defect F-11 was written against — and no link on "Outstanding here" while a
page filter narrows it, because that count is the tree's and the record
cannot be narrowed to a page.

**Why a browser.** The claim is that pressing the number opens the pane with
the filter set to the state the number counted, and that the rows shown then
number what the figure said. That is the address, the listener and the
record's own filter agreeing, and only the rendered DOM shows it.
"""

from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import pytest

from clauditseo.db.connection import connect
from clauditseo.persistence import runs
from tests.test_a11y_rendered import DIST

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")

pytestmark = [
    NEEDS_BROWSER,
    pytest.mark.skipif(not (DIST / "index.html").is_file(),
                       reason="dashboard not built (npm run build in dashboard/)"),
]

# The standing figures are lane entries since brief v23 step BL: what is
# waiting (outstanding) and what is settled (fixed to date), each still a link
# onto the record filtered to what it counts (F-11).
_FIGS_JS = """() => [...document.querySelectorAll('.lane-waiting .cl-entry, .lane-settled .cl-entry')].map((d) => ({
  label: (d.querySelector('dt')?.textContent || '').trim(),
  value: (d.querySelector('dd')?.textContent || '').trim(),
  href: d.querySelector('a')?.getAttribute('href') || null,
  name: d.querySelector('a')?.getAttribute('aria-label') || null,
}))"""

_PANE_JS = """() => ({
  name: (document.querySelector('.pane-name')?.textContent || '').trim(),
  filter: document.querySelector('[aria-label="state filter"] [aria-pressed="true"]')?.dataset.state || null,
  rows: document.querySelectorAll('tbody tr:has(code)').length,
  // Coverage notes are a strip under the table since brief v2 step F, and
  // the standing figure counts them with the rows.
  notes: document.querySelectorAll('.coverage-notes li').length,
  hash: window.location.hash,
})"""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def served():
    """A real server holding one audit: open findings, none fixed."""
    import tempfile

    import httpx
    import uvicorn

    from clauditseo.api.app import create_app
    from tests.test_coverage import DIMS, _Hub, _run

    tmp = Path(tempfile.mkdtemp(prefix="figures"))
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
                            json={"name": "Figures Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "figures.fixture"}, timeout=30).json()
        conn = connect(db)
        run_id = runs.create_run(conn, site["id"], DIMS, "T2")
        runs.complete_run(conn, run_id, _run(_Hub()))
        conn.close()
        yield base, site["id"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_the_outstanding_figure_opens_the_record_on_what_it_counted(served):
    import httpx
    from playwright.sync_api import sync_playwright

    base, site_id = served
    cur = httpx.get(f"{base}/api/sites/{site_id}/anatomy", timeout=30).json()["current"]
    assert cur["outstanding"] > 0 and cur["fixed"] == 0, (
        "precondition: the fixture needs something outstanding and nothing "
        f"fixed, to show a link on one and none on the other: {cur}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        try:
            # The lanes are the landing since brief v24 step BM.
            pg.goto(f"{base}/#/sites/{site_id}", wait_until="load",
                    timeout=30_000)
            pg.wait_for_selector(".lane-waiting .cl-entry", timeout=30_000)
            figs = {f["label"].lower(): f for f in pg.evaluate(_FIGS_JS)}

            # "Outstanding in the record" since audit F5 (2026-09-18): the
            # figure is `standing_by_state` over every audit and sat bare
            # beside a primary action counting this run's findings, which on
            # Birch read 167 and 164. Matched by prefix so the label may say
            # what it counts without this needing to restate the sentence.
            key = next((k for k in figs if k.startswith("outstanding")), None)
            assert key, f"no outstanding figure among {list(figs)}"
            out = figs[key]
            assert out["href"] and "tab=all" in out["href"] \
                and "state=outstanding" in out["href"], out
            assert out["name"] and out["name"].startswith(f"{cur['outstanding']} "), (
                f"the link's name does not say what it counts: {out}")
            fixed = figs["fixed to date"]
            assert fixed["href"] is None, (
                f"a figure of zero offers a control onto nothing: {fixed}")
            # The page counts carry no link: the reference row above the pane
            # is the same number reaching the same pane (second audit, F-18).
            # They stand in the bar's Pages column since brief v8 step X, and
            # 150 step BJ replaced that step's three figures - the FIRST is
            # now the site size, and the record is kept and demoted to
            # bookkeeping. What this clause is about is the absence of a
            # control, so it reads the whole column rather than position one:
            # the label it used to pin is asserted where it now stands, and
            # which figure leads is BJ's clause, not this one's.
            pages = pg.evaluate("""() => [...document.querySelectorAll('.lane-measured .cl-entry')]
              .map((d) => ({ label: (d.querySelector('dt')?.textContent || '').trim(),
                             href: d.querySelector('dd.fig a')?.getAttribute('href') || null }))""")
            assert pages, "the measured lane drew no entry"
            # Either spelling of the leading figure: this fixture has no
            # sitemap, so its site size is UNKNOWN and the label says so
            # (`site size`) rather than dividing by a declaration that
            # failed. `on the site` is the known case. The same allowance is
            # made in `test_the_scope_bar_is_three_columns`, and for the same
            # reason - which of the two is drawn is 150 BJ's clause, not this
            # one's.
            # BL: BJ's coverage leads what has been measured. The PAGE figure
            # is still no control - the reference row above the pane is the
            # same number reaching the same pane. Since item 207 two figures in
            # this lane are doors, each to a catalogue narrowed to exactly
            # what it counted (`only=`); a door anywhere else in the lane would
            # open something it did not count.
            # Sentence case since item 174 ("Pages audited, site size unknown").
            assert "pages audited" in pages[0]["label"].lower(), pages
            assert pages[0]["href"] is None, (
                "the page figure offers a control onto the pane its own reference row reaches", pages)
            assert all(p["href"] is None or "tab=analyses&only=" in p["href"] for p in pages), (
                "a measured figure opens something that is not narrowed to what it counted", pages)

            pg.click(".lane-waiting a[href*='state=outstanding']")
            pg.wait_for_function(f"({_PANE_JS})().name === 'Record'", timeout=10_000)
            got = pg.evaluate(_PANE_JS)
            assert got["filter"] == "outstanding", got
            # Coverage notes are not findings and not in the figure since
            # brief v5 step S: the rows alone are what it counted.
            assert got["rows"] == cur["outstanding"], (
                "the record shows a different number of rows from the figure "
                f"that opened it: {got} vs {cur['outstanding']}")

        finally:
            browser.close()


def test_a_state_named_in_the_address_sets_the_record_s_filter(served):
    """The half a figure's link relies on, driven directly: `?state=fixed` on a
    fresh load, and an unknown state leaves the default alone. Two pages,
    because a second `goto` on one page is a hash change inside the mounted
    app, where the filter is local state and would carry over."""
    from playwright.sync_api import sync_playwright

    base, site_id = served
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            pg = browser.new_page()
            pg.goto(f"{base}/#/sites/{site_id}?tab=all&state=fixed",
                    wait_until="load", timeout=30_000)
            pg.wait_for_selector("[aria-label='state filter'] [data-state]", timeout=30_000)
            got = pg.evaluate(_PANE_JS)
            assert got["filter"] == "fixed" and got["rows"] == 0, got

            pg = browser.new_page()
            pg.goto(f"{base}/#/sites/{site_id}?tab=all&state=bogus",
                    wait_until="load", timeout=30_000)
            pg.wait_for_selector("[aria-label='state filter'] [data-state]", timeout=30_000)
            got = pg.evaluate(_PANE_JS)
            # The pane's default since item 237: outstanding plus what waits
            # for the operator.
            assert got["filter"] == "attention", got
        finally:
            browser.close()
