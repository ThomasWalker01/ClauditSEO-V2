"""The Links part page (brief v17 step AW, part 3).

The fifth part on the three-block layout, and the first whose "now" block
is about pages other than the one on screen: `orphan`, `inlinks-low` and
`anchor-generic` are all statements about somebody else's markup, so a
page's own record could never carry the answer. Both directions are read
off the same crawl the page was read from, which is what stops the
heading's count and the finding's count disagreeing.

The Internal link suggestions block leaves the Analyse body with this.
It stood there from brief v5 step T: a result about internal links with
no check behind it, no record row and no place in any report.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
import pytest

from clauditseo.db.connection import connect
from clauditseo.persistence import runs
from clauditseo.persistence.repo import create_id, now_iso
from tests.test_a11y_rendered import DIST
from tests.test_the_part_page_is_three_blocks import three_block_parts
from tests.test_triage_ranks_the_section_rail import _serve
from tests.parts import ANATOMY_READY, open_part, open_page_filter

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")

BASE = "https://graph.test"
UI = Path(__file__).resolve().parents[1] / "dashboard" / "src"


def test_links_renders_as_three_blocks():
    assert "links" in three_block_parts(), sorted(three_block_parts())


def test_the_suggestions_block_has_left_the_analyse_body():
    src = (UI / "pane_analyse.tsx").read_text(encoding="utf-8")
    assert "LinkSuggestions" not in src, (
        "the block is still rendered on Analyse; brief v17 step AW closes "
        "v5 step T by moving it onto the part page")
    assert "link-suggestions" not in src


def _plant(db, site_id):
    """Four pages: a home, a hub, a spoke one page links to, and a page
    nothing links to. The nav points at the hub from every page, so the
    fold has something to count."""
    from clauditseo.crawler.crawl import extract_link_details
    from clauditseo.crawler.evidence import snapshot
    from clauditseo.crawler.types import CrawlResult, Page
    from clauditseo.engine.types import Tier

    def page(path, body):
        p = Page(url=BASE + path, requested_url=BASE + path, status=200,
                 content_type="text/html; charset=utf-8",
                 content=f"<html><head><title>{path}</title></head>"
                         f"<body>{body}</body></html>")
        p.link_details = extract_link_details(p)
        p.outlinks = [link["url"] for link in p.link_details]
        return p

    nav = '<nav><a href="/events">Events</a><a href="/">Home</a></nav>'
    crawl = CrawlResult(start_url=BASE + "/", tier=Tier.T2)
    crawl.pages.extend([
        page("/", nav + '<main><h1>Home</h1>'
                        '<a href="/events">Birch Events</a>'
                        '<a href="/events-team">Meet the events team</a></main>'),
        page("/events", nav + '<main><h1>Events</h1>'
                              '<a href="/events-team">Learn more</a></main>'),
        page("/events-team", nav + "<main><h1>The events team</h1></main>"),
        page("/nobody", nav + "<main><h1>Unlinked</h1></main>"),
    ])

    conn = connect(db)
    run_id = runs.create_run(conn, site_id, ["LNK"], "T2")
    runs.store_evidence(conn, run_id, snapshot(crawl))
    runs.mark_complete(conn, run_id, now_iso())
    with conn:
        for check, url, fp in (("orphan", BASE + "/nobody", "sweep-orphan"),
                               ("anchor-generic", BASE + "/events", "sweep-generic")):
            conn.execute(
                "INSERT INTO findings (id, run_id, dimension, check_id, severity, source,"
                " summary, affected_urls, fingerprint, created_at) VALUES (?, ?, 'LNK', ?,"
                " 'medium', 'deterministic', ?, ?, ?, ?)",
                (create_id(), run_id, check, f"{check} on {url}",
                 json.dumps([url]), fp, now_iso()))
            conn.execute(
                "INSERT INTO finding_states (site_id, fingerprint, state, changed_by_run,"
                " updated_at) VALUES (?, ?, 'open', ?, ?)", (site_id, fp, run_id, now_iso()))
    conn.close()
    return run_id


@pytest.fixture(scope="module")
def served():
    server, thread, db, base = _serve("graph")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "Graph Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "graph.test"}, timeout=30).json()
        run_id = _plant(db, site["id"])
        yield base, site["id"], run_id
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_the_page_facts_carry_both_directions(served):
    base, site_id, _ = served
    # `page_facts` reaches a screen through the anatomy's narrow: there is
    # one payload for "the screen scoped to this page", and a second route
    # would be a second answer to it.
    facts = httpx.get(f"{base}/api/sites/{site_id}/anatomy",
                      params={"page": BASE + "/events-team"}, timeout=30).json()["facts"]
    incoming = facts["inlinks"]
    # Two pages link here from body copy, and the anchors are the ones the
    # markup wrote — one of them the generic phrase the sweep raised.
    body = [link for link in incoming if link["region"] == "body"]
    assert {link["source"] for link in body} == {BASE + "/", BASE + "/events"}, body
    assert {link["anchor"] for link in body} == {"Meet the events team", "Learn more"}, body
    # And this page's own links: the nav's two, no body link of its own.
    out = facts["link_inventory"]
    assert out and all(link["region"] == "nav" for link in out), out
    # The orphan has nothing at all.
    alone = httpx.get(f"{base}/api/sites/{site_id}/anatomy",
                      params={"page": BASE + "/nobody"}, timeout=30).json()["facts"]
    assert [link for link in alone["inlinks"] if link["region"] == "body"] == []


def test_the_count_the_heading_shows_is_the_count_the_check_used():
    """One walk of the graph, not two.

    The heading says how many pages link here and `inlinks-low` decides
    whether that is too few. Two derivations of one number is how a badge
    comes to read 2 above a list of three, and both read `region` the same
    way — body only, because a navigation points at every page from every
    page and counting it would mean no site ever has an under-linked page.
    """
    src = (UI / "part_page.tsx").read_text(encoding="utf-8")
    from clauditseo.modules import links as mod
    assert mod.TEMPLATE_REGIONS == {"nav", "footer"}, mod.TEMPLATE_REGIONS
    # The screen folds on the same rule the module counts on: body, and
    # everything that is not body is the site's furniture.
    assert 'const isBody = (link: { region?: string }) => (link.region || "body") === "body";' in src
    # And the heading's number is the filtered length, not the list's:
    # `1 page links here` above three rows of navigation is the disagreement
    # this clause exists to stop.
    assert "const inBody = (facts.inlinks ?? []).filter(isBody).length;" in src


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
  head: (document.querySelector('.links-head')?.textContent || '').trim(),
  bands: [...document.querySelectorAll('.links-band h5')].map((h) => h.textContent.trim()),
  rows: [...document.querySelectorAll('.links-band-in .links-table tbody tr')]
    .map((tr) => [...tr.querySelectorAll('td')].map((td) => td.textContent.trim())),
  template: [...document.querySelectorAll('.links-template')].map((p) => p.textContent.trim()),
})"""


@NEEDS_BROWSER
@pytest.mark.skipif(not (DIST / "index.html").is_file(), reason="dashboard not built")
def test_the_now_block_is_two_lists_with_the_furniture_folded(browser, served):
    base, site_id, _ = served
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    try:
        pg.goto(f"{base}/#/sites/{site_id}?tab=findings", wait_until="load", timeout=30_000)
        pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
        open_part(pg, 'Links on the page')
        pg.wait_for_selector(".part-page", timeout=15_000)
        # Narrowed to one page, which is where the two lists stand.
        # A page the record holds a finding on, which is what the picker
        # offers: the hub, whose one generic anchor the sweep raised.
        open_page_filter(pg)
        pg.fill(".page-find", "/events")
        pg.wait_for_selector(".links-now", timeout=15_000)
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    assert got["bands"][:2] == ["Links into this page · 1",
                               "Links out of this page · 1"], got["bands"]
    assert "from the home page" in got["head"], got["head"]
    assert [row[:2] for row in got["rows"]] == [["/", "Birch Events"]], got["rows"]
    assert any("nav" in line and "counted once for the site" in line
               for line in got["template"]), got["template"]
