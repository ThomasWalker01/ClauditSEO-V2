"""The site screen picks no audit (item 239 step 5, the operator's ruling of
2026-09-24: "the header's audit picker is retired").

  - No pane carries a select or listbox of audits. The bar says the current
    audit - its score, tier and date - as text, not a control.
  - A part page renders the same with and without a stale `run=` in the
    address: every section reads The Latest View, and nothing reads a run
    named in the address.
  - The Audits tab is the one way into a run's own record: "view as this
    audit saw it" opens it under the banner "Viewing as of audit ...", with
    the way back to the current view.

Replaces `test_the_site_screen_has_one_audit_picker`,
`test_the_audit_picker_is_wide_enough_to_read` and
`test_the_picker_defaults_to_a_site_wide_run`, whose control is gone. The
fixture is `test_the_analyses_pane_reads_one_audit`'s: two completed
audits, so there is an older one that a stale address could name.
"""

from __future__ import annotations

import pytest

from tests.test_a11y_rendered import DIST
from tests.test_the_analyses_pane_reads_one_audit import served  # noqa: F401  (reused fixture)
from tests.parts import ANATOMY_READY, open_part

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")

pytestmark = [
    NEEDS_BROWSER,
    pytest.mark.skipif(not (DIST / "index.html").is_file(),
                       reason="dashboard not built (npm run build in dashboard/)"),
]

#: Every pane, by address, with what it waits for.
PANES = {
    "history": ".scan-matrix",
    "findings": ".catalogue-shop .crow-part",
    "all": ".state-filters",
    "pages": ".pane-body",
    "notes": ".pane-body",
}

_JS = """() => ({
  // A select or listbox whose options are dated is an audit picker, under
  // whatever class it wears.
  pickers: [...document.querySelectorAll('select, [role=listbox]')].filter((s) =>
    [...(s.options || s.querySelectorAll('[role=option]'))].some((o) => /\\d{4}-\\d{2}-\\d{2}/.test(o.textContent))).length,
  now: (document.querySelector('#topbar-context .audit-now-text')?.textContent || '').trim(),
  nowControls: document.querySelector('#topbar-context .audit-now')
    ?.querySelectorAll('select, button, input').length ?? -1,
})"""


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            yield b
        finally:
            b.close()


@pytest.mark.parametrize("tab", list(PANES))
def test_no_pane_offers_an_audit_to_pick(browser, served, tab):
    base, site_id, _older, _newer = served
    pg = browser.new_page()
    try:
        pg.goto(f"{base}/#/sites/{site_id}?tab={tab}", wait_until="load", timeout=30_000)
        pg.wait_for_selector(PANES[tab], timeout=30_000)
        pg.wait_for_selector("#topbar-context .audit-now[data-audit]", state="attached", timeout=30_000)
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    assert got["pickers"] == 0, f"{tab}: an audit picker is on the screen: {got}"
    assert got["nowControls"] == 0, f"{tab}: the current audit is a control: {got}"
    # Score, tier and date: "T2 · 2026-09-..." with the score before it.
    assert " · T2 · 20" in got["now"], f"{tab}: {got}"


def _part(pg, base, site_id, tail=""):
    pg.goto(f"{base}/#/sites/{site_id}?tab=findings{tail}", wait_until="load", timeout=30_000)
    pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
    open_part(pg, "Crawl & sitemaps")
    pg.wait_for_selector(".anat-pane .part-prov", timeout=15_000)
    pg.wait_for_timeout(300)
    return pg.evaluate("""() => ({
      pane: (document.querySelector('.anat-pane')?.innerText || '').trim(),
      now: (document.querySelector('#topbar-context .audit-now-text')?.textContent || '').trim(),
      banner: !!document.querySelector('.history-banner'),
    })""")


def test_a_stale_run_in_the_address_changes_nothing(browser, served):
    base, site_id, older, _newer = served
    got = []
    # A page each: the second address differs from the first by its hash
    # alone, which is navigation within an app already holding the part open.
    for tail in ("", f"&run={older}"):
        pg = browser.new_page(viewport={"width": 1400, "height": 900})
        try:
            got.append(_part(pg, base, site_id, tail))
        finally:
            pg.close()
    plain, stale = got
    assert not plain["banner"] and not stale["banner"], (plain, stale)
    assert plain["now"] == stale["now"], (plain["now"], stale["now"])
    assert plain["pane"] == stale["pane"], "the part page read the run named in the address"


def test_the_audits_tab_opens_a_run_as_it_saw_the_site(browser, served):
    base, site_id, older, _newer = served
    pg = browser.new_page(viewport={"width": 1400, "height": 900})
    try:
        pg.goto(f"{base}/#/sites/{site_id}?tab=all&view=audits", wait_until="load", timeout=30_000)
        pg.wait_for_selector(".runs-table tbody tr", timeout=30_000)
        link = pg.locator(f'.runs-table a.row-link[href*="run={older}"]')
        cue = link.inner_text()
        link.click()
        pg.wait_for_selector(".history-banner", timeout=15_000)
        banner = pg.inner_text(".history-banner")
        heading = pg.inner_text("#pane h2, .pane-body h2")
        list_gone = pg.locator(".runs-table").count() == 0
        pg.click('.history-banner a:text-is("back to current")')
        pg.wait_for_selector(".runs-table tbody tr", timeout=15_000)
        after = {"banner": pg.locator(".history-banner").count(),
                 "hash": pg.evaluate("() => window.location.hash")}
    finally:
        pg.close()
    assert "view as this audit saw it" in cue, cue
    assert banner.startswith("Viewing as of audit T2 · ") and banner.endswith("back to current"), banner
    assert heading.startswith("Audit of "), heading
    assert list_gone, "the history view drew the audits list beside the run's own record"
    assert after["banner"] == 0 and "run=" not in after["hash"], after
