"""The first prompt written to the contract: Title & description. The
sweep measures description length; `title-desc` is a conforming brief
whose six inputs the engine fills from the run; the Images brief keeps only
the heading checks and stays a legacy brief; and on screen `read
title-desc` opens a report, the Record shows the part's checks with sweep
and brief counts, and the part page shows a replacement table.

Brief v10 step AG (`_plans/site-screen-brief-v10-2026-09-04.md`).
"""

from __future__ import annotations

import dataclasses
import json
import time
from urllib.parse import urlsplit

import httpx
import pytest

from clauditseo import briefs
from clauditseo.analysts.base import AnalystResponse
from clauditseo.analysts.expert import (EXPERT_TOOLS, TITLE_DESC_CHECKS, build_context,
                                        conforms, render_prompt, run_expert)
from clauditseo.config import Settings
from clauditseo.db.connection import connect
from clauditseo.engine.types import Severity, Site
from clauditseo.modules.onp import DESC_MAX, DESC_MIN, GUIDELINES, OnPageModule
from clauditseo.modules.pagefacts import PageFacts
from clauditseo.persistence import runs
from tests.test_a11y_rendered import DIST
from clauditseo.crawler.evidence import snapshot
from tests.test_coverage import DIMS, _Hub, _crawl, _run
from tests.test_triage_ranks_the_section_rail import _serve
from tests.parts import ANATOMY_READY, open_part

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")


def _facts(path: str, desc: str | None) -> PageFacts:
    url = f"https://fixture.local{path}"
    f = PageFacts(url=url, path=path)
    f.title = "A title of a sensible length for the tab"
    f.meta_description = desc
    f.headings = [(1, "One heading")]
    return f


def test_the_sweep_measures_description_length_and_warns_outside_the_window():
    ids = lambda f: {x.check_id: x for x in OnPageModule()._page_checks(f)}  # noqa: E731
    short = ids(_facts("/short", "Too short to earn the click."))
    assert "meta-desc-length" in short and short["meta-desc-length"].severity == Severity.MEDIUM   # brief v11 step AI
    # Brief v16i: the short side still measures CHARACTERS and the row says
    # so. Adequacy is not a width fact - in pixels a description of short
    # words would score worse than one of wide ones, which is not a defect
    # anybody would act on.
    assert "under the 120" in short["meta-desc-length"].summary
    assert short["meta-desc-length"].evidence["measured"] == "characters"
    # And a description's over-length measures pixels at the desktop cut (it
    # has no measured mobile width; item 152). `l` is 222/1000 em
    # against `x`'s 500, so this string is well past 160 CHARACTERS and still
    # inside 920 px - the false positive the unit change removes. (`x` is not
    # narrow enough: 161 of them is 1127 px and really is cut.)
    long_chars = ids(_facts("/long", "l" * (DESC_MAX + 1)))
    assert "meta-desc-length" not in long_chars, (
        "a narrow string over the character bound still fires, so the check "
        "did not move to pixels")
    wide = ids(_facts("/wide", "W" * 200))
    assert "meta-desc-length" in wide
    assert wide["meta-desc-length"].evidence["measured"] == "pixels"
    assert wide["meta-desc-length"].evidence["falls_off"]
    fits = ids(_facts("/fits", "y" * DESC_MIN))
    assert "meta-desc-length" not in fits
    assert "meta-desc-length" not in ids(_facts("/none", None)) and "meta-desc-missing" in ids(_facts("/none", None))
    # The registry carries both units for one release: the pixel maximum the
    # check now enforces, and the character bounds it replaced.
    g = GUIDELINES["meta_description"]
    assert (g["min"], g["max"], g["check"]) == (120, 160, "meta-desc-length")
    assert g["max_px"] == 920 and g["font"] == ("Arial", 14)


def test_title_desc_is_a_conforming_brief_on_its_own_part_and_onpage_hygiene_keeps_the_headings():
    td = briefs.by_id()["title-desc"]
    assert (td.part, td.scope, td.tier) == ("title-desc", "site", "standard")
    assert list(td.checks) == [f"ONP/{c}" for c in TITLE_DESC_CHECKS]
    assert conforms("title-desc")
    # The Images brief since brief v15 step AQ, which is what the stopgap
    # became: fifteen checks, on the contract, and none of them a title's.
    im = briefs.by_id()["images"]
    # Sixteen: plus `img-logo` (AU6) and `img-heavy` (AU7), less
    # `img-review-schema`, which step AS moved to Structured data.
    assert im.part == "images" and len(im.checks) == 16
    assert conforms("images")
    text = im.path.read_text(encoding="utf-8")
    assert "title-duplicate" not in text and "OTHER_PAGE_TITLES_AND_METAS" not in text


def _seed(base: str, db, domain: str):
    client = httpx.post(f"{base}/api/clients", json={"name": "Title Co"}, timeout=30).json()
    site = httpx.post(f"{base}/api/clients/{client['id']}/sites", json={"domain": domain}, timeout=30).json()
    conn = connect(db)
    result = _run(_Hub())
    run_id = runs.create_run(conn, site["id"], DIMS, "T2")
    runs.complete_run(conn, run_id, result)
    # The crawl's record, which the API's audit path stores and this
    # fixture's direct path does not: the brief reads its pages from it.
    runs.store_evidence(conn, run_id, snapshot(_crawl()))
    return conn, site["id"], run_id


class _Stub:
    name = "stub"
    model_id = "stub-1"

    def __init__(self, text):
        self.text = text
        self.prompt = ""

    def run_agent(self, system, bundle, toolkit, max_tokens, max_output=0):
        self.prompt = bundle
        return AnalystResponse(findings=[], tokens_in=10, tokens_out=10, text=self.text)


def _block(pages: list[str]) -> str:
    rows = [{"check": "ONP/title-length", "page": urlsplit(pages[0]).path or "/", "status": "FAIL",
             "severity": "MEDIUM", "evidence": "\"Home\" · 4 chars",
             "replacement": "What the fixture site does, and where - Fixture", "note": "48 chars"},
            {"check": "ONP/meta-desc-missing", "page": urlsplit(pages[-1]).path or "/", "status": "FAIL",
             "severity": "MEDIUM", "evidence": "no <meta name=description>",
             "replacement": "A description of the page that earns the click, written in active voice and "
                            "describing what the page does rather than repeating its title."}]
    body = json.dumps({"part": "title-desc", "run_id": "x", "source": "brief", "rows": rows,
                       "not_assessable": [], "assumptions": ["topic for / taken from h1"]})
    return ("```json\n" + body + "\n```\n\n### Title & description — assessment\n"
            "| Check | Page | Evidence | Severity |\n|---|---|---|---|\n"
            "| ONP/title-length | / | \"Home\" · 4 chars | MEDIUM |\n\n"
            "### Replacement copy\n| Page | Current title → Replacement (chars) | Current description → Replacement (chars) |\n"
            "|---|---|---|\n\n### Patterns\nNone.\n\n### Not assessable\nNone.\n\n### Out of scope\nNone.\n")


@pytest.fixture(scope="module")
def served():
    server, thread, db, base = _serve("titledesc")
    try:
        conn, site_id, run_id = _seed(base, db, "titledesc.fixture")
        ev = runs.get_evidence(conn, run_id)
        pages = [p["url"] for p in ev["pages"] if p.get("status") == 200]
        cfg = dataclasses.replace(Settings(), anthropic_api_key="")
        stub = _Stub(_block(pages))
        got = run_expert(conn, run_id, "title-desc", ev, Site(domain="titledesc.fixture"), cfg, stub,
                         use_cache=False)
        conn.close()
        yield base, site_id, run_id, got, stub.prompt
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_the_engine_fills_every_input_from_the_run_and_the_contract_reads(served):
    base, site_id, run_id, got, prompt = served
    assert got["status"] == "ok" and got["contract"]["status"] == "read", got.get("reason")
    assert len(got["contract"]["rows"]) == 2 and got["contract"]["dropped"] == []
    assert "[NOT SUPPLIED]" not in prompt and "{{" not in prompt
    for token in ("AUDIT:", "BRAND:", "SITE TYPE:", "PAGE SET:", "AUTOMATIC CHECK RESULTS:", "COMPARISON SET:"):
        assert token in prompt, token
    assert "| url | title | title_chars | meta_description | meta_chars | h1 | topic |" in prompt
    # The sweep's own result for the six checks travels with the prompt -
    # on this fixture, that it raised none of them.
    assert "- ONP/" in prompt or "the automatic checks raised none of the six checks" in prompt
    states = httpx.get(f"{base}/api/sites/{site_id}", timeout=30).json()["states"]
    mine = [s for s in states if s.get("brief") == "title-desc"]
    assert {s["check_id"] for s in mine} == {"title-length", "meta-desc-missing"}
    assert all(s["dimension"] == "ONP" and s["source_word"] == "brief" and s["proposed"] for s in mine)


_JS = """() => ({
  groups: [...document.querySelectorAll('.record-shape tr.group-row, tr.group-row')].map((tr) => ({
    key: (tr.querySelector('code')?.textContent || '').trim(),
    sources: (tr.querySelector('.group-sources')?.textContent || '').trim(),
  })),
  tagged: [...document.querySelectorAll('tr .tone-source-brief')].length,
  proposed: [...document.querySelectorAll('.proposed')].map((d) => d.textContent.trim()),
})"""


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            yield b
        finally:
            b.close()


@NEEDS_BROWSER
@pytest.mark.skipif(not (DIST / "index.html").is_file(), reason="dashboard not built")
def test_read_opens_the_report_the_record_counts_both_sources_and_the_part_shows_the_table(browser, served):
    base, site_id, run_id, got, _ = served
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    try:
        pg.goto(f"{base}/#/sites/{site_id}?tab=all", wait_until="load", timeout=30_000)
        pg.wait_for_selector("tr.group-row", timeout=30_000)
        pg.click('[aria-label="state filter"] [data-state="all"]')
        pg.wait_for_timeout(300)
        record = pg.evaluate(_JS)
        # Expand the title-length group: the brief's instance is tagged and
        # carries the proposed copy.
        pg.click('tr.group-row:has(code:text-is("ONP/title-length")) .group-toggle')
        pg.wait_for_selector(".proposed", timeout=15_000)
        opened = pg.evaluate(_JS)
        # The part page: a card per problem with the copy on it since brief
        # v13 step AO, and the report opened from the catalogue drawer,
        # which is where the Read button lives now.
        pg.goto(f"{base}/#/sites/{site_id}?tab=findings", wait_until="load", timeout=30_000)
        pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
        open_part(pg, 'Title & description')
        pg.wait_for_selector(".anat-pane .fix-card", timeout=15_000)
        table = pg.evaluate("""() => [...document.querySelectorAll('.anat-pane .fix-card')].map((c) => [
          c.querySelector('.fix-page code')?.textContent || '',
          c.querySelector('.fix-check')?.textContent || '',
          (c.querySelector('.fix-now s')?.textContent || '').trim(),
          ((c.querySelector('.fix-rep')?.textContent || '')
            + (c.querySelector('.fix-meta')?.textContent || '')).trim(),
          (c.querySelector('.fix-copy')?.textContent || '').trim(),
        ])""")
        pg.click(".anat-catalogue-open")
        pg.wait_for_selector(".catalogue-drawer", timeout=15_000)
        pg.click(".catalogue-drawer tr:has(code:text-is('title-desc')) button.btn-secondary")
        pg.wait_for_selector(".catalogue-drawer .report-view", timeout=15_000)
        report = pg.inner_text(".catalogue-drawer")
    finally:
        pg.close()
    by_key = {g["key"]: g["sources"] for g in record["groups"]}
    assert "ONP/title-length" in by_key and "ONP/meta-desc-missing" in by_key, by_key
    # The fixture's page passes the sweep's six checks, so both groups are
    # the brief's alone here; both sources on one line is asserted on the
    # contested fixture in `test_the_re_audit_column_puts_the_run_first.py`.
    assert opened["tagged"] >= 1 and any("What the fixture site does" in p for p in opened["proposed"]), opened
    assert len(table) == 2 and any("What the fixture site does" in row[3] and "chars" in row[3] for row in table), table
    assert all(row[4] == "copy replacement" for row in table), table
    assert "Title & description — assessment" in report and "```json" not in report
