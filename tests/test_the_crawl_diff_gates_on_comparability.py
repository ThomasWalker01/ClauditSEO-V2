"""The crawl diff renders only across a comparable pair, and says why when
there is none; the record marks a page the latest site-wide crawl did not
fetch, and never a page a small scan merely did not reach.

Brief v2 step B (`_plans/site-screen-brief-v2-2026-09-03.md`, WF-05 and
WF-04's root). On the operator's site the newest audit was a T1
navigation scan after a T2 site scan, and "Between the last two crawls"
reported the pages the smaller scan never visited as "19 pages gone" -
which is what put `/apply` in the record as open on a page the diff called
gone. The predicate is the one the runs table's reading column already
stands on: tier, engine, scope, dimensions.

**Two fixtures.** The sweep's site seeds T2 then T3, so its newest pair is
not comparable and the gate's sentence must paint. The one-audit fixture
holds two T2 audits of one result, a comparable pair, so the sentence must
not.

**The marker's join, read off the API as the screen reads it.** The run
carries `crawled_paths` as JSON text; the latest site-wide audit's set is
what a finding's page is looked up in, by path.
"""

from __future__ import annotations

import json

import pytest

from tests.test_a11y_rendered import DIST
from tests.test_a11y_rendered import served as sweep_served  # noqa: F401  (reused fixture)
from tests.test_the_analyses_pane_reads_one_audit import served as pair_served  # noqa: F401

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")

pytestmark = [
    NEEDS_BROWSER,
    pytest.mark.skipif(not (DIST / "index.html").is_file(),
                       reason="dashboard not built (npm run build in dashboard/)"),
]

_AUDIT = """() => ({
  gate: (document.querySelector('.crawl-diff-gate')?.textContent || '').trim(),
  diffs: [...document.querySelectorAll('.pane-body h3')].filter((h) => /Between the last two crawls/.test(h.textContent)).length,
})"""

_RECORD = """() => ({
  marked: [...document.querySelectorAll('tbody tr .page-gone')].length,
  rows: document.querySelectorAll('tbody tr:has(code)').length,
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


def _audits(base, site_id):
    import httpx
    runs = httpx.get(f"{base}/api/sites/{site_id}", timeout=30).json()["runs"]
    return [r for r in runs if r["kind"] == "audit" and r["status"] == "complete"]


def test_a_pair_that_differs_gets_the_sentence_and_no_diff(browser, sweep_served):
    base, ids = sweep_served
    audits = _audits(base, ids["site"])
    assert len(audits) >= 2 and audits[0]["tier"] != audits[1]["tier"], (
        "precondition: the sweep's newest two audits share a tier")
    pg = browser.new_page()
    try:
        pg.goto(f"{base}/#/sites/{ids['site']}?tab=all&view=audits", wait_until="load", timeout=30_000)
        pg.wait_for_selector(".runs-table tbody tr", timeout=30_000)
        got = pg.evaluate(_AUDIT)
    finally:
        pg.close()
    assert got["diffs"] == 0, "a diff painted across two runs that cannot be read as one series"
    assert got["gate"].startswith("Between the two newest crawls: no comparable pair yet"), got["gate"]
    assert f"tier {audits[1]['tier']} → {audits[0]['tier']}" in got["gate"], got["gate"]


def test_a_comparable_pair_gets_no_such_sentence(browser, pair_served):
    base, site_id, _older, _newer = pair_served
    audits = _audits(base, site_id)
    assert len(audits) >= 2 and audits[0]["tier"] == audits[1]["tier"] \
        and sorted(audits[0]["dimensions"]) == sorted(audits[1]["dimensions"]), (
        "precondition: the pair fixture's audits are not comparable")
    pg = browser.new_page()
    try:
        pg.goto(f"{base}/#/sites/{site_id}?tab=all&view=audits", wait_until="load", timeout=30_000)
        pg.wait_for_selector(".runs-table tbody tr", timeout=30_000)
        got = pg.evaluate(_AUDIT)
    finally:
        pg.close()
    assert got["gate"] == "", got["gate"]


def test_the_record_marks_only_pages_the_latest_site_wide_crawl_did_not_fetch(browser, sweep_served):
    import httpx

    base, ids = sweep_served
    site = httpx.get(f"{base}/api/sites/{ids['site']}", timeout=30).json()
    # The screen's own choice of crawl (brief v3 step I): the newest
    # complete audit whose stored scope is site-wide, or - with no stored
    # scope - whose crawl fetched at least fifty pages. Never the tier. The
    # sweep's fixture crawls one page, so it has no such crawl and the
    # record marks nothing: a one-page scan is not a reading of the site.
    def scope(r):
        if r.get("scan_scope"):
            return r["scan_scope"]
        n = len(json.loads(r["crawled_paths"])) if r.get("crawled_paths") else 0
        return None if n == 0 else "page" if n == 1 else "nav" if n < 50 else "site"
    crawl = next((r for r in site["runs"]
                  if r["kind"] == "audit" and r["status"] == "complete" and r.get("crawled_paths")
                  and scope(r) in ("site", "full")), None)
    fetched = set(json.loads(crawl["crawled_paths"])) if crawl else None

    from urllib.parse import urlsplit
    import re
    def path(u):
        s = urlsplit(u); return s.path + (f"?{s.query}" if s.query else "")
    # Coverage notes are a strip of their own since brief v2 step F, not rows.
    note = re.compile(r"(-not-assessed$|-coverage$|^third-party-scripts)")
    rows_expected = [s for s in site["states"]
                     if not (s["severity"] == "info" and note.search(s["check_id"]))]
    expected = 0 if fetched is None else sum(
        1 for s in rows_expected
        if any(u.startswith("http") and path(u) not in fetched for u in s["affected_urls"]))

    pg = browser.new_page()
    try:
        pg.goto(f"{base}/#/sites/{ids['site']}?tab=all&group=none", wait_until="load", timeout=30_000)
        pg.wait_for_selector(".state-filters", timeout=30_000)
        pg.click('[aria-label="state filter"] [data-state="all"]')
        pg.wait_for_selector("tbody tr:has(code)", timeout=30_000)
        # Every row, not the first page of fifty.
        while pg.locator("button:has-text('show')").filter(has_text="more").count():
            pg.click("button:has-text('more')")
            pg.wait_for_timeout(200)
        got = pg.evaluate(_RECORD)
    finally:
        pg.close()
    assert got["rows"] == len(rows_expected), got
    assert got["marked"] == expected, (
        f"{got['marked']} rows marked as on a page not in the latest crawl; "
        f"the API's join gives {expected}")
