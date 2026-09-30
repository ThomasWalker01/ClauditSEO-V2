"""Headings on the part page's three blocks (brief v14 step AP).

The same layout as Title & description, with two renderers of its own: an
outline for "what the page has now", and a before-and-after outline in
each fix card. The outline is what the parser saw - document order and
level, the region it was found in, each problem tagged on its own line -
and a fix card shows only the lines that move, with a word for what
happened to each. A check held for want of a list on the site record is
one line naming the input, not a card per page, and a group whose pages
share a template says so once. Nothing forks the component AO built.
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
BASE = "https://outline.fixture"
HOME = BASE + "/"
POST = BASE + "/blog/one"

HOME_HTML = (
    "<html lang='en'><head><title>Welcome to Outline</title></head><body>"
    "<header><h2>Site navigation</h2></header>"
    "<main><h1>Welcome to Outline</h1>"
    "<p>We plan and run events across the country for companies of every size.</p>"
    "<h2>How do we work?</h2>"
    "<p>An image caption sits here instead of an answer.</p>"
    "<h4>Our clients</h4><p>Some of them are large.</p></main></body></html>"
)
POST_HTML = ("<html><body><main><h1>A post</h1><h4>Why it matters</h4>"
             "<p>Because it does.</p></main></body></html>")

#: The brief's answer for the home page: the h4 relevelled, nothing else.
HOME_FIX = ("h1 Welcome to Outline / h2 How do we work? / h3 Our clients")
POST_FIX = ("h1 A post / h2 Why it matters")


def _row(check_id, page, replacement, severity="medium"):
    return {"check": f"ONP/{check_id}", "dimension": "ONP", "check_id": check_id,
            "page": page, "status": "FAIL", "severity": severity, "evidence": "x",
            "replacement": replacement, "note": ""}


def _plant(db, site_id):
    conn = connect(db)
    run_id = runs.create_run(conn, site_id, ["ONP"], "T2")
    crawl = CrawlResult(start_url=HOME, tier=Tier.T2, pages=[
        Page(url=HOME, requested_url=HOME, status=200, content_type="text/html", content=HOME_HTML),
        Page(url=POST, requested_url=POST, status=200, content_type="text/html", content=POST_HTML)])
    runs.store_evidence(conn, run_id, snapshot(crawl))
    runs.mark_complete(conn, run_id, now_iso())
    with conn:
        for url, fp in ((HOME, "sweep-home-skip"), (POST, "sweep-post-skip")):
            conn.execute(
                "INSERT INTO findings (id, run_id, dimension, check_id, severity, source, summary,"
                " affected_urls, fingerprint, created_at) VALUES (?, ?, 'ONP', 'heading-skip',"
                " 'medium', 'deterministic', 'a level was skipped', ?, ?, ?)",
                (create_id(), run_id, json.dumps([url]), fp, now_iso()))
            conn.execute(
                "INSERT INTO finding_states (site_id, fingerprint, state, changed_by_run, updated_at)"
                " VALUES (?, ?, 'open', ?, ?)", (site_id, fp, run_id, now_iso()))
    rows = [_row("heading-skip", HOME, HOME_FIX), _row("heading-skip", POST, POST_FIX)]
    held = [{"check": "ONP/h1-triple-restated", "page": "/", "needs": "GBP primary category"},
            {"check": "ONP/h3-sub-service", "page": "/", "needs": "SUB_SERVICES"},
            {"check": "ONP/h3-geo-map", "page": "/", "needs": "LOCATION PAGES"}]
    runs.store_expert_report(conn, run_id, "headings", {
        "model": "claude-sonnet-5", "cost": 0.13,
        "report": "## Headings — assessment\nOne page skips a level. The blog template "
                  "starts at h4. Nothing else moved.\n\n### Patterns\nNone.\n",
        "findings": [],
        "contract": {"status": "read", "part": "headings", "rows": rows, "dropped": [],
                     "assumptions": [], "not_assessable": held, "uncovered": []}})
    runs.record_contract_findings(conn, run_id, "headings", "claude-sonnet-5", rows)
    runs.recompute_contract_states(conn, site_id, "headings")
    conn.close()
    return run_id


@pytest.fixture(scope="module")
def served():
    server, thread, db, base = _serve("outline")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "Outline Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "outline.fixture"}, timeout=30).json()
        run_id = _plant(db, site["id"])
        yield base, site["id"], run_id
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_the_payload_carries_the_outline_and_falls_back_where_a_run_predates_it(served):
    base, site_id, _ = served
    got = httpx.get(f"{base}/api/sites/{site_id}/anatomy", params={"page": HOME}, timeout=30).json()
    facts = got["facts"]
    assert facts["main_region"] == "<main>"
    levels = [(h[0], h[2]) for h in facts["outline"]]
    assert levels == [(2, False), (1, True), (2, True), (4, True)], facts["outline"]
    assert facts["outline"][2][1] == "How do we work?"
    # `headings` stays beside it, which is what a run crawled before the
    # outline existed carries on its own.
    assert [h[0] for h in facts["headings"]] == [2, 1, 2, 4]


def test_the_component_is_not_forked():
    """The brief's own grep: one definition each, used by both parts."""
    defs = {"PartPage": 0, "FixCard": 0}
    for path in SRC.glob("*.tsx"):
        text = path.read_text(encoding="utf-8")
        for name in defs:
            defs[name] += len(re.findall(rf"^function {name}\(|^export function {name}\(",
                                         text, re.M))
    assert defs == {"PartPage": 1, "FixCard": 1}, defs
    part_page = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    assert '"title-desc": {' in part_page and "headings: {" in part_page
    # One renderer table, and Headings takes both slots of it.
    assert part_page.count("PART_RENDERERS: Record<string, Renderer>") == 1


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
  ladderRungs: document.querySelectorAll('.now-card .ho-ladder .ho-heading').length,
  note: (document.querySelector('.now-note')?.textContent || '').replace(/\\s+/g, ' ').trim(),
  cards: [...document.querySelectorAll('.fix-card')].map((c) => ({
    name: (c.querySelector('.fix-name')?.textContent || '').trim(),
    copy: (c.querySelector('.fix-copy')?.textContent || '').trim(),
    was: [...c.querySelectorAll('.outline-was .out-line')].map((l) =>
      `${l.classList.contains('out-struck') ? '-' : ' '}${l.querySelector('.out-lvl')?.textContent} `
      + `${l.querySelector('.out-text')?.textContent}`),
    now: [...c.querySelectorAll('.outline-now .out-line')].map((l) =>
      `${l.classList.contains('out-new') ? '+' : ' '}${l.querySelector('.out-lvl')?.textContent} `
      + `${l.querySelector('.out-text')?.textContent}`
      + `${l.querySelector('.out-mark') ? ' [' + l.querySelector('.out-mark').textContent + ']' : ''}`),
    why: (c.querySelector('.fix-why')?.textContent || '').trim(),
  })),
  na: [...document.querySelectorAll('.fix-na')].map((p) => p.textContent.replace(/\\s+/g, ' ').trim()),
  // Every clean line, joined. There is one per section since brief v17
  // step AV3 - free checks and Analysis are counted apart - and the clause
  // below is about every check of the part being accounted for somewhere,
  // which is a question about both.
  clean: [...document.querySelectorAll('.cause-clean-line')]
    .map((p) => p.textContent.trim()).join(' '),
  groups: [...document.querySelectorAll('.fix-group')].map((g) => g.textContent.replace(/\\s+/g, ' ').trim()),
  checks: [...document.querySelectorAll('.checks-table tbody tr')].map((tr) =>
    [...tr.querySelectorAll('td')].map((td) => td.textContent.trim())),
  reaudit: document.querySelectorAll('.reaudit').length,
  selects: document.querySelectorAll('.anat-pane select').length,
})"""


def _open(pg, base, site_id):
    pg.goto(f"{base}/#/sites/{site_id}?tab=findings", wait_until="load", timeout=30_000)
    pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
    open_part(pg, 'Headings')
    pg.wait_for_selector(".part-page", timeout=15_000)


@NEEDS_BROWSER
@pytest.mark.skipif(not (DIST / "index.html").is_file(), reason="dashboard not built")
def test_narrowed_the_outline_is_what_the_parser_saw_and_the_fix_is_an_outline(browser, served):
    base, site_id, _ = served
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    try:
        _open(pg, base, site_id)
        open_page_filter(pg)
        pg.fill(".page-find", "/")
        pg.wait_for_selector(".now-card .ho-ladder", timeout=15_000)
        # Two cards on this page: the level skip, and the triple held for
        # want of the category.
        try:
            pg.wait_for_function(
                "() => document.querySelectorAll('.anat-pane .fix-card').length === 2", timeout=15_000)
        except Exception as e:
            raise AssertionError((str(e).splitlines()[0], pg.evaluate(_JS)))
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    assert got["acts"][0].startswith("Re-check Headings") and "· this page · free" in got["acts"][0], got["acts"]
    assert "analysis headings" in got["prov"][1] and "claude-sonnet-5" in got["prov"][1]
    # The page-scope outline is the v16d ladder (the tagged list beneath it is
    # retired, Q-51); its four headings are drawn as rungs, and the skip, the
    # second H1 and the per-heading judgements the list used to tag are on the
    # ladder and the fix cards below rather than on a second outline. The
    # ladder's own rendering is held by test_the_headings_outline_blocks_are_drawn.
    assert got["ladderRungs"] == 4, got["ladderRungs"]
    assert got["note"] == ("Document order and level as the parser saw them; main region "
                           "<main>. Styling is not evidence."), got["note"]
    # One card, and its body is an outline: the h4 struck, the h3 green.
    card = got["cards"][0]
    assert card["name"] == "Level skipped" and card["copy"] == "copy outline", card
    # Only the lines that move, with one line of context above; the site's
    # navigation heading is outside main and is not shown as cut.
    assert card["was"] == [" H2 How do we work?", "-H4 Our clients"], card["was"]
    assert card["now"] == [" H2 How do we work?",
                           "+H3 Our clients [relevelled h4 → h3]"], card["now"]
    # The held check is the AO card, with its link and nothing to copy.
    held = got["cards"][1]
    # Item 211: the title is the check's plain name; the pill says held.
    assert "not checked" not in held["name"] and held["copy"] == "", held
    # Item 211: label and value apart in the text, in the table's shape.
    assert held["why"].startswith("Why held: needs GBP primary category"), held
    # The two checks that need a list on the record are one line each,
    # never a card per page.
    assert sorted(got["na"]) == [
        # Item 211: the prompt's variable names said as words, on read.
        "h3-geo-map not assessable — needs location pages.",
        # And a word with a home links to it, which the variable name did not.
        "h3-sub-service not assessable — needs sub-services — set it on Admin › Sites"], got["na"]
    assert "h1-missing" in got["clean"] and "h3-sub-service" not in got["clean"], got["clean"]


@NEEDS_BROWSER
@pytest.mark.skipif(not (DIST / "index.html").is_file(), reason="dashboard not built")
def test_the_whole_site_lists_every_check_and_names_the_template_a_group_shares(browser, served):
    base, site_id, _ = served
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    try:
        _open(pg, base, site_id)
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    # Every check of the part is accounted for: raised in the table, held
    # or N/A on their lines, the rest clean.
    listed = {r[1].split("/")[1] for r in got["checks"]}
    named = set(re.findall(r"h\d-[a-z-]+|heading-skip",
                           got["clean"] + " ".join(got["na"]) + " ".join(str(r) for r in got["checks"])))
    assert "heading-skip" in listed
    assert len(named) >= 13, sorted(named)
    assert got["reaudit"] == 0 and got["selects"] == 0, got
    # Both pages skip a level; they share no template, so nothing claims one.
    skip = next(g for g in got["groups"] if "heading-skip" in g)
    assert skip.startswith("ONP/heading-skip · 2 pages"), skip
    assert "template" not in skip, skip


def test_the_template_is_named_only_where_pages_share_one():
    """The group header states one change for many pages, or nothing."""
    src = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    assert "export function templateOf" in src
    assert "template <code>{tpl.prefix}*</code>" in src
