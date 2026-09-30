"""The precheck compared with the one before it: the sets diffed, the
suggestion a rule that fires at exactly the line, and the route that
serves both.

Brief v4 Item 2 (`_plans/site-screen-brief-v4-2026-09-03.md`). The
precheck's payload already holds the URL sets behind its counts
(`nav_urls`, `page_urls`, `not_in_sitemap`), so no new write was needed
for the diff; "the next audit after the prior check" is derived from the
run list at read time rather than written on the precheck row. What the
payload cannot say is said in `precheck_compare.py`: nav and footer are
one list, so "moved" is not reported; the sitemap list is capped at 500
and the payload says `capped` when a diff is over the cap.
"""

from __future__ import annotations

import pytest

from clauditseo.precheck_compare import (SUGGEST_MIN_PAGES, SUGGEST_MIN_SHARE,
                                         compare, path_key, suggest)
from tests.test_precheck_reads_what_the_site_says_about_itself import (  # noqa: F401
    FakeFetcher, HOME, SITEMAP, _api, site)


def test_the_rule_fires_at_exactly_the_line_and_not_below():
    # 10% of 30 is 3 pages: at the line on both counts.
    assert suggest(2, 1, 30, 0)["cell"] == "full:quick"
    # Under the share: 2 of 30.
    assert suggest(2, 0, 30, 0)["cell"] is None
    # Over the share but under the page floor: 2 of 10 is 20%.
    assert suggest(2, 0, 10, 0)["cell"] is None
    # At the floor and over the share.
    assert suggest(3, 0, 10, 0)["cell"] == "full:quick"
    # Only the navigation moved.
    assert suggest(0, 0, 30, 2)["cell"] == "nav:quick"
    # Nothing moved.
    assert suggest(0, 0, 30, 0)["cell"] is None
    # No readable prior sitemap: the share cannot be taken, nav decides.
    assert suggest(5, 0, None, 1)["cell"] == "nav:quick"
    assert SUGGEST_MIN_SHARE == 0.10 and SUGGEST_MIN_PAGES == 3


def test_a_precheck_url_and_a_crawled_path_name_one_page():
    assert path_key("https://ex.test/about/") == "/about"
    assert path_key("/about/") == "/about"
    assert path_key("https://ex.test/") == "/"
    assert path_key("/a?x=1") == "/a?x=1"


def test_the_first_check_diffs_against_the_last_audits_crawl():
    now = {"checked_at": "2026-09-03T11:33:00", "sitemap_state": "ok", "sitemap_files": 2,
           "nav_urls": ["https://ex.test/", "https://ex.test/about"],
           "page_urls": ["https://ex.test/", "https://ex.test/about", "https://ex.test/new"]}
    got = compare(now, None, prior_kind="crawl", prior_at="2026-09-01T00:00:00",
                  before_audit=None, audit_paths=["/", "/about/", "/old"])
    assert got["diff"]["full"] == {"added": ["/new"], "removed": ["/old"], "known": True}
    assert got["diff"]["nav"]["known"] is False
    assert got["prior"]["kind"] == "crawl" and got["prior"]["full"] == 3


def _second(site_pages: dict) -> dict:
    """The site a check later: the sitemap grew by four and lost one, the
    header gained a link."""
    grown = dict(site_pages)
    grown["https://ex.test/sitemap.xml"] = (200, SITEMAP.replace(
        "  <url><loc>https://ex.test/secret-orphan</loc></url>\n",
        "".join(f"  <url><loc>https://ex.test/new-{n}</loc></url>\n" for n in range(1, 5))))
    grown["https://ex.test/"] = (200, HOME.replace(
        '<a href="/about">About</a></header>',
        '<a href="/about">About</a><a href="/careers">Careers</a></header>'))
    return grown


def test_the_route_serves_now_prior_diff_and_suggestion(tmp_path, monkeypatch, site):
    client, site_id = _api(tmp_path, monkeypatch, "cmp.db")
    assert client.get(f"/api/sites/{site_id}/precheck/compare").json() is None

    monkeypatch.setattr("clauditseo.precheck.Fetcher", lambda **_: FakeFetcher(site))
    client.post(f"/api/sites/{site_id}/precheck", json={})
    # One check and no audit: nothing to compare with, and the payload says so.
    alone = client.get(f"/api/sites/{site_id}/precheck/compare").json()
    assert alone["prior"]["kind"] is None and alone["diff"]["full"]["known"] is False

    monkeypatch.setattr("clauditseo.precheck.Fetcher", lambda **_: FakeFetcher(_second(site)))
    client.post(f"/api/sites/{site_id}/precheck", json={})
    got = client.get(f"/api/sites/{site_id}/precheck/compare").json()
    assert got["prior"]["kind"] == "precheck" and got["prior"]["full"] == 4
    assert got["now"]["full"] == 7 and got["now"]["sitemap_files"] == 1
    assert got["diff"]["full"]["added"] == ["/new-1", "/new-2", "/new-3", "/new-4"]
    assert got["diff"]["full"]["removed"] == ["/secret-orphan"]
    assert got["diff"]["nav"]["added"] == ["/careers"] and got["diff"]["nav"]["removed"] == []
    # Five of four published: over the line, and at least three pages.
    assert got["suggestion"]["cell"] == "full:quick"
    assert got["suggestion"]["changed"] == 5
    assert got["prior"]["before_audit"] is None, "no audit ran between the checks"
