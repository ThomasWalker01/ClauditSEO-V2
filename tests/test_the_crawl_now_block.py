"""Crawl & sitemaps' site-level "now" (item 137, brief v18 step AZ).

The four counts and the venn are read off one stored run's crawl evidence;
`crawl_now_payload` is the reader. Held here:

  - the four counts (published · in sitemap · reached · render-only) and the
    three venn regions, computed from a hand-built crawl evidence whose sets
    are known, so the arithmetic is pinned rather than trusted;
  - `published` is the union of reached and in-sitemap on this host, so the
    three venn regions sum to it and each page lands in exactly one;
  - the UA matrix is passed through and is null on a run that captured none —
    the block states the absence rather than drawing an empty table;
  - the client renderer is registered for the crawl part, site-scoped, and
    draws the counts, the venn and the caveat.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import clauditseo.modules  # noqa: F401  (register dimensions)
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo, runs


@pytest.fixture
def seeded(tmp_path):
    conn = connect(tmp_path / "c.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site_id = repo.create_site(conn, repo.create_client(conn, op, "C"), "x.test")
    yield conn, site_id
    conn.close()


def _page(path, status=200):
    return {"url": f"https://x.test{path}", "status": status,
            "content_type": "text/html"}


def _run_with_evidence(conn, site_id, evidence, ua_matrix=None):
    run_id = runs.create_run(conn, site_id, ["TEC"], "T2")
    conn.execute("UPDATE audit_runs SET status='complete' WHERE id=?", (run_id,))
    ev = {"start_url": "https://x.test/", **evidence}
    if ua_matrix is not None:
        ev["ua_matrix"] = ua_matrix
    conn.execute("UPDATE audit_runs SET crawl_evidence=? WHERE id=?",
                 (json.dumps(ev), run_id))
    return run_id


def test_the_four_counts_and_the_venn(seeded):
    conn, site_id = seeded
    # reached = {/, /a, /b, /c}; sitemap declares {/, /a, /d, /e}; so
    # published = {/, /a, /b, /c, /d, /e} = 6.
    run_id = _run_with_evidence(conn, site_id, {
        "pages": [_page("/"), _page("/a"), _page("/b"), _page("/c"),
                  _page("/dead", status=404)],  # 404 is attempted, not reached
        "sitemap_entries": ["https://x.test/", "https://x.test/a",
                            "https://x.test/d", "https://x.test/e"],
        "sitemaps": [{"url": "https://x.test/sitemap.xml", "status": 200}],
    })
    p = runs.crawl_now_payload(conn, run_id)
    assert p["reached"] == 4, p           # the four 200s, not the 404
    assert p["in_sitemap"] == 4, p
    assert p["published"] == 6, p         # union of the two sets
    assert p["sitemap_files"] == 1, p
    v = p["venn"]
    assert v["reached_not_in_sitemap"] == 2   # /b /c
    assert v["in_sitemap_and_reached"] == 2   # / /a
    assert v["published_not_reached"] == 2    # /d /e
    # The three regions partition `published`.
    assert (v["reached_not_in_sitemap"] + v["in_sitemap_and_reached"]
            + v["published_not_reached"]) == p["published"]


def test_a_trailing_slash_does_not_split_a_page(seeded):
    conn, site_id = seeded
    # The crawl reached /a (no slash); the sitemap lists /a/ (slash). One page,
    # so it belongs to the in-sitemap-and-reached region, not two regions.
    run_id = _run_with_evidence(conn, site_id, {
        "pages": [_page("/a")],
        "sitemap_entries": ["https://x.test/a/"],
    })
    p = runs.crawl_now_payload(conn, run_id)
    assert p["published"] == 1, p
    assert p["venn"]["in_sitemap_and_reached"] == 1, p
    assert p["venn"]["reached_not_in_sitemap"] == 0, p


def test_an_offsite_sitemap_url_is_not_this_sites_page(seeded):
    conn, site_id = seeded
    run_id = _run_with_evidence(conn, site_id, {
        "pages": [_page("/")],
        "sitemap_entries": ["https://x.test/", "https://other.test/x"],
    })
    p = runs.crawl_now_payload(conn, run_id)
    assert p["in_sitemap"] == 1, p   # only the on-host URL counts


def test_the_ua_matrix_is_null_without_a_matrix_pass(seeded):
    conn, site_id = seeded
    run_id = _run_with_evidence(conn, site_id, {"pages": [_page("/")]})
    assert runs.crawl_now_payload(conn, run_id)["ua_matrix"] is None


def test_the_ua_matrix_is_reshaped_to_what_the_table_draws(seeded):
    # The crawler stores {agent, robots, home_status, probe_status, headers,
    # error}; the "now" table wants {agent, robots, fetched:[{url,status}],
    # note}, with the probe URLs named. The payload reshapes it, recomputing the
    # probe URLs from the crawl's own reached pages (the crawler stores only
    # their statuses) — so a live run's matrix renders, not breaks (item 137).
    conn, site_id = seeded
    stored = [
        {"agent": "Googlebot", "robots": "allow", "home_status": 200,
         "probe_status": [200], "headers": {}, "error": None},
        {"agent": "GPTBot", "robots": "disallow", "home_status": None,
         "probe_status": [None], "headers": {}, "error": None},
        {"agent": "ClaudeBot", "robots": "allow", "home_status": 200,
         "probe_status": [403], "headers": {"cf-ray": "abc"}, "error": None},
    ]
    run_id = _run_with_evidence(conn, site_id, {
        "pages": [_page("/"), _page("/about")]}, ua_matrix=stored)
    m = runs.crawl_now_payload(conn, run_id)["ua_matrix"]
    # Named fetched URLs: home (start) then the one probe page.
    assert m[0]["fetched"] == [{"url": "https://x.test/", "status": 200},
                               {"url": "https://x.test/about", "status": 200}]
    assert m[0]["note"] is None                           # allow, all 200
    assert m[1]["note"] == "blocked at the rule"          # disallow
    # Allowed by robots but a probe 403'd — a server refusal, with the CDN hint.
    assert "refused by the server" in m[2]["note"] and "cf-ray" in m[2]["note"]


def test_no_run_reads_nothing(seeded):
    conn, _ = seeded
    assert runs.crawl_now_payload(conn, None) is None


# ---- the client renderer ---------------------------------------------------

def _src(name: str) -> str:
    return (Path(__file__).resolve().parents[1] / "dashboard" / "src"
            / name).read_text(encoding="utf-8")


def test_the_block_is_crawls_site_picture_on_the_three_block_layout():
    # Brief v25 step BP: Crawl moved to the three-block layout once that
    # layout's site slot could narrow (item 137's reason for keeping it off is
    # gone). The block is Crawl's `siteNow`, above the depth control, and the
    # layout of last resort keeps its own mount for a harness that draws Crawl
    # there (`tests/last_resort.py`).
    part = _src("part_page.tsx")
    reg = part[part.index("export const PART_RENDERERS"):]
    assert "crawl: { noPageBlock: true, now: NoPageNow, siteNow: CrawlSiteNow" in reg
    site_now = part[part.index("function CrawlSiteNow"):part.index("function IndexabilitySiteNow")]
    assert "<CrawlNowBlock now={part.crawl_now}" in site_now and "<CrawlDepthBlock" in site_now


def test_the_block_draws_the_counts_the_venn_and_the_caveat():
    cn = _src("crawl_now.tsx")
    for count in ("Published", "In sitemap", "Reached", "Render-only"):
        assert count in cn, f"the four-count strip is missing {count}"
    assert "cn-venn" in cn, "no venn"
    # The UA-string caveat, stated once, and the absence-of-matrix line.
    assert "not proof of what the named crawler sees" in cn
    assert "No crawler access test in this audit" in cn
    # The status cells reuse the declared badge classes, not a new colour.
    assert "str-badge str-" in cn


def test_the_block_css_is_declared():
    css = _src("styles.css")
    for cls in (".cn-kv", ".cn-venn", ".cn-matrix", ".cn-caveat"):
        assert cls in css, f"{cls} is used but not declared"


def test_the_block_draws_the_parity_probe_and_says_when_it_did_not_run():
    """Item 151's page half: the probe's sentence, a row per probed page, and
    the two things that separate "tested clean" from "not tested" - the
    absence and the JavaScript limit - in words."""
    cn = _src("crawl_now.tsx")
    assert "mobile_parity?: MobileParity | null" in cn
    assert "<ParitySection parity={now.mobile_parity} />" in cn
    assert "What each device and Googlebot is served" in cn
    assert "Not assessed: this run did not fetch pages as a phone and as" in cn
    assert "No JavaScript was executed" in cn
    for column in ("iPhone vs desktop", "Googlebot vs browser"):
        assert column in cn
    css = _src("styles.css")
    for cls in (".cn-parity-statement", ".cn-parity-raised"):
        assert cls in css, f"{cls} is used but not declared"
