"""The catalogue of every brief is a drawer from the right of the Analyse
pane: the content under it does not move, it is absent from the pane's
body, one row per brief in sidebar order with one estimate or "unpriced",
no model select, and a page-scoped brief says it needs a page.

Brief v4 Item 3e (`_plans/site-screen-brief-v4-2026-09-03.md`). The lanes
stood in the pane's body with a sixteen-option model select on every row
and a price beside "unpriced".
"""

from __future__ import annotations

import re

import pytest

from tests.test_a11y_rendered import DIST, served  # noqa: F401  (reused fixture)
from tests.parts import ANATOMY_READY

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")

pytestmark = [
    NEEDS_BROWSER,
    pytest.mark.skipif(not (DIST / "index.html").is_file(),
                       reason="dashboard not built (npm run build in dashboard/)"),
]

_JS = """() => {
  const pane = document.querySelector('.anat-pane');
  const r = pane ? pane.getBoundingClientRect() : null;
  const drawer = document.querySelector('.catalogue-drawer');
  return {
    paneBox: r ? [Math.round(r.left), Math.round(r.top), Math.round(r.width)] : null,
    drawers: document.querySelectorAll('.catalogue-drawer').length,
    inBody: document.querySelectorAll('.pane-body .catalogue-drawer, .pane-body .lane').length,
    fixed: drawer ? getComputedStyle(drawer).position : null,
    fabs: document.querySelectorAll('.catalogue-fab').length,
    bigSelects: drawer ? [...drawer.querySelectorAll('select')].filter((s) => s.options.length > 3).length : 0,
    rows: drawer ? [...drawer.querySelectorAll('.catalogue-table tbody tr.crow')].map((tr) => ({
      part: tr.cells[0].textContent.trim(), tool: tr.querySelector('code')?.textContent.trim(),
      scope: tr.cells[2].textContent.trim(), model: tr.cells[3].textContent.trim(),
      est: tr.cells[4].textContent.trim(), state: tr.cells[5].textContent.trim(),
      act: tr.cells[6].textContent.trim() })) : [],
    focused: document.activeElement?.textContent?.trim() || null,
    // The product's part order, from the drawer's own part headers since the
    // sidebar's retirement (brief v24 step BO).
    sidebar: [...document.querySelectorAll('.catalogue-drawer .crow-part-link')].map((n) => n.textContent.trim()),
  };
}"""


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            yield b
        finally:
            b.close()


def test_the_drawer_opens_over_the_content_and_holds_one_row_per_brief(browser, served):
    import httpx

    base, ids = served
    lanes = httpx.get(f"{base}/api/runs/{ids['run']}/analyses", timeout=30).json()
    # Triage writes to no part and left the catalogue (brief v10 step AD);
    # the client plan writes `report` and never entered it (brief v18 step
    # AY). The drawer is a list of sidebar sections, so a brief belonging
    # to none of them has no row to sit in - its door is elsewhere.
    briefs = [b for b in lanes["ready"] + lanes["available"]
              if b["type"] != "triage" and b.get("part") not in ("none", "report")]
    pg = browser.new_page(viewport={"width": 1400, "height": 900})
    try:
        # A part open: the drawer stands over a part only; with none the shop is
        # the body (brief v24 step BO).
        pg.goto(f"{base}/#/sites/{ids['site']}?tab=findings&part=crawl", wait_until="load", timeout=30_000)
        pg.wait_for_selector(".anat-pane", timeout=30_000)
        pg.wait_for_selector(".catalogue-fab", timeout=30_000)
        # KI-60. The header above the pane keeps settling after the pane and
        # the control resolve: the legend strip's catalogue control grows
        # its "N not run · USD x for all" once the lanes land, and at this
        # width that wraps the strip onto a second row, moving the pane down
        # by one line. Under a parallel suite the lanes land after `closed`
        # is read and before `opened` is, and the one-axis 19px difference
        # was charged to the drawer. Read `closed` once the strip carries
        # the lanes' words, so both readings see the same header.
        pg.wait_for_function("() => /not run/.test(document.querySelector('.legend-catalogue')?.textContent || '')",
                             timeout=30_000)
        pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
        pg.wait_for_timeout(300)
        closed = pg.evaluate(_JS)
        pg.click(".catalogue-fab")
        pg.wait_for_selector(".catalogue-table tbody tr.crow", timeout=30_000)
        pg.wait_for_timeout(300)
        opened = pg.evaluate(_JS)
        pg.keyboard.press("Escape")
        pg.wait_for_function("() => !document.querySelector('.catalogue-drawer')", timeout=15_000)
        pg.click(".anat-catalogue-open")
        pg.wait_for_selector(".catalogue-table tbody tr.crow", timeout=30_000)
        again = pg.evaluate(_JS)
        # The drawer covers the strip while open; the strip's control closes it.
        pg.click(".anat-catalogue-open")
        pg.wait_for_function("() => !document.querySelector('.catalogue-drawer')", timeout=15_000)
        # Off Analyse the tab is gone.
        pg.click('a.seq-name:text-is("Record")')
        pg.wait_for_selector(".state-filters", timeout=30_000)
        record = pg.evaluate(_JS)
    finally:
        pg.close()
    assert closed["drawers"] == 0 and closed["fabs"] == 1, closed
    assert opened["drawers"] == 1 and opened["fixed"] == "fixed" and opened["fabs"] == 0, opened
    assert opened["paneBox"] == closed["paneBox"], "the content moved when the drawer opened"
    assert opened["inBody"] == 0, "the catalogue is in the pane's body"
    assert opened["bigSelects"] == 0, "a model select stands in the catalogue"
    assert opened["focused"] == "close ×", opened["focused"]
    assert len(opened["rows"]) == len(briefs), (len(opened["rows"]), len(briefs))
    assert {r["tool"] for r in opened["rows"]} == {b["tool"] for b in briefs}
    # Sidebar order: the parts named on the rows appear in the sidebar's order.
    order = [r["part"] for r in opened["rows"] if r["part"] != "—"]
    idx = [opened["sidebar"].index(p) for p in order]
    assert idx == sorted(idx), (order, opened["sidebar"])
    assert all(r["part"] == "—" for r in opened["rows"][len(order):]), "a part-less row sits among the parts"
    triage = [r for r in opened["rows"] if r["tool"] == "triage"]
    assert len(triage) == 0, "triage ranks the rest from step 3; it is not a row in the catalogue"
    # One estimate, or one of the two honest absences (brief v5 step Q):
    # "unpriced" only where the model has no price on file, with the way to
    # set one; "no estimate yet" where it has a price and no history.
    for r in opened["rows"]:
        # `model · ` since brief v17 step AV5: the kind of cost, then the
        # figure. What this clause is about is the figure.
        assert r["est"].startswith("model · "), r
        est = r["est"][len("model · "):]
        assert (re.fullmatch(r"(USD|~).*", est) and "unpriced" not in est) \
            or est.startswith("unpriced — set on Admin") \
            or est.startswith("no estimate yet"), r
    # A page-scoped brief that has not run says it needs a page; one that
    # has (onpage-hygiene is page-scoped by its header since brief v10 step
    # AD, and the fixture read it) is read like any other.
    #
    # Since item 145 retired `entity-graph`, `content-brief` is the only
    # page-scoped brief, and the rendered fixture stores a report for it (the
    # figure-lapse clause needs a page-route brief to open). So this fixture
    # can show a read page brief and not an unread one; each page-scoped row
    # must be one of the two states, and an unread one must say so.
    page_scoped = [r for r in opened["rows"] if r["scope"] == "one page"]
    assert page_scoped, "no page-scoped brief in the catalogue"
    for r in page_scoped:
        if "read" in r["state"]:
            continue
        # The state cell opens with the dot's own screen-reader word.
        assert r["state"].endswith("needs a page") and r["act"] == "pick a page", r
    assert again["drawers"] == 1, again
    assert record["drawers"] == 0 and record["fabs"] == 0, record


def test_the_retired_lanes_are_gone_from_the_source():
    from pathlib import Path
    src = Path(__file__).resolve().parents[1] / "dashboard" / "src"
    analyses = (src / "analyses.tsx").read_text(encoding="utf-8")
    for name in ("function AnalysesTab", "function AnalysisLanes", "function TriagePanel"):
        assert name not in analyses, f"{name} survives"
    assert "row-model" not in (src / "catalogue.tsx").read_text(encoding="utf-8")
