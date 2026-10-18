"""The step names in the suggested order are links, and they drive the tabs.

`Sequence` rendered each step's name as a `<span>`. The strip described the
work and led nowhere: the only way from "2. Audit" to the audits was the tab
row below it, which meant two navigations over one screen and the numbered
one inert. `_plans/site-screen-ia-plan-v2.md` §7 step 3 makes the names links
into the existing tab state, safe only now that the strip lives above the tabs
(§7 step 1) rather than inside one of them — v1's impossible step.

**Two rules from §5f are asserted, not assumed.** The step name is the nav
link and the action pill is a sibling, never nested inside it: a card that
nested its action in its link would cost two tab stops per step and put a
control that spends tokens inside an anchor. And `aria-current="step"` marks
the step whose pane is on screen — a state that can now coexist with "do this
next" on one card, so both are asserted as words and not only as classes.

**Why a browser.** The claim is that a click on a name changes what the
screen shows. Tab state is local, and the link's target may already be the
URL — after the first click on "Audit" the hash reads `?tab=history`, a tab
click changes the pane without changing the hash (§5g, deliberately unfixed
until step 5), and a second click on "Audit" must still bring History back.
That last case is `nav.ts`'s no-op made observable, on the six new anchors
that would otherwise have shipped with it.

**The population is the strip as rendered**: every `.seq-step` is checked,
so a seventh step is in scope without a line changing, and the count is
asserted against `sequenceSteps`' six.
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

#: Four destinations since brief v24 step BN.
STEPS = 4

#: Which tab each step's name opens, by the tab's rendered label — and, for
#: the two steps that are other routes, the route's tail. Copied from
#: `sequenceSteps` rather than derived, so a step re-pointed at the wrong
#: pane fails here by name.
TARGETS = {
    "Audit": ("tab", "Audit"),
    "Analyses": ("tab", "Analyses"),
    "Record": ("tab", "Record"),
    "Client report": ("route", "/reports"),
}

_STRIP_JS = """() => [...document.querySelectorAll('.seq-step')].map((li) => ({
  name: (li.querySelector('a.seq-name')?.textContent || '').trim(),
  href: li.querySelector('a.seq-name')?.getAttribute('href') || null,
  links: li.querySelectorAll('a.seq-name').length,
  nested: li.querySelectorAll('.seq-name a, .seq-name button, .seq-name input').length,
  current: li.querySelector('a.seq-name')?.getAttribute('aria-current') || null,
  here: li.classList.contains('seq-here'),
  next: !!li.querySelector('.seq-badge'),
}))"""

_ACTIVE_JS = """() => ({
  tab: (document.querySelector('.pane-name')?.textContent || '').trim(),
  hash: window.location.hash,
  current: (document.querySelector('a.seq-name[aria-current=step]')?.textContent || '').trim(),
})"""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def served():
    """A real server holding one audit, so every step has something to say."""
    import tempfile

    import httpx
    import uvicorn

    from clauditseo.api.app import create_app
    from tests.test_coverage import DIMS, _Hub, _run

    tmp = Path(tempfile.mkdtemp(prefix="steplinks"))
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
                            json={"name": "Steps Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "steps.fixture"}, timeout=30).json()
        conn = connect(db)
        run_id = runs.create_run(conn, site["id"], DIMS, "T2")
        runs.complete_run(conn, run_id, _run(_Hub()))
        conn.close()
        yield base, site["id"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_every_step_name_is_a_link_with_nothing_nested_inside_it(served):
    from playwright.sync_api import sync_playwright

    base, site_id = served
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        try:
            pg.goto(f"{base}/#/sites/{site_id}", wait_until="load",
                    timeout=30_000)
            pg.wait_for_selector(".seq-step", timeout=30_000)
            assert pg.locator("nav[aria-label] .seq").count() == 1, (
                "the strip is not inside a labelled <nav>")
            strip = pg.evaluate(_STRIP_JS)
        finally:
            browser.close()

    assert len(strip) == STEPS, strip
    assert [st["name"] for st in strip] == list(TARGETS), strip
    for st in strip:
        assert st["links"] == 1 and st["href"], (
            f"step {st['name']!r} has no link for its name: {st}")
        assert st["nested"] == 0, (
            f"step {st['name']!r} nests a control inside its nav link "
            f"(§5f): {st}")
        kind, want = TARGETS[st["name"]]
        if kind == "route":
            assert st["href"].endswith(want), (st, want)
        else:
            assert "?tab=" in st["href"], (st, want)


def test_a_click_on_a_step_name_opens_its_pane_and_says_so(served):
    from playwright.sync_api import sync_playwright

    base, site_id = served
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        try:
            pg.goto(f"{base}/#/sites/{site_id}", wait_until="load",
                    timeout=30_000)
            pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
            before = pg.evaluate(_ACTIVE_JS)
            # The bare address is the landing since brief v24 step BM, which
            # is no step's pane, so no step is marked before a click.
            assert before["tab"] == "Where it stands" and before["current"] == "", (
                f"the landing marks a step before any click: {before}")

            def open_step(name: str) -> dict:
                pg.click(f"a.seq-name:text-is('{name}')")
                pg.wait_for_function(
                    f"({_ACTIVE_JS})().tab === {TARGETS[name][1]!r}",
                    timeout=10_000)
                return pg.evaluate(_ACTIVE_JS)

            got = open_step("Audit")
            assert "?tab=history" in got["hash"], (
                f"the step link did not write the hash it names: {got}")
            assert got["current"] == "Audit", got
            here = [st for st in pg.evaluate(_STRIP_JS) if st["here"]]
            assert [st["name"] for st in here] == ["Audit"], (
                "the step on screen is not said in a word as well as a "
                f"class: {here}")

            got = open_step("Record")
            assert "?tab=all" in got["hash"] and got["current"] == "Record", got

            # A reference link changes the pane AND the hash — the tab row
            # it replaced did only the first (§5g). Reference is not a step,
            # so no step is marked while it shows.
            pg.click(".ref-link:has-text('Notes')")
            pg.wait_for_function(f"({_ACTIVE_JS})().tab === 'Client notes'", timeout=10_000)
            got = pg.evaluate(_ACTIVE_JS)
            assert got["current"] == "", (
                f"Notes is reference, not a step, and a step is marked: {got}")
            assert "?tab=notes" in got["hash"], (
                f"the reference link did not write the hash it names: {got}")

            # And the step whose pane the URL already names, pressed again:
            # the no-op `nav.ts` exists for, on these anchors.
            got = open_step("Record")
            assert got["current"] == "Record", got
            pg.click("a.seq-name:text-is('Record')")
            pg.wait_for_timeout(300)
            got = pg.evaluate(_ACTIVE_JS)
            assert got["tab"] == "Record" and got["current"] == "Record", got
        finally:
            browser.close()
