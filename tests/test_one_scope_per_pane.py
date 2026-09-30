"""One scope per pane (brief v12 step AM): narrowing to a page applies to
every block on the part page - the cause rows' counts, pages and source
tags, the `N findings` column and the replacement table all read the
narrowed record; a `narrowed to /path ×` chip stands in the legend strip
on every pane while the narrow is on, and the sidebar head says whose
counts these are; brief-only rows the sweep has not corroborated are
shown in the cause table and the replacement table alike, tagged
`candidate`, so the two agree on the count.
"""

from __future__ import annotations

import json

import httpx
import pytest

from clauditseo.db.connection import connect
from clauditseo.persistence import runs
from clauditseo.persistence.repo import create_id, now_iso
from tests.test_a11y_rendered import DIST
from tests.test_triage_ranks_the_section_rail import _serve
from tests.parts import ANATOMY_READY, open_part, open_page_filter

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")

pytestmark = [
    NEEDS_BROWSER,
    pytest.mark.skipif(not (DIST / "index.html").is_file(),
                       reason="dashboard not built (npm run build in dashboard/)"),
]

BASE = "https://scope.fixture"
DESC = ("A description of the about page that says what it delivers, written in active "
        "voice and long enough for the window the sweep measures.")


def _row(check_id, page, replacement):
    return {"check": f"ONP/{check_id}", "dimension": "ONP", "check_id": check_id,
            "page": page, "status": "FAIL", "severity": "medium", "evidence": "x",
            "replacement": replacement, "note": ""}


def _plant(db, site_id):
    """Two pages. The sweep raised meta-desc-missing on /about; the brief
    raised title-length on / (uncorroborated: a candidate) and
    meta-desc-missing on /about (corroborated: open)."""
    conn = connect(db)
    run_id = runs.create_run(conn, site_id, ["ONP"], "T2")
    runs.store_evidence(conn, run_id, {"pages": [{"url": BASE + "/", "status": 200},
                                                  {"url": BASE + "/about", "status": 200}]})
    runs.mark_complete(conn, run_id, now_iso())
    with conn:
        conn.execute(
            "INSERT INTO findings (id, run_id, dimension, check_id, severity, source, summary,"
            " affected_urls, fingerprint, created_at) VALUES (?, ?, 'ONP', 'meta-desc-missing',"
            " 'medium', 'deterministic', 'no description', ?, 'sweep-about', ?)",
            (create_id(), run_id, json.dumps([BASE + "/about"]), now_iso()))
        # The sweep's row has a state, as it would after a real run.
        conn.execute(
            "INSERT INTO finding_states (site_id, fingerprint, state, changed_by_run, updated_at)"
            " VALUES (?, 'sweep-about', 'open', ?, ?)", (site_id, run_id, now_iso()))
    rows = [_row("title-length", BASE + "/", "What the fixture site does, and where - Fixture"),
            _row("meta-desc-missing", BASE + "/about", DESC)]
    runs.store_expert_report(conn, run_id, "title-desc", {
        "model": "stub", "report": "### Title & description — assessment\ntwo rows.", "findings": [],
        "contract": {"status": "read", "part": "title-desc", "rows": rows, "dropped": [],
                     "assumptions": [], "not_assessable": [], "uncovered": []}})
    runs.record_contract_findings(conn, run_id, "title-desc", "stub", rows)
    runs.recompute_contract_states(conn, site_id, "title-desc")
    conn.close()
    return run_id


@pytest.fixture(scope="module")
def served():
    server, thread, db, base = _serve("scope")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "Scope Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "scope.fixture"}, timeout=30).json()
        run_id = _plant(db, site["id"])
        yield base, site["id"], run_id
    finally:
        server.should_exit = True
        thread.join(timeout=10)


_JS = """() => ({
  causes: [...document.querySelectorAll('.anat-pane .checks-table tbody tr')].map((tr) => {
    const td = [...tr.querySelectorAll('td')];
    return {
      check: (td[1]?.textContent || '').trim(),
      tags: [['sweep', td[2]], ['brief', td[3]]]
        .filter(([, c]) => c && c.textContent.trim() !== '\u2014')
        .map(([w, c]) => `${w} ${c.textContent.trim()}`),
      pages: (td[4]?.textContent || '').trim(),
      state: (td[5]?.textContent || '').trim(),
      clean: false,
    };
  }),
  reps: [...document.querySelectorAll('.anat-pane .fix-card')].map((c) => ({
    page: (c.querySelector('.fix-page code')?.textContent || '').trim(),
    candidate: !!c.querySelector('.tone-state-candidate'),
  })),
  // One per section since brief v17 step AV3; joined, for the reason
  // the other two clauses reading this line record.
  clean: [...document.querySelectorAll('.anat-pane .cause-clean-line')]
    .map((p) => p.textContent.trim()).join(' '),
  cards: document.querySelectorAll('.anat-pane .fix-card').length,
  chip: (document.querySelector('.legend-strip .legend-narrow')?.textContent || '').trim(),
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


def _open_part(pg, base, site_id):
    pg.goto(f"{base}/#/sites/{site_id}?tab=findings", wait_until="load", timeout=30_000)
    pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
    open_part(pg, 'Title & description')
    pg.wait_for_selector(".anat-pane .fix-card", timeout=15_000)


def test_candidates_are_shown_and_tagged_in_both_tables_and_the_narrow_reaches_every_block(browser, served):
    base, site_id, _ = served
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    try:
        _open_part(pg, base, site_id)
        whole = pg.evaluate(_JS)
        # Narrow to the home page through the pane's own control.
        open_page_filter(pg)
        pg.fill(".page-find", "/")
        try:
            pg.wait_for_function(
                "() => document.querySelector('.legend-strip .legend-narrow') !== null", timeout=15_000)
            pg.wait_for_function(
                "() => document.querySelectorAll('.anat-pane .fix-card').length === 1",
                timeout=15_000)
            # The narrowed payload has landed once the other page's check
            # has left the fixes for the clean line (brief v12 step AN).
            pg.wait_for_function(
                "() => [...document.querySelectorAll('.anat-pane .cause-clean-line')]"
                ".map((p) => p.textContent).join(' ')"
                ".includes('meta-desc-missing')", timeout=15_000)
        except Exception as e:      # say what the screen holds, not only that it timed out
            raise AssertionError((str(e).splitlines()[0], pg.evaluate(_JS)))
        narrowed = pg.evaluate(_JS)
        # The chip stands on every pane while the narrow is on.
        chips = {}
        # The scope is in the address since brief v23 step BK, so the pane
        # address carries it: a hand-typed `?tab=` with no `page=` is site mode
        # by design now, where before a same-document goto kept React state.
        scope = pg.evaluate(
            "() => new URLSearchParams(location.hash.split('?')[1] || '').get('page')")
        assert scope, "narrowing did not put the page in the address"
        # And the part, since brief v24 step BM: it is the address's too.
        part = pg.evaluate(
            "() => new URLSearchParams(location.hash.split('?')[1] || '').get('part')")
        assert part, "opening the part did not put it in the address"
        from urllib.parse import quote
        for tab in ("precheck", "history", "all", "findings"):
            pg.goto(f"{base}/#/sites/{site_id}?tab={tab}&part={part}&page={quote(scope, safe='')}",
                    wait_until="load", timeout=30_000)
            pg.wait_for_selector(".legend-strip", timeout=15_000)
            chip = pg.locator(".legend-strip .legend-narrow")
            chips[tab] = (chip.count(), chip.inner_text() if chip.count() else "")
        # Its × clears the narrow.
        pg.click(".legend-strip .legend-narrow-clear")
        pg.wait_for_function(
            "() => document.querySelector('.legend-strip .legend-narrow') === null", timeout=15_000)
        cleared = pg.evaluate(_JS)
    finally:
        pg.close()

    # Whole site: the uncorroborated row is a candidate - counted and tagged
    # on its cause row, and tagged in the replacement table, so the two
    # agree; the corroborated one carries both sources and no tag.
    by = {c["check"]: c for c in whole["causes"]}
    tl, md = by["ONP/title-length"], by["ONP/meta-desc-missing"]
    assert tl["tags"] == ["brief 1"] and tl["pages"] == "1", tl
    assert tl["state"] == "candidate", tl
    assert md["tags"] == ["sweep 1", "brief 1"] and md["pages"] == "1" and md["state"] == "open", md
    # Four free and one analysis since brief v17 step AV3: the sections
    # count apart, because a reader asking "what did the free pass find"
    # is owed its own answer rather than a total that mixes the two.
    # The absence claim carries its population too (item 155): clean on
    # every page THIS RUN FETCHED, not over a record that includes pages
    # nobody looked at.
    assert whole["clean"].startswith("4 checks clean on every page this audit fetched"), whole["clean"]
    assert "1 check clean on every page this audit fetched" in whole["clean"], whole["clean"]
    assert "title-entity-alignment" in whole["clean"], whole["clean"]
    assert sorted((r["page"], r["candidate"]) for r in whole["reps"]) == [("/", True), ("/about", False)]
    # The sidebar head's "counts for /..." went with the sidebar (brief v24
    # step BO; channel ruling 2026-09-15, item 6).
    assert whole["chip"] == ""

    # Narrowed to `/`: only that page's rows, on every block.
    assert narrowed["reps"] == [{"page": "/", "candidate": True}], narrowed["reps"]
    # Narrowed, the checks table gives way to the page's own card.
    assert narrowed["causes"] == [] and narrowed["cards"] == 1, narrowed
    assert narrowed["clean"].startswith("6 checks pass on this page: "), narrowed["clean"]
    assert narrowed["chip"].startswith("narrowed to /"), narrowed["chip"]
    for tab, (n, text) in chips.items():
        assert n == 1 and " ".join(text.split()).startswith("narrowed to /"), (tab, n, text)
    assert cleared["chip"] == "" and len(cleared["reps"]) == 2
