"""The client screen lands by a rule, once, and collapses its navigation on a
phone.

`?tab=` absent used to mean step 4 for every site at every age: a brand-new
client opened on the one step that cannot do anything yet — "needs an audit",
"no completed audit", "No completed audit yet" — while the chooser sat two
panes away. `_plans/site-screen-ia-plan-v2.md` §4c is the landing rule, in
order: an explicit `?tab=` wins; else the last pane viewed for this site; else,
once the position has arrived, the Audit pane for a site with no audit yet and
step 4 otherwise. Decided once per site entry (§5b): the position is polled
every 1.5s while a run is in flight, and a landing tied to it would navigate
the screen while the operator reads. And the site switcher drops `tab` from
the query tail it keeps, so site B does not land on site A's pane.

§5e is the other half of step 6. Six full cards were 2.24 viewports of
navigation before content at 320px on a one-page fixture — a lower bound — and
`test_reflow.py` measures horizontal scroll only, so it passed. Below ~700px
the strip is numbered chips: the note and the action pills are gone, and this
file holds the chrome to a height budget that the reflow guard cannot see.

**Why a browser.** All four claims are about which pane paints, or how tall
the chrome is, on a real load with the address the operator would have; two
of them depend on `localStorage` and on the position arriving asynchronously.

**Two sites in one fixture**, because the rule's third clause is about a
site's age: one with no audit, one with. A one-site fixture could show the
default but not the choice.
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
from tests.parts import ANATOMY_READY

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")

pytestmark = [
    NEEDS_BROWSER,
    pytest.mark.skipif(not (DIST / "index.html").is_file(),
                       reason="dashboard not built (npm run build in dashboard/)"),
]

#: The chrome above the pane at 320×720 may take at most this many viewports.
#: Measured on this one-page fixture: 2.24 before the collapse, 1.52 after —
#: the strip is now a row of chips and the rest is the two standing panes,
#: which carry the figures and the page filter and are not navigation. The
#: budget is the measurement with a margin for a real site's longer notes,
#: well under the full-card figure, and it is the assertion `test_reflow.py`
#: cannot make: that guard measures horizontal scroll only.
VIEWPORTS_BEFORE_PANE = 1.75

_SCREEN_JS = """() => ({
  name: (document.querySelector('.pane-name')?.textContent || '').trim(),
  hash: window.location.hash,
  steps: document.querySelectorAll('.seq-step').length,
  filter: document.querySelector('[aria-label="state filter"] [aria-pressed="true"]')?.dataset.state || null,
})"""

_CHROME_JS = """() => {
  const pane = document.querySelector('.pane-body');
  const shown = (sel) => [...document.querySelectorAll(sel)]
    .filter((el) => el.offsetParent !== null).length;
  return {
    paneTop: pane ? pane.getBoundingClientRect().top + window.scrollY : null,
    viewport: window.innerHeight,
    scrollWidth: document.documentElement.scrollWidth,
    actions: shown('.seq-action'),
    notes: shown('.seq-note'),
    names: shown('a.seq-name'),
  };
}"""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def served():
    """Two sites of one client: `young` has no audit, `old` has one."""
    import tempfile

    import httpx
    import uvicorn

    from clauditseo.api.app import create_app
    from tests.test_coverage import DIMS, _Hub, _run

    tmp = Path(tempfile.mkdtemp(prefix="landing"))
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
                            json={"name": "Landing Co"}, timeout=30).json()
        old = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                         json={"domain": "old.fixture"}, timeout=30).json()
        young = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                           json={"domain": "young.fixture"}, timeout=30).json()
        conn = connect(db)
        run_id = runs.create_run(conn, old["id"], DIMS, "T2")
        runs.complete_run(conn, run_id, _run(_Hub()))
        conn.close()
        yield base, {"old": old["id"], "young": young["id"]}
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def _land(pg, base: str, site_id: str, tail: str = "") -> dict:
    pg.goto(f"{base}/#/sites/{site_id}{tail}", wait_until="load", timeout=30_000)
    pg.wait_for_selector(".pane-name", timeout=30_000)
    return pg.evaluate(_SCREEN_JS)


def test_a_site_with_no_audit_lands_on_the_chooser_and_one_with_lands_on_step_four(served):
    from playwright.sync_api import sync_playwright

    base, ids = served
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            # A fresh context each time: nothing remembered, so the third
            # clause is what decides.
            pg = browser.new_context().new_page()
            got = _land(pg, base, ids["young"])
            # Nothing has been counted here: step 1's pane, where the free
            # check is. (A site counted but never audited lands on the
            # chooser - §4c's `next <= 2`, now that step 1 has a pane.)
            # Precheck folded into Audit (brief v24 step BN).
            assert got["name"] == "Audit", got
            assert "tab=" not in got["hash"], (
                f"landing rewrote the address it was asked to land from: {got}")
            # Nothing has run here: one sentence says what to do first, and
            # the six cards stand beneath it in their not-run states - the
            # navigation stays (second audit F-19; operator's decision).
            assert got["steps"] == 4 and pg.locator(".seq-fresh").count() == 1, (
                f"a site where nothing has run lost its cards or its sentence: {got}")
            assert pg.locator(".seq-step.seq-done").count() == 0, (
                "a card is ticked on a site where nothing has run")
            # The precheck's control is on its own pane, where a fresh site
            # lands (brief v2 step A); "What to do" is retired.
            assert pg.locator(".pane-body .pre-panel").count() == 1, (
                "the precheck control is not on step 1's pane")

            pg = browser.new_context().new_page()
            got = _land(pg, base, ids["old"])
            # An audited site lands on the lanes since brief v24 step BM.
            assert got["name"] == "Where it stands", got
            assert got["steps"] == 4 and pg.locator(".seq-fresh").count() == 0, got
        finally:
            browser.close()


def test_the_bare_address_is_the_landing_and_the_record_remembers_its_filter(served):
    """Brief v24 step BM retires rule 2's pane half: the bare address of an
    audited site is the landing, whatever pane was viewed last, because Back
    from a part opened on a lane must return to the landing (BM's accept).
    What was viewed ON a pane is still remembered: the Record comes back on
    the filter it was left on (second audit, F-13)."""
    from playwright.sync_api import sync_playwright

    base, ids = served
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_context().new_page()
        try:
            got = _land(pg, base, ids["old"], "?tab=all")
            assert got["name"] == "Record", got
            pg.click('[aria-label="state filter"] [data-state="fixed"]')
            got = _land(pg, base, ids["old"])
            assert got["name"] == "Where it stands", (
                f"the bare address did not land on the landing: {got}")
            got = _land(pg, base, ids["old"], "?tab=all")
            assert got["filter"] == "fixed", (
                f"the record came back on its default, not on what was left: {got}")
            # The other site has its own memory, which is empty: the rule.
            got = _land(pg, base, ids["young"])
            assert got["name"] == "Audit", (
                f"site B landed on site A's remembered pane: {got}")
        finally:
            browser.close()


def test_switching_site_drops_the_pane_from_the_tail(served):
    """The switcher keeps the query tail across a site change and deletes
    only `run`; §4c says `tab` must join it, or the rule never applies."""
    from playwright.sync_api import sync_playwright

    base, ids = served
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_context().new_page()
        try:
            got = _land(pg, base, ids["old"], "?tab=all")
            assert got["name"] == "Record", got
            # Attached, not visible: a datalist's options never paint.
            pg.wait_for_selector("#site-search-list option", state="attached",
                                 timeout=15_000)
            labels = pg.evaluate(
                "() => [...document.querySelectorAll('#site-search-list option')]"
                ".map((o) => o.value)")
            target = next(l for l in labels if "young.fixture" in l)
            pg.fill(".gs-input", target)
            pg.wait_for_function(
                f"() => location.hash.startsWith('#/sites/{ids['young']}')",
                timeout=15_000)
            pg.wait_for_selector(".pane-name", timeout=30_000)
            got = pg.evaluate(_SCREEN_JS)
            assert "tab=" not in got["hash"], (
                f"the switcher carried the pane across the site change: {got}")
            assert got["name"] == "Audit", (
                f"site B did not land by its own rule after the switch: {got}")
        finally:
            browser.close()


def test_on_a_phone_the_strip_is_chips_and_the_chrome_fits_a_budget(served):
    from playwright.sync_api import sync_playwright

    base, ids = served
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_context(viewport={"width": 320, "height": 720}).new_page()
        try:
            _land(pg, base, ids["old"])
            pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
            got = pg.evaluate(_CHROME_JS)
        finally:
            browser.close()

    assert got["names"] == 4, f"the chips lost a destination name: {got}"
    assert got["actions"] == 0 and got["notes"] == 0, (
        f"the strip still carries actions or notes at 320px: {got}")
    assert got["scrollWidth"] <= 320, got
    assert got["paneTop"] is not None
    ratio = got["paneTop"] / got["viewport"]
    assert ratio <= VIEWPORTS_BEFORE_PANE, (
        f"{ratio:.2f} viewports of chrome before the pane at 320×720 "
        f"(budget {VIEWPORTS_BEFORE_PANE}): {got}")
