"""The re-audit drawer opens from a finding, pre-scoped, and never asks the
server for a set of pages it cannot take.

Brief step 5 (`_plans/site-screen-reorg-brief-2026-09-03.md`, WF-02). The
route to a re-run from a finding was the launcher on another screen, or the
coarse control found under the section. The drawer is the Analyses pane's
third column whenever a part with a sweep behind it is open: the sweep and
what else moves with it, the pages, the depth and the time, around the one
control that commits - `SectionRefresh`, unchanged.

**Why a browser, and why the request is intercepted.** The claims are about
what one press paints and what the commit sends. The launch route is
intercepted and answered `202` with a made-up run id, so the commit's body
can be read without a crawl starting; the fixture is the sweep's
(`test_section_refresh.py` reuses it the same way).

**The premise the brief got wrong, recorded here.** The brief wrote the
pages select as disabled "until F-06". F-06 is built for one page
(`POST /api/sites/{id}/refresh`, `PageRefresh`), and that option is live
once a page is narrowed to; what no route takes is a set of pages, and
those options are the disabled ones. The clause below holds the drawer to
that: the body it sends names dimensions and never a URL list.
"""

from __future__ import annotations

from tests.last_resort import on_the_layout_of_last_resort
import json

import pytest

from tests.test_a11y_rendered import DIST, served  # noqa: F401  (reused fixture)

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")

pytestmark = [
    NEEDS_BROWSER,
    pytest.mark.skipif(not (DIST / "index.html").is_file(),
                       reason="dashboard not built (npm run build in dashboard/)"),
]

_JS = """() => {
  const d = document.querySelector('.reaudit');
  const sel = d?.querySelector('.reaudit-pages');
  return {
    drawers: document.querySelectorAll('.reaudit').length,
    heading: (d?.querySelector('h3')?.textContent || '').trim(),
    from: (d?.querySelector('.reaudit-from')?.textContent || '').trim(),
    // The sweep chips are the third group since brief v5 step U.
    chips: [...(d?.querySelectorAll('.reaudit-sweep .tone') || [])]
      .map((c) => c.textContent.trim()),
    pages: sel ? { value: sel.value,
                   options: [...sel.options].map((o) => ({ value: o.value, disabled: o.disabled })) } : null,
    scopeNote: (d?.querySelector('.reaudit-scope-note')?.textContent || '').trim(),
    depths: [...(d?.querySelectorAll('.reaudit-depth button.tone') || [])].map((b) => ({
      text: b.textContent.trim(), on: b.getAttribute('aria-pressed') === 'true' })),
    cost: (d?.querySelector('.reaudit-cost')?.textContent || '').trim(),
    confirms: d ? d.querySelectorAll('.sec-refresh-confirm').length : 0,
    confirmText: (d?.querySelector('.sec-refresh-confirm')?.textContent || '').trim(),
    openers: d ? d.querySelectorAll('.sec-refresh-open').length : 0,
    marks: d ? d.querySelectorAll('.spend-mark').length : 0,
    // The section card no longer holds the control.
    inCard: document.querySelectorAll('.anat-pane .sec-refresh').length,
    columns: getComputedStyle(document.querySelector('.anat-layout')).gridTemplateColumns.split(' ').length,
  };
}"""


# Which dimension refreshes Indexability & canonicals, read off the rule rather
# than written out. It was ONP by a tie broken on the code while ONP and TEC
# covered five sections each; item 143 step BD moved `security` out of TEC, so
# TEC covers four and is now the smallest run that refreshes the section.
from clauditseo import anatomy as _an_refresh  # noqa: E402
from tests.parts import ANATOMY_READY, open_part

INDEX_DIM = _an_refresh.refresh_for("indexability")["dimension"]
INDEX_ALSO = len(_an_refresh.refresh_for("indexability")["also"])


@pytest.fixture(scope="module")


def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            yield b
        finally:
            b.close()


def _open_headings(browser, base, site_id, width=1400):
    pg = browser.new_page(viewport={"width": width, "height": 900})
    on_the_layout_of_last_resort(pg)
    pg.goto(f"{base}/#/sites/{site_id}?tab=findings", wait_until="load", timeout=30_000)
    pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
    # Images, not Headings: the drawer this reads is gone from the parts
    # that render as three blocks (brief v13 step AO, brief v14 step AP),
    # and Images keeps it under the same dimension these clauses name.
    # Indexability & canonicals since brief v16 step AT: Structured data took the three-block layout, and this clause drives the old part page's own controls.
    open_part(pg, 'Indexability & canonicals')
    pg.wait_for_selector(".reaudit", timeout=15_000)
    return pg


def test_the_drawer_states_the_sweep_the_pages_and_the_depth_before_any_click(browser, served):
    base, ids = served
    pg = _open_headings(browser, base, ids["site"])
    try:
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    assert got["drawers"] == 1 and got["heading"] == "Re-check Indexability & canonicals", got
    assert got["chips"] and got["chips"][0].startswith(INDEX_DIM), got["chips"]
    assert len(got["chips"]) > 1 and all(c.startswith("+ ") for c in got["chips"][1:]), (
        f"the parts that move with ONP are not listed before the click: {got['chips']}")
    assert got["pages"]["value"] == "site", got["pages"]
    disabled = {o["value"] for o in got["pages"]["options"] if o["disabled"]}
    assert {"finding", "nav", "filter"} <= disabled, got["pages"]
    assert "one" in disabled, "one page is offered before a page is narrowed to"
    # Brief v2 step D: the copy names the one page-scoped run this product
    # has (verify, from a finding) and says what no route takes.
    assert "verify" in got["scopeNote"] and "no route takes a list of pages" in got["scopeNote"], got["scopeNote"]
    assert "not yet available" not in got["scopeNote"], got["scopeNote"]
    # Three depths, Quick the default (brief v5 step U); every one is free,
    # since the sweep asks for no analyst at any depth.
    assert [d["text"].split(" ·")[0] for d in got["depths"]] == ["Quick", "Standard", "Deep"], got["depths"]
    assert [d["on"] for d in got["depths"]] == [True, False, False], got["depths"]
    assert all(d["text"].endswith("· free") for d in got["depths"]), got["depths"]
    # The sweep's fixture has run no precheck, so the honest estimate is the
    # sentence that says so; a fixture with one gets a time. Either way the
    # sweep asks for no analyst and the line says so.
    assert got["cost"].startswith(("Estimated ", "Run the precheck")), got["cost"]
    assert "no model" in got["cost"], got["cost"]
    assert got["openers"] == 1 and got["confirms"] == 0 and got["marks"] == 0, got
    assert got["inCard"] == 0, "the section card still holds the refresh control"
    # Two columns of the pane's own grid: the content and the drawer. The
    # parts list is the screen's sidebar since brief v4 Item 3a, outside it.
    assert got["columns"] == 2, f"the drawer is not the pane's second column at 1400px: {got}"


def test_one_press_on_a_finding_opens_the_drawer_pre_scoped_and_named(browser, served):
    base, ids = served
    pg = _open_headings(browser, base, ids["site"])
    try:
        # Instances stand under their cause since brief v2 step E: open the
        # worst cause, then press the first instance's re-audit.
        pg.click("table.causes tbody tr.cause-row:first-child .group-toggle")
        pg.click(".anat-pane table.causes tbody tr:not(.cause-row) >> nth=0 >> button:text-is('re-audit')")
        # From a finding that names a page, the drawer opens on the finding's
        # own scope (brief v2 step D): the verify run, through the fix loop's
        # own client function, with the sweep one choice away.
        pg.wait_for_selector(".reaudit .reaudit-verify", timeout=15_000)
        scoped = pg.evaluate(_JS)
        pg.select_option(".reaudit .reaudit-pages", "site")
        pg.wait_for_selector(".reaudit .sec-refresh-confirm", timeout=15_000)
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    finding_option = [o for o in scoped["pages"]["options"] if o["value"] == "finding"][0]
    assert not finding_option["disabled"], "the finding's own pages are not offered as a scope"
    assert scoped["pages"]["value"] == "finding", scoped["pages"]
    assert "verify" in scoped["scopeNote"] and "list of pages" in scoped["scopeNote"], scoped["scopeNote"]
    assert scoped["from"].startswith("From ") and "page" in scoped["from"], scoped["from"]
    # The primary button stays above its confirmation (brief v5 step U).
    assert got["confirms"] == 1 and got["openers"] == 1, got
    assert f"Re-run {INDEX_DIM}?" in got["confirmText"], got["confirmText"]


def test_the_finding_scope_is_the_records_verify_and_sends_the_finding_not_urls(browser, served):
    """Brief v2 step D. The route takes fingerprints, so the drawer sends the
    finding; the request carries no URL, and it is the same route the
    Record's banner posts to."""
    base, ids = served
    sent: list[dict] = []

    def answer(route):
        sent.append(json.loads(route.request.post_data or "{}"))
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps({"outcomes": [{"fingerprint": sent[-1]["fingerprints"][0],
                                                     "cleared": False, "decided": True,
                                                     "outcome": "still_present"}]}))

    pg = _open_headings(browser, base, ids["site"])
    try:
        pg.route("**/api/sites/*/verify", answer)
        # Instances stand under their cause since brief v2 step E: open the
        # worst cause, then press the first instance's re-audit.
        pg.click("table.causes tbody tr.cause-row:first-child .group-toggle")
        pg.click(".anat-pane table.causes tbody tr:not(.cause-row) >> nth=0 >> button:text-is('re-audit')")
        pg.wait_for_selector(".reaudit .reaudit-verify button", timeout=15_000)
        pg.click(".reaudit .reaudit-verify button")
        pg.wait_for_function(
            "() => /Verified:/.test(document.querySelector('.reaudit-verify')?.textContent || '')",
            timeout=15_000)
    finally:
        pg.close()
    assert len(sent) == 1 and list(sent[0]) == ["fingerprints"] and len(sent[0]["fingerprints"]) == 1, sent


def test_the_commit_sends_what_the_section_control_always_sent_and_never_a_url_list(browser, served):
    base, ids = served
    sent: list[dict] = []

    def answer(route):
        sent.append(json.loads(route.request.post_data or "{}"))
        route.fulfill(status=202, content_type="application/json",
                      body=json.dumps({"run_id": "drawer-test"}))

    pg = _open_headings(browser, base, ids["site"])
    try:
        pg.route("**/api/sites/*/audits", answer)
        pg.click(".reaudit .sec-refresh-open")
        pg.wait_for_selector(".reaudit .sec-refresh-confirm", timeout=15_000)
        pg.click(".reaudit .sec-refresh-confirm .tone-action-primary")
        pg.wait_for_selector(".reaudit .sec-refresh-done", timeout=15_000)
    finally:
        pg.close()
    assert sent == [{"dims": [INDEX_DIM], "tier": "auto", "analyst": False}], sent
    for body in sent:
        assert not any(k in body for k in ("urls", "only_urls", "start_url", "scope")), body


def test_a_chosen_depth_rides_on_the_same_request_as_its_tier(browser, served):
    base, ids = served
    sent: list[dict] = []

    def answer(route):
        sent.append(json.loads(route.request.post_data or "{}"))
        route.fulfill(status=202, content_type="application/json",
                      body=json.dumps({"run_id": "drawer-test"}))

    pg = _open_headings(browser, base, ids["site"])
    try:
        pg.route("**/api/sites/*/audits", answer)
        pg.click(".reaudit button.tone:has-text('Standard')")
        pg.click(".reaudit .sec-refresh-open")
        pg.wait_for_selector(".reaudit .sec-refresh-confirm", timeout=15_000)
        got = pg.evaluate(_JS)
        pg.click(".reaudit .sec-refresh-confirm .tone-action-primary")
        pg.wait_for_selector(".reaudit .sec-refresh-done", timeout=15_000)
    finally:
        pg.close()
    assert "Depth: T2, as chosen in the drawer" in got["confirmText"], got["confirmText"]
    assert got["cost"].startswith(("Estimated ", "Run the precheck")), got["cost"]
    if got["cost"].startswith("Estimated "):
        assert "at Standard" in got["cost"], got["cost"]
    assert sent == [{"dims": [INDEX_DIM], "tier": "T2", "analyst": False}], sent
