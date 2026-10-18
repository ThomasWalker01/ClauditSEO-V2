"""`CNT/entity-page-verdict` — what one page is about (item 136q commit 6 /
136o Tab 4).

Three engine-computed states from the record's own entities: about one entity
(PASS), about N and owns K (FAIL), about none (FAIL). INFO and unscored,
because the fault is already scored by `topic-drift`, Coverage's `gap` rows
and Cannibalisation's clusters - this states what the page IS ABOUT, and its
`contested[]` names the same pairs so the two cannot drift.
"""

from __future__ import annotations

from clauditseo.engine.types import Site
from clauditseo.modules.cnt import ContentModule
from clauditseo.modules.pagefacts import PageFacts

SITE = Site(domain="x.test", brand="Acme", sub_services=[
    {"name": "Bridging finance", "url": "https://x.test/bridging"},
    {"name": "Equipment finance", "url": "https://x.test/equipment"}])


def _facts(path, title, headings):
    f = PageFacts(url="https://x.test" + path, path=path, title=title)
    f.headings = headings
    return f


def _ev(path, title, headings, site=SITE):
    v = ContentModule()._entity_page_verdict(_facts(path, title, headings), site)
    return v.evidence


def test_one_entity_in_url_title_and_h1_is_about_one():
    ev = _ev("/bridging", "Bridging finance | Acme", [(1, "Bridging finance")])
    assert ev["status"] == "PASS", ev
    assert ev["verdict"].startswith("About one entity"), ev
    assert ev["owns"] == 1


def test_h2s_naming_several_services_is_about_several():
    """Coverage's 'home page doing every service'. The H1/H2s name more than
    one service, so the verdict is 'about N', and it FAILS."""
    ev = _ev("/", "Home", [(1, "Our services"),
                           (2, "Bridging finance"), (2, "Equipment finance")])
    assert ev["status"] == "FAIL"
    assert "About 2 entities" in ev["verdict"], ev
    assert set(ev["contested"]) == {"Bridging finance", "Equipment finance"}


def test_no_entity_in_url_title_h1_is_about_none_and_points_at_topic_drift():
    ev = _ev("/blog/a-post", "A blog post about nothing named", [(1, "A post")])
    assert ev["status"] == "FAIL"
    assert ev["verdict"] == "About none", ev
    v = ContentModule()._entity_page_verdict(
        _facts("/blog/a-post", "A blog post", [(1, "A post")]), SITE)
    assert "topic-drift" in v.recommendation or "one entity" in v.recommendation


def test_no_site_record_entities_is_not_assessable():
    """A record with no entities cannot answer, so the verdict is
    not_assessable and never 'about none' - which would report the empty
    record as the page's fault."""
    ev = _ev("/x", "Some title", [(1, "A heading")], site=Site(domain="x.test"))
    assert ev["verdict"] == "not_assessable", ev
    assert "needs" in ev


def test_the_check_is_free_info_and_unscored():
    from clauditseo.anatomy import CHECK_CATEGORY
    from clauditseo.checks import check_cost
    from clauditseo.engine.types import Severity
    from clauditseo.modules.cnt import DEFAULT_SEVERITY

    assert check_cost("CNT/entity-page-verdict") == "free"
    assert CHECK_CATEGORY["entity-page-verdict"] == "content"
    # INFO weighs 0.0 in scoring, so it is unscored by construction.
    assert DEFAULT_SEVERITY["entity-page-verdict"] == Severity.INFO


def test_it_emits_one_row_per_page():
    """Not one per entity: the verdict is about the page."""
    from clauditseo.crawler.types import CrawlResult, Page, Tier

    def page(path, title, h1):
        return Page(url="https://x.test" + path, requested_url="https://x.test" + path,
                    status=200, content_type="text/html",
                    content=f"<html><head><title>{title}</title></head>"
                            f"<body><main><h1>{h1}</h1><p>words here in body</p>"
                            "</main></body></html>")
    crawl = CrawlResult(start_url="https://x.test/", tier=Tier.T2,
                        pages=[page("/bridging", "Bridging finance", "Bridging finance"),
                               page("/about", "About Acme", "About")])
    rows = [f for f in ContentModule().run(list(crawl.pages), Tier.T2,
                                           {"crawl": crawl, "site": SITE})
            if f.check_id == "entity-page-verdict"]
    assert len(rows) == 2, [r.subject for r in rows]


def test_the_page_verdict_reader_returns_the_finding(tmp_path):
    """Tab 4 page scope reads the verdict from the finding the check emitted,
    not a recomputation - one definition of what a page is about."""
    import json
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.persistence import repo, runs

    conn = connect(tmp_path / "c.db"); migrate(conn)
    op = repo.ensure_default_operator(conn)
    site_id = repo.create_site(conn, repo.create_client(conn, op, "C"), "x.test")
    run_id = runs.create_run(conn, site_id, ["CNT"], "T2")
    conn.execute(
        "INSERT INTO findings (id, run_id, dimension, check_id, severity, source,"
        " summary, affected_urls, fingerprint, created_at, evidence)"
        " VALUES (?, ?, 'CNT', 'entity-page-verdict', 'info', 'deterministic',"
        " 's', ?, 'v1', ?, ?)",
        (repo.create_id(), run_id, json.dumps(["https://x.test/bridging"]),
         repo.now_iso(),
         json.dumps({"verdict": "About one entity — Bridging finance",
                     "status": "PASS", "entities": ["Bridging finance"],
                     "about": 1, "owns": 1, "contested": []})))
    conn.commit()
    # Read by a differently-spelled URL (trailing slash) - resolved by path.
    pv = runs.page_entity_verdict(conn, run_id, "https://x.test/bridging/")
    assert pv and pv["status"] == "PASS"
    assert pv["verdict"].startswith("About one entity")
    assert runs.page_entity_verdict(conn, run_id, "https://x.test/other") is None
    conn.close()
