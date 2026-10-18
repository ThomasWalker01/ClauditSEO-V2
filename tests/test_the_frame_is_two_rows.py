"""The site screen's frame is the scope bar and the rail, and nothing else.

Brief v2 step A (`_plans/site-screen-brief-v2-2026-09-03.md`, UI-07, UI-08,
UX-12). The frame stood five rows tall before any pane: the alert strip,
the picker, the counts, the "What to do" pane and the rail. The pane is
retired - its controls went to the steps that own them (open audit and the
scheduler to step 2, the precheck to step 1) and its one sentence is the
next tile; the alert is a chip in the scope bar; the rail's state slot is
one word per state, and location is the outline alone.

**Why a browser.** The claims are about what stands between the screen's
top and its pane, and what words the rail paints.
"""

from __future__ import annotations

import re
from pathlib import Path

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

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"

_JS = """() => {
  const content = document.getElementById('content');
  const pane = document.querySelector('.pane-body');
  // Everything between the top of the routed content and the pane, as the
  // direct children that stand above it.
  // The screen's own children above the pane body. The reference row and
  // the pane's heading are the pane's, not the frame's, and the status
  // region has no height.
  const above = [];
  for (const el of content.children) {
    if (!pane || !(el.compareDocumentPosition(pane) & Node.DOCUMENT_POSITION_FOLLOWING)) continue;
    if (el.contains(pane)) continue;
    if (el.getBoundingClientRect().height === 0) continue;
    if (el.matches('nav.refs, .pane-head, .sr-only')) continue;
    above.push(el.className.split(' ')[0] || el.tagName.toLowerCase());
  }
  const words = [...document.querySelectorAll('.seq-step .seq-words > span')]
    .map((s) => s.textContent.trim().toLowerCase()).filter(Boolean);
  return {
    above,
    panes: document.querySelectorAll('.cur-pane').length,
    // Item 174: the regressions alert is about this run, not navigation, so
    // it sits in the head under the headline - and nowhere else.
    alertInBar: !!document.querySelector('#topbar-context .alertline'),
    alertsElsewhere: document.querySelectorAll('.alertline').length
      - document.querySelectorAll('.run-scope .alertline').length,
    // Item 174: the filter is page mode's control; in site mode the bar holds
    // the mode switch that shows it, and no filter anywhere else.
    filterInBar: !!document.querySelector('.client-context .mode-switch')
      && document.querySelectorAll('.page-find').length
         === document.querySelectorAll('.client-context .page-find').length,
    words,
    stateSlots: [...document.querySelectorAll('.seq-state')].map((s) => s.textContent.trim().toLowerCase()),
    openAudit: !!document.querySelector('.seq-step a[href^="#/runs/"]'),
    precheckAction: (document.querySelector('.seq-step:first-child .seq-action a')?.textContent || '').trim(),
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


def test_no_source_file_names_the_retired_pane():
    hits = [p.name for p in SRC.glob("*.tsx") if '"What to do"' in p.read_text(encoding="utf-8")]
    assert hits == [], hits


def test_the_frame_is_the_bar_and_the_rail(browser, served):
    base, ids = served
    pg = browser.new_page(viewport={"width": 1280, "height": 900})
    try:
        pg.goto(f"{base}/#/sites/{ids['site']}?tab=findings", wait_until="load", timeout=30_000)
        pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
        pg.wait_for_selector(".run-scope .bl-sentence", timeout=30_000)
        # Step 2's tile names the selected audit once the picker's list has
        # landed, which under a parallel run can be after the counts.
        pg.wait_for_selector(".seq-step a[href^='#/runs/']", state="attached", timeout=30_000)
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    assert got["panes"] == 0, f"a standing pane still stands above the pane body: {got}"
    # The page filter is the bar's left column (brief v4 Item 1, which
    # absorbed brief v3 step J the other way round).
    assert got["filterInBar"], "the page filter is not in the scope bar"
    assert got["alertsElsewhere"] == 0 and not got["alertInBar"], got
    # The rail's vocabulary: one word per state, no location word.
    assert "showing" not in got["words"] and "leaves this screen" not in got["words"], got["words"]
    assert set(got["words"]) <= {"done", "partial", "next", "running now", "idle"}, got["words"]
    assert all("showing" not in s for s in got["stateSlots"]), got["stateSlots"]
    # Step 1's action opens its own pane; step 2's tile opens the audit.
    assert got["precheckAction"] in ("run precheck", "open precheck"), got["precheckAction"]
    assert got["openAudit"], "step 2's tile offers no way to open the selected audit"
    # Item 173: the rail left its card for the head's actions row, so one
    # block stands above the pane - the head holding the sentence, the actions
    # and the strip. The picker, filter and chip are in the shell's bar, which
    # is not the screen's child.
    assert got["above"] == ["run-scope"], (
        f"more than the head stands above the pane: {got['above']}")


def test_the_scheduler_and_the_precheck_control_are_on_the_audit_destination(browser, served):
    base, ids = served
    pg = browser.new_page(viewport={"width": 1280, "height": 900})
    try:
        pg.goto(f"{base}/#/sites/{ids['site']}?tab=history", wait_until="load", timeout=30_000)
        pg.wait_for_selector(".scan-matrix", timeout=30_000)
        audit = pg.evaluate("() => document.querySelectorAll('.pane-body .schedule-open').length")
        # Precheck folds into Audit (brief v24 step BN): the same pane.
        pg.wait_for_selector(".pane-body .pre-panel", timeout=30_000)
        pre = pg.evaluate("() => [...document.querySelectorAll('.pane-body .pre-panel button')].map((b) => b.textContent.trim())")
    finally:
        pg.close()
    assert audit == 1, "the scheduler is not on the Audit pane"
    assert any(re.match(r"(re-)?run precheck", t) for t in pre), pre
