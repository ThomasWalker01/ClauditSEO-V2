"""Step 4's pane is one pane, and one audit governs the whole of it.

Two tabs held it: Current, the issue browser, and Analyses, the catalogue of
briefs. The browser's read and run controls, and the strip's step cards, read
`latest_run` off the anatomy payload; the catalogue read the operator's sticky
pick from the selection bar. Merged as first specified, a step card would have
said "3 to read" about one audit a foot above lanes reading "Ready to read · 0"
about another — the same defect class the merge was meant to remove.
`_plans/site-screen-ia-plan-v2.md` §3 conditions the merge on one run scope
and recommends option (i): the pane takes the run selector and the browser
follows it. This is §7 step 4, with step 2's pane taking the chooser in the
same commit.

**What the fixture arranges, and why.** Two completed audits, a stored brief
on the OLDER one and none on the newer, so the two audits answer differently:
whichever the pane is scoped to, the strip's step 4 and the ready lane must
agree with each other and with that audit. A fixture with one audit could not
tell "both follow the pick" from "both happen to read the latest".

**Why a browser.** The scope is a `<select>` in the pane, the readers are a
card in the header and a lane under the tree, and the claim is that changing
the one moves both. That is three components and a context, and only the
rendered DOM shows them agreeing.

**Compatibility is asserted, not assumed** (§6): `?tab=analyses` was the one
value the product itself wrote, and it lands on the merged pane.
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

TOOL = "images"           # the Images brief (brief v15 step AQ)

#: Step 4's card and the ready lane, at one instant.
_READ_JS = """() => {
  const li = [...document.querySelectorAll('.seq-step')].find(
    (el) => (el.querySelector('.seq-name')?.textContent || '').trim() === 'Analyses');
  return {
    card: (li?.querySelector('.seq-state')?.textContent || '').trim(),
    // The catalogue is a drawer since brief v4 Item 3e; a read brief is a
    // row in the read state.
    ready: document.querySelectorAll('.catalogue-shop .crow-read').length,
    scopes: document.querySelectorAll('.run-scope').length,
    tab: (document.querySelector('.pane-name')?.textContent || '').trim(),
    tabs: document.querySelectorAll('button[role=tab]').length,
    tree: document.querySelectorAll('.anat-layout').length,
    current: (document.querySelector('a.seq-name[aria-current=step]')?.textContent || '').trim(),
  };
}"""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def served():
    """Two completed audits; a brief stored on the older one only."""
    import tempfile

    import httpx
    import uvicorn

    from clauditseo.api.app import create_app
    from tests.test_coverage import DIMS, _Hub, _run

    tmp = Path(tempfile.mkdtemp(prefix="onescope"))
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
                            json={"name": "Scope Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "scope.fixture"}, timeout=30).json()
        conn = connect(db)
        result = _run(_Hub())
        older = runs.create_run(conn, site["id"], DIMS, "T2")
        runs.complete_run(conn, older, result)
        # A second, so the two rows sort apart on `started_at`.
        time.sleep(1.1)
        newer = runs.create_run(conn, site["id"], DIMS, "T2")
        runs.complete_run(conn, newer, result)
        runs.store_expert_report(
            conn, older, TOOL,
            {"model": "test-model", "report": "# Hygiene\n\nOne brief.",
             "findings": []})
        conn.close()
        yield base, site["id"], older, newer
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_the_card_and_the_lane_read_one_audit(served):
    """Both read the newest reading of the site. Item 239 step 5 retired the
    pick they used to follow together; the agreement is what is left."""
    import httpx
    from playwright.sync_api import sync_playwright

    base, site_id, older, newer = served
    lanes_old = httpx.get(f"{base}/api/runs/{older}/analyses", timeout=30).json()
    lanes_new = httpx.get(f"{base}/api/runs/{newer}/analyses", timeout=30).json()
    assert [a["tool"] for a in lanes_old["ready"]] == [TOOL], (
        "precondition: the older audit does not hold exactly the one stored "
        f"brief: {lanes_old['ready']}")
    assert lanes_new["ready"] == [], (
        f"precondition: the newer audit has a brief too: {lanes_new['ready']}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        try:
            # `?tab=findings`: the bare address is the landing since brief v24
            # step BM.
            pg.goto(f"{base}/#/sites/{site_id}?tab=findings", wait_until="load",
                    timeout=30_000)
            pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
            # With no part open the shop is Analyses' own body (brief v24
            # step BO).
            pg.wait_for_selector(".catalogue-shop .catalogue-table", timeout=30_000)
            got = pg.evaluate(_READ_JS)
            assert got["scopes"] == 1, (
                f"the pane carries {got['scopes']} run bars, not one: {got}")
            assert got["tree"] == 1 and got["tab"] == "Analyses", got
            assert got["tabs"] == 0, (
                f"the tab row is retired and {got['tabs']} tabs rendered")
            assert got["ready"] == 0, got
            # The line leads with the free count since brief v17 step AV5;
            # what this clause is about is that nothing is claimed to be
            # waiting to read, which is what "to read" would say.
            assert "to read" not in got["card"], (
                "step 4 says something is to read on an audit with no brief: "
                f"{got}")
            assert got["card"].endswith(("available", "analysis not run")), got

        finally:
            browser.close()


def test_the_old_analyses_address_lands_on_the_merged_pane(served):
    from playwright.sync_api import sync_playwright

    base, site_id, _older, _newer = served
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        try:
            pg.goto(f"{base}/#/sites/{site_id}?tab=analyses", wait_until="load",
                    timeout=30_000)
            pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
            got = pg.evaluate(_READ_JS)
            assert got["tab"] == "Analyses" and got["tree"] == 1, got
            assert got["current"] == "Analyses", (
                f"the merged pane is not marked as step 4's: {got}")
        finally:
            browser.close()


def test_step_two_s_pane_holds_the_chooser_and_the_launcher_still_does(served):
    from playwright.sync_api import sync_playwright

    base, site_id, _older, _newer = served
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        try:
            # Brief v24 step BN: Audit holds the precheck counts above the
            # chooser and the ranking below it, each once; the runs are the
            # Record's.
            pg.goto(f"{base}/#/sites/{site_id}?tab=history", wait_until="load",
                    timeout=30_000)
            pg.wait_for_selector(".scan-matrix", timeout=30_000)
            pg.wait_for_selector(".pane-body .pre-panel", timeout=10_000)
            assert pg.locator(".scan-matrix").count() == 1, "Audit does not hold the chooser"
            assert pg.locator(".pane-body .pre-panel").count() == 1, (
                "the precheck panel is not on Audit exactly once")
            # The ranking block was the third thing on this pane until item
            # 196. The ranking is computed with the audit now and reaches the
            # reader as the order of the parts and of the catalogue, so there
            # is no block to hold and nothing to scroll to.
            assert pg.locator(".pane-body .tri-pane-head").count() == 0, (
                "the ranking block is back on Audit")
            assert pg.locator(".pane-body .runs-table").count() == 0, (
                "the runs table is still on Audit")
            assert pg.locator(".seq-here a.seq-name").inner_text().strip() == "Audit"
            # A folded step's own action still leads here: Audit's panel
            # carries each step's action, and the audit's goes to this pane.
            hrefs = pg.eval_on_selector_all(".seq-step:nth-child(1) .seq-action a",
                                            "els => els.map((e) => e.getAttribute('href'))")
            assert any(h and h.endswith("?tab=history") for h in hrefs), hrefs

            pg.goto(f"{base}/#/sites/{site_id}/launch", wait_until="load",
                    timeout=30_000)
            pg.wait_for_selector(".scan-matrix", timeout=30_000)
            assert pg.locator(".scan-matrix").count() == 1, (
                "the launcher lost its chooser")
        finally:
            browser.close()
