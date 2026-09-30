"""A part's "read" pill is the newest run of that analysis on the site,
dated, and opens the report on the run it is on - whatever audit the header
holds (since step 5, the header holds none). No pill opens to a 404.

Brief v6 steps V1 and V4 bound the pills to the picked audit and added a
second, muted "read elsewhere" pill for a report on another run. Item 239
step 4 (amendment 10) retires both: the pills read the Latest View's newest
analysis per tool, the rule the rows beneath them already read, so a pill
and its rows cannot name different runs. This file keeps the fixture that
proved the old rule - an analysis on the OLDER of two audits, the newer
picked - because it is exactly the case the new rule changes.
"""

from __future__ import annotations

from tests.last_resort import on_the_layout_of_last_resort
import time

import httpx
import pytest

from clauditseo.db.connection import connect
from clauditseo.persistence import runs
from tests.test_a11y_rendered import DIST
from tests.test_coverage import DIMS, _Hub, _run
from tests.test_triage_ranks_the_section_rail import _serve
from tests.parts import ANATOMY_READY, open_part

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")

pytestmark = [
    NEEDS_BROWSER,
    pytest.mark.skipif(not (DIST / "index.html").is_file(),
                       reason="dashboard not built (npm run build in dashboard/)"),
]

#: A brief whose part still renders the cause table and its read pills.
TOOL = "crawl"


@pytest.fixture(scope="module")
def served():
    """Two site-wide audits; a brief written against the OLDER one."""
    server, thread, db, base = _serve("pickerrun")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "Picker Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "pickerrun.fixture"}, timeout=30).json()
        conn = connect(db)
        result = _run(_Hub())
        older = runs.create_run(conn, site["id"], DIMS, "T2")
        runs.complete_run(conn, older, result)
        runs.store_expert_report(
            conn, older, TOOL,
            {"model": "test-model", "report": "# Hygiene\n\nRead once.",
             "findings": [{"code": "title-missing", "severity": "high",
                           "summary": "A title is missing."}]})
        time.sleep(1.1)
        newer = runs.create_run(conn, site["id"], DIMS, "T2")
        runs.complete_run(conn, newer, result)
        conn.close()
        yield base, site["id"], older, newer
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def _crawl(anatomy: dict) -> dict:
    return next(c for c in anatomy["categories"] if c["key"] == "crawl")


def test_the_pill_is_the_newest_analysis_whatever_the_pick(served):
    base, site_id, older, newer = served
    views = [httpx.get(f"{base}/api/sites/{site_id}/anatomy", params=p, timeout=30).json()
             for p in ({"run_id": older}, {"run_id": newer}, {})]
    for view in views:
        part = _crawl(view)
        assert part["analysed_by"] == [TOOL], part["analysed_by"]
        assert [(a["tool"], a["run_id"]) for a in part["analysed"]] == [(TOOL, older)]
        assert part["analysed"][0]["audits_since"] == 1, part["analysed"]
        assert TOOL not in part["can_run"], part["can_run"]
        # The two old run-bound fields are gone, not left beside the new one.
        assert "read_against" not in view and "read_elsewhere" not in part
    # Every pill opens a report.
    for a in _crawl(views[1])["analysed"]:
        got = httpx.get(f"{base}/api/runs/{a['run_id']}/expert/{a['tool']}", timeout=30)
        assert got.status_code == 200, (a, got.status_code)


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            yield b
        finally:
            b.close()


def test_the_pill_says_its_date_and_opens_the_report(browser, served):
    base, site_id, older, newer = served
    pg = browser.new_page(viewport={"width": 1400, "height": 900})
    on_the_layout_of_last_resort(pg)
    try:
        pg.goto(f"{base}/#/sites/{site_id}?tab=findings", wait_until="load", timeout=30_000)
        pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
        open_part(pg, 'Crawl & sitemaps')
        pg.wait_for_selector(".anat-pane .read-analysis", timeout=15_000)
        got = pg.evaluate("""() => ({
          current: document.querySelector('.audit-now')?.dataset.audit,
          pills: [...document.querySelectorAll('.anat-pane .read-analysis')].map((b) => ({ text: b.textContent.trim(), run: b.dataset.run })),
          elsewhere: document.querySelectorAll('.read-elsewhere').length,
          runs: [...document.querySelectorAll('.anat-pane .cat-run button')].map((b) => b.textContent.trim()),
        })""")
        pg.click(".anat-pane .read-analysis")
        pg.wait_for_selector(".anat-pane .sec-report", timeout=15_000)
        report = pg.inner_text(".anat-pane .sec-report")
        # The drawer's dot says the part has been read, with the newer audit
        # the header's current one.
        pg.click(".catalogue-fab")
        pg.wait_for_selector(".catalogue-drawer .crow-part", timeout=15_000)
        pg.wait_for_timeout(300)
        dots = pg.evaluate("() => document.querySelectorAll('.crow-part .cat-read').length")
    finally:
        pg.close()
    assert got["current"] == newer, got
    assert len(got["pills"]) == 1 and got["pills"][0]["run"] == older, got["pills"]
    assert got["pills"][0]["text"].startswith(f"read {TOOL} · "), got["pills"]
    assert got["elsewhere"] == 0
    assert not any(f"run {TOOL}" in p for p in got["runs"]), got["runs"]
    assert "Read once" in report, report
    assert dots >= 1
