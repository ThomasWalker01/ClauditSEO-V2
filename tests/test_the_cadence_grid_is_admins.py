"""Item 177, "the cadence grid goes to Admin" (concept H5, relocated).

"When does each site run" is one question about every site, and answering it
meant opening each site's schedule modal in turn. Admin > Cadences is the same
data across sites: one row per site, the whole-audit cadence and the brief
cadences as columns, what each row costs a year, and the total.

The accept criterion, driven: every site's cadence and the annual cost of all of
them on one screen, changed without leaving it - and a cadence set there is the
one that site's own schedule modal shows, because the grid and the modal read
and write the same fields (one source of truth). The modal stays.

The arithmetic is shared, not copied: the grid prices a schedule with
`annualCost`, which the modal uses too, so the two cannot price one schedule
differently.

Runs against this module's own fixture server and database, never the
operator's.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_a11y_rendered import DIST, served  # noqa: F401  (module fixture)

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"

pytestmark = [
    pytest.mark.skipif(
        __import__("importlib.util", fromlist=["util"]).find_spec("playwright") is None,
        reason="playwright is not installed"),
    pytest.mark.skipif(not (DIST / "index.html").is_file(),
                       reason="dashboard not built (npm run build in dashboard/)"),
]


def test_the_grid_and_the_modal_share_one_arithmetic():
    grid = (SRC / "cadence.tsx").read_text(encoding="utf-8")
    modal = (SRC / "schedule.tsx").read_text(encoding="utf-8")
    assert "export function annualCost" in modal and "annualCost(data?.available" in modal, (
        "the modal no longer prices through the shared computation")
    assert "annualCost(" in grid and "PER_YEAR" not in grid, (
        "the grid prices a schedule with its own copy of the arithmetic")
    assert "/api/sites/${siteId}/schedule" in grid and "api.put" in grid, (
        "the grid does not write the site's own schedule fields")


def test_every_site_on_one_screen_changed_in_place_and_the_modal_agrees(served):
    import httpx
    from playwright.sync_api import sync_playwright

    base, ids = served
    site = ids["site"] if isinstance(ids, dict) else ids
    sites = httpx.get(f"{base}/api/overview", timeout=30).json()["sites"]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page(viewport={"width": 1440, "height": 1000})
        try:
            pg.goto(f"{base}/#/admin?tab=cadence", wait_until="load", timeout=30_000)
            pg.wait_for_selector(f'.cadence-row[data-site="{site}"] select.cadence-audit', timeout=30_000)
            rows = pg.locator(".cadence-row").count()
            start = pg.url

            # The whole audit, in place.
            pg.select_option(f'.cadence-row[data-site="{site}"] select.cadence-audit', "weekly")
            pg.wait_for_function(
                f"() => fetch('{base}/api/sites/{site}/schedule').then((r) => r.json())"
                ".then((s) => s.audit_cadence === 'weekly')", timeout=15_000)

            # A brief, through a column added here, in place.
            tool = pg.eval_on_selector(".cadence-add select",
                                       "s => [...s.options].map((o) => o.value).filter(Boolean)[0]")
            pg.select_option(".cadence-add select", tool)
            cell = f'.cadence-row[data-site="{site}"] select.cadence-tool[aria-label^="{tool} cadence"]'
            pg.wait_for_selector(cell, timeout=10_000)
            pg.select_option(cell, "monthly")
            pg.wait_for_function(
                f"() => fetch('{base}/api/sites/{site}/schedule').then((r) => r.json())"
                f".then((s) => s.tools.some((t) => t.tool_id === '{tool}' && t.cadence === 'monthly'))",
                timeout=15_000)
            pg.wait_for_function(
                f"""() => !document.querySelector('.cadence-row[data-site="{site}"][aria-busy]')""",
                timeout=10_000)
            money = pg.evaluate("""() => ({
              rows: [...document.querySelectorAll('.cadence-row .cadence-cost')]
                .map((c) => c.dataset.usd).filter((v) => v !== '').map(Number),
              total: Number(document.querySelector('.cadence-total [data-usd]').dataset.usd) })""")
            stayed = pg.url == start

            # The site's own modal, from its own Audit pane, shows the same.
            pg.goto(f"{base}/#/sites/{site}?tab=history", wait_until="load", timeout=30_000)
            pg.click(".schedule-open", timeout=30_000)
            pg.wait_for_selector(".modal .sched-block", timeout=15_000)
            modal = pg.evaluate(f"""() => ({{
              audit: document.querySelector('.modal input[name=audit]:checked')?.value,
              tool: document.querySelector('.modal select[aria-label="cadence for {tool}"]')?.value }})""")
        finally:
            browser.close()
    assert rows == len(sites), f"the grid shows {rows} rows for {len(sites)} sites"
    assert stayed, "changing a cadence left the grid"
    assert abs(sum(money["rows"]) - money["total"]) < 1e-9, f"the total is not the rows' sum: {money}"
    assert modal == {"audit": "weekly", "tool": "monthly"}, (
        f"the site's own schedule modal disagrees with the grid: {modal}")
