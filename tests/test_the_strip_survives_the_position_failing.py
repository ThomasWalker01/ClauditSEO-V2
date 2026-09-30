"""The navigation renders from a payload that cannot take it down.

`StandingHeader` returned an `ErrorNote` in place of everything on a failed
anatomy fetch, and `<Loading/>` in place of everything before it arrived. That
was the failure mode the Current tab had before the hoist, and it was
deferred, in two source comments, on the ground that the tab row was the
navigation and the fetch could not touch it. The tab row was retired at step 5.
Measured after that: with `**/api/sites/*/anatomy*` aborted and the address on
`?tab=all`, the record pane rendered twelve rows under **zero** steps, and the
only in-screen links left were Pages and Notes. That is
`_plans/site-screen-ia-plan-v2.md` §5c, live — "the nav must render from a
payload that cannot take it down, degrading to unlabelled step states rather
than disappearing" — and the audit of 2026-09-02 put it first.

**Why a browser.** The claim is about what is on screen when one of three
requests fails, and the strip is drawn from that request's data by a
component two levels down from the one that decides the pane. A source read
would be satisfied by the early return moving; what matters is six cards with
their links, under a failure that is still shown and still retryable.

**Two states, both driven.** Failed, by aborting the route; and loading, by
holding the route open — the state every ordinary load passes through, and
the one in which the strip used to be absent on every visit for as long as
the position took to arrive. The recovery is driven too: the retry in the
position's pane, with the route restored, puts the states back.
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

#: Four destinations since brief v24 step BN (six steps before).
STEPS = 4

_STRIP_JS = """() => ({
  steps: [...document.querySelectorAll('.seq-step')].map((li) => ({
    name: (li.querySelector('a.seq-name')?.textContent || '').trim(),
    href: li.querySelector('a.seq-name')?.getAttribute('href') || null,
    state: (li.querySelector('.seq-state')?.textContent || '').trim(),
    done: li.classList.contains('seq-done'),
  })),
  badges: document.querySelectorAll('.seq-badge').length,
  errors: document.querySelectorAll('p.error').length,
  retry: document.querySelectorAll('p.error button').length,
  // The standing figures: the bar's state sentence since brief v24 step BM
  // moved the lanes to the landing. `.fig-coverage` since item 174, when the
  // assessed clause left the sentence for the Settled lane.
  figures: document.querySelectorAll('.run-scope .bl-sentence .fig-coverage').length,
  rows: document.querySelectorAll('tbody tr:has(code)').length,
  unread: (document.querySelector('.anat-unread')?.textContent || '').trim(),
  tree: document.querySelectorAll('.anat-layout').length,
})"""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def served():
    """A real server holding one audit, so the panes have rows to keep."""
    import tempfile

    import httpx
    import uvicorn

    from clauditseo.api.app import create_app
    from tests.test_coverage import DIMS, _Hub, _run

    tmp = Path(tempfile.mkdtemp(prefix="survive"))
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
                            json={"name": "Survive Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "survive.fixture"}, timeout=30).json()
        conn = connect(db)
        run_id = runs.create_run(conn, site["id"], DIMS, "T2")
        runs.complete_run(conn, run_id, _run(_Hub()))
        # A ranking and a read brief, so steps 3 and 4 have something to be
        # "done" about. The lanes come from a different request from the
        # position, and answer when it does not: without these two rows the
        # guard could not tell "not ticked because not loaded" from "not
        # ticked because nothing ever ran" (second audit, F-25).
        runs.store_expert_report(
            conn, run_id, "triage",
            {"model": "test-model", "report": "# Triage\n\nRanked.",
             "findings": [{"code": "img-alt-missing", "severity": "high",
                           "summary": "Images lack alt text."}]})
        runs.store_expert_report(
            conn, run_id, "onpage-hygiene",
            {"model": "test-model", "report": "# Hygiene\n\nRead.", "findings": []})
        conn.close()
        yield base, site["id"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def _all_steps_with_links(got: dict) -> None:
    assert len(got["steps"]) == STEPS, got
    for st in got["steps"]:
        assert st["href"], f"a step lost its link: {st}"


def test_a_failed_position_leaves_every_step_and_says_so(served):
    from playwright.sync_api import sync_playwright

    base, site_id = served
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        try:
            pg.route("**/api/sites/*/anatomy*", lambda route: route.abort())
            pg.goto(f"{base}/#/sites/{site_id}?tab=all", wait_until="load",
                    timeout=30_000)
            pg.wait_for_selector("p.error", timeout=30_000)
            pg.wait_for_selector("tbody tr:has(code)", timeout=30_000)
            got = pg.evaluate(_STRIP_JS)

            _all_steps_with_links(got)
            assert got["rows"] > 0, got
            assert got["errors"] == 1 and got["retry"] == 1, (
                f"the failure is not shown once, with its retry: {got}")
            assert got["figures"] == 0, "figures painted from a failed fetch"
            assert got["badges"] == 0, (
                f"a step is recommended from a position nobody read: {got}")
            for st in got["steps"]:
                # Audit folds Precheck in (brief v24 step BN), whose line reads
                # the precheck rather than the position; its Audit line must
                # still say it did not load.
                if st["name"] == "Audit":
                    assert "Audit: not loaded" in st["state"] and not st["done"], st
                    continue
                assert st["state"] == "not loaded" and not st["done"], (
                    f"a card states a position that did not load: {st}")

            # The merged pane keeps its promise honest too.
            pg.click("a.seq-name:text-is('Analyses')")
            pg.wait_for_selector(".anat-unread", timeout=10_000)
            got = pg.evaluate(_STRIP_JS)
            assert got["tree"] == 0 and "could not be read" in got["unread"], got

            # Recovery: the route comes back and the retry beside the failure
            # puts the states back, on the same page.
            pg.unroute("**/api/sites/*/anatomy*")
            pg.click("p.error button")
            pg.wait_for_function(
                f"({_STRIP_JS})().steps.some((s) => s.state.includes('last ran'))",
                timeout=15_000)
            got = pg.evaluate(_STRIP_JS)
            assert got["errors"] == 0 and got["figures"] == 1, got
            assert got["tree"] == 1 and got["unread"] == "", got
        finally:
            browser.close()


def test_a_position_still_loading_leaves_every_step(served):
    from playwright.sync_api import sync_playwright

    base, site_id = served
    held: list = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        try:
            pg.route("**/api/sites/*/anatomy*", lambda route: held.append(route))
            pg.goto(f"{base}/#/sites/{site_id}?tab=all", wait_until="load",
                    timeout=30_000)
            pg.wait_for_selector(".seq-step", timeout=30_000)
            pg.wait_for_selector("tbody tr:has(code)", timeout=30_000)
            assert held, "no position request was made, so nothing is loading"
            got = pg.evaluate(_STRIP_JS)

            _all_steps_with_links(got)
            assert got["badges"] == 0 and got["errors"] == 0, got
            audit = next(s for s in got["steps"] if s["name"] == "Audit")
            assert "Audit: loading…" in audit["state"] and not audit["done"], audit

            for route in held:
                route.continue_()
            pg.wait_for_function(
                f"({_STRIP_JS})().steps.some((s) => s.state.includes('last ran'))",
                timeout=15_000)
        finally:
            browser.close()
