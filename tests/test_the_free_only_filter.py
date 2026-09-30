"""`free only` — the filter that separates what the audit found for
nothing from what a model was paid to read (brief v17 step AV4).

Step AV3 split the checks table on `cost`; the fix cards were still one
undifferentiated list, so the half of AV3 that says "and the fix cards"
is closed here as well — a card is where an operator acts, and a screen
that costs the argument in its table and forgets it two blocks down has
not made the argument.

The filter itself is one piece of state, held in the address so a link
carries it: `&cost=free` collapses Analysis to its heading and count on
every part page, splits the sidebar's badge into what free work found and
what analysis added, and filters the Record. It never hides the heading -
"there are three more findings here and they cost money to see" is the
whole point, and a section that vanished would say the opposite.
"""

from __future__ import annotations

import json

import httpx
import pytest

from clauditseo.db.connection import connect
from clauditseo.persistence import repo, runs
from clauditseo.persistence.repo import create_id, now_iso
from tests.test_a11y_rendered import DIST
from tests.test_triage_ranks_the_section_rail import _serve
from tests.parts import ANATOMY_READY, open_part

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")

BASE = "https://costs.fixture"
HOME = BASE + "/"
ABOUT = BASE + "/about"
LONG = ("Costs Group is a privately owned full-service events company for clients seeking "
        "creative, impeccably designed and expertly executed events and travel experiences "
        "across the whole of Australia, for companies large and small alike, every year.")
GOOD = ("Costs Group plans and delivers corporate events and travel experiences for "
        "Australian companies, from boutique businesses to the largest brands.")


def _plant(db, site_id):
    """Two free findings and one that only a model could have raised.

    The two `meta-desc-*` rows are the sweep's: no brief is needed to know
    a description is missing or over the bound. `title-entity-alignment`
    is the part's one `model` check, and it is planted open rather than as
    a candidate because that is what it becomes on the second run - the
    state this screen has to render, not the one it passes through.
    """
    conn = connect(db)
    run_id = runs.create_run(conn, site_id, ["ONP"], "T2")
    pages = [{"url": HOME, "status": 200, "title": "Costs Group - Events - Australia",
              "meta_description": LONG, "canonical": HOME},
             {"url": ABOUT, "status": 200, "title": "About Costs Group",
              "meta_description": None, "canonical": ABOUT}]
    runs.store_evidence(conn, run_id, {"pages": pages})
    runs.mark_complete(conn, run_id, now_iso())
    planted = (("meta-desc-length", HOME, "sweep-home-len", "deterministic"),
               ("meta-desc-missing", ABOUT, "sweep-about-missing", "deterministic"),
               ("title-entity-alignment", HOME, "brief-home-align", "model-judgement"))
    with conn:
        for check, url, fp, source in planted:
            conn.execute(
                "INSERT INTO findings (id, run_id, dimension, check_id, severity, source,"
                " summary, affected_urls, fingerprint, created_at) VALUES (?, ?, 'ONP', ?,"
                " 'medium', ?, ?, ?, ?, ?)",
                (create_id(), run_id, check, source, f"{check} on {url}",
                 json.dumps([url]), fp, now_iso()))
            conn.execute(
                "INSERT INTO finding_states (site_id, fingerprint, state, changed_by_run,"
                " updated_at) VALUES (?, ?, 'open', ?, ?)", (site_id, fp, run_id, now_iso()))
    rows = [{"check": "ONP/title-entity-alignment", "dimension": "ONP",
             "check_id": "title-entity-alignment", "page": HOME, "status": "FAIL",
             "severity": "medium", "evidence": "the title names no entity",
             "replacement": GOOD, "note": ""}]
    runs.store_expert_report(conn, run_id, "title-desc", {
        "model": "claude-sonnet-5", "cost": 0.08,
        "report": "## Title & description — assessment\n"
                  "1 FAIL / 0 WARN / 0 not assessable / 2 pages assessed.\n",
        "findings": [],
        "contract": {"status": "read", "part": "title-desc", "rows": rows, "dropped": [],
                     "assumptions": [], "not_assessable": [], "uncovered": []}})
    conn.close()
    return run_id


@pytest.fixture(scope="module")
def served():
    server, thread, db, base = _serve("costs")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "Costs Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "costs.fixture"}, timeout=30).json()
        run_id = _plant(db, site["id"])
        yield base, site["id"], run_id
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_the_payload_says_what_each_of_the_parts_checks_costs(served):
    base, site_id, _ = served
    view = httpx.get(f"{base}/api/sites/{site_id}/anatomy", timeout=30).json()
    part = next(c for c in view["categories"] if c["key"] == "title-desc")
    costs = part["check_cost"]
    assert costs["ONP/title-entity-alignment"] == "model", costs
    assert {costs[c] for c in part["brief_checks"]
            if c != "ONP/title-entity-alignment"} == {"free"}, costs
    # And the three findings the screen must split are all in the record.
    # `["value"]`: the count carries its population since item 156.
    assert part["total"]["value"] == 3, part["total"]


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            yield b
        finally:
            b.close()


_JS = """() => {
  const pane = document.querySelector('.anat-pane');
  const heads = (sel) => [...document.querySelectorAll(sel)]
    .map((h) => h.textContent.trim());
  return {
    // The order the sections stand in, and what each of them holds.
    fixHeads: heads('.part-fixes .fixes-head'),
    checkHeads: heads('.part-checks .checks-head'),
    // A card, and which section it sits under: the nearest heading above.
    cards: [...document.querySelectorAll('.fix-card')].map((c) => {
      let el = c.previousElementSibling, head = '';
      for (let n = c; n && !head; n = n.previousElementSibling) {
        if (n.classList && n.classList.contains('fixes-head')) head = n.textContent.trim();
      }
      return { head, check: (c.querySelector('.fix-check')?.textContent || '').trim() };
    }),
    rows: [...document.querySelectorAll('.checks-table tbody tr')]
      .map((tr) => (tr.querySelector('code')?.textContent || '').trim()),
    chip: (document.querySelector('.legend-strip .cost-chip')?.textContent || '').trim(),
    chipOn: document.querySelector('.legend-strip .cost-chip')?.getAttribute('aria-pressed'),
    // The part's count and its free / analysis split stand on the shop's
    // part header since brief v24 step BO.
    badges: [...document.querySelectorAll('.catalogue-shop .crow-part')]
      .map((b) => `${(b.querySelector('.crow-part-link')?.textContent || '').trim()}|`
                  + `${(b.querySelector('.crow-part-open .count, .crow-part-open')?.textContent || '').replace(/[^0-9]/g, '')}|`
                  + `${(b.querySelector('.sb-model')?.textContent || '').trim()}`),
    hash: window.location.hash,
    text: (pane?.textContent || ''),
  };
}"""


def _open(pg, base, site_id):
    pg.goto(f"{base}/#/sites/{site_id}?tab=findings", wait_until="load", timeout=30_000)
    pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
    open_part(pg, 'Title & description')
    pg.wait_for_selector(".part-page", timeout=15_000)


@NEEDS_BROWSER
@pytest.mark.skipif(not (DIST / "index.html").is_file(), reason="dashboard not built")
def test_the_fixes_are_free_checks_then_analysis(browser, served):
    """AV3's other half: the cards carry the same argument as the table."""
    base, site_id, _ = served
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    try:
        _open(pg, base, site_id)
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    assert [h.split("·")[0].strip() for h in got["fixHeads"]] \
        == ["Free checks", "Analysis"], got["fixHeads"]
    assert "2" in got["fixHeads"][0] and "1" in got["fixHeads"][1], got["fixHeads"]
    under = {c["check"]: c["head"] for c in got["cards"]}
    assert under.get("ONP/title-entity-alignment", "").startswith("Analysis"), under
    assert under.get("ONP/meta-desc-length", "").startswith("Free checks"), under


@NEEDS_BROWSER
@pytest.mark.skipif(not (DIST / "index.html").is_file(), reason="dashboard not built")
def test_free_only_collapses_analysis_and_is_named_in_the_address(browser, served):
    base, site_id, _ = served
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    try:
        _open(pg, base, site_id)
        before = pg.evaluate(_JS)
        assert before["chip"].startswith("free only"), before["chip"]
        assert before["chipOn"] == "false", before["chipOn"]
        assert "ONP/title-entity-alignment" in before["rows"], before["rows"]
        pg.click(".legend-strip .cost-chip")
        pg.wait_for_function(
            "() => document.querySelector('.legend-strip .cost-chip')"
            "?.getAttribute('aria-pressed') === 'true'", timeout=10_000)
        after = pg.evaluate(_JS)
        # Pressed again, the filter goes - and goes out of the address too.
        pg.click(".legend-strip .cost-chip")
        pg.wait_for_function(
            "() => document.querySelector('.legend-strip .cost-chip')"
            "?.getAttribute('aria-pressed') === 'false'", timeout=10_000)
        cleared = pg.evaluate(_JS)
    finally:
        pg.close()
    assert "cost=free" in after["hash"], after["hash"]
    # The heading and its count stay: "three more findings, and they cost
    # money to see" is the whole reason for the filter.
    assert [h.split("·")[0].strip() for h in after["checkHeads"]] \
        == ["Free checks", "Analysis"], after["checkHeads"]
    assert "ONP/title-entity-alignment" not in after["rows"], after["rows"]
    assert "ONP/meta-desc-length" in after["rows"], after["rows"]
    assert not [c for c in after["cards"] if c["head"].startswith("Analysis")], after["cards"]
    assert [c for c in after["cards"] if c["head"].startswith("Free checks")], after["cards"]
    assert "cost=" not in cleared["hash"], cleared["hash"]
    assert "ONP/title-entity-alignment" in cleared["rows"], cleared["rows"]


@NEEDS_BROWSER
@pytest.mark.skipif(not (DIST / "index.html").is_file(), reason="dashboard not built")
def test_the_shop_header_says_what_free_found_and_what_analysis_added(browser, served):
    base, site_id, _ = served
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    try:
        pg.goto(f"{base}/#/sites/{site_id}?tab=findings", wait_until="load", timeout=30_000)
        pg.wait_for_selector(".catalogue-shop .crow-part-open", timeout=30_000)
        before = pg.evaluate(_JS)
        pg.click(".legend-strip .cost-chip")
        pg.wait_for_function(
            "() => document.querySelector('.legend-strip .cost-chip')"
            "?.getAttribute('aria-pressed') === 'true'", timeout=10_000)
        after = pg.evaluate(_JS)
    finally:
        pg.close()
    mine = [b for b in before["badges"] if b.startswith("Title & description|")]
    assert mine == ["Title & description|3|"], mine
    mine = [b for b in after["badges"] if b.startswith("Title & description|")]
    assert mine == ["Title & description|2|+1 analysis"], mine
    # A part with no analysis of its own says nothing extra - "+0 analysis"
    # is furniture on every other row of the list.
    assert not [b for b in after["badges"]
                if b.endswith("|+0 analysis")], after["badges"]


@NEEDS_BROWSER
@pytest.mark.skipif(not (DIST / "index.html").is_file(), reason="dashboard not built")
def test_the_record_offers_free_and_analysis_as_chips(browser, served):
    base, site_id, _ = served
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    try:
        pg.goto(f"{base}/#/sites/{site_id}?tab=all", wait_until="load", timeout=30_000)
        pg.wait_for_selector(".cost-filters .chip", timeout=30_000)
        # A RACE, and it was here before this clause ever failed. The chips
        # render as soon as the SITE payload lands - they are the record's own
        # rows - but their counts come from the ANATOMY payload, which carries
        # `check_cost` and arrives separately. Read between the two, every row
        # reads `free`, because `checkCost` falls back to free for a check the
        # map does not hold: the observed failure was `free 3 · analysis 0`
        # against `free 2 · analysis 1`, the same three rows with the model one
        # misfiled. Waiting on the sidebar's leaves is waiting on the anatomy
        # payload, which is what the counts actually depend on.
        pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
        pg.wait_for_function(
            "() => [...document.querySelectorAll('.cost-filters .chip')]"
            ".some((c) => !/ 0$/.test(c.textContent.trim()))", timeout=15_000)
        chips = pg.eval_on_selector_all(
            ".cost-filters .chip", "els => els.map((e) => e.textContent.trim())")
        pg.click(".cost-filters .chip[data-cost='model']")
        pg.wait_for_function(
            "() => document.querySelector(\".cost-filters .chip[data-cost='model']\")"
            "?.getAttribute('aria-pressed') === 'true'", timeout=10_000)
        checks = pg.eval_on_selector_all(
            ".table-scroll .findings tbody code",
            "els => [...new Set(els.map((e) => e.textContent.trim()))]")
    finally:
        pg.close()
    assert [c.split()[0] for c in chips] == ["free", "analysis"], chips
    assert chips[0].endswith("2") and chips[1].endswith("1"), chips
    assert [c for c in checks if "title-entity-alignment" in c], checks
    assert not [c for c in checks if "meta-desc" in c], checks
