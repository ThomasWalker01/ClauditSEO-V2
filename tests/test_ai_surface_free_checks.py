"""The AI surface's free checks (item 145, brief v22 step BG).

`ai-surface.md` names these as the automatic checks' rows: directives stated
as facts, differences measured for named UA strings, the render share, a
stale llms.txt, the entity's machine resolution, record entities no page
names, and the one row that says what a crawl cannot observe. The prompt
reads them; it may not introduce them.
"""

from __future__ import annotations

import json

import clauditseo.modules  # noqa: F401  (register dimensions)
from clauditseo.crawler.parity import document
from clauditseo.crawler.types import CrawlResult, Page
from clauditseo.engine.types import Severity, Site, Tier
from clauditseo.modules.ais import UNMEASURED, AiSurfaceModule

BASE = "https://site.test"


def _page(path, body, status=200, headers=None, requested=None):
    return Page(url=BASE + path, requested_url=BASE + (requested or path), status=status,
                content=body, content_type="text/html; charset=utf-8", headers=headers or {})


def _html(title, h1, body="", head=""):
    return (f"<html><head><title>{title}</title>{head}</head><body><h1>{h1}</h1>"
            f"<main><p>{body}</p></main></body></html>")


def _run(crawl, site=None, **context):
    return AiSurfaceModule().run(crawl.pages, Tier.T2,
                                 {"crawl": crawl, "site": site or Site(domain="site.test"), **context})


def _by(found, check):
    return [f for f in found if f.check_id == check]


def test_the_unmeasured_row_is_always_emitted_verbatim_and_unscored():
    from clauditseo.engine import scoring
    found = _run(CrawlResult(start_url=BASE + "/", tier=Tier.T2))
    rows = _by(found, "ai-experience-unmeasured")
    assert len(rows) == 1 and rows[0].summary == UNMEASURED
    assert rows[0].severity is Severity.INFO
    assert scoring.subscore("AIS", rows, 1.0, {}).score == scoring.subscore("AIS", [], 1.0, {}).score


def test_an_ai_agent_robots_txt_says_nothing_to_is_unstated_with_its_class():
    robots = "User-agent: *\nAllow: /\n\nUser-agent: GPTBot\nDisallow: /\n\nUser-agent: ClaudeBot\nAllow: /\n"
    crawl = CrawlResult(start_url=BASE + "/", tier=Tier.T2, robots_txt=robots, robots_status=200)
    row, = _by(_run(crawl), "ai-crawler-allowed-unstated")
    named = {a["agent"] for a in row.evidence["agents"]}
    assert "GPTBot" not in named and "ClaudeBot" not in named, "both are stated, one each way"
    assert "OAI-SearchBot" in named and "Googlebot" not in named
    assert row.severity is Severity.INFO
    assert {"agent": "CCBot", "class": "dataset"} in row.evidence["agents"]


def test_noai_in_meta_or_header_is_a_directive_per_page():
    crawl = CrawlResult(start_url=BASE + "/", tier=Tier.T2)
    crawl.pages = [_page("/", _html("Home", "Home", head='<meta name="robots" content="noai, noimageai">')),
                   _page("/h", _html("H", "H"), headers={"x-robots-tag": "noai"}),
                   _page("/ok", _html("Ok", "Ok"))]
    rows = {f.subject: f.evidence["tokens"] for f in _by(_run(crawl), "noai-meta")}
    assert rows == {"/": ["noai", "noimageai"], "/h": ["noai"]}


def test_a_page_whose_text_arrives_by_script_reports_its_share():
    crawl = CrawlResult(start_url=BASE + "/", tier=Tier.T2)
    crawl.pages = [_page("/", _html("Home", "Home", "word " * 30)),
                   _page("/full", _html("Full", "Full", "word " * 300))]
    blocks = {BASE + "/": [{"words": 400}], BASE + "/full": [{"words": 310}]}
    rows = _by(_run(crawl, text_blocks=blocks, rendered_coverage={"rendered": 2, "pages": 2}),
               "content-behind-js")
    assert [r.subject for r in rows] == ["/"]
    assert rows[0].severity is Severity.HIGH and rows[0].evidence["share"] < 0.5
    assert "2 of 2 pages" in rows[0].summary


def test_an_llms_txt_url_that_redirects_404s_or_was_not_crawled_is_stale():
    crawl = CrawlResult(start_url=BASE + "/", tier=Tier.T2, llms_txt_status=200,
                        llms_txt=f"# Site\n## Pages\n- [Home]({BASE}/): home\n"
                                 f"- [Old]({BASE}/old): moved\n- [Gone]({BASE}/gone): gone\n"
                                 f"- [Never]({BASE}/never): never\n- [Elsewhere](https://other.test/x): x\n")
    crawl.pages = [_page("/", _html("Home", "Home")),
                   _page("/new", _html("New", "New"), requested="/old"),
                   _page("/gone", "", status=404)]
    row, = _by(_run(crawl), "llms-txt-stale")
    reasons = {s["url"].removeprefix(BASE): s["reason"] for s in row.evidence["stale"]}
    assert reasons == {"/old": f"redirects to {BASE}/new", "/gone": "status 404",
                       "/never": "not in the crawl"}


def _home_with(jsonld):
    crawl = CrawlResult(start_url=BASE + "/", tier=Tier.T2)
    head = f'<script type="application/ld+json">{json.dumps(jsonld)}</script>'
    crawl.pages = [_page("/", _html("Home", "Home", head=head))]
    return crawl


def test_an_entity_with_no_id_or_no_recorded_same_as_is_unresolvable():
    site = Site(domain="site.test", sameas_sources=["https://www.linkedin.com/company/site"])
    no_id = _by(_run(_home_with({"@context": "https://schema.org", "@type": "LocalBusiness",
                                 "name": "Site"}), site), "entity-unresolvable")
    assert no_id and "no @id" in no_id[0].summary
    wrong_pin = _by(_run(_home_with({"@context": "https://schema.org", "@type": "LocalBusiness",
                                     "@id": BASE + "/#org", "name": "Site",
                                     "sameAs": ["https://facebook.com/site"]}), site),
                    "entity-unresolvable")
    assert wrong_pin and "sameAs pins none" in wrong_pin[0].summary
    resolved = _run(_home_with({"@context": "https://schema.org", "@type": "LocalBusiness",
                                "@id": BASE + "/#org", "name": "Site",
                                "sameAs": ["https://linkedin.com/company/site/"]}), site)
    assert not _by(resolved, "entity-unresolvable")


def test_a_record_entity_no_page_names_at_its_top_is_unnamed_by_contents_test():
    from clauditseo.modules.cnt import ContentModule
    site = Site(domain="site.test", sub_services=[{"name": "Bridging finance", "url": BASE + "/bridging"},
                                                  {"name": "Invoice finance", "url": BASE + "/invoice"}])
    crawl = CrawlResult(start_url=BASE + "/", tier=Tier.T2)
    crawl.pages = [_page("/", _html("Home", "Home")),
                   _page("/bridging", _html("Bridging finance", "Bridging finance"))]
    unnamed = [f.evidence["entity"] for f in _by(_run(crawl, site), "entity-unnamed")]
    assert unnamed == ["Invoice finance"]
    # One test, two readers: Content's page verdict sees the same entity at
    # the top of /bridging and nothing about invoices anywhere.
    verdicts = [f for f in ContentModule().run(crawl.pages, Tier.T2, {"crawl": crawl, "site": site})
                if f.check_id == "entity-page-verdict"]
    assert any("Bridging finance" in (v.evidence.get("entities") or []) for v in verdicts)
    assert not any("Invoice finance" in (v.evidence.get("entities") or []) for v in verdicts)


def test_an_ai_agent_served_a_different_document_is_ua_sensitive_and_a_refusal_is_not():
    crawl = CrawlResult(start_url=BASE + "/", tier=Tier.T2)
    home = _page("/", _html("Home", "Home", "Real words about the service. " * 40))
    crawl.pages = [home]
    # Lighter by a third: a served difference, not a stub (a body under half
    # the crawl's is an edge block, and is edge-blocks-ai-ua's).
    lighter = _page("/", _html("Home", "Home", "Real words about the service. " * 27))
    refused = Page(url=BASE + "/", requested_url=BASE + "/", status=403, content="", headers={})
    crawl.ua_matrix = [
        {"agent": "PerplexityBot", "agent_class": "index", "sent": True, "robots": "allow",
         "home_status": 200, "probe_status": [], "home_body_len": len(lighter.content),
         "headers": {}, "docs": {BASE + "/": document(lighter)}},
        {"agent": "ClaudeBot", "agent_class": "training", "sent": True, "robots": "allow",
         "home_status": 403, "probe_status": [], "home_body_len": 0,
         "headers": {"server": "cloudflare"}, "docs": {BASE + "/": document(refused)}},
        {"agent": "Googlebot", "agent_class": "search", "sent": True, "robots": "allow",
         "home_status": 200, "probe_status": [], "home_body_len": len(lighter.content),
         "headers": {}, "docs": {BASE + "/": document(lighter)}},
    ]
    found = _run(crawl)
    sensitive = [f.evidence["agent"] for f in _by(found, "ua-sensitive")]
    assert sensitive == ["PerplexityBot"], "a refusal is edge-blocks-ai-ua's; Googlebot is bot-parity's"
    row = _by(found, "ua-sensitive")[0]
    assert "cloaking" not in row.summary.lower() and row.severity is Severity.HIGH
    assert _by(found, "edge-blocks-ai-ua")[0].evidence["agent"] == "ClaudeBot"


def test_the_matrix_keeps_a_document_per_response():
    from tests.test_ua_matrix import FAST, _UAServer
    from clauditseo.crawler.crawl import crawl
    with _UAServer() as s:
        cr = crawl(s.base + "/", Tier.T2, budget=FAST, ua_matrix=True)
    row = next(r for r in cr.ua_matrix if r["agent"] == "PerplexityBot")
    assert set(row["docs"]) == {s.base + "/", *[u for u in row["docs"] if u != s.base + "/"]}
    assert row["docs"][s.base + "/"]["title"] == "UA Matrix Fixture Home"
    assert "content" not in json.dumps(row["docs"]), "no body travels in the evidence"


def test_nested_rendered_blocks_count_their_words_once():
    """twenty22's first run: a nav `li` block carries its links' words and each
    link is a block too. Summed, a server-rendered page read as 41% initial."""
    from clauditseo.modules.pagefacts import rendered_words
    blocks = [{"tag": "li", "words": 120, "rect": {"x": 0, "y": 0, "w": 300, "h": 400}},
              {"tag": "a", "words": 40, "rect": {"x": 10, "y": 10, "w": 100, "h": 20}},
              {"tag": "a", "words": 80, "rect": {"x": 10, "y": 40, "w": 100, "h": 20}},
              {"tag": "p", "words": 200, "rect": {"x": 400, "y": 0, "w": 300, "h": 200}}]
    assert rendered_words(blocks) == 320
    crawl = CrawlResult(start_url=BASE + "/", tier=Tier.T2)
    crawl.pages = [_page("/", _html("Home", "Home", "word " * 300))]
    found = _run(crawl, text_blocks={BASE + "/": blocks})
    assert not _by(found, "content-behind-js"), "300 of 320 words are in the initial HTML"


def test_an_entity_with_no_sameas_is_unresolvable_whatever_the_record_says():
    row, = _by(_run(_home_with({"@context": "https://schema.org", "@type": "Organization",
                                "@id": BASE + "/#organization", "name": "Site"})), "entity-unresolvable")
    assert row.severity is Severity.HIGH and "sameAs pins nothing" in row.summary
    assert "sameas_sources" in row.recommendation
    assert "not_assessable" not in row.evidence


def test_an_entity_with_pins_and_an_empty_record_is_not_assessed_not_passed(tmp_path):
    from clauditseo.crawler.evidence import snapshot
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.persistence import repo, runs
    crawl = _home_with({"@context": "https://schema.org", "@type": "Organization",
                        "@id": BASE + "/#organization", "name": "Site",
                        "sameAs": ["https://www.linkedin.com/company/site"]})
    assert not _by(_run(crawl), "entity-unresolvable")
    conn = connect(tmp_path / "n.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site_id = repo.create_site(conn, repo.create_client(conn, op, "T"), "site.test")
    run_id = runs.create_run(conn, site_id, ["AIS"], "T2")
    runs.store_evidence(conn, run_id, snapshot(crawl))
    checks = {"ai-surface": ["AIS/entity-unresolvable"]}
    reason = runs.not_assessed_payload(conn, run_id, checks_by_part=checks)["ai-surface"]["AIS/entity-unresolvable"]
    assert "sameas_sources on the site record is empty" in reason
    repo.update_site(conn, site_id, sameas_sources=["https://www.linkedin.com/company/site"])
    assert "AIS/entity-unresolvable" not in runs.not_assessed_payload(
        conn, run_id, checks_by_part=checks).get("ai-surface", {})
    conn.close()
