"""The Precheck pane shows now beside prior with what moved, suggests the
scan the difference calls for, lands that cell pre-selected on the Audit
pane without pressing it, says the page-list run needs a route, and marks
findings on removed pages as gone.

Brief v4 Item 2 (`_plans/site-screen-brief-v4-2026-09-03.md`). The rule
itself is unit-tested in `test_the_precheck_compares_now_with_prior.py`;
this file reads the screen.

**Why the wire is rewritten here.** The sweep's fixture runs no precheck,
so the two payloads the pane reads are answered through the page's own
route table: a precheck, and a comparison in which the sitemap grew by
forty-six pages and lost `/p1` - a page the fixture's findings name, so
the record's gone marker can be read.
"""

from __future__ import annotations

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

ADDED = [f"/new-{n}" for n in range(1, 47)]


def _precheck(base_url: str) -> dict:
    return {
        "entry_url": base_url + "/", "checked_at": "2026-09-03T11:33:00", "took_ms": 9300,
        "sitemap_state": "ok", "sitemap_files": 8, "sitemap_urls": 55, "sitemap_truncated": False,
        "nav_count": 15, "footer_count": 1, "nav_unique": 15,
        "not_linked": [], "not_in_sitemap": [], "warnings": [],
        "nav_urls": [base_url + f"/n{n}" for n in range(15)],
        "page_urls": [base_url + p for p in ADDED] + [base_url + f"/n{n}" for n in range(9)],
        "page_urls_capped": False, "findings_meaningful": True,
        "scopes": {"page": {"pages": 1, "basis": "a URL you name"},
                   "nav": {"pages": 15, "basis": "15 in navigation, 1 in the footer"},
                   "full": {"pages": 55, "basis": "sitemap, 8 files"}},
    }


COMPARE = {
    "now": {"checked_at": "2026-09-03T11:33:00", "nav": 15, "full": 55, "full_capped": False,
            "sitemap_files": 8, "sitemap_state": "ok"},
    "prior": {"kind": "precheck", "at": "2026-09-02T12:17:00",
              "before_audit": {"id": "r1", "started_at": "2026-09-02T14:00:00", "tier": "T3"},
              "nav": 10, "full": 10, "full_capped": False, "sitemap_files": 2, "sitemap_state": "ok"},
    "diff": {"nav": {"added": ["/n10", "/n11", "/n12", "/n13", "/n14"], "removed": [], "known": True},
             "full": {"added": ADDED, "removed": ["/p1"], "known": True},
             "capped": False},
    "suggestion": {"cell": "full:quick", "changed": 47, "share": 4.7,
                   "reason": "47 pages added or removed is 470% of the 10 published before, over the 10% line",
                   "min_share": 0.1, "min_pages": 3},
}

_JS = """() => {
  const rows = [...document.querySelectorAll('.pre-compare tbody tr')].map((tr) =>
    [...tr.cells].map((td) => td.textContent.trim().replace(/\\s+/g, ' ')));
  return {
    rows,
    prior: (document.querySelector('.pre-prior')?.textContent || '').trim(),
    suggest: (document.querySelector('.pre-suggest b')?.textContent || '').trim(),
    run: document.querySelector('.pre-suggest-acts a')?.getAttribute('href') || null,
    pageList: (() => { const b = document.querySelector('.pre-suggest-acts button'); return b ? {text: b.textContent.trim(), disabled: b.disabled, why: document.getElementById(b.getAttribute('aria-describedby') || '')?.textContent.trim()} : null; })(),
    rec: [...document.querySelectorAll('.scan-cell.is-rec')].map((b) => b.getAttribute('aria-label')),
    pane: (document.querySelector('.pane-name')?.textContent || '').trim(),
    // Precheck's line inside Audit's panel since brief v24 step BN.
    tile: (() => { const li = [...document.querySelectorAll('.seq-step')].find((el) => (el.querySelector('.seq-name')?.textContent || '').trim() === 'Audit'); return (li?.querySelector('.seq-state')?.textContent || '').trim().split(' · Audit: ')[0].replace(/^Precheck: /, ''); })(),
    // The pages line stands on Audit's precheck block since the sidebar's
    // retirement (brief v24 step BO).
    pagesLine: (document.querySelector('.pre-pages-line')?.textContent || '').trim(),
    goneCount: parseInt(document.querySelector('[aria-label="state filter"] [data-state="gone"] .tone-count-info')?.textContent || '-1', 10),
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


def _wire(pg, site_id: str, base: str, fixture_site: str):
    pre = _precheck(fixture_site)
    pg.route(f"**/api/sites/{site_id}/precheck",
             lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(pre)))
    pg.route(f"**/api/sites/{site_id}/precheck/compare",
             lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(COMPARE)))
    posted = []
    pg.route(f"**/api/sites/{site_id}/audits",
             lambda r: (posted.append(r.request.post_data),
                        r.fulfill(status=202, content_type="application/json",
                                  body=json.dumps({"run_id": "never"}))))
    return posted


def test_now_beside_prior_the_suggestion_and_the_cell_it_lands_on(browser, served):
    import httpx

    base, ids = served
    site = httpx.get(f"{base}/api/sites/{ids['site']}", timeout=30).json()
    pg = browser.new_page(viewport={"width": 1400, "height": 900})
    try:
        posted = _wire(pg, ids["site"], base, site["domain"].rstrip("/"))
        pg.goto(f"{base}/#/sites/{ids['site']}?tab=precheck", wait_until="load", timeout=30_000)
        pg.wait_for_selector(".pre-compare", timeout=30_000)
        pg.wait_for_selector(".seq-step .seq-state", state="attached", timeout=30_000)
        pg.wait_for_timeout(300)
        got = pg.evaluate(_JS)
        pg.click('.pre-suggest-acts a:has-text("Show Full · Quick in the grid")')
        pg.wait_for_selector(".scan-matrix", timeout=30_000)
        pg.wait_for_timeout(300)
        landed = pg.evaluate(_JS)
    finally:
        pg.close()
    scope = {r[0].split(" ")[0]: r for r in got["rows"]}
    assert scope["Nav"][1:4] == ["15", "10", "+5 · +50%"], scope["Nav"]
    assert scope["Full"][1:4] == ["55", "10", "+45 · +450%"], scope["Full"]
    assert "46 added" in scope["Full"][4] and "1 removed" in scope["Full"][4], scope["Full"]
    assert "sitemap files 2 → 8" in scope["Full"][4], scope["Full"]
    assert scope["Robots"][1:3] == ["ok", "ok"], scope["Robots"]
    assert got["prior"].startswith("prior 2026-09-02 12:17 (before audit 2026-09-02 T3)"), got["prior"]
    assert got["suggest"] == "Suggested: Full · Quick · free", got["suggest"]
    assert got["run"] == f"#/sites/{ids['site']}?tab=history&scope=full&depth=quick", got["run"]
    assert got["pageList"] == {"text": "Scan only the 46 new pages", "disabled": True,
                               "why": "not available yet"}, got["pageList"]
    assert got["tile"] == "counted 11:33 · 55 pages · +46", got["tile"]
    # Both directions on one line since brief v12 step AN: 46 pages arrived
    # and one went, which `+46 · 1 gone` read as a single movement.
    assert got["pagesLine"].startswith("+46 · −1 since last check"), got["pagesLine"]
    # Landed on Audit with the cell marked, and nothing started.
    assert landed["pane"] == "Audit", landed["pane"]
    assert len(landed["rec"]) == 1 and landed["rec"][0].startswith("Full"), landed["rec"]
    assert posted == [], "landing on the cell pressed it"


def test_a_finding_on_a_page_the_sitemap_dropped_is_gone(browser, served):
    import httpx

    base, ids = served
    site = httpx.get(f"{base}/api/sites/{ids['site']}", timeout=30).json()
    on_p1 = [s for s in site["states"]
             if any(u.rstrip("/").endswith("/p1") for u in s["affected_urls"])
             and not (s["severity"] == "info")]
    assert on_p1, "precondition: no fixture finding names /p1"
    pg = browser.new_page(viewport={"width": 1400, "height": 900})
    try:
        pg.goto(f"{base}/#/sites/{ids['site']}?tab=all", wait_until="load", timeout=30_000)
        pg.wait_for_selector('[aria-label="state filter"] [data-state="gone"]', timeout=30_000)
        pg.wait_for_timeout(300)
        before = pg.evaluate(_JS)
        _wire(pg, ids["site"], base, site["domain"].rstrip("/"))
        pg.reload(wait_until="load")
        # The Record has no pages line since the sidebar's retirement (brief
        # v24 step BO): the comparison has landed when the gone chip counts
        # the pages it dropped.
        pg.wait_for_function(
            "(n) => parseInt(document.querySelector('[aria-label=\"state filter\"] [data-state=\"gone\"] .tone-count-info')?.textContent || '-1', 10) >= n",
            arg=before["goneCount"] + len(on_p1), timeout=30_000)
        pg.wait_for_timeout(300)
        after = pg.evaluate(_JS)
    finally:
        pg.close()
    assert after["goneCount"] >= before["goneCount"] + len(on_p1), (before["goneCount"], after["goneCount"], len(on_p1))
