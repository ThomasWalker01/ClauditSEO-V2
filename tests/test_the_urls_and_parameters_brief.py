"""URLs & parameters (item 141, brief v19 step BB): the contract brief, its
fourteen checks (ten the sweep raises from the URL strings, four the brief
judges), the pattern table and parameter inventory derivation, and the "now"
payload the part page draws.

The Accept criteria this file pins:
  - pattern derivation (date-folder collapse, last segment -> <slug>);
  - a parameter variant with a correct canonical is not flagged;
  - the sweep raises `url-parameter-unclassified` for a key with no class and
    no canonical on its variants;
  - the brief itself constrains renames (a 301 always, never more than one URL)
    — asserted against the prompt, which is where a model-run brief carries it.
"""

from __future__ import annotations

from clauditseo import briefs, urlshape
from clauditseo.analysts.expert import (EXPERT_TOOLS, _urls_context,
                                        _url_policy_rows, conforms)
from clauditseo.anatomy import CHECK_CATEGORY
from clauditseo.crawler.types import CrawlResult, Page
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.engine.types import Tier
from clauditseo.modules import tec
from clauditseo.modules.tec import TechnicalModule
from clauditseo.persistence import repo, runs

FREE = ["url-uppercase", "url-non-ascii", "url-separator", "url-encoded-chars",
        "url-trailing-slash-mixed", "url-length", "url-depth", "url-id-only",
        "url-repeated-tokens", "url-parameter-unclassified"]
ANALYSIS = ["url-slug-not-descriptive", "url-slug-entity",
            "url-parameter-policy", "url-rename"]


def test_the_brief_loads_conforms_and_owns_its_part():
    by = briefs.by_id()
    assert by["urls"].part == "urls" and by["urls"].scope == "site"
    assert len(by["urls"].checks) == 14 and conforms("urls")
    assert EXPERT_TOOLS["urls"]["build"] is _urls_context
    assert EXPERT_TOOLS["urls"]["checks"] == [f"TEC/{c}" for c in FREE + ANALYSIS]


def test_the_ten_free_checks_are_registered_and_the_four_analysis_are_held():
    for c in FREE:
        assert c in tec.DEFAULT_SEVERITY, c
    for c in ANALYSIS:
        assert c in tec.BRIEF_ONLY_CHECKS, c
        assert c not in tec.DEFAULT_SEVERITY, c
    # The two duplicate-makers are HIGH; the four cheap ones are LOW.
    assert tec.DEFAULT_SEVERITY["url-parameter-unclassified"].value == "high"
    assert tec.DEFAULT_SEVERITY["url-trailing-slash-mixed"].value == "high"
    for c in ("url-encoded-chars", "url-length", "url-depth", "url-repeated-tokens"):
        assert tec.DEFAULT_SEVERITY[c].value == "low"


def test_every_check_is_filed_on_the_urls_part():
    for c in FREE + ANALYSIS:
        assert CHECK_CATEGORY[c] == "urls", c


def test_pattern_derivation_collapses_dates_and_the_last_segment():
    assert urlshape.derive_pattern("/blog/2024/03/15/my-post/") == "/blog/YYYY/MM/DD/<slug>/"
    # Two service pages are one template — only the last segment moves.
    assert urlshape.derive_pattern("/services/plumbing/") == "/services/<slug>/"
    assert urlshape.derive_pattern("/services/electrical/") == "/services/<slug>/"
    assert urlshape.derive_pattern("/") == "/"
    table = urlshape.pattern_table([
        "https://x.test/services/plumbing/",
        "https://x.test/services/electrical/",
        "https://x.test/blog/2024/03/15/a/",
        "https://x.test/blog/2023/12/01/b/",
    ])
    by = {r["pattern"]: r for r in table}
    assert by["/services/<slug>/"]["count"] == 2 and by["/services/<slug>/"]["depth"] == 2
    assert by["/blog/YYYY/MM/DD/<slug>/"]["count"] == 2
    assert by["/blog/YYYY/MM/DD/<slug>/"]["depth"] == 5


def _pg(url, canonical=None, links=None):
    html = "<html><head><title>t</title>"
    if canonical:
        html += f'<link rel="canonical" href="{canonical}">'
    html += "</head><body><h1>h</h1></body></html>"
    p = Page(url=url, requested_url=url, status=200, content_type="text/html", content=html)
    if links:
        p.link_details = links
    return p


def test_the_sweep_raises_the_free_checks_from_the_url_strings():
    pages = [
        _pg("https://x.test/"),
        _pg("https://x.test/services/Plumbing/"),                 # uppercase
        _pg("https://x.test/über/"),                              # non-ascii
        _pg("https://x.test/about_us/"),                          # separator
        _pg("https://x.test/blog/2024/03/15/my-first-post/"),     # depth 5
        _pg("https://x.test/p/12345"),                            # id-only
        _pg("https://x.test/services/plumbing-services/plumbing/"),  # repeated
        _pg("https://x.test/list"),
        _pg("https://x.test/list/"),                              # slash pair
    ]
    crawl = CrawlResult(start_url="https://x.test/", tier=Tier.T2, pages=pages)
    fired = {f.check_id for f in TechnicalModule()._url_checks(crawl, {"crawl": crawl, "site": None})}
    for c in ("url-uppercase", "url-non-ascii", "url-separator", "url-depth",
              "url-id-only", "url-repeated-tokens", "url-trailing-slash-mixed"):
        assert c in fired, c


def test_a_parameter_variant_with_a_correct_canonical_is_not_flagged():
    # /list?sort=asc is reached and canonicalises to /list — it is owned, so the
    # sort key does not fire. /promo?utm_source=* strips to /promo, which has no
    # canonical, so utm_source is unclassified and fires. (Accept criterion.)
    pages = [
        _pg("https://x.test/"),
        _pg("https://x.test/list"),
        _pg("https://x.test/list?sort=asc", canonical="https://x.test/list"),
        _pg("https://x.test/promo",
            links=[{"href": "https://x.test/promo?utm_source=fb"}]),
    ]
    crawl = CrawlResult(start_url="https://x.test/", tier=Tier.T2, pages=pages)
    unclassified = {f.subject for f in TechnicalModule()._url_checks(
        crawl, {"crawl": crawl, "site": None})
        if f.check_id == "url-parameter-unclassified"}
    assert "?utm_source=*" in unclassified
    assert "?sort=*" not in unclassified


def test_the_site_record_class_suppresses_the_unclassified_check():
    class _Site:
        parameter_rules = [{"key": "utm_source", "class": "tracking"}]
    pages = [_pg("https://x.test/"),
             _pg("https://x.test/promo",
                 links=[{"href": "https://x.test/promo?utm_source=fb"}])]
    crawl = CrawlResult(start_url="https://x.test/", tier=Tier.T2, pages=pages)
    fired = [f for f in TechnicalModule()._url_checks(
        crawl, {"crawl": crawl, "site": _Site()})
        if f.check_id == "url-parameter-unclassified"]
    assert fired == []


def test_the_brief_constrains_renames_to_one_url_and_a_written_301():
    # A model-run brief carries these in its prompt; the record cannot enforce
    # what a model wrote, so the constraint is pinned where it lives.
    text = (briefs.by_id()["urls"].path).read_text(encoding="utf-8")
    assert "301" in text
    assert "mass rename" in text.lower()
    assert "one row per (check, url)" in text.lower()


# --- the "now" payload and the site fields --------------------------------

def _stored_run(tmp_path, pages, **site_fields):
    conn = connect(tmp_path / "urls.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "URL Co")
    site_id = repo.create_site(conn, client, "x.test")
    if site_fields:
        repo.update_site(conn, site_id, **site_fields)
    run_id = runs.create_run(conn, site_id, ["TEC"], "T2")
    from clauditseo.crawler.evidence import snapshot
    crawl = CrawlResult(start_url="https://x.test/", tier=Tier.T2, pages=pages)
    runs.store_evidence(conn, run_id, snapshot(crawl))
    return conn, run_id


def test_the_now_payload_draws_the_two_tables_and_the_counts(tmp_path):
    pages = [
        _pg("https://x.test/"),
        _pg("https://x.test/services/plumbing/"),
        _pg("https://x.test/services/electrical/"),
        _pg("https://x.test/blog/2024/03/15/a-post/"),
        _pg("https://x.test/promo",
            links=[{"href": "https://x.test/promo?utm_source=fb"}]),
    ]
    conn, run_id = _stored_run(tmp_path, pages)
    now = runs.urls_now_payload(conn, run_id)
    assert now["urls"] == 5
    patterns = {r["pattern"] for r in now["patterns"]}
    assert "/services/<slug>/" in patterns
    assert "/blog/YYYY/MM/DD/<slug>/" in patterns
    params = {p["key"]: p for p in now["parameters"]}
    assert params["utm_source"]["class"] == "unclassified"
    assert now["unclassified"] == 1
    assert now["convention"]["scheme"] == "https"


def test_the_thresholds_round_trip_and_fall_back(tmp_path):
    conn, run_id = _stored_run(tmp_path, [_pg("https://x.test/")],
                               url_max_chars="90", max_depth="4")
    now = runs.urls_now_payload(conn, run_id)
    assert now["thresholds"]["url_max_chars"] == 90
    assert now["thresholds"]["max_depth"] == 4
    # Unset ones keep the urlshape default.
    assert now["thresholds"]["slug_max_words"] == urlshape.DEFAULT_SLUG_MAX_WORDS
    assert now["thresholds"]["rename_inlink_cap"] == urlshape.DEFAULT_RENAME_INLINK_CAP


def test_the_length_check_reads_the_site_threshold():
    long_slug = "a" * 80
    pages = [_pg("https://x.test/"), _pg(f"https://x.test/{long_slug}/")]
    crawl = CrawlResult(start_url="https://x.test/", tier=Tier.T2, pages=pages)

    class _Tight:
        url_max_chars = "40"
    fired = {f.check_id for f in TechnicalModule()._url_checks(
        crawl, {"crawl": crawl, "site": _Tight()})}
    assert "url-length" in fired

    class _Loose:
        url_max_chars = "200"
        slug_max_words = "50"
    fired = {f.check_id for f in TechnicalModule()._url_checks(
        crawl, {"crawl": crawl, "site": _Loose()})}
    assert "url-length" not in fired


def test_the_handoff_reads_the_url_policy_rows_into_indexability(tmp_path):
    conn, run_id = _stored_run(tmp_path, [_pg("https://x.test/")])
    # No urls report yet -> no handoff rows.
    assert _url_policy_rows(conn, run_id) == []
    runs.store_expert_report(conn, run_id, "urls", {
        "model": "stub", "report": "", "findings": [],
        "contract": {"status": "read", "rows": [
            {"check": "TEC/url-parameter-policy", "page": None,
             "url": "?utm_source=*", "status": "FAIL", "severity": "medium",
             "evidence": "x", "replacement": "class: tracking", "kind": "policy"}]}})
    rows = _url_policy_rows(conn, run_id)
    assert rows and "utm_source" in rows[0] and "tracking" in rows[0]
