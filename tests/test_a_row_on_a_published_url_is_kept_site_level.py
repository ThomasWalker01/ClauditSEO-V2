"""A row on a URL the site publishes is kept site-level (item 275, row 3).

The Crawl brief writes per-page rows for `unreachable`, `sitemap-404s` and
`sitemap-noindex` naming the page, and the contract drops a row whose page is
not in the run's page set. An unreachable URL is one the crawl did not fetch,
so every such row was dropped: eight on twenty22, each "`TEC/unreachable` ·
/portfolio/ · page ... is not in the run's page set". A URL the run's
sitemaps list is now stored site-level with the URL in its evidence, as a
Security well-known path already is.
"""

from __future__ import annotations

import json

from clauditseo.analysts import contract, expert

BASE = "https://t.fixture"
PAGES = [BASE + "/", BASE + "/about/"]
CHECKS = ["TEC/unreachable", "TEC/sitemap-404s", "TEC/sitemap-noindex", "TEC/render-only"]


def _row(check, page):
    return {"check": check, "page": page, "status": "FAIL", "severity": "MEDIUM",
            "evidence": "listed in the sitemap, never reached", "replacement": "", "note": ""}


def _parse(rows, declared):
    block = json.dumps({"part": "crawl", "rows": rows, "not_assessable": []})
    return contract.parse("```json\n" + block + "\n```\n", CHECKS, PAGES,
                          rules=contract.Rules(declared_paths=declared))


def test_a_listed_url_the_crawl_did_not_fetch_is_kept_site_level():
    got = _parse([_row("TEC/unreachable", BASE + "/portfolio/")], {"/portfolio"})
    assert len(got.rows) == 1 and not got.dropped, got.dropped
    row = got.rows[0]
    assert row.evidence.startswith(BASE + "/portfolio/: "), row.evidence
    assert row.page == BASE + "/", row.page


def test_an_unlisted_url_or_another_check_is_still_dropped():
    # Not in the sitemaps: still a page outside the run.
    assert not _parse([_row("TEC/unreachable", BASE + "/nowhere/")], {"/portfolio"}).rows
    # Listed, but a check about a page the crawl read keeps the page-set rule.
    assert not _parse([_row("TEC/render-only", BASE + "/portfolio/")], {"/portfolio"}).rows
    # No evidence to read the sitemaps from: the rule is not applied.
    assert not _parse([_row("TEC/unreachable", BASE + "/portfolio/")], None).rows


def test_the_rules_carry_the_sitemaps_paths():
    assert expert._declared_paths({"sitemap_entries": [BASE + "/Portfolio/", BASE + "/"]}) \
        == {"/portfolio", "/"}
    assert expert._declared_paths(None) is None
