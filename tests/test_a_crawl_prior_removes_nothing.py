"""Against a crawl the precheck removes nothing, and a check older than the
last audit says so (item 254).

Round-2 audit of the Audit pane, IP-01, Critical. A first check has no
prior check and was compared with the newest audit's crawl. Two faults:

- the crawl was NEWER than the check (17 Sept sitemap against a 29 Sept
  crawl), so the table ran backwards; and
- the list of pages the crawl read that the sitemap does not declare was
  called "removed" and fed to the Record's "on pages gone" - four live nav
  pages on twenty22, with open findings, filed as gone from the site.
"""

from __future__ import annotations

import json

import pytest

from clauditseo.precheck_compare import CRAWL_IS_NEWER, compare, later
from tests.test_precheck_reads_what_the_site_says_about_itself import (  # noqa: F401
    FakeFetcher, _api, site)


def test_two_stamps_are_ordered_as_moments_not_as_text():
    """A check is stamped in local time and a run in UTC. As text, a check
    made at 21:02 +10:00 sorts after an audit that started an hour later."""
    check, audit = "2026-09-17T21:02:30+10:00", "2026-09-17T12:00:00+00:00"
    assert check > audit, "the premise: text order is the wrong way round"
    assert later(audit, check) and not later(check, audit)
    assert later("2026-09-18T00:00:00", "2026-09-17T23:00:00+00:00"), "no offset reads as UTC"
    assert not later(None, check) and not later("not a date", check)


NOW = {"checked_at": "2026-09-03T11:33:00+00:00", "sitemap_state": "ok", "sitemap_files": 1,
       "nav_urls": ["https://ex.test/"],
       "page_urls": ["https://ex.test/"] + [f"https://ex.test/new-{n}" for n in range(4)]}


def test_a_crawl_prior_suggests_on_what_the_sitemap_declares_alone():
    """Ten pages the crawl read and the sitemap does not list call for no
    scan; four the sitemap declares and the crawl did not read do."""
    got = compare(NOW, None, prior_kind="crawl", prior_at="2026-09-01T00:00:00+00:00",
                  before_audit=None,
                  audit_paths=["/"] + [f"/nav-{n}" for n in range(10)])
    assert len(got["diff"]["full"]["removed"]) == 10 and len(got["diff"]["full"]["added"]) == 4
    sug = got["suggestion"]
    assert sug["changed"] == 4, sug
    assert "the sitemap declares were not in the last crawl" in sug["reason"], sug["reason"]
    assert "added or removed" not in sug["reason"] and "published before" not in sug["reason"]


def test_a_check_older_than_the_newest_audit_is_stale():
    got = compare(NOW, None, prior_kind=None, prior_at=None, before_audit=None,
                  prior_reason=CRAWL_IS_NEWER, newest_audit_at="2026-09-29T06:09:00+00:00")
    assert got["stale"] == {"audit_at": "2026-09-29T06:09:00+00:00"}
    assert got["prior"]["reason"] == CRAWL_IS_NEWER
    fresh = compare(NOW, None, prior_kind=None, prior_at=None, before_audit=None,
                    newest_audit_at="2026-09-01T00:00:00+00:00")
    assert fresh["stale"] is None and fresh["prior"]["reason"] is None


def _audit(db, site_id: str, started: str, paths: list[str]) -> None:
    from clauditseo.db.connection import connect
    from clauditseo.persistence import runs
    conn = connect(db)
    run_id = runs.create_run(conn, site_id, ["TEC"], "T2", scan_scope="site")
    conn.execute("UPDATE audit_runs SET status='complete', started_at=?, created_at=?,"
                 " finished_at=?, crawled_paths=? WHERE id=?",
                 (started, started, started, json.dumps(paths), run_id))
    conn.commit()
    conn.close()


def test_the_route_takes_a_crawl_as_prior_only_when_it_is_older(tmp_path, monkeypatch, site):
    client, site_id = _api(tmp_path, monkeypatch, "cmp254.db")
    monkeypatch.setattr("clauditseo.precheck.Fetcher", lambda **_: FakeFetcher(site))
    # An audit from long before the check: a prior, and worded as a crawl.
    _audit(tmp_path / "cmp254.db", site_id, "2020-01-01T00:00:00+00:00", ["/", "/only-crawled"])
    client.post(f"/api/sites/{site_id}/precheck", json={})
    older = client.get(f"/api/sites/{site_id}/precheck/compare").json()
    assert older["prior"]["kind"] == "crawl" and older["stale"] is None, older["prior"]
    assert "/only-crawled" in older["diff"]["full"]["removed"]

    # An audit after the check: the check is now the older of the two.
    _audit(tmp_path / "cmp254.db", site_id, "2099-01-01T00:00:00+00:00", ["/", "/only-crawled"])
    newer = client.get(f"/api/sites/{site_id}/precheck/compare").json()
    assert newer["prior"]["kind"] is None, newer["prior"]
    assert newer["prior"]["reason"] == CRAWL_IS_NEWER
    assert newer["diff"]["full"] == {"added": [], "removed": [], "known": False}
    assert newer["stale"] == {"audit_at": "2099-01-01T00:00:00+00:00"}


# ---- the screen ----------------------------------------------------------------

from tests.test_a11y_rendered import DIST, served  # noqa: E402,F401  (reused fixture)
from tests.test_the_precheck_pane_compares_and_suggests import (  # noqa: E402,F401
    COMPARE, NEEDS_BROWSER, _JS, _precheck, browser)

BUILT = pytest.mark.skipif(not (DIST / "index.html").is_file(),
                           reason="dashboard not built (npm run build in dashboard/)")

#: The first check against an older crawl: `/p1` is a page the crawl read
#: that the sitemap does not declare. The fixture's findings name it.
CRAWL = {**COMPARE,
         "stale": None,
         "prior": {**COMPARE["prior"], "kind": "crawl", "reason": None, "before_audit": None},
         "suggestion": {**COMPARE["suggestion"], "changed": 46,
                        "reason": "46 pages the sitemap declares were not in the last crawl, "
                                  "460% of the 10 it read, over the 10% line"}}

#: A check an audit has since overtaken: nothing beside it, and it says why.
STALE = {**COMPARE,
         "stale": {"audit_at": "2026-09-29T06:09:00+00:00"},
         "prior": {"kind": None, "at": None, "reason": CRAWL_IS_NEWER, "before_audit": None,
                   "nav": None, "full": None, "full_capped": False,
                   "sitemap_files": None, "sitemap_state": None},
         "diff": {"nav": {"added": [], "removed": [], "known": False},
                  "full": {"added": [], "removed": [], "known": False}, "capped": False},
         "suggestion": {"cell": None, "changed": 0, "share": None,
                        "reason": "nothing to run: nothing published moved since the prior check",
                        "min_share": 0.1, "min_pages": 3}}


def _wire(pg, site_id: str, fixture_site: str, payload: dict) -> None:
    pre = _precheck(fixture_site)
    pg.route(f"**/api/sites/{site_id}/precheck",
             lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(pre)))
    pg.route(f"**/api/sites/{site_id}/precheck/compare",
             lambda r: r.fulfill(status=200, content_type="application/json",
                                 body=json.dumps(payload)))


@NEEDS_BROWSER
@BUILT
def test_against_a_crawl_the_lists_are_named_for_what_they_are(browser, served):
    import httpx
    base, ids = served
    site_row = httpx.get(f"{base}/api/sites/{ids['site']}", timeout=30).json()
    pg = browser.new_page(viewport={"width": 1400, "height": 900})
    try:
        _wire(pg, ids["site"], site_row["domain"].rstrip("/"), CRAWL)
        pg.goto(f"{base}/#/sites/{ids['site']}?tab=precheck", wait_until="load", timeout=30_000)
        pg.wait_for_selector(".pre-compare", timeout=30_000)
        pg.wait_for_timeout(300)
        got = pg.evaluate(_JS)
        rule = pg.evaluate("() => document.querySelector('.pre-rule')?.textContent || ''")
    finally:
        pg.close()
    full = {r[0].split(" ")[0]: r for r in got["rows"]}["Full"][4]
    assert "46 declared, not crawled" in full and "1 crawled, not declared" in full, full
    assert "removed" not in full and "added" not in full, full
    assert "on pages gone" not in rule and "nothing is removed" in rule, rule
    assert "since last check" not in got["pagesLine"], got["pagesLine"]
    assert got["tile"] == "counted 11:33 · 55 pages", got["tile"]


@NEEDS_BROWSER
@BUILT
def test_a_page_the_crawl_read_and_the_sitemap_omits_is_not_gone(browser, served):
    import httpx
    base, ids = served
    site_row = httpx.get(f"{base}/api/sites/{ids['site']}", timeout=30).json()
    pg = browser.new_page(viewport={"width": 1400, "height": 900})
    try:
        pg.goto(f"{base}/#/sites/{ids['site']}?tab=all", wait_until="load", timeout=30_000)
        pg.wait_for_selector('[aria-label="state filter"] [data-state="gone"]', timeout=30_000)
        pg.wait_for_timeout(300)
        before = pg.evaluate(_JS)
        _wire(pg, ids["site"], site_row["domain"].rstrip("/"), CRAWL)
        with pg.expect_response(lambda r: r.url.endswith("/precheck/compare")):
            pg.reload(wait_until="load")
        pg.wait_for_selector('[aria-label="state filter"] [data-state="gone"]', timeout=30_000)
        pg.wait_for_timeout(600)
        after = pg.evaluate(_JS)
    finally:
        pg.close()
    assert after["goneCount"] == before["goneCount"], (before["goneCount"], after["goneCount"])


@NEEDS_BROWSER
@BUILT
def test_a_check_older_than_the_last_audit_says_so_and_offers_the_re_run(browser, served):
    import httpx
    base, ids = served
    site_row = httpx.get(f"{base}/api/sites/{ids['site']}", timeout=30).json()
    pg = browser.new_page(viewport={"width": 1400, "height": 900})
    try:
        _wire(pg, ids["site"], site_row["domain"].rstrip("/"), STALE)
        pg.goto(f"{base}/#/sites/{ids['site']}?tab=precheck", wait_until="load", timeout=30_000)
        pg.wait_for_selector(".pre-cost.pre-stale", timeout=30_000)
        got = pg.evaluate("""() => ({
          stamp: document.querySelector('.pre-cost').textContent.trim().replace(/\\s+/g, ' '),
          colour: getComputedStyle(document.querySelector('.pre-cost')).color,
          muted: getComputedStyle(document.querySelector('.pre-note')).color,
          pill: document.querySelector('.pre-cta button').className,
          table: !!document.querySelector('.pre-compare'),
          first: (document.querySelector('.pre-first')?.textContent || '').trim().replace(/\\s+/g, ' '),
        })""")
    finally:
        pg.close()
    assert got["stamp"].endswith("older than the last audit · re-run"), got["stamp"]
    assert got["colour"] != got["muted"], "the stale stamp is drawn like any other"
    assert "tone-action-primary" in got["pill"], got["pill"]
    assert not got["table"], "a table was drawn against a crawl newer than the check"
    assert got["first"] == f"Nothing to compare with: {CRAWL_IS_NEWER}.", got["first"]
