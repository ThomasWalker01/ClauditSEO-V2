"""An HTML page served at /llms.txt is no llms.txt, and a string in it that
urlsplit cannot parse does not fail the audit (27 Oct).

A WordPress site answered `/llms.txt` with its own home page and a 200. The
crawl stored that page as the file, `llms-txt-stale` read URLs out of its
JSON-LD, one of them carried an unbalanced `[`, and `urlsplit` raised
"Invalid IPv6 URL" -- which failed the whole audit, twice, with that text as
its only explanation.
"""
from __future__ import annotations

from clauditseo.analysts.ai_surface import llms_txt_text
from clauditseo.crawler.types import CrawlResult, Page, served_html
from clauditseo.engine.types import Site, Tier
from clauditseo.modules.ais import AiSurfaceModule

HOME = "https://shop.example.test/"
HTML = ('<!doctype html>\n<html><head><script type="application/ld+json">'
        '{"@context":"https://schema.org","@graph":[{"@type":"Organization",'
        '"url":"https://shop.example.test/"}]}</script></head><body></body></html>')


def _crawl(**kw) -> CrawlResult:
    page = Page(url=HOME, requested_url=HOME, status=200, content_type="text/html",
                content="<html></html>")
    return CrawlResult(start_url=HOME, tier=Tier.T2, pages=[page], **kw)


def _run(crawl: CrawlResult):
    site = Site(domain="shop.example.test", locale="en-AU", business_type="ecommerce",
                target_market=None)
    return AiSurfaceModule().run(crawl.pages, Tier.T2, {"crawl": crawl, "site": site})


def test_an_html_body_is_told_by_its_header_or_its_first_bytes():
    assert served_html("text/html; charset=UTF-8", "# Shop\n")
    assert served_html("", "  \n<!DOCTYPE html><html>")
    assert served_html(None, "<html lang=en>")
    assert not served_html("text/plain", "# Shop\n> A made-up shop\n")
    assert not served_html(None, None)


def test_an_html_page_at_llms_txt_is_reported_missing_not_read():
    got = _run(_crawl(llms_txt_status=200, llms_txt_served_html=True))
    missing = [f for f in got if f.check_id == "llms-txt-missing"]
    assert len(missing) == 1 and "HTML page" in missing[0].summary
    assert missing[0].evidence == {"status": 200, "served": "html"}
    assert not [f for f in got if f.check_id == "llms-txt-stale"]


def test_an_unparseable_url_in_the_body_does_not_fail_the_audit():
    # The stored shape of a run crawled before the HTML test existed.
    got = _run(_crawl(llms_txt_status=200, llms_txt=HTML + "\nhttps://x[y/"))
    assert all(f.check_id != "llms-txt-missing" for f in got)


def test_the_ai_surface_brief_is_told_the_file_is_absent():
    said = llms_txt_text({"llms_txt_status": 200, "llms_txt_served_html": True})
    assert said.startswith("absent") and "HTML page" in said
    # A run stored before the flag existed: the body itself says so.
    assert llms_txt_text({"llms_txt_status": 200, "llms_txt": HTML}).startswith("absent")
    assert "```markdown" in llms_txt_text({"llms_txt_status": 200, "llms_txt": "# Shop\n"})
