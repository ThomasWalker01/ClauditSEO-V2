"""A keyboard reaches the pane without walking the chrome, and a pane change
is said.

The client screen carries the standing position, the six-step strip and the
reference row above its pane, on every pane. Measured in the second audit of
2026-09-02: twenty-six tab stops before the pane and no bypass (F-20, WCAG
2.2 §2.4.1); and a pane change that left focus on the step name, spoke in no
live region, and put the pane's name in a `<strong>` outside the heading
outline (F-21).

Now: the first tab stop on the page is a skip link that lands on the pane;
the pane is a region labelled by its own name, which is a heading; and a
visually hidden status region says which pane is showing, so a change is
announced without moving focus off the control that made it.

**Why a browser.** Every claim is about focus order, focus movement and what
a live region holds after a keypress, which only a driven document can show.
The one thing not measured is a screen reader's actual speech.

**Why the same fix loop is asserted here.** F-17 is a keyboard journey too: a
tick made on the Analyses pane, then a press on the Record step, must show
the same mark without a re-read in between. Two loops with two sets made
that a refetch away; one loop makes it immediate, and the immediacy is the
observable.
"""

from __future__ import annotations

from tests.last_resort import on_the_layout_of_last_resort
import socket
import threading
import time
from pathlib import Path

import pytest

from clauditseo.db.connection import connect
from clauditseo.persistence import runs
from tests.test_a11y_rendered import DIST
from tests.parts import ANATOMY_READY, open_part

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")

pytestmark = [
    NEEDS_BROWSER,
    pytest.mark.skipif(not (DIST / "index.html").is_file(),
                       reason="dashboard not built (npm run build in dashboard/)"),
]

_FOCUS_JS = """() => {
  const el = document.activeElement;
  return {
    tag: el?.tagName || null,
    id: el?.id || null,
    cls: el?.className || null,
    text: (el?.textContent || '').trim().slice(0, 40),
  };
}"""

_PANE_JS = """() => ({
  name: (document.querySelector('h2.pane-name')?.textContent || '').trim(),
  region: (() => {
    const r = document.getElementById('pane');
    return r ? { role: r.getAttribute('role'), labelledby: r.getAttribute('aria-labelledby'),
                 tabindex: r.getAttribute('tabindex') } : null;
  })(),
  status: [...document.querySelectorAll('[role=status]')]
    .map((s) => (s.textContent || '').trim()).filter(Boolean),
  marked: document.querySelectorAll('.pane-body input.fix-chk:checked').length,
})"""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def served():
    """A real server holding one audit with open findings and no marks."""
    import tempfile

    import httpx
    import uvicorn

    from clauditseo.api.app import create_app
    from tests.test_coverage import DIMS, _Hub, _run

    tmp = Path(tempfile.mkdtemp(prefix="reachpane"))
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
                            json={"name": "Reach Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "reach.fixture"}, timeout=30).json()
        conn = connect(db)
        run_id = runs.create_run(conn, site["id"], DIMS, "T2")
        runs.complete_run(conn, run_id, _run(_Hub()))
        conn.close()
        yield base, site["id"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_the_first_tab_stop_skips_to_the_pane_and_the_change_is_said(served):
    from playwright.sync_api import sync_playwright

    base, site_id = served
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        on_the_layout_of_last_resort(pg)
        try:
            pg.goto(f"{base}/#/sites/{site_id}?tab=findings", wait_until="load",
                    timeout=30_000)
            pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
            got = pg.evaluate(_PANE_JS)
            assert got["name"] == "Analyses", (
                f"the pane's name is not a heading: {got}")
            assert got["region"] == {"role": "region", "labelledby": "pane-name",
                                     "tabindex": "-1"}, got["region"]
            assert "Showing Analyses" in got["status"], (
                f"nothing says which pane is showing: {got['status']}")

            # The first Tab from the top of the document is the skip link,
            # and Enter on it lands focus on the pane.
            pg.keyboard.press("Tab")
            first = pg.evaluate(_FOCUS_JS)
            assert first["cls"] == "skip" and "Skip" in first["text"], (
                f"the first tab stop is not the skip link: {first}")
            pg.keyboard.press("Enter")
            landed = pg.evaluate(_FOCUS_JS)
            assert landed["id"] == "pane", (
                f"the skip link did not land on the pane: {landed}")

            # A pane change from the keyboard is announced, and focus stays
            # where the operator put it.
            pg.focus("a.seq-name:text-is('Record')")
            pg.keyboard.press("Enter")
            pg.wait_for_function(
                f"({_PANE_JS})().name === 'Record'", timeout=10_000)
            got = pg.evaluate(_PANE_JS)
            assert "Showing Record" in got["status"], got["status"]
            after = pg.evaluate(_FOCUS_JS)
            assert after["text"] == "Record" and after["tag"] == "A", (
                f"focus moved off the control that changed the pane: {after}")
        finally:
            browser.close()


def test_a_mark_made_on_one_pane_is_on_the_other_without_a_re_read(served):
    from playwright.sync_api import sync_playwright

    base, site_id = served
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        on_the_layout_of_last_resort(pg)
        try:
            pg.goto(f"{base}/#/sites/{site_id}?tab=findings", wait_until="load",
                    timeout=30_000)
            pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
            # A part that keeps the old page, chosen from the payload:
            # the first leaf with something open is Title & description,
            # which has had its own renderer since brief v13 step AO and
            # has no cause table. Six parts have one now - Content was the
            # last, at brief v17 step AX - and this clause is about the
            # cause table's ticks.
            import httpx

            from tests.test_the_part_page_is_three_blocks import old_page_part

            view = httpx.get(f"{base}/api/sites/{site_id}/anatomy", timeout=30).json()
            open_part(pg, old_page_part(view))
            # The instances, and their ticks, stand under the worst cause
            # since brief v2 step E.
            pg.click("table.causes tbody tr.cause-row:first-child .group-toggle")
            pg.wait_for_selector(".pane-body input.fix-chk", timeout=15_000)
            pg.locator(".pane-body input.fix-chk").first.check()
            # No wait for the server: the claim is the set, not the store.
            pg.click("a.seq-name:text-is('Record')")
            pg.wait_for_function(
                f"({_PANE_JS})().name === 'Record'", timeout=10_000)
            got = pg.evaluate(_PANE_JS)
            assert got["marked"] >= 1, (
                "a mark made on the Analyses pane is not on the Record pane "
                f"until that pane re-reads - two fix loops, not one: {got}")
        finally:
            browser.close()
