"""The Audit pane lists the runs once, in one dimension order, with the
trend's reading on each row and the destructive verb behind a disclosure.

Brief step 7 (`_plans/site-screen-reorg-brief-2026-09-03.md`, UX-02, UX-06,
UI-03, UI-04). The pane showed the history twice - a score-trend table and
a runs table - under a dot chart with no axis and no dates that restated
the table beneath it; each run listed its dimensions in the order it was
asked for, so two rows read the same set two ways; and `delete` stood at
equal weight beside `vs previous` on every row.

**Why a browser.** The claims are about what paints: one table, one
picture that is not a restatement of it, an order, a disclosure. Where a
comparison stops being one is asserted elsewhere on rendered text
(`test_a11y_rendered.py`) and is untouched here.

**A picture stands over the table again, and the clause changed shape
rather than being dropped.** UX-06 removed a chart, and this file asserted
`svgs == 0` for it. Brief v16f draws one back, so the assertion that can
still fail is not "no chart" — it is the thing UX-06 actually objected to:
a chart with no axis and no dates that restates the table beneath it. What
is asserted now is that the chart carries both, and that the trend's own
TABLE is still gone, which is the half of UX-02 nothing has proposed
undoing.

**The join the reading rests on.** A trend point names the run that made
it: `metric_snapshots.run_id`, since migration 0044. It was a join on the
stamp the two share, and the stamp is second-resolution — the clause below
used to reproduce the screen's three-part narrowing key to work around
that. It reads the id off the API instead now, which is the same join the
screen makes and no longer an approximation of it.
"""

from __future__ import annotations

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
  const pane = document.querySelector('.pane-body');
  const heads = [...pane.querySelectorAll('.runs-table thead th')].map((th) => th.textContent.trim());
  return {
    ask: (document.querySelector('.pane-ask')?.textContent || '').trim(),
    scanHeading: (pane.querySelector('.scan-matrix')?.closest('.card')?.querySelector('h3')?.textContent || '').trim(),
    charts: pane.querySelectorAll('svg.st-chart').length,
    ticks: [...pane.querySelectorAll('.st-tick')].map((t) => t.textContent.trim()),
    whens: [...pane.querySelectorAll('.st-when')].map((t) => t.textContent.trim()),
    trendTables: pane.querySelectorAll('.trend-table').length,
    runsTables: pane.querySelectorAll('.runs-table').length,
    frame: (pane.querySelector('.st-now')?.textContent || '').trim(),
    heads,
    rows: [...pane.querySelectorAll('.runs-table tbody tr')].map((tr) => {
      const cells = [...tr.querySelectorAll('td')].map((td) => td.textContent.trim());
      return {
        started: cells[0], dims: cells[2], reading: cells[5],
        compareInline: !!tr.querySelector('td:nth-child(7) > a'),
        // `checkVisibility`: a closed <details> hides its content with
        // content-visibility, which offsetParent does not see.
        deleteVisible: [...tr.querySelectorAll('button')].some((b) =>
          b.textContent.trim() === 'delete' && b.checkVisibility()),
        more: tr.querySelectorAll('details.row-more').length,
      };
    }),
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


@pytest.fixture(scope="module")
def screen(browser, served):
    base, ids = served
    pg = browser.new_page(viewport={"width": 1280, "height": 900})
    try:
        pg.goto(f"{base}/#/sites/{ids['site']}?tab=all&view=audits", wait_until="load", timeout=30_000)
        pg.wait_for_selector(".runs-table tbody tr", timeout=30_000)
        pg.wait_for_selector(".st-now", timeout=30_000)
        # The dimension order arrives with `/api/meta`; wait for it to apply
        # rather than reading the rows' own order.
        pg.wait_for_function(
            "() => document.querySelector('.runs-table tbody td:nth-child(3)')?.textContent.trim().length > 0",
            timeout=30_000)
        pg.wait_for_timeout(400)
        yield pg.evaluate(_JS), base, ids
    finally:
        pg.close()


def test_one_table_lists_the_runs_and_the_picture_over_it_is_not_a_second(screen):
    got, _, _ = screen
    assert got["runsTables"] == 1 and got["trendTables"] == 0, got
    # One chart, and it carries the two things UX-06 removed the last one
    # for lacking: an axis a reader can place a score on, and a date under
    # every point. Counted rather than merely present, because two charts on
    # one pane is the restatement UX-02 is about in its other half.
    assert got["charts"] == 1, f"{got['charts']} trend charts on the pane"
    assert got["ticks"], "the chart carries no axis, which is what UX-06 removed"
    assert len(got["whens"]) == len(got["rows"]) - 1, (
        "the chart draws a point for every run rather than for every scored "
        f"one, or none of them is dated: {got['whens']} against "
        f"{len(got['rows'])} rows")
    assert got["frame"], "the trend's sentence is gone with the chart"
    assert got["heads"][:6] == ["Started", "Tier", "Dimensions", "Status", "Score",
                                "Reads against"], got["heads"]
    # The chooser is Audit's since brief v24 step BN; the runs are the
    # Record's Audits view, which draws no second way to start one.
    assert got["scanHeading"] == "", got["scanHeading"]
    assert "every audit so far" in got["ask"] and "Choose a scan" not in got["ask"], got["ask"]


def test_every_row_lists_its_dimensions_in_the_servers_order(screen):
    import httpx

    got, base, _ = screen
    order = [d["code"] for d in httpx.get(f"{base}/api/meta", timeout=30).json()["dimensions"]]
    assert got["rows"], got
    for row in got["rows"]:
        dims = [d.strip() for d in row["dims"].split(",") if d.strip()]
        ranked = sorted(dims, key=lambda d: (order.index(d) if d in order else 999, d))
        assert dims == ranked, (f"row {row['started']} lists {dims}, "
                                f"the canonical order is {ranked}")


def test_each_row_reads_against_the_run_its_point_names(screen):
    import httpx

    got, base, ids = screen
    site = httpx.get(f"{base}/api/sites/{ids['site']}", timeout=30).json()
    # The join the screen makes, read off the payload: a point names its run.
    with_point = {p["run_id"] for p in site["trend"] if p["run_id"]}
    assert with_point, "precondition: no trend point names the run that made it"
    assert with_point < {r["id"] for r in site["runs"]}, (
        "precondition: every run in the fixture has a point, so a row that "
        "must read a dash does not exist and the count below cannot fail")
    readings = [r["reading"] for r in got["rows"]]
    assert sum(1 for r in readings if r != "—") == len(with_point), (
        readings, len(with_point))
    # The shapes the column takes on THIS fixture: the first point, a point
    # with no earlier run measured its way, and a point that names the
    # earlier run it does read against. The fourth shape — "nearest same
    # basis", where the partner is not the point before — needs a history
    # with a run between the pair, and is asserted on the operator's own nine
    # points in `test_the_score_trend_is_drawn.py`.
    assert any(r == "— first point" for r in readings), readings
    assert any(r.startswith("nothing —") for r in readings), readings
    assert any(r[:1].isdigit() for r in readings), (
        f"no row names the run it reads against: {readings}")


def test_delete_is_behind_a_disclosure_and_vs_previous_is_not(screen):
    got, _, _ = screen
    assert any(r["compareInline"] for r in got["rows"]), got["rows"]
    with_more = [r for r in got["rows"] if r["more"]]
    assert with_more, "no row offers the disclosure"
    assert all(not r["deleteVisible"] for r in got["rows"]), (
        f"delete is visible before the disclosure is opened: {got['rows']}")
