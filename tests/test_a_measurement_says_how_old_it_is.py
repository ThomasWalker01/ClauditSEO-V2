"""A measurement says how old it is (item 239 step 6).

  - Under the operator's warning age a part's date is muted; from it, in the
    warning tone, "may be out of date", with the part's re-check beside it;
    from the out-of-date age, in the danger tone, "out of date", and the part
    is marked stale in the parts strip - a word, not a colour alone.
  - The two ages are the operator's: `/api/prefs/age`, set in Admin, 30 and
    90 days by default, and a warning that would come after staleness is
    refused.
  - A part whose items were measured on different days says its range.

The rendered fixture is one site whose only audit ran 45 days ago: the
warning case under the defaults, and out of date once Admin's ages are 10
and 40.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from clauditseo.persistence import latest_view, runs
from tests.needs_build import needs_build
from tests.parts import ANATOMY_READY, open_part
from tests.test_page_facts_read_the_latest_view import _history

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")
PART = "Crawl & sitemaps"


def test_a_part_whose_items_were_measured_on_different_days_says_its_range(tmp_path):
    conn, site, _ids = _history(tmp_path, "r")
    parts = {c["key"]: c for c in runs.anatomy_view(conn, site)["categories"]}
    # Title & description: the ONP-only T2 of 23 Sept fetched 40 pages of
    # 60; the other 20 keep T3's reading of 18 Sept.
    rng = parts["title-desc"]["measured_range"]
    assert rng["from"].startswith("2026-09-18") and rng["to"].startswith("2026-09-23"), rng
    assert parts["title-desc"]["age_thresholds"] == {"warn_days": 30, "stale_days": 90}


@pytest.fixture(scope="module")
def served():
    """One site whose only audit ran 45 days ago."""
    from clauditseo.db.connection import connect
    from tests.test_coverage import DIMS, _Hub, _run
    from tests.test_triage_ranks_the_section_rail import _serve

    server, thread, db, base = _serve("ages")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "Age Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "ages.fixture"}, timeout=30).json()
        conn = connect(db)
        run = runs.create_run(conn, site["id"], DIMS, "T2")
        runs.complete_run(conn, run, _run(_Hub()))
        at = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat(timespec="seconds")
        conn.execute("UPDATE audit_runs SET started_at=?, finished_at=? WHERE id=?", (at, at, run))
        conn.commit()
        latest_view.rebuild(conn, site["id"], "test: dated 45 days ago")
        conn.close()
        yield base, site["id"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_the_ages_are_the_operators_and_a_late_warning_is_refused(served):
    base, _site = served
    got = httpx.get(f"{base}/api/prefs/age", timeout=30).json()
    assert (got["warn_days"], got["stale_days"]) == (30, 90), got
    bad = httpx.put(f"{base}/api/prefs/age", json={"warn_days": 90, "stale_days": 30}, timeout=30)
    assert bad.status_code == 422, bad.text
    assert httpx.get(f"{base}/api/prefs/age", timeout=30).json()["warn_days"] == 30


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            yield b
        finally:
            b.close()


def _read(browser, base, site_id):
    pg = browser.new_page(viewport={"width": 1400, "height": 900})
    try:
        pg.goto(f"{base}/#/sites/{site_id}?tab=findings", wait_until="load", timeout=30_000)
        pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
        key = open_part(pg, PART)
        pg.wait_for_selector(".anat-pane .part-prov .age", timeout=15_000)
        return pg.evaluate("""(key) => {
          const age = document.querySelector('.part-prov .prov-line .age');
          const link = document.querySelector(`.part-switch .cl-part-${key}`);
          return {
            tone: age?.dataset.age || null, text: age?.textContent.trim() || '',
            classes: age ? [...age.classList] : [],
            recheck: !!age?.parentElement?.querySelector('.age-recheck'),
            stale: (link?.querySelector('.parts-stale')?.textContent || '').trim(),
          };
        }""", key)
    finally:
        pg.close()


@NEEDS_BROWSER
@needs_build
def test_an_old_measurement_says_so_in_its_tone_and_offers_the_re_check(browser, served):
    base, site_id = served
    warned = _read(browser, base, site_id)
    assert warned["tone"] == "warn" and "tone-warn" in warned["classes"], warned
    assert warned["text"] == "measured 6 weeks ago, may be out of date", warned
    assert warned["recheck"], f"no re-check beside a date that may be out of date: {warned}"
    assert warned["stale"] == "", warned
    # Admin's ages move the same date to out of date, and the part is marked.
    httpx.put(f"{base}/api/prefs/age", json={"warn_days": 10, "stale_days": 40}, timeout=30)
    try:
        stale = _read(browser, base, site_id)
    finally:
        httpx.put(f"{base}/api/prefs/age", json={"warn_days": 30, "stale_days": 90}, timeout=30)
    assert stale["tone"] == "stale" and "tone-bad" in stale["classes"], stale
    assert stale["text"] == "measured 6 weeks ago, out of date", stale
    assert stale["stale"] == "stale", f"the parts strip does not mark the part stale: {stale}"
