"""A part opens on its causes, not its instances; the briefs for the part
stand under the causes; the catalogue stands behind one control; and no
rail row wraps.

Brief v2 step E (`_plans/site-screen-brief-v2-2026-09-03.md`, UX-07, UI-06,
UX-10). Headings opened on fifty flat instance rows, worst first - "Heading
level jumps H1→H4 on /blog/…" forty-five times - with no cause or template
between the operator and the list (UX-07); part names wrapped letter by
letter when the shared-pages tag appeared (UI-06); and twenty-three briefs
with a model select each stood above the parts list (UX-10).

A cause is a check from one source, counted from the site's record rather
than the part's capped fifty, with its pages and the templates among them;
the instances open beneath. The sweep's rows and a brief's are never
merged. The briefs for the part are listed under the causes; the whole
catalogue opens from the rail's foot.
"""

from __future__ import annotations

from tests.last_resort import on_the_layout_of_last_resort
import pytest

from tests.test_a11y_rendered import DIST, served  # noqa: F401  (reused fixture)
from tests.parts import ANATOMY_READY, open_part

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
  const rows = [...(pane?.querySelectorAll('table.causes tbody tr') || [])];
  const rowKind = (tr) => tr.classList.contains('cause-row') ? 'cause'
    : tr.classList.contains('cause-template-row') ? 'template'
    : tr.classList.contains('cause-confirm') ? 'confirm'
    : tr.classList.contains('pages-row') ? 'pages' : 'instance';
  return {
    causes: rows.filter((tr) => rowKind(tr) === 'cause').map((tr) => ({
      check: (tr.querySelector('code')?.textContent || '').trim(),
      source: (tr.querySelector('[class*="tone-source-"]')?.textContent || '').trim(),
      pages: (() => {
        // The pages a cause row accounts for. Since item 155 the cell is a
        // count carrying its population - `12 of 16 pages crawled`, and a
        // second span for what the record holds outside the assessed set -
        // so the number is read off the count's own data rather than the
        // cell's text, which is that item's clause and not this one's. The
        // two halves sum to what the cell used to show alone.
        const c = tr.querySelector('td.num [data-population]');
        if (!c) return (tr.querySelector('td.num')?.textContent || '').trim();
        const v = Number(c.getAttribute('data-value') || 0);
        const out = Number(
          tr.querySelector('td.num .prev-outside')?.getAttribute('data-outside') || 0);
        return String(v + out);
      })(),
      expanded: tr.querySelector('.group-toggle')?.getAttribute('aria-expanded'),
      templates: [...tr.querySelectorAll('.cause-template')].map((t) => t.textContent.trim()),
    })),
    instances: rows.filter((tr) => rowKind(tr) === 'instance').length,
    order: [...(pane?.querySelectorAll('table.causes, .cause-briefs, .cat-run') || [])]
      .map((el) => el.className.split(' ')[0] || el.tagName.toLowerCase()),
    // The catalogue is a drawer since brief v4 Item 3e.
    catalogue: document.querySelectorAll('.catalogue-drawer').length,
    // The catalogue's control is the legend strip's since brief v4 Item 3d.
    foot: (document.querySelector('.legend-catalogue')?.textContent || '').trim(),
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


def _open(browser, base, site_id, part="Crawl & sitemaps", width=1280):
    pg = browser.new_page(viewport={"width": width, "height": 900})
    on_the_layout_of_last_resort(pg)
    pg.goto(f"{base}/#/sites/{site_id}?tab=findings", wait_until="load", timeout=30_000)
    pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
    open_part(pg, part)
    pg.wait_for_selector("table.causes", timeout=15_000)
    return pg


def test_a_part_opens_on_its_causes_with_the_instances_beneath(browser, served):
    import httpx

    base, ids = served
    site = httpx.get(f"{base}/api/sites/{ids['site']}", timeout=30).json()
    # The fixture's twelve-page row, which moved from
    # `CNT/duplicate-content` to `TEC/http-status-error` at brief v17 step
    # AX when Content gained a renderer and lost its cause table.
    skips = [s for s in site["states"] if s["check_id"] == "http-status-error"
             and s["state"] in ("open", "regressed")]
    assert skips, "precondition: the fixture has no open http-status-error finding"
    pages = len({u for s in skips for u in s["affected_urls"]})

    pg = _open(browser, base, ids["site"])
    try:
        got = pg.evaluate(_JS)
        pg.click("table.causes tbody tr.cause-row:first-child .group-toggle")
        pg.wait_for_selector("table.causes tbody tr:not(.cause-row)", timeout=15_000)
        opened = pg.evaluate(_JS)
    finally:
        pg.close()
    # Every check of the part is a cause row, `0` where nothing was raised
    # (brief v11 step AH); the ones carrying rows stay few.
    raised = [c for c in got["causes"] if c["source"]]
    assert raised and len(raised) <= 5, got["causes"]
    assert got["instances"] == 0, "instances paint before a cause is opened"
    # The tag carries the source's count since brief v10 step AF: `sweep 2`.
    skip = [c for c in got["causes"] if c["check"].endswith("/http-status-error") and c["source"].startswith("automatic checks")]
    assert len(skip) == 1, got["causes"]
    assert skip[0]["pages"] == str(pages), (skip[0], pages)
    assert opened["instances"] >= 1 and opened["causes"][0]["expanded"] == "true", opened
    # Briefs stand under the causes.
    assert got["order"][:2] == ["findings", "cause-briefs"] or got["order"][0] == "findings", got["order"]
    assert "cause-briefs" in got["order"] and got["order"].index("cause-briefs") > got["order"].index("findings")


def test_the_catalogue_is_behind_the_rails_control(browser, served):
    base, ids = served
    pg = _open(browser, base, ids["site"])
    try:
        before = pg.evaluate(_JS)
        pg.click(".anat-catalogue-open")
        pg.wait_for_selector(".catalogue-drawer", timeout=15_000)
        after = pg.evaluate(_JS)
    finally:
        pg.close()
    assert before["catalogue"] == 0 and before["foot"].startswith("open the catalogue"), before["foot"]
    assert "All analyses" in before["foot"], before["foot"]
    assert after["catalogue"] >= 1 and after["foot"].startswith("hide the catalogue"), after["foot"]


# `test_no_rail_name_is_clipped_and_the_re_run_is_a_glyph` retired with the
# rail it measured (brief v24 step BO). The re-run glyph's home is the
# shop header: tests/test_a_re_run_is_one_press_from_the_shop.py.
