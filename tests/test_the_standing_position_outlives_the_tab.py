"""The standing position and the suggested order are on every tab of the
client screen, once each.

`Sequence` — the numbered 1–6 strip — and the "Where it stands" pane rendered
inside `AnatomyView`, which `SiteDetailView` mounted only under the Current
tab. A navigation that claims to describe the whole of the work lived inside
one view of it and vanished when you left that view: on History or The record
there was no strip, no standing figures, and no page filter. That is the
premise of `_plans/site-screen-ia-plan-v2.md` (§1) and its §7 step 1 is the
hoist: the state both readers need moves up into `SiteDetailView`, the header
renders above the panes, and the tree stays on the Analyses pane. The tab row
itself was retired at step 5; the panes are opened by the strip's step names
and the reference row now, and those links do write the address.

**Why a browser.** The claim is about what is on screen after a pane is
chosen, and the strip is drawn by a component two levels down from the one
that decides the pane. Only a rendered DOM can show that the strip is there
after the click.

**Once, not at least once.** Under Current the header and the tree are both
mounted, and both read the same fetch. A hoist that left a copy behind in
`AnatomyView` would pass "the strip is present" on every tab and paint two
strips on the first, so the count is asserted exactly.

**The population is read off the screen**, not from a literal list of pane
names: every step name that stays on this screen and every reference link is
clicked, so a new pane is in scope here without a line changing, and the
count walked is asserted non-empty in the same test. On every pane the strip
must also hold no control that spends — no button, no spend mark — which is
the rule the 17:08 incident of 2026-09-02 was the breach of (second audit,
F-28).
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
from tests.parts import ANATOMY_READY, open_page_filter

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")

pytestmark = [
    NEEDS_BROWSER,
    pytest.mark.skipif(not (DIST / "index.html").is_file(),
                       reason="dashboard not built (npm run build in dashboard/)"),
]

#: What the head of the screen is made of, each as the class the product
#: renders it under: the strip, the standing figures, and the page filter
#: that scopes them (§5a: the filter moves with the header, because a figure
#: labelled "Outstanding here" with the control that caused it nowhere on
#: screen is the defect the plan names).
HEAD = {
    ".seq": "the suggested order",
    # The standing figures were the "Waiting on you" lane in the bar (brief
    # v23 step BL). Brief v24 step BM moved the lanes to the landing's body,
    # so what every pane's head carries once is the state sentence.
    ".bl-sentence": "the state sentence",
    # The page filter is the Analyse pane's since brief v3 step J: it narrows
    # that pane's parts and facts, and the bar's figures are the site's.
}

#: Six steps today. Read from `sequenceSteps` rather than derived, because a
#: strip that rendered with a step missing is exactly what this must notice.
#: Four destinations since brief v24 step BN.
STEPS = 4

_COUNTS_JS = """(sels) => Object.fromEntries(
  sels.map((s) => [s, document.querySelectorAll(s).length]))"""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def served():
    """A real server holding one audit, so the strip has something to say."""
    import tempfile

    import httpx
    import uvicorn

    from clauditseo.api.app import create_app
    from tests.test_coverage import DIMS, _Hub, _run

    tmp = Path(tempfile.mkdtemp(prefix="standing"))
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
                            json={"name": "Standing Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "standing.fixture"}, timeout=30).json()
        conn = connect(db)
        run_id = runs.create_run(conn, site["id"], DIMS, "T2")
        runs.complete_run(conn, run_id, _run(_Hub()))
        conn.close()
        yield base, site["id"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_every_tab_carries_the_head_of_the_screen_once(served):
    from playwright.sync_api import sync_playwright

    base, site_id = served
    seen: dict[str, dict[str, int]] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        try:
            pg.goto(f"{base}/#/sites/{site_id}", wait_until="load",
                    timeout=30_000)
            # The tree is the last thing to paint under Current; once it is
            # there the head above it has its data too.
            pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
            # Every pane this screen has: the step names that stay on it
            # and the reference row. The tab row is gone (step 5).
            tabs = pg.query_selector_all('a.seq-name[href*="?tab="], .ref-link')
            assert tabs, "the client screen rendered no pane links to walk"
            for tab in tabs:
                name = (tab.text_content() or "").strip()
                tab.click()
                # Nothing is awaited between the click and the read on
                # purpose: the head must not depend on what the tab loads.
                seen[name] = pg.evaluate(
                    _COUNTS_JS, list(HEAD) + [".seq-step", ".seq button", ".seq .spend-mark"])
        finally:
            browser.close()

    assert len(seen) >= 2, f"walked fewer than two tabs: {seen}"
    for name, counts in seen.items():
        for sel, what in HEAD.items():
            assert counts[sel] == 1, (
                f"on the {name!r} tab {what} ({sel}) rendered "
                f"{counts[sel]} times, not once: {counts}")
        assert counts[".seq-step"] == STEPS, (
            f"on the {name!r} tab the strip holds {counts['.seq-step']} "
            f"steps, not {STEPS}")
        assert counts[".seq button"] == 0 and counts[".seq .spend-mark"] == 0, (
            f"on the {name!r} pane the strip holds a control that spends: {counts}")


def test_the_page_filter_in_the_head_still_narrows_the_tree(served):
    """The filter moved; the tree it narrows did not. §5a's condition is that
    the control and the figures it drives stay together, and this is the
    other half: the control still reaches the tree a screen below it."""
    from playwright.sync_api import sync_playwright

    base, site_id = served

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        try:
            pg.goto(f"{base}/#/sites/{site_id}", wait_until="load",
                    timeout=30_000)
            pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
            pages = pg.evaluate(
                "() => [...document.querySelectorAll('#anat-pages option')]"
                ".map((o) => o.value)")
            assert pages, "the fixture audit crawled no page to narrow to"
            open_page_filter(pg)
            pg.fill(".page-find", pages[0])
            # The head says so in rendered text, and it says so on the
            # figures' own pane rather than in the tree.
            pg.wait_for_selector(".cur-filter-note", timeout=15_000)
            assert pg.locator(".lane-waiting").count() == 1
            # `textContent`, not `inner_text`: the label is rendered
            # uppercase by a `text-transform`, and this is about the words.
            label = pg.evaluate(
                "() => document.querySelector('.lane-waiting').textContent")
            assert "on this page" in label, (
                "the standing figures do not state their scope while a page "
                f"filter is active: {label!r}")
        finally:
            browser.close()
