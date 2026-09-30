"""The scope bar and the landing (brief v23 step BL, brief v24 step BM).

BM moved the three lanes out of the bar and into the body as the landing; the
bar keeps the state sentence, the one primary action, the integrity line, the
mode switch, the picker and the context band. The lanes' clauses below read
them where they are now. The rest of this docstring is BL's history.

The scope bar's three columns were the three lanes (brief v23 step BL):
Waiting on you, with the pill naming the run its counts are computed from;
What has been measured; Settled. Above them the state sentence names the run
it describes; beside them the picker, its alert row and the context band. The
scope sentence stays a tooltip only.

Brief v8 step X made the bar three KPI columns (Standing / Pages / Reading
audit), after a two-column bar ~220px tall that named one run beside counts
computed against another. BL replaced the KPI columns with the lanes rather
than adding lanes beneath them (question channel 2026-09-13, option A).
"""

from __future__ import annotations

import httpx
import pytest

from tests.test_a11y_rendered import DIST, served  # noqa: F401  (reused fixture)
from tests.test_a_brief_never_runs_against_a_nav_scan import served as nav_served  # noqa: F401

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")

pytestmark = [
    NEEDS_BROWSER,
    pytest.mark.skipif(not (DIST / "index.html").is_file(),
                       reason="dashboard not built (npm run build in dashboard/)"),
]

VIEWPORT = {"width": 1568, "height": 1080}

_JS = """() => {
  const bar = document.querySelector('.run-scope');
  const landing = document.querySelector('.cl-landing');
  const cols = ['.lane-waiting', '.lane-measured', '.lane-settled'].map((s) => landing?.querySelector(s));
  const box = (el) => el ? el.getBoundingClientRect() : null;
  const [a, b, c] = cols.map(box);
  const dl = (sel) => [...document.querySelectorAll(sel + ' > div')].map((d) => ({
    label: (d.querySelector('dt')?.textContent || '').trim(),
    value: (d.querySelector('dd')?.textContent || '').trim(),
  }));
  return {
    barHeight: bar ? bar.getBoundingClientRect().height : -1,
    threeAcross: a && b && c && Math.abs(a.top - b.top) < 4 && Math.abs(b.top - c.top) < 4
      && a.right <= b.left + 1 && b.right <= c.left + 1,
    heads: [...(landing?.querySelectorAll('.cl-lane-head .sel-lbl') || [])].map((e) => e.textContent.trim()),
    // Item 239 step 5: the bar says the current audit, `.audit-now`.
    barHeads: [...document.querySelectorAll('.audit-now > .sel-lbl')].map((e) => e.textContent.trim()),
    lanesInBar: bar ? bar.querySelectorAll('.cl-lane').length : -1,
    pillRun: landing?.querySelector('.cur-when')?.dataset.run || null,
    pillText: (landing?.querySelector('.cur-when')?.textContent || '').trim(),
    pillHref: landing?.querySelector('.cur-when')?.getAttribute('href') || null,
    current: document.querySelector('.audit-now')?.dataset.audit || null,
    standing: dl('.lane-waiting .cl-lane-list').map((f) => f.label),
    pages: dl('.lane-measured .cl-lane-list'),
    // The per-run figure in the Pages column. It was `in this audit's
    // crawl`; 150 BJ replaced that with coverage, which is the figure
    // that is per run now - so the guarantee this reads (the number is
    // the PICKED run's) moved with it.
    // The state sentence names the run it describes (BL), and it is the
    // picker's run - the guarantee `.fig-coverage` carried before.
    crawlRun: bar?.querySelector('.bl-sentence')?.dataset.run || null,
    crawlValue: (bar?.querySelector('.bl-sentence .fig-coverage-n')?.textContent || '').trim(),
    filterUnderPages: false,  // item 174: no filter in site mode
    noteInline: (bar?.textContent || '').includes('Changes every pane below'),
    alertRow: !!bar?.querySelector('.scope-pick .scope-alert'),
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


def _land(pg, base, site_id):
    # The landing (BM): the bare site address.
    pg.goto(f"{base}/#/sites/{site_id}", wait_until="load", timeout=30_000)
    pg.wait_for_selector(".cl-landing .cl-lane-list", timeout=30_000)
    pg.wait_for_selector(".audit-now[data-audit]", state="attached", timeout=30_000)
    pg.wait_for_selector(".cl-landing .cur-when", timeout=30_000)
    pg.wait_for_timeout(300)


# `test_the_bar_guard_is_re_measured_and_recorded` (the bar within 130 px at
# 1568 wide, the filter in its side column, the alert row inside the picker) is
# RETIRED by item 173 (channel ruling 20260917-1125, part G): the head it measured
# is no longer a three-column card. Its replacement, and the claims of it that
# still hold, are in `tests/test_the_head_is_a_headline_then_actions.py`.


def test_the_standing_pill_names_the_run_the_counts_come_from(browser, served):
    """The pill is the run that last moved a finding state - the site's
    running total is not one run's output - and it tracks that run rather
    than the picker.

    **The last clause was a coincidence and is now an assertion.** It read
    `pillRun == picked`, true on a fixture where the picker's default and the
    last mover happened to be the same run - which meant it could not tell
    "the pill names the mover" from "the pill names the pick", and the whole
    reason the pill exists is that those are two different runs. The sweep
    fixture holds three audits since brief v16f and a brief finding reaches
    `open` on its second sighting, so the mover is the second audit and the
    picker defaults to the newest. Measured on this fixture: the pill names
    the middle T3 and the picker the newest.

    So the premise is read off the payload and both arms are asserted. Where
    the two runs coincide the pill must name both; where they do not it must
    follow the mover and NOT the pick, which is the clause that can now
    fail for the reason this pill was added."""
    base, ids = served
    current = httpx.get(f"{base}/api/sites/{ids['site']}/anatomy", timeout=30).json()["current"]
    pg = browser.new_page(viewport=VIEWPORT)
    try:
        _land(pg, base, ids["site"])
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    assert current["last_move"], current
    assert got["pillRun"] == current["last_move"]["run_id"], got
    assert got["pillHref"] == f"#/runs/{current['last_move']['run_id']}", got
    assert got["pillText"].startswith(f"as of {current['last_move']['at'][:10]} {current['last_move']['at'][11:16]}"), got["pillText"]
    # Item 239 step 5: the header's current audit, where the picker was.
    assert got["current"], "the bar names no current audit, so neither arm asserts anything"
    if current["last_move"]["run_id"] == got["current"]:
        assert got["pillRun"] == got["current"], (
            "the current audit IS the last mover and the pill names "
            f"{got['pillRun']} instead of {got['current']}")
    else:
        assert got["pillRun"] != got["current"], (
            f"the pill followed the header to {got['current']}; the run that "
            f"last moved a state is {current['last_move']['run_id']}, and a "
            "pill that tracks the audit named above is the confusion it was added to end")


def test_a_newer_nav_scan_is_not_what_the_site_screen_reads(browser, nav_served):
    """Item 239 step 5: nothing picks an audit, so a nav scan newer than the
    site-wide run is never what the site screen reads - the sentence and the
    pill both name the site-wide run. (This clause picked the nav scan and
    watched the figure move with the pick; the pick is retired.)"""
    base, site_id, wide, nav = nav_served
    current = httpx.get(f"{base}/api/sites/{site_id}/anatomy", timeout=30).json()["current"]
    pg = browser.new_page(viewport=VIEWPORT)
    try:
        _land(pg, base, site_id)
        pg.wait_for_timeout(300)
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    assert got["crawlRun"] == wide, got
    assert got["pillRun"] == current["last_move"]["run_id"] == wide, (got["pillText"], current["last_move"])
    assert "site-wide" in got["pillText"], got["pillText"]
