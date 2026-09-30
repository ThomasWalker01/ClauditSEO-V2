"""The Images brief, its checks and the inventory it reads (brief v15
step AQ).

The fifteen check ids are registered at the severities the prompt states;
A held-only check can only ever be held, and a row for one anywhere but
`not_assessable` is dropped with a reason. The sweep emits the delivery
checks the stored inventory can answer and states its basis on each one;
the ones needing a measurement this crawl does not take are the brief's.
The inventory carries what an image's own markup says - the region, the
link around it, the caption, the words beside it - and marks what nobody
measured as such rather than as absent. The prompt loads, conforms and
renders with nothing unfilled, and the two briefs it replaces are gone.
"""

from __future__ import annotations

import json
import re

import httpx
import pytest

from clauditseo import briefs
from clauditseo.analysts import contract
from clauditseo.analysts.expert import (EXPERT_TOOLS, IMAGES_CHECKS, NOT_MEASURED,
                                        _images_context, conforms, render_prompt)
from clauditseo.checks import brief_only_checks, default_severities
from clauditseo.crawler.evidence import snapshot
from clauditseo.crawler.types import CrawlResult, Page
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.engine.types import Site, Tier
from clauditseo.modules.onp import HELD_ONLY_CHECKS, OnPageModule
from clauditseo.modules.pagefacts import extract_facts
from clauditseo.persistence import repo, runs
from tests.test_triage_ranks_the_section_rail import _serve

BASE = "https://pix.fixture"
HOME = BASE + "/"

HTML = (
    "<html lang='en'><head><title>Pix</title></head><body>"
    "<header><img src='logo.svg' alt='Pix home' width='32' height='32'></header>"
    "<main>"
    "<img src='IMG_4821.jpg' loading='lazy'>"
    "<p>Pix runs events across the country for companies of every size.</p>"
    "<figure><img src='team-photo.png' width='800' height='600'>"
    "<figcaption>The team at the 2025 gala</figcaption></figure>"
    "<a href='/events'><img src='card-a.png' alt='a' width='400' height='300'></a>"
    "<a href='/events'><img src='card-b.png' alt='b' width='400' height='300'></a>"
    "</main></body></html>"
)


def _facts():
    return extract_facts(Page(url=HOME, requested_url=HOME, status=200,
                              content_type="text/html", content=HTML))


# --- the registry -----------------------------------------------------------

def test_the_sixteen_checks_are_registered_at_the_severities_the_prompt_states():
    d = default_severities()
    assert d["ONP/img-lcp-lazy"] == "high" and d["ONP/img-weight-budget"] == "high"
    for c in ("img-dimensions-missing", "img-oversized", "img-no-srcset", "img-sizes-wrong",
              "img-legacy-format", "img-text-in-image", "img-duplicate-links",
              "img-link-alt-not-destination", "img-alt-missing"):
        assert d[f"ONP/{c}"] == "medium", c
    for c in ("img-alt-decorative-nonempty", "img-filename-generic", "img-sitemap-missing"):
        assert d[f"ONP/{c}"] == "low", c
    # Empty since brief v16 step AS took `img-review-schema` to the
    # Structured data part, and the mechanism stays: what it does - stand a
    # card for a check that can never be raised, and keep it out of the
    # line saying which checks pass - is a property of held-only checks
    # rather than of that one.
    assert HELD_ONLY_CHECKS == ()
    assert set(IMAGES_CHECKS) == {c.split("/")[1] for c in EXPERT_TOOLS["images"]["checks"]}
    # Sixteen: fifteen at brief v15, plus `img-logo` at v16 step AU6 and
    # `img-heavy` at AU7, less `img-review-schema`, which step AS moved to
    # the Structured data part as `schema-review-unsupported`. The number
    # is pinned rather than counted from the prompt, because the prompt and
    # the registry agreeing with each other proves nothing if both were
    # edited in one pass without anybody deciding to move a check.
    assert len(IMAGES_CHECKS) == 16
    # The ones no sweep can compute here are registered as the brief's.
    brief_only = {c.split("/")[1] for c in brief_only_checks()}
    assert {"img-oversized", "img-weight-budget", "img-sizes-wrong", "img-text-in-image",
            "img-link-alt-not-destination", "img-sitemap-missing"} <= brief_only


def test_a_held_only_check_is_dropped_wherever_else_it_is_named(monkeypatch):
    """The mechanism, driven through the register rather than through
    whichever check happens to be in it.

    `HELD_ONLY` is empty since brief v16 step AS retired its one member, so
    this clause names its own. That is not a weaker test: what has to hold
    is that a row for a check in the register is dropped with a reason
    wherever it appears outside `not_assessable`, and a clause tied to one
    check id would have gone green-by-vacancy the day that id left - which
    is exactly what an empty register does to a test that reads it.
    """
    monkeypatch.setattr(contract, "HELD_ONLY", ("img-review-schema",))
    checks = ["ONP/img-review-schema", "ONP/img-lcp-lazy", "ONP/img-legacy-format"]
    block = json.dumps({"rows": [
        {"check": "ONP/img-review-schema", "page": "/", "image": "stars.jpg",
         "status": "FAIL", "severity": "LOW", "evidence": "x", "replacement": "y"},
        {"check": "ONP/img-lcp-lazy", "page": "/", "image": "hero.jpg", "status": "FAIL",
         "severity": "HIGH", "evidence": "x", "replacement": "<img>",
         "also_resolves": ["ONP/img-legacy-format"], "kind": "template",
         "group": "template:hero"}],
        "not_assessable": [{"check": "ONP/img-review-schema", "page": "/",
                            "image": "stars.jpg", "needs": "review provenance"}]})
    got = contract.parse("```json\n" + block + "\n```\n", checks, [HOME],
                         defaults=default_severities())
    assert [r.check for r in got.rows] == ["ONP/img-lcp-lazy"]
    assert got.dropped[0]["reason"].startswith("ONP/img-review-schema can only be held")
    # The row's own fields survive the parse.
    row = got.rows[0]
    assert row.image == "hero.jpg" and row.kind == "template" and row.group == "template:hero"
    assert row.also_resolves == ["ONP/img-legacy-format"] and row.severity == "high"
    # It is still held, which is the only place it may be named.
    assert got.not_assessable[0]["needs"] == "review provenance"


def test_a_row_cannot_claim_to_close_a_check_the_brief_may_not_emit():
    block = json.dumps({"rows": [
        {"check": "ONP/img-lcp-lazy", "page": "/", "image": "hero.jpg", "status": "FAIL",
         "severity": "HIGH", "evidence": "x", "replacement": "<img>",
         "also_resolves": ["ONP/title-length"]}]})
    got = contract.parse("```json\n" + block + "\n```\n", ["ONP/img-lcp-lazy"], [HOME],
                         defaults=default_severities())
    assert not got.rows and "also_resolves names ONP/title-length" in got.dropped[0]["reason"]


# --- the inventory and the sweep --------------------------------------------

def test_the_inventory_carries_what_the_markup_says_about_each_image():
    inventory = [i for i in _facts().image_details if i["tag"] == "img"]
    by = {i["src"]: i for i in inventory}
    assert by["logo.svg"]["region"] == "header" and not by["logo.svg"]["in_main"]
    assert by["IMG_4821.jpg"]["region"] == "main" and by["IMG_4821.jpg"]["loading"] == "lazy"
    assert by["IMG_4821.jpg"]["adjacent_text"].startswith("Pix runs events")
    assert by["team-photo.png"]["caption"] == "The team at the 2025 gala"
    assert by["card-a.png"]["linked_to"] == "/events"
    # The crawl stores it, so the brief can read it.
    crawl = CrawlResult(start_url=HOME, tier=Tier.T2, pages=[
        Page(url=HOME, requested_url=HOME, status=200, content_type="text/html", content=HTML)])
    stored = snapshot(crawl)["pages"][0]["image_inventory"]
    assert [i["src"] for i in stored] == [i["src"] for i in inventory]


def test_the_sweep_emits_the_checks_the_inventory_can_answer_and_says_its_basis():
    found = OnPageModule()._image_checks([_facts()])
    by_check: dict[str, list] = {}
    for f in found:
        by_check.setdefault(f.check_id, []).append(f)
    assert set(by_check) == {"img-dimensions-missing", "img-legacy-format", "img-no-srcset",
                             "img-filename-generic", "img-alt-decorative-nonempty",
                             "img-lcp-lazy", "img-duplicate-links", "img-logo"}
    # Every row names the image it is about and how it was judged.
    for f in found:
        assert f.evidence.get("basis"), f.check_id
        # A `content-first` row is the exception, and it is the only one:
        # what it reports is an image that is not there, so there is no
        # image for it to name (brief v16 step AU6). Every other row names
        # the image or the link it is about.
        assert (f.evidence.get("image") or f.evidence.get("href")
                or f.evidence.get("kind") == "content-first"), f.check_id
    # The main region's first image, loaded lazily, and only that one.
    lcp = by_check["img-lcp-lazy"]
    assert len(lcp) == 1 and lcp[0].evidence["image"] == "IMG_4821.jpg"
    assert "not measured" in lcp[0].evidence["basis"]
    # The icon in the header, not the photograph in the article.
    dec = by_check["img-alt-decorative-nonempty"]
    assert [d.evidence["image"] for d in dec] == ["logo.svg"]
    # This page declares a header and the only image in it is 32x32, which
    # is an icon by the same threshold every other check here uses. So AU6
    # finds no logo, and says so rather than promoting the icon: the row is
    # `content-first`, because what is missing is a logo rather than an
    # attribute on one. The basis names what was looked at, which is the
    # difference between "your site has no logo" and "I could not find
    # one" - a page that declares no header at all raises nothing, and
    # `test_a_page_with_no_header_is_not_told_it_has_no_logo` is that half.
    logo = by_check["img-logo"]
    assert len(logo) == 1 and logo[0].evidence["image"] is None
    assert logo[0].evidence["kind"] == "content-first"
    assert "every image in it is an icon" in logo[0].evidence["basis"]
    # Two cards linking to one page is one link's work done twice.
    dup = by_check["img-duplicate-links"]
    assert len(dup) == 1 and dup[0].evidence["href"] == "/events" and dup[0].evidence["images"] == 2
    # A vector icon is not asked for a srcset, and a photograph is.
    # One finding for the page naming all four (item 246, the operator's
    # ruling a): one identity per check per page, every image listed.
    srcset = by_check["img-no-srcset"]
    assert len(srcset) == 1 and set(srcset[0].evidence["images"]) == {
        "IMG_4821.jpg", "team-photo.png", "card-a.png", "card-b.png"}


def test_a_page_with_no_header_is_told_that_rather_than_told_it_has_no_logo():
    """AU6 raises `img-logo` where a header was read and no logo was in it.

    A page that declares no header region is a different case. `html.parser`
    builds no tree, so a masthead in an unlabelled `<div>` is invisible to
    it - and "your site has no logo" would fire on every page of every site
    that styles its header without a landmark, which is many of them, and
    every one of those findings would be false.

    AU6 left that case silent. The operator's ruling on 2026-09-06 is that
    silence reads as "checked, fine", which is worse than either sentence: a
    client whose logo row is simply missing learns nothing. So the engine
    says what it knows - that it could not find a header to look in - as a
    coverage note, which is the shape for "could not measure this, and here
    is why". Not a finding: the site has markup this parser cannot read,
    not a problem with its logo.
    """
    html = ("<html><body><div class='top'><img src='brand.svg' alt='Brand'></div>"
            "<main><img src='pix-team.avif' alt='The team' width='1200' height='800' "
            "srcset='pix-team-800.avif 800w' sizes='100vw'></main></body></html>")
    facts = extract_facts(Page(url=HOME, requested_url=HOME, status=200,
                               content_type="text/html", content=html))
    raised = [f for f in OnPageModule()._image_checks([facts])]
    assert [f.check_id for f in raised if f.check_id == "img-logo"] == []
    note = next((f for f in raised if f.check_id == "img-logo-not-assessed"), None)
    assert note is not None, [f.check_id for f in raised]
    assert note.severity.value == "info", note.severity
    assert "header landmark" in note.summary, note.summary
    assert "<header>" in note.recommendation, note.recommendation


def test_a_page_whose_images_are_all_in_order_raises_nothing():
    clean = ("<html><body><main><img src='pix-team-melbourne.avif' alt='The team' "
             "width='1200' height='800' srcset='pix-team-800.avif 800w' sizes='100vw'>"
             "</main></body></html>")
    facts = extract_facts(Page(url=HOME, requested_url=HOME, status=200,
                               content_type="text/html", content=clean))
    # The note is expected and is not about this page's images: a fixture
    # with no header landmark is told so once (operator, 2026-09-06).
    assert [f.check_id for f in OnPageModule()._image_checks([facts])
            if f.check_id != "img-logo-not-assessed"] == []


# --- the prompt and what it replaced ----------------------------------------

def test_the_prompt_loads_conforms_and_the_two_it_replaces_are_gone():
    by = briefs.by_id()
    assert by["images"].part == "images" and by["images"].scope == "site"
    assert len(by["images"].checks) == 16 and conforms("images")
    assert "onpage-hygiene" not in by and "image-optimisation" not in by
    assert "onpage-hygiene" not in EXPERT_TOOLS and "image-optimisation" not in EXPERT_TOOLS
    from pathlib import Path
    prompts = Path(__file__).resolve().parents[1] / "clauditseo" / "prompts"
    assert (prompts / "images.md").is_file()
    assert not (prompts / "onpage-hygiene.md").exists()
    assert not (prompts / "image-optimisation.md").exists()


def _site(tmp_path, **fields):
    conn = connect(tmp_path / "pix.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Pix Co")
    site_id = repo.create_site(conn, client, "pix.fixture")
    if fields:
        repo.update_site(conn, site_id, **fields)
    return conn, site_id


def test_the_prompt_renders_with_nothing_unfilled_and_names_what_was_not_measured(tmp_path):
    conn, site_id = _site(tmp_path)
    run_id = runs.create_run(conn, site_id, ["ONP"], "T2")
    crawl = CrawlResult(start_url=HOME, tier=Tier.T2, pages=[
        Page(url=HOME, requested_url=HOME, status=200, content_type="text/html", content=HTML)])
    runs.store_evidence(conn, run_id, snapshot(crawl))
    ev = runs.get_evidence(conn, run_id)
    ctx = _images_context(ev, Site(domain="pix.fixture"), conn=conn, run_id=run_id)
    prompt = render_prompt("images", ctx)
    assert "{{" not in prompt and "[NOT SUPPLIED]" not in prompt
    # The inventory is in it, and what nobody measured says so.
    assert "IMG_4821.jpg" in prompt and NOT_MEASURED in prompt
    assert "| region |" in prompt and "| linked_to |" in prompt
    assumed = ctx["_ENGINE_ASSUMPTIONS"]
    assert any("was not observed on this run" in a for a in assumed), assumed
    assert any("breakpoints not set" in a for a in assumed), assumed
    assert any("platform not set" in a for a in assumed), assumed
    # The defaults the prompt states, where the record says nothing.
    assert "480 / 768 / 1024 / 1440 / 1920" in prompt
    assert "200" in ctx["BUDGET_LCP_KB"] and ctx["REVIEW_PROVENANCE"] == "unconfirmed"
    # The record's own values win where it has them.
    conn2, site2 = _site(tmp_path / "two", platform="WordPress", breakpoints=[600, 1200],
                         budget_lcp_kb="150", review_provenance="confirmed")
    site = Site(domain="pix.fixture", platform="WordPress", breakpoints=[600, 1200],
                budget_lcp_kb="150", review_provenance="confirmed")
    ctx2 = _images_context(ev, site, conn=conn, run_id=run_id)
    assert ctx2["PLATFORM"] == "WordPress" and ctx2["BREAKPOINTS"] == "600 / 1200"
    assert ctx2["BUDGET_LCP_KB"] == "150" and ctx2["REVIEW_PROVENANCE"] == "confirmed"
    assert not any("platform not set" in a for a in ctx2["_ENGINE_ASSUMPTIONS"])


@pytest.fixture(scope="module")
def served():
    server, thread, db, base = _serve("pixrec")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "Pix Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "pix.fixture"}, timeout=30).json()
        yield base, site["id"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_the_site_record_carries_the_image_fields_and_refuses_a_bad_provenance(served):
    base, site_id = served
    fields = {"platform": "WordPress + Elementor", "cdn_or_image_pipeline": "Cloudflare Images",
              "breakpoints": [480, 1024], "budget_lcp_kb": "180", "budget_page_kb": "900",
              "review_provenance": "confirmed",
              "priority_internal_targets": ["/events", "/travel"]}
    assert httpx.put(f"{base}/api/sites/{site_id}", json=fields, timeout=30).status_code == 200
    rec = httpx.get(f"{base}/api/sites/{site_id}/record", timeout=30).json()
    for k, v in fields.items():
        assert rec[k] == v, (k, rec.get(k))
    bad = httpx.put(f"{base}/api/sites/{site_id}", json={"review_provenance": "maybe"}, timeout=30)
    assert bad.status_code == 422 and "review_provenance" in bad.text


# --- what only a browser can say --------------------------------------------

def test_the_two_checks_a_browser_unlocks_need_the_numbers_and_say_where_they_came_from():
    """`img-oversized` and `img-weight-budget` (brief v15, the rendering
    pass). Both are silent without a measurement and neither invents one."""
    facts = _facts()
    # Nothing measured: neither check fires, whatever the markup says.
    silent = {f.check_id for f in OnPageModule()._image_checks([facts])}
    assert "img-oversized" not in silent and "img-weight-budget" not in silent

    measured = {HOME: {
        "IMG_4821.jpg": {"rendered": {"1440": [640, 360]}, "intrinsic_w": 1920,
                         "weight_kb": 420, "lcp_candidate": True, "above_fold": True},
        "team-photo.png": {"rendered": {"1440": [800, 600]}, "intrinsic_w": 800,
                           "weight_kb": 700, "lcp_candidate": False, "above_fold": False},
    }}
    found = OnPageModule()._image_checks([facts], measured, (200, 1000))
    by: dict[str, list] = {}
    for f in found:
        by.setdefault(f.check_id, []).append(f)
    over = by["img-oversized"]
    assert [o.evidence["image"] for o in over] == ["IMG_4821.jpg"]
    assert over[0].evidence["intrinsic_w"] == 1920 and over[0].evidence["widest_rendered"] == 640
    assert "measured in a browser" in over[0].evidence["basis"]
    # The paint over its own budget, and the page over the page's.
    budget = by["img-weight-budget"]
    assert {b.evidence.get("weight_kb") or b.evidence.get("page_kb") for b in budget} == {420, 1120}
    # The lazy check now names the measured paint rather than document order.
    lcp = by["img-lcp-lazy"][0]
    assert "largest paint" in lcp.summary and "measured in a browser" in lcp.evidence["basis"]


def test_a_measured_field_reaches_the_prompt_and_an_unmeasured_one_says_so(tmp_path):
    conn = connect(tmp_path / "measured.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Pix Co")
    site_id = repo.create_site(conn, client, "pix.fixture")
    run_id = runs.create_run(conn, site_id, ["ONP"], "T2")
    crawl = CrawlResult(start_url=HOME, tier=Tier.T2, pages=[
        Page(url=HOME, requested_url=HOME, status=200, content_type="text/html", content=HTML)])
    measured = {HOME: {"IMG_4821.jpg": {"rendered": {"768": [360, 200], "1440": [640, 360]},
                                        "intrinsic_w": 1920, "intrinsic_h": 1080,
                                        "weight_kb": 420, "lcp_candidate": True,
                                        "above_fold": True, "css_aspect_ratio": "16 / 9"}}}
    runs.store_evidence(conn, run_id, snapshot(crawl, measured))
    ev = runs.get_evidence(conn, run_id)
    # The measurement is stored beside the markup, on the image it is about.
    stored = {i["src"]: i for i in ev["pages"][0]["image_inventory"]}
    assert stored["IMG_4821.jpg"]["weight_kb"] == 420
    assert stored["IMG_4821.jpg"]["lcp_candidate"] is True
    assert "weight_kb" not in stored["team-photo.png"]
    prompt = render_prompt("images", _images_context(ev, Site(domain="pix.fixture"),
                                                     conn=conn, run_id=run_id))
    # Measured reads as a number; unmeasured reads as unmeasured. Never blank.
    assert "| 420 |" in prompt and "768:360 1440:640" in prompt and "16 / 9" in prompt
    assert "1920x1080" in prompt and NOT_MEASURED in prompt


def test_the_pass_is_optional_and_a_crawl_without_it_stores_what_it_always_did():
    """`imaging.measure` answers `{}` where Playwright is absent, and the
    snapshot then carries the markup's fields and no others."""
    from clauditseo import imaging

    assert imaging.measure([], cap=0) == {}
    crawl = CrawlResult(start_url=HOME, tier=Tier.T2, pages=[
        Page(url=HOME, requested_url=HOME, status=200, content_type="text/html", content=HTML)])
    plain = snapshot(crawl)["pages"][0]["image_inventory"]
    assert plain and all("weight_kb" not in i and "rendered" not in i for i in plain)
    assert all("src" in i and "region" in i for i in plain)
