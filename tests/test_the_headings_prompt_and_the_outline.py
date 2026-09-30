"""The Headings brief and what the engine hands it (brief v11 step AJ):
the crawl records each page's outline - level, text, whether the heading
sits in the main region, the first words after it - and how the main
region was found; both prompts load, conform, and render against a run
with no placeholder unfilled and nothing `[NOT SUPPLIED]`; the triples
come from the latest Title & description run or, absent one, the site
record, and the fallbacks are listed as assumptions; the Images part is
the Images stopgap.
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from clauditseo import ENGINE_VERSION, briefs
from clauditseo.analysts.expert import (EXPERT_TOOLS, _headings_context, _page_triples,
                                        conforms, render_prompt)
from clauditseo.crawler.evidence import snapshot
from clauditseo.crawler.types import CrawlResult, Page
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.engine.types import Site, Tier
from clauditseo.modules.pagefacts import extract_facts
from clauditseo.persistence import repo, runs

HTML = (
    "<html lang='en'><head><title>Pest control Richmond | Acme</title></head><body>"
    "<header><h2>Site navigation</h2></header>"
    "<main><h1>Pest control in Richmond</h1>"
    "<p>Acme treats homes and businesses across Richmond and the inner east, "
    "with same-week appointments and a twelve month guarantee on every job we do, "
    "so you know the problem stays solved after we leave your property.</p>"
    "<h2>How much does pest control cost in Richmond?</h2>"
    "<p>Most treatments cost between two and four hundred dollars.</p>"
    "<h4>Termites</h4><p>Inspections start at one hundred and fifty.</p></main>"
    "<footer><h2>Contact</h2></footer></body></html>"
)


def _page(html: str = HTML, url: str = "https://x.test/") -> Page:
    return Page(url=url, requested_url=url, status=200, content_type="text/html", content=html)


def test_the_parser_records_the_outline_with_region_and_following_words():
    facts = extract_facts(_page())
    assert facts.main_region == "<main>"
    levels = [(h["level"], h["in_main"]) for h in facts.outline]
    assert levels == [(2, False), (1, True), (2, True), (4, True), (2, False)]
    h1 = facts.outline[1]
    assert h1["text"] == "Pest control in Richmond"
    # Every word up to the next heading, and never more than forty.
    assert h1["next_text"].startswith("Acme treats homes and businesses") and 30 < len(h1["next_text"].split()) <= 40
    question = facts.outline[2]
    assert question["next_text"] == "Most treatments cost between two and four hundred dollars."
    # No main region at all: every heading is in the whole body.
    plain = extract_facts(_page("<html><body><h1>A</h1><p>b</p><h3>C</h3></body></html>"))
    assert plain.main_region == "whole body" and [h["in_main"] for h in plain.outline] == [False, False]
    # role=main and <article> count too, in that order of confidence.
    art = extract_facts(_page("<html><body><article><h1>A</h1></article></body></html>"))
    assert art.main_region == "<article>" and art.outline[0]["in_main"]


def test_the_snapshot_carries_the_outline_and_the_engine_says_so():
    # 0.12.0 when the outline was recorded, 0.13.0 for the image
    # inventory, 0.14.0 for the structured-data one, 0.16.0 for the raw
    # JSON-LD blocks the picture is built from, 0.17.0 for `has_post_form`
    # (brief v16h), 0.18.0 for `redirect_statuses` (item 137, F-13), 0.19.0 for
    # the per-page `perf` trace (item 141, brief v19 step BC), 0.20.0 for that
    # trace's two heads and its mobile render (brief 160 steps 1-3), 0.21.0 for
    # title-length firing at the mobile width (item 152), 0.22.0 for the SEC
    # dimension, 0.23.0 to 0.25.0 for its new collectors (item 143 step BD), 0.26.0
    # for head-divergent (item 165), 0.27.0 for the mobile parity probe (item
    # 151). The clause
    # is about the outline being *in* the snapshot at a version that says so,
    # not about which version that is - so the number moves and the point of
    # asserting it does not: a snapshot whose shape changed without the
    # version changing is what this line catches.
    assert ENGINE_VERSION == "0.27.0"
    crawl = CrawlResult(start_url="https://x.test/", tier=Tier.T2, pages=[_page()])
    rec = snapshot(crawl)["pages"][0]
    assert rec["main_region"] == "<main>"
    assert rec["outline"][1][:3] == [1, "Pest control in Richmond", True]
    assert rec["outline"][1][3].startswith("Acme treats")


def test_both_prompts_load_and_conform_and_the_stopgap_is_images():
    by = briefs.by_id()
    assert by["headings"].part == "headings" and by["headings"].scope == "site"
    assert len(by["headings"].checks) == 13 and conforms("headings")
    assert by["title-desc"].checks[3] == "ONP/title-entity-alignment" and conforms("title-desc")
    # The Images brief took the part at brief v15 step AQ.
    # Sixteen: plus `img-logo` (AU6) and `img-heavy` (AU7), less
    # `img-review-schema`, which step AS moved to Structured data.
    assert by["images"].part == "images" and len(by["images"].checks) == 16
    assert conforms("images")
    assert EXPERT_TOOLS["headings"]["build"] is _headings_context


def _site(tmp_path, **fields):
    conn = connect(tmp_path / "headings.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Outline Co")
    site_id = repo.create_site(conn, client, "x.test")
    if fields:
        repo.update_site(conn, site_id, **fields)
    return conn, site_id


def _run(conn, site_id):
    run_id = runs.create_run(conn, site_id, ["ONP"], "T2")
    crawl = CrawlResult(start_url="https://x.test/", tier=Tier.T2,
                        pages=[_page(), _page(url="https://x.test/pest-control-richmond")])
    runs.store_evidence(conn, run_id, snapshot(crawl))
    return run_id


def test_headings_renders_with_every_placeholder_filled_and_names_its_fallbacks(tmp_path):
    conn, site_id = _site(tmp_path)
    run_id = _run(conn, site_id)
    ev = runs.get_evidence(conn, run_id)
    site = Site(domain="x.test", **{k: v for k, v in repo.site_record(repo.get_site(conn, site_id)).items()
                                    if k in ("locale", "business_type", "brand", *repo.SITE_TEXT_FIELDS,
                                             *repo.SITE_JSON_FIELDS)})
    ctx = _headings_context(ev, site, conn=conn, run_id=run_id)
    prompt = render_prompt("headings", ctx)
    assert "{{" not in prompt and "[NOT SUPPLIED]" not in prompt
    assert 'h1 "Pest control in Richmond" [main] → "Acme treats' in prompt
    assert "| <main> |" in prompt
    assert "registered default severity per check: ONP/h1-missing = medium" in prompt
    assert "ONP/h1-triple-restated = FAIL high / WARN low" in prompt
    # Nothing on the record: the tokens say so, and the fallbacks are listed.
    assert "(none)" in prompt
    assumed = ctx["_ENGINE_ASSUMPTIONS"]
    assert any("page triples taken from the site record alone" in a for a in assumed), assumed
    assert any("brand not set on the site record" in a for a in assumed), assumed
    # Title & description renders against the same run without a gap.
    from clauditseo.analysts.expert import _title_desc_context
    td = render_prompt("title-desc", _title_desc_context(ev, site, conn=conn, run_id=run_id))
    assert "{{" not in td and "[NOT SUPPLIED]" not in td
    assert "| page_type |" in td and "TITLE_MIN" not in td


def test_the_triples_come_from_the_latest_title_desc_run_when_there_is_one(tmp_path):
    conn, site_id = _site(tmp_path, brand="Acme", gbp_primary_category="Pest Control Service",
                          location_pages=[{"url": "/pest-control-richmond",
                                           "location_entity": "Richmond Victoria"}])
    run_id = _run(conn, site_id)
    ev = runs.get_evidence(conn, run_id)
    site = Site(domain="x.test", brand="Acme", gbp_primary_category="Pest Control Service",
                location_pages=[{"url": "/pest-control-richmond", "location_entity": "Richmond Victoria"}])
    records = [p for p in ev["pages"] if p.get("status") == 200]
    table, why = _page_triples(conn, site, records, "https://x.test/")
    assert why and "site record alone" in why
    assert "| /pest-control-richmond | location | Acme | Pest Control Service | Richmond Victoria |" in table
    # A stored Title & description run names page types and a service.
    runs.store_expert_report(conn, run_id, "title-desc", {
        "model": "stub", "report": "", "findings": [],
        "contract": {"status": "read", "rows": [
            {"check": "ONP/title-entity-alignment", "page": "https://x.test/", "status": "FAIL",
             "severity": "medium", "evidence": "x", "replacement": "Termite inspections - Acme",
             "extra": {"page_type": "service"}}]}})
    table, why = _page_triples(conn, site, records, "https://x.test/")
    assert why is None
    assert "| / | service | Acme | Termite inspections | n/a |" in table
