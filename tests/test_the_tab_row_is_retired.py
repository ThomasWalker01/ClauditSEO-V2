"""The client screen has one navigation: the strip, with a reference row.

The tab row is gone. It named the same panes the numbered strip names, in
different words, and it changed the pane without writing the address — so the
back button did nothing and a stored link named a pane the screen was no
longer on (`_plans/site-screen-ia-plan-v2.md` §5g). §7 step 5 retires it:
Pages and Notes sit in a reference row ABOVE the pane, because the record has
been measured at 41,034px unfiltered and a destination placed after that is
not a destination (§2 rule 3); each pane says what it is in text; and every
`?tab=` value the product or a test ever wrote still lands where its content
went (§6) — with the one rule that an unknown value is never a silent
fallthrough.

**Why a browser.** The claims are about what a stored address opens and what
the screen says about it, and the address is read on boot and on
`hashchange`. A source scan would be satisfied by the alias table existing;
what matters is the pane that paints.

**The population is §6's table, restated here by name** so that a pane
renamed or an alias dropped fails against the word the operator would have
typed. `record` is in it because a test navigated to it for months and passed
only because an unknown value fell through to the default.
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

#: Plan §6: old address → the pane its content went to, by the pane's own
#: rendered name. `None` is "no `?tab=` at all".
LANDS = {
    # The landing since brief v24 step BM: the bare address is the lanes.
    None: "Where it stands",
    # Precheck and Triage fold into Audit (brief v24 step BN).
    "precheck": "Audit",
    "findings": "Analyses",
    "analyses": "Analyses",
    "history": "Audit",
    # Step 3's pane retired into step 4's section rail (brief step 3).
    # Its own pane again since brief v4 Item 3c.
    "triage": "Audit",
    "all": "Record",
    "record": "Record",
    "pages": "Pages",
    "notes": "Client notes",
}

_SCREEN_JS = """() => {
  const refs = document.querySelector('nav.refs');
  const pane = document.querySelector('.pane-body');
  return {
    tablist: document.querySelectorAll('[role=tablist], [role=tab]').length,
    name: (document.querySelector('.pane-name')?.textContent || '').trim(),
    ask: (document.querySelector('.pane-ask')?.textContent || '').trim(),
    refs: [...document.querySelectorAll('.ref-link')].map((a) => ({
      text: (a.childNodes[0]?.textContent || '').trim(),
      href: a.getAttribute('href'),
      current: a.getAttribute('aria-current'),
    })),
    refsAbovePane: !!(refs && pane
      && (refs.compareDocumentPosition(pane) & Node.DOCUMENT_POSITION_FOLLOWING)),
    unknown: (document.querySelector('.pane-unknown')?.textContent || '').trim(),
    hash: window.location.hash,
    filter: document.querySelector('[aria-label="state filter"] [aria-pressed="true"]')?.dataset.state || null,
  };
}"""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def served():
    """A real server holding one audit, so every pane has content."""
    import tempfile

    import httpx
    import uvicorn

    from clauditseo.api.app import create_app
    from tests.test_coverage import DIMS, _Hub, _run

    tmp = Path(tempfile.mkdtemp(prefix="notabs"))
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
                            json={"name": "No Tabs Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "notabs.fixture"}, timeout=30).json()
        conn = connect(db)
        run_id = runs.create_run(conn, site["id"], DIMS, "T2")
        runs.complete_run(conn, run_id, _run(_Hub()))
        conn.close()
        yield base, site["id"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_the_screen_has_no_tab_row_and_a_reference_row_above_the_pane(served):
    from playwright.sync_api import sync_playwright

    base, site_id = served
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        try:
            pg.goto(f"{base}/#/sites/{site_id}", wait_until="load",
                    timeout=30_000)
            pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
            got = pg.evaluate(_SCREEN_JS)
        finally:
            browser.close()

    assert got["tablist"] == 0, f"a tab row is still rendered: {got}"
    # The landing's name since brief v24 step BM.
    # Item 173 (ruling C): the landing's name is kept - F-21's announcement and
    # the outline hang on it - but not drawn, and its subtitle is gone.
    assert got["name"] == "Where it stands" and not got["ask"], (
        f"the pane does not say what it is in text: {got}")
    # "Client notes", since audit F12: `Notes 0` in the bar sat beside a
    # headline counting coverage notes.
    assert [r["text"] for r in got["refs"]] == ["Pages", "Client notes"], got["refs"]
    for r in got["refs"]:
        assert r["href"] and "?tab=" in r["href"], r
        assert r["current"] is None, f"a reference is marked on step 4: {r}"
    assert got["refsAbovePane"], (
        "the reference row is not above the pane (plan §2 rule 3)")


@pytest.mark.parametrize("value", list(LANDS))
def test_every_old_address_lands_where_its_content_went(served, value):
    from playwright.sync_api import sync_playwright

    base, site_id = served
    tail = "" if value is None else f"?tab={value}"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        try:
            pg.goto(f"{base}/#/sites/{site_id}{tail}", wait_until="load",
                    timeout=30_000)
            pg.wait_for_selector(".pane-name", timeout=30_000)
            got = pg.evaluate(_SCREEN_JS)
        finally:
            browser.close()

    assert got["name"] == LANDS[value], (value, got)
    assert got["unknown"] == "", (
        f"a known address is reported as unknown: {value!r} → {got}")
    if value in ("pages", "notes"):
        marked = [r["text"] for r in got["refs"] if r["current"]]
        assert marked == [LANDS[value]], got["refs"]
    if value in ("all", "record"):
        # Open + regressed + to confirm since item 237: plan §4a's "what is
        # outstanding", with the analysis findings that wait for the operator.
        assert got["filter"] == "attention", (
            "the record does not open on what is outstanding (plan §4a, item 237): "
            f"{got}")


def test_an_unknown_address_is_said_rather_than_swallowed(served):
    from playwright.sync_api import sync_playwright

    base, site_id = served
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        try:
            pg.goto(f"{base}/#/sites/{site_id}?tab=bogus", wait_until="load",
                    timeout=30_000)
            # The region is always mounted (a live region must exist before
            # it speaks), so wait for its words rather than for it.
            pg.wait_for_function(
                "() => (document.querySelector('.pane-unknown')?.textContent || '').trim() !== ''",
                timeout=30_000)
            got = pg.evaluate(_SCREEN_JS)
            assert got["name"] == "Analyses", got
            assert "bogus" in got["unknown"] and "Analyses" in got["unknown"], got

            # And a reference link both changes the pane and writes the
            # address, which the tab row it replaced never did (§5g).
            pg.click(".ref-link:has-text('Notes')")
            pg.wait_for_function(f"({_SCREEN_JS})().name === 'Client notes'",
                                 timeout=10_000)
            got = pg.evaluate(_SCREEN_JS)
            assert got["hash"].endswith("?tab=notes"), got
            assert got["unknown"] == "", (
                f"the unknown-name note outlived the address that caused it: {got}")
        finally:
            browser.close()
