"""The one-page Structured data view lists that page's eligibility, and the
site view lists each verdict once with the pages it covers (item 242).

The operator, on Structured data narrowed to `/`: "Is this duplicating
information? This is only one page selected for the schema." Under the
picture were ~55 rows, one per page the analysis judged, none naming its
page - so a verdict that held on 14 pages read as one line said 14 times,
and only the first was about `/`.

  - The page view's graph carries the rows whose page is the page in view,
    and the screen draws exactly those.
  - The site view draws each (rich result, verdict, reason) once, with its
    page count, opening to the pages.
  - The graph's entity verdict reads this page's markup alone, and says so;
    where the sweep's id checks are raised on the page, it says the
    automatic checks disagree rather than drawing the verdict as settled.
"""

from __future__ import annotations

import json

import httpx
import pytest

from clauditseo.db.connection import connect
from clauditseo.persistence import runs
from clauditseo.persistence.repo import create_id, now_iso
from tests.parts import ANATOMY_READY, open_part
from tests.test_a11y_rendered import DIST
from tests.test_the_structured_data_picture_is_drawn import (
    NEEDS_BROWSER, RICH, SITE, THREE, _open, _plant)
from tests.test_triage_ranks_the_section_rail import _serve

OTHER = f"https://{SITE}/blog/post"
DEGRADED = ("Article (BlogPosting)", "ELIGIBLE BUT DEGRADED", "BlogPosting node has no @id")

#: Four rows over three pages. The degraded Article verdict holds on two of
#: them, word for word - the shape that read as a duplicate on screen.
ELIGIBILITY = [
    {"page": RICH, "rich_result": "LocalBusiness", "verdict": "ELIGIBLE",
     "reason": "all required properties present"},
    {"page": THREE, "rich_result": DEGRADED[0], "verdict": DEGRADED[1], "reason": DEGRADED[2]},
    {"page": OTHER, "rich_result": DEGRADED[0], "verdict": DEGRADED[1], "reason": DEGRADED[2]},
    {"page": OTHER, "rich_result": "none", "verdict": "NONE TARGETED",
     "reason": "service-type page has no Service node"},
]


def _plant_eligibility(db, site_id: str) -> None:
    """The structured-data analysis's stored answer, and one sweep id check
    raised on the rich page and nowhere else."""
    conn = connect(db)
    run_id = conn.execute("SELECT id FROM audit_runs WHERE site_id = ?",
                          (site_id,)).fetchone()[0]
    with conn:
        conn.execute(
            "INSERT INTO expert_reports (run_id, tool_id, model_id, report, findings,"
            " created_at, contract) VALUES (?, 'structured-data', 'm', '', '[]', ?, ?)",
            (run_id, now_iso(), json.dumps({"eligibility": ELIGIBILITY})))
        conn.execute(
            "INSERT INTO findings (id, run_id, dimension, check_id, severity, source,"
            " summary, affected_urls, fingerprint, created_at, evidence)"
            " VALUES (?, ?, 'ONP', 'schema-duplicate-id', 'medium', 'deterministic',"
            " '@id #organization is declared by 2 entities', ?, 'sg-dup', ?, '{}')",
            (create_id(), run_id, json.dumps([RICH]), now_iso()))
        conn.execute(
            "INSERT INTO finding_states (site_id, fingerprint, state, changed_by_run,"
            " updated_at) VALUES (?, 'sg-dup', 'open', ?, ?)",
            (site_id, run_id, now_iso()))
    conn.close()


@pytest.fixture(scope="module")
def served():
    server, thread, db, base = _serve("sgelig")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "Eligibility Co"},
                            timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": SITE}, timeout=30).json()
        _plant(db, site["id"])
        _plant_eligibility(db, site["id"])
        yield base, site["id"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def _schema(base: str, site_id: str, page: str | None = None) -> dict:
    view = httpx.get(f"{base}/api/sites/{site_id}/anatomy",
                     params={"page": page} if page else {}, timeout=30).json()
    return next(c for c in view["categories"] if c["key"] == "schema")


def test_the_page_views_graph_carries_only_that_pages_rows(served):
    base, site_id = served
    rich = _schema(base, site_id, RICH)["graph"]["eligibility"]
    assert [e["page"] for e in rich] == [RICH], rich
    three = _schema(base, site_id, THREE)["graph"]["eligibility"]
    assert [e["page"] for e in three] == [THREE], three
    # The site view still has the whole list: the grouped card reads it.
    assert len(_schema(base, site_id)["brief_eligibility"]) == len(ELIGIBILITY)


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            yield b
        finally:
            b.close()


_PAGE_JS = """() => ({
  rows: [...document.querySelectorAll('.sg-eligibility li')].map((l) => l.textContent.trim()),
  verdict: (document.querySelector('.sg-verdict')?.textContent || '').trim(),
  disputed: !!document.querySelector('.sg-verdict .sg-disputed'),
})"""


@NEEDS_BROWSER
@pytest.mark.skipif(not (DIST / "index.html").is_file(), reason="dashboard not built")
def test_the_page_view_draws_the_pages_rows_and_says_whose_verdict_it_is(browser, served):
    base, site_id = served
    pg = browser.new_page(viewport={"width": 1440, "height": 900})
    try:
        _open(pg, base, site_id, RICH)
        got = pg.evaluate(_PAGE_JS)
        assert len(got["rows"]) == 1 and got["rows"][0].startswith("LocalBusiness"), got
        assert "(this page’s markup)" in got["verdict"], got["verdict"]
        # The sweep raised schema-duplicate-id on this page.
        assert got["disputed"], got["verdict"]
        assert "automatic checks disagree on this page" in got["verdict"]

        _open(pg, base, site_id, THREE)
        got = pg.evaluate(_PAGE_JS)
        assert len(got["rows"]) == 1 and got["rows"][0].startswith(DEGRADED[0]), got
        # Nothing is raised on this page, so the verdict stands on its own.
        assert not got["disputed"], got["verdict"]
    finally:
        pg.close()


_SITE_JS = """() => {
  const card = document.querySelector('.sd-site');
  if (!card) return null;
  const lines = [...card.querySelectorAll('.sd-eligibility > li')];
  return {
    entity: (card.querySelector('.sd-entity')?.textContent || ''),
    lines: lines.map((l) => ({
      head: [...l.childNodes].filter((n) => !(n instanceof HTMLDetailsElement))
                              .map((n) => n.textContent).join('').trim(),
      count: (l.querySelector('summary')?.textContent || '').trim(),
      pages: [...l.querySelectorAll('details li button')].map((b) => b.textContent.trim()),
    })),
  };
}"""


@NEEDS_BROWSER
@pytest.mark.skipif(not (DIST / "index.html").is_file(), reason="dashboard not built")
def test_the_site_view_says_each_verdict_once_with_its_pages(browser, served):
    base, site_id = served
    pg = browser.new_page(viewport={"width": 1440, "height": 900})
    try:
        pg.goto(f"{base}/#/sites/{site_id}?tab=findings", wait_until="load", timeout=30_000)
        pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
        open_part(pg, "Structured data")
        pg.wait_for_selector(".sd-site", timeout=15_000)
        got = pg.evaluate(_SITE_JS)
        heads = [line["head"] for line in got["lines"]]
        assert len(heads) == len(set(heads)) == 3, heads
        for line in got["lines"]:
            assert line["count"] and len(line["pages"]) == int(line["count"].split()[0]), line
        degraded = next(line for line in got["lines"] if DEGRADED[2] in line["head"])
        assert degraded["count"] == "2 pages", degraded
        assert sorted(degraded["pages"]) == ["/blog/post", "/three-blocks"], degraded
        # Worst first: the degraded verdict leads the eligible one.
        assert DEGRADED[1] in got["lines"][0]["head"], heads
    finally:
        pg.close()
