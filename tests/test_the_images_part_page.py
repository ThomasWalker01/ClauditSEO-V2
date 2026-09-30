"""The Images part page on the AO layout (brief v15 step AR).

The same three blocks as Title & description and Headings, with two
renderers of its own: a grid of every image the crawl read, carrying what
a browser measured where one ran, and a fix card whose body is the markup
before and after, attribute by attribute. One card per replacement rather
than per check - a row that says it also resolves five others renders
once, naming all six - and a group says whether the change is one file's,
a template's or a pipeline's. `img-review-schema` never renders as open.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
import pytest

from clauditseo.crawler.evidence import snapshot
from clauditseo.crawler.types import CrawlResult, Page
from clauditseo.db.connection import connect
from clauditseo.engine.types import Tier
from clauditseo.persistence import runs
from clauditseo.persistence.repo import create_id, now_iso
from tests.test_a11y_rendered import DIST
from tests.test_triage_ranks_the_section_rail import _serve
from tests.parts import ANATOMY_READY, open_part, open_page_filter

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"
BASE = "https://pixel.fixture"
HOME = BASE + "/"

HTML = (
    "<html lang='en'><head><title>Pixel</title></head><body>"
    # A logo and an icon, because that is what a header holds and because
    # AU6 turns on telling them apart: the logo is linked home and named
    # after the brand, the icon is 32px and decorative. A header with only
    # an icon in it is a different fixture, and
    # `test_the_images_brief_and_its_checks` is where it lives.
    "<header><a href='/'><img src='pixel-logo.svg' alt='Pixel' width='220' "
    "height='60'></a><img src='cart.svg' alt='Cart' width='32' height='32'></header>"
    "<main><img src='hero-final-v3.jpg' loading='lazy'>"
    "<p>Pixel runs events across the country.</p>"
    "<img src='team.png' alt='The team' width='800' height='600'></main></body></html>"
)

#: One markup change closing five checks on the hero, as the brief writes
#: one: the tag, then the preload line beside it.
HERO_FIX = (
    '<img src="pixel-events-hero.avif" width="1920" height="1080" '
    'fetchpriority="high" decoding="async" '
    'srcset="pixel-events-hero-768.avif 768w, pixel-events-hero-1920.avif 1920w" '
    'sizes="100vw" alt="The Pixel team running a corporate event">\n'
    '<link rel="preload" as="image" href="pixel-events-hero-1920.avif" fetchpriority="high">'
)


def _row(check_id, image, replacement, also=(), kind="image", group=None):
    return {"check": f"ONP/{check_id}", "dimension": "ONP", "check_id": check_id,
            "page": HOME, "image": image, "status": "FAIL", "severity": "medium",
            "evidence": "x", "replacement": replacement, "note": "",
            "also_resolves": list(also), "kind": kind, "group": group}


def _plant(db, site_id):
    conn = connect(db)
    run_id = runs.create_run(conn, site_id, ["ONP"], "T2")
    crawl = CrawlResult(start_url=HOME, tier=Tier.T2, pages=[
        Page(url=HOME, requested_url=HOME, status=200, content_type="text/html", content=HTML)])
    measured = {HOME: {
        "hero-final-v3.jpg": {"rendered": {"768": [720, 405], "1440": [1440, 810]},
                              "intrinsic_w": 2880, "intrinsic_h": 1620, "weight_kb": 812,
                              "lcp_candidate": True, "above_fold": True,
                              "css_aspect_ratio": "16 / 9"},
        "team.png": {"rendered": {"1440": [800, 600]}, "intrinsic_w": 800,
                     "intrinsic_h": 600, "weight_kb": 90, "lcp_candidate": False,
                     "above_fold": False},
    }}
    runs.store_evidence(conn, run_id, snapshot(crawl, measured))
    runs.mark_complete(conn, run_id, now_iso())
    with conn:
        conn.execute(
            "INSERT INTO findings (id, run_id, dimension, check_id, severity, source, summary,"
            " affected_urls, fingerprint, created_at) VALUES (?, ?, 'ONP', 'img-lcp-lazy',"
            " 'high', 'deterministic', 'the hero is loaded lazily', ?, 'sweep-hero', ?)",
            (create_id(), run_id, json.dumps([HOME]), now_iso()))
        conn.execute(
            "INSERT INTO finding_states (site_id, fingerprint, state, changed_by_run, updated_at)"
            " VALUES (?, 'sweep-hero', 'open', ?, ?)", (site_id, run_id, now_iso()))
    rows = [_row("img-lcp-lazy", "hero-final-v3.jpg", HERO_FIX,
                 also=["ONP/img-legacy-format", "ONP/img-weight-budget",
                       "ONP/img-no-srcset", "ONP/img-dimensions-missing",
                       "ONP/img-alt-missing"],
                 kind="template", group="template:hero"),
            _row("img-filename-generic", "team.png",
                 '<img src="pixel-team-2025.png" width="800" height="600" alt="The team">')]
    # Both shapes a held answer arrives in, because Birch produced both and
    # each broke the page differently. `img-sitemap-missing` is held for
    # the whole site, written `page: "*"`, and narrowing to a page used to
    # drop it and then count the check as passing there. The held-only
    # check is written by the brief as well as standing on the registry,
    # and the page rendered both cards for it.
    held = [{"check": "ONP/img-sitemap-missing", "page": "*", "image": "*",
             "needs": "the image sitemap"},
            {"check": "ONP/img-review-schema", "page": "*", "image": "stars.jpg",
             "needs": "review provenance"}]
    runs.store_expert_report(conn, run_id, "images", {
        "model": "claude-sonnet-5", "cost": 0.5,
        "report": "## Images — assessment\nTwo images, one paint. Nothing else moved.\n",
        "findings": [],
        "contract": {"status": "read", "part": "images", "rows": rows, "dropped": [],
                     "assumptions": [], "not_assessable": held, "uncovered": []}})
    runs.record_contract_findings(conn, run_id, "images", "claude-sonnet-5", rows)
    runs.recompute_contract_states(conn, site_id, "images")
    conn.close()
    return run_id


@pytest.fixture(scope="module")
def served():
    server, thread, db, base = _serve("pixelpart")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "Pixel Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "pixel.fixture"}, timeout=30).json()
        run_id = _plant(db, site["id"])
        yield base, site["id"], run_id
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_the_record_keeps_what_an_image_answer_carries(served):
    base, site_id, _ = served
    states = httpx.get(f"{base}/api/sites/{site_id}", timeout=30).json()["states"]
    hero = next(s for s in states if s["check_id"] == "img-lcp-lazy" and s["source_word"] == "brief")
    assert hero["image"] == "hero-final-v3.jpg" and hero["kind"] == "template"
    assert hero["group"] == "template:hero"
    assert len(hero["also_resolves"]) == 5
    # And the inventory the grid renders, measured where a browser ran.
    facts = httpx.get(f"{base}/api/sites/{site_id}/anatomy",
                      params={"page": HOME}, timeout=30).json()["facts"]
    by = {i["src"]: i for i in facts["image_inventory"]}
    assert by["hero-final-v3.jpg"]["weight_kb"] == 812
    assert by["hero-final-v3.jpg"]["lcp_candidate"] is True
    assert "weight_kb" not in by["pixel-logo.svg"]
    # The record names its own logo and which signal found it (brief v16
    # step AU6), so the sweep and the page read one answer rather than
    # deriving two. No schema on this fixture, so the markup decides.
    assert by["pixel-logo.svg"]["is_logo"] is True
    assert by["pixel-logo.svg"]["logo_from"].startswith("a header image linked to the home")
    assert not by["cart.svg"].get("is_logo")


def test_the_component_is_not_forked_and_images_supplies_two_renderers():
    defs = {"PartPage": 0, "FixCard": 0}
    for path in SRC.glob("*.tsx"):
        text = path.read_text(encoding="utf-8")
        for name in defs:
            defs[name] += len(re.findall(rf"^function {name}\(|^export function {name}\(",
                                         text, re.M))
    assert defs == {"PartPage": 1, "FixCard": 1}, defs
    part_page = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    assert part_page.count("PART_RENDERERS: Record<string, Renderer>") == 1
    assert "images: { now: ImagesNow, body: ImagesFixBody" in part_page


def test_the_markup_panels_read_the_attributes_of_both_sides():
    """`attrsOf` and `attrsIn` are what the two panels line up, so a
    replacement carrying a preload line beside its tag still diffs."""
    src = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    assert "export function attrsOf" in src and "export function attrsIn" in src
    # A brief writes the filename it was shown; the inventory holds the URL
    # the page served, which on a CDN carries a resize path and a query.
    assert "export function sameImage" in src and "export function imageIn" in src


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            yield b
        finally:
            b.close()


_JS = """() => ({
  acts: [...document.querySelectorAll('.part-acts button')].map((b) => b.textContent.trim()),
  prov: [...document.querySelectorAll('.part-prov .prov-line')].map((p) => p.textContent.trim()),
  grid: [...document.querySelectorAll('.img-grid-body .img-card')].map((c) => ({
    name: (c.querySelector('.img-name')?.textContent || '').trim(),
    lines: [...c.querySelectorAll('.img-line')].map((l) => l.textContent.trim()),
    alt: (c.querySelector('.img-alt')?.textContent || '').trim(),
    tags: [...c.querySelectorAll('.out-tag')].map((t) => t.textContent.trim()),
  })),
  note: (document.querySelector('.now-note')?.textContent || '').replace(/\\s+/g, ' ').trim(),
  cards: [...document.querySelectorAll('.fix-card')].map((c) => ({
    checks: [...c.querySelectorAll('.fix-check')].map((k) => k.textContent.trim()),
    kind: (c.querySelector('.fix-kind')?.textContent || '').trim(),
    copy: (c.querySelector('.fix-copy')?.textContent || '').trim(),
    struck: [...c.querySelectorAll('.img-markup .out-struck')].map((x) => x.textContent.trim()),
    added: [...c.querySelectorAll('.img-markup .out-new')].map((x) => x.textContent.trim()),
    panels: c.querySelectorAll('.img-panel').length,
    why: (c.querySelector('.fix-why')?.textContent || '').trim(),
  })),
  na: [...document.querySelectorAll('.fix-na')].map((p) => p.textContent.replace(/\\s+/g, ' ').trim()),
  bands: [...document.querySelectorAll('.img-band')].map((d) => ({
    cls: d.className,
    open: d.open,
    summary: (d.querySelector('summary')?.textContent || '').replace(/\\s+/g, ' ').trim(),
    cards: [...d.querySelectorAll('.img-card')].map((c) => ({
      name: (c.querySelector('.img-name')?.textContent || '').trim(),
      lines: [...c.querySelectorAll('.img-line')].map((l) => l.textContent.trim()),
      chips: [...c.querySelectorAll('.img-chips .chip')].map((x) => x.textContent.trim()),
    })),
  })),
  // One clean line per section now, not one for the part.
  clean: [...document.querySelectorAll('.cause-clean-line')].map((p) => p.textContent.trim()),
  // The first table is Free checks since brief v17 step AV3; both
  // carry the same columns.
  checksHead: [...(document.querySelector('.checks-table')?.querySelectorAll('thead th') || [])].map((t) => t.textContent),
  checksTables: document.querySelectorAll('.checks-table').length,
  checksHeads: [...document.querySelectorAll('.checks-head')].map((h) => h.textContent.replace(/\s+/g, ' ').trim()),
  reaudit: document.querySelectorAll('.reaudit').length,
  selects: document.querySelectorAll('.anat-pane select').length,
})"""


def _open(pg, base, site_id):
    pg.goto(f"{base}/#/sites/{site_id}?tab=findings", wait_until="load", timeout=30_000)
    pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
    open_part(pg, 'Images')
    pg.wait_for_selector(".part-page", timeout=15_000)


@NEEDS_BROWSER
@pytest.mark.skipif(not (DIST / "index.html").is_file(), reason="dashboard not built")
def test_narrowed_the_grid_shows_every_image_and_a_fix_is_markup_before_and_after(browser, served):
    base, site_id, _ = served
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    try:
        _open(pg, base, site_id)
        open_page_filter(pg)
        pg.fill(".page-find", "/")
        pg.wait_for_selector(".img-grid-body .img-card", timeout=15_000)
        pg.wait_for_function(
            "() => document.querySelectorAll('.anat-pane .fix-card').length >= 2", timeout=15_000)
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    assert got["acts"][0].startswith("Re-check Images") and "· this page · free" in got["acts"][0], got["acts"]
    assert "analysis images" in got["prov"][1], got["prov"]
    # The body's images, measured where a browser ran and silent where none
    # did. The header's are not here: since brief v16 step AU3 the page's
    # furniture is a collapsed row above this grid rather than the first
    # cards in it, which is what a site with one footer icon on 248 pages
    # needs it to be.
    assert [g["name"] for g in got["grid"]] == ["hero-final-v3.jpg", "team.png"]
    hero = got["grid"][0]
    assert "jpg · 812 KB" in hero["lines"][0], hero
    assert "2880×1620 intrinsic · renders at 1440px" in hero["lines"][1], hero
    assert "above the fold" in hero["lines"][2] and "largest paint" in hero["lines"][2], hero
    assert hero["alt"] == "alt missing" and "No alt text" in hero["tags"], hero
    # One band, not three: this page has no footer images, and an empty row
    # saying so would be a sentence about nothing (AU3).
    assert [b["cls"] for b in got["bands"]] == ["img-band img-band-header"], got["bands"]
    header = got["bands"][0]
    assert header["open"] is False, "the furniture opens on a click, not on arrival"
    assert header["summary"].startswith("Header · 2 images · "), header["summary"]
    # The logo first inside the band (AU6): it is the image an operator
    # opens the header looking for, and the icons are why it was folded.
    assert [c["name"] for c in header["cards"]] == ["pixel-logo.svg", "cart.svg"], header
    logo = header["cards"][0]
    # What the image is to the site, before what it is as a file: this one
    # is the logo, and it is the same logo on every page (AU6, AU3).
    assert sorted(logo["chips"]) == ["logo", "template"], logo
    # The same card the body renders, inside the row: an image nobody
    # measured says so on every line, wherever it sits.
    assert "weight not measured" in logo["lines"][0], logo
    assert "paint not measured" in logo["lines"][2], logo
    assert got["note"].startswith("Every <img> the crawl read on this page, measured in a "
                                  "browser at 768, 1440 pixels wide."), got["note"]
    # One card per replacement, naming every check it closes.
    card = next(c for c in got["cards"] if "ONP/img-lcp-lazy" in c["checks"])
    assert len(card["checks"]) == 6 and "ONP/img-weight-budget" in card["checks"], card
    assert card["kind"] == "template: hero" and card["copy"] == "copy markup", card
    assert card["panels"] == 2, card
    # The markup before and after: what goes, and what arrives.
    assert any('src="hero-final-v3.jpg"' in x.replace("\\n", "") for x in card["struck"]), card["struck"]
    assert any("loading" in x for x in card["struck"]), card["struck"]
    assert any('fetchpriority="high"' in x for x in card["added"]), card["added"]
    # The five checks it closes are not cards of their own.
    assert not any(c["checks"] == ["ONP/img-weight-budget"] for c in got["cards"]), got["cards"]
    # Held for a list on the record: one line, not a card per page.
    assert any("img-sitemap-missing not assessable" in n for n in got["na"]), got["na"]
    # And the one that can only ever be held is a card, never open.
    review = next(c for c in got["cards"] if "ONP/img-review-schema" in c["checks"])
    assert review["copy"] == "", review
    # Item 211: label and value apart in the text, in the table's shape.
    assert review["why"].startswith("Why held: needs review provenance"), review
    assert got["reaudit"] == 0 and got["selects"] == 0, got


@NEEDS_BROWSER
@pytest.mark.skipif(not (DIST / "index.html").is_file(), reason="dashboard not built")
def test_the_whole_site_counts_images_beside_pages(browser, served):
    base, site_id, _ = served
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    try:
        _open(pg, base, site_id)
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    assert got["checksHead"] == ["Severity", "Check", "Automatic", "Analysis", "Pages", "Images", "State"]
    assert not got["grid"], "the grid is the one-page block"
    card = next(c for c in got["cards"] if "ONP/img-lcp-lazy" in c["checks"])
    assert card["kind"] == "template: hero", card


@NEEDS_BROWSER
@pytest.mark.skipif(not (DIST / "index.html").is_file(), reason="dashboard not built")
def test_a_held_only_check_is_never_counted_among_the_checks_that_pass(browser, served):
    """`img-review-schema` cannot pass, so nothing may say it did.

    The check is held-only (`contract.HELD_ONLY`): the parser drops any row
    for it that is not `not_assessable`, because whether a review widget's
    stars are real is a question about provenance rather than about markup,
    and no engine reading a page can answer it. So it has no open rows -
    and the clean line, which is "every check of this part with no row
    against it", read that absence as a pass.

    Observed on Birch at brief v15 step AR, on the running product: the
    brief returned no `not_assessable` row for it and the page reported
    `6 checks pass on this page: ... img-review-schema ...`. That is the
    one sentence on the part page that a reader acts on without opening
    anything, and it was claiming a check nobody ran.

    Driven on the whole-site view rather than asserted about the source,
    because what is wrong is what an operator reads.
    """
    base, site_id, _ = served
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    try:
        _open(pg, base, site_id)
        got = pg.evaluate(_JS)
        # The narrowed view too: the line is rendered on both scopes and
        # the fixture's held row only reaches one of them.
        open_page_filter(pg)
        pg.fill(".page-find", "/")
        pg.wait_for_selector(".now-card", timeout=15_000)
        pg.wait_for_timeout(300)
        narrowed = pg.evaluate(_JS)
    finally:
        pg.close()
    for scope, seen in (("whole site", got), ("narrowed", narrowed)):
        assert "img-review-schema" not in seen["clean"], (
            f"{scope}: a held-only check is named among the checks that pass, "
            f"and it has no pass to name: {seen['clean']!r}")
        # The same sentence, the other way a check reaches it. A row the
        # brief held for the whole site is written `page: "*"`, and
        # narrowing dropped it - so `img-sitemap-missing` read as passing
        # on Birch's home page while the brief was saying site-wide that it
        # could not judge it. One `na` line either way, never a pass.
        assert "img-sitemap-missing" not in seen["clean"], (
            f"{scope}: a check the brief held for the whole site is named "
            f"among the checks that pass here: {seen['clean']!r}")
        assert any("the image sitemap" in n for n in seen["na"]), (
            f"{scope}: the site-wide held check is neither passing nor "
            f"stated: {seen['na']!r}")
        # And the reason the held-only check is absent from that line is
        # that it is held, not that it left the part: one card, and one.
        cards = [c for c in seen["cards"] if "ONP/img-review-schema" in c["checks"]]
        assert len(cards) == 1, (
            f"{scope}: a held-only check gets one card. The registry stands "
            "one for every site and the brief writes its own on `page: \"*\"`, "
            "and Birch rendered both - the same answer twice, differing only "
            f"in how much it said: {cards}")
