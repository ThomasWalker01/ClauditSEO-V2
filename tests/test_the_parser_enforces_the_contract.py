"""The parser enforces the contract it was given (brief v12 step AL): a
replacement beginning `[TO CONFIRM` moves its row to `not_assessable` with
the bracket's text as `needs`; an alignment row without the GBP primary
category (or, on a location page, the location entity) is `not_assessable`
naming the input whatever the brief wrote; a replacement outside the part's
bounds is dropped with the measurement; under `triple` a title using `|` is
dropped; a stored contract can be re-judged under the rules without a
model call, and the report row, the record and the states follow; the
stored report carries its contract; and the part page counts what the
replacement table does not show.
"""

from __future__ import annotations

import json
import sqlite3

import httpx
import pytest

from clauditseo.analysts import contract
from clauditseo.analysts.expert import contract_rules, reparse_contract
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.engine.types import Site
from clauditseo.modules.onp import TITLE_TARGET_MAX, TITLE_TARGET_MIN
from clauditseo.persistence import repo, runs
from tests.test_a11y_rendered import DIST
from tests.test_triage_ranks_the_section_rail import _serve
from tests.parts import ANATOMY_READY, open_part

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")

BASE = "https://birch.fixture"
PAGES = [BASE + "/", BASE + "/about", BASE + "/richmond", BASE + "/team", BASE + "/events"]
CHECKS = ["ONP/title-entity-alignment", "ONP/meta-desc-missing", "ONP/meta-desc-length",
          "ONP/title-length"]
DESC_OK = ("Meet the team who plan and deliver the events and travel experiences for clients "
           "across Australia, with a named lead on every brief.")            # 135 chars
DESC_SHORT = "Meet the team who plan and deliver the travel experiences for clients across Australia now."
DESC_LONG = DESC_OK + " And a little more besides, to be sure of the ceiling."
assert 120 <= len(DESC_OK) <= 160 and len(DESC_SHORT) < 120 and len(DESC_LONG) > 160


def _row(check, page, replacement, **extra):
    return {"check": check, "page": page, "status": "FAIL", "severity": "MEDIUM",
            "evidence": "x", "replacement": replacement, **extra}


def _parse(rows, rules, strategy=None, not_assessable=None):
    block = {"rows": rows, "not_assessable": not_assessable or []}
    if strategy:
        block["strategy"] = strategy
    return contract.parse("```json\n" + json.dumps(block) + "\n```\n", CHECKS, PAGES, rules=rules)


def test_the_rules_come_from_the_registry_and_the_site_record():
    site = Site(domain="birch.fixture", gbp_primary_category="Events Company",
                title_strategy="neighbourhood",
                location_pages=[{"url": "/richmond", "location_entity": "Richmond Victoria"}])
    r = contract_rules(site)
    assert r.title_bounds == (TITLE_TARGET_MIN, TITLE_TARGET_MAX) == (30, 60)
    assert r.desc_bounds == (120, 160) and r.neighbourhood_ceiling == 240
    assert r.strategy == "neighbourhood" and r.gbp_primary_category == "Events Company"
    assert r.location_entities == {"/richmond": "Richmond Victoria"}
    # The block's own strategy wins over the record's.
    assert contract_rules(site, "triple").strategy == "triple"
    assert contract_rules(Site(domain="x")).strategy == "triple"


def test_a_to_confirm_replacement_moves_its_row_to_not_assessable():
    got = _parse([_row("ONP/meta-desc-missing", "/team",
                       "[TO CONFIRM: page has enough distinct content to describe]"),
                  _row("ONP/meta-desc-missing", "/about", DESC_OK)],
                 contract_rules(Site(domain="birch.fixture")))
    assert [r.page for r in got.rows] == [BASE + "/about"]
    assert got.not_assessable == [{"check": "ONP/meta-desc-missing", "page": "/team",
                                   "needs": "page has enough distinct content to describe"}]
    assert not got.dropped
    # Nothing to store, so nothing to copy: the row is not in `rows`.
    assert not any(r.replacement and r.replacement.startswith("[TO") for r in got.rows)


def test_an_alignment_row_needs_the_gbp_category_and_a_location_page_its_entity():
    title = "Birch Group - Events Company - Richmond Victoria"   # 48 chars, `-`
    rows = [_row("ONP/title-entity-alignment", "/", "Travel and Events Company - Birch Group", page_type="other"),
            _row("ONP/title-entity-alignment", "/richmond", title, page_type="location")]
    # No category on the record: every alignment row is not assessable,
    # whatever the brief graded - and a row the brief already listed there
    # is not listed twice.
    got = _parse(rows, contract_rules(Site(domain="birch.fixture")),
                 not_assessable=[{"check": "ONP/title-entity-alignment", "page": "/",
                                  "needs": "GBP primary category"}])
    assert not got.rows and not got.dropped
    assert got.not_assessable == [
        {"check": "ONP/title-entity-alignment", "page": "/", "needs": "GBP primary category"},
        {"check": "ONP/title-entity-alignment", "page": "/richmond", "needs": "GBP primary category"}]
    # The category set, the location page still needs its entity.
    got = _parse(rows, contract_rules(Site(domain="birch.fixture", gbp_primary_category="Events Company")))
    assert [r.page for r in got.rows] == [BASE + "/"]
    assert got.not_assessable == [{"check": "ONP/title-entity-alignment", "page": "/richmond",
                                   "needs": "location entity for /richmond"}]
    # Both supplied: both rows stand.
    got = _parse(rows, contract_rules(Site(
        domain="birch.fixture", gbp_primary_category="Events Company",
        location_pages=[{"url": "/richmond", "location_entity": "Richmond Victoria"}])))
    assert len(got.rows) == 2 and not got.not_assessable and not got.dropped


def test_a_replacement_outside_the_bounds_is_dropped_with_the_measurement():
    rules = contract_rules(Site(domain="birch.fixture", gbp_primary_category="Events Company"))
    got = _parse([_row("ONP/meta-desc-missing", "/team", DESC_SHORT),                  # 91 < 120
                  _row("ONP/meta-desc-length", "/", DESC_LONG),
                  _row("ONP/title-entity-alignment", "/about", "About - Birch Group", page_type="other"),  # 19 < 30
                  _row("ONP/title-length", "/", "keep"),
                  _row("ONP/meta-desc-missing", "/about", DESC_OK)], rules)
    reasons = [d["reason"] for d in got.dropped]
    assert reasons == [f"replacement outside bounds ({len(DESC_SHORT)} < 120)",
                       f"replacement outside bounds ({len(DESC_LONG)} > 160)",
                       "replacement outside bounds (19 < 30)"], reasons
    assert [d["row"]["page"] for d in got.dropped] == [BASE + "/team", BASE + "/", BASE + "/about"]
    assert [r.page for r in got.rows] == [BASE + "/", BASE + "/about"]     # `keep` is exempt


def test_under_neighbourhood_the_ceiling_is_soft_on_location_and_service_pages():
    rules = contract_rules(Site(domain="birch.fixture", gbp_primary_category="Events Company",
                                title_strategy="neighbourhood"))
    long_title = "Birch Group - Events Company - Richmond Victoria, " + ", ".join(
        ["Hawthorn", "Kew", "Abbotsford", "Collingwood", "Fitzroy", "Carlton"]) + " events"  # ~110 chars
    got = _parse([_row("ONP/title-entity-alignment", "/richmond", long_title, page_type="service"),
                  _row("ONP/title-entity-alignment", "/about", long_title, page_type="other")], rules)
    assert [r.page for r in got.rows] == [BASE + "/richmond"]
    assert got.dropped[0]["reason"] == f"replacement outside bounds ({len(long_title)} > 60)"


def test_under_triple_a_title_with_a_pipe_is_dropped():
    rules = contract_rules(Site(domain="birch.fixture", gbp_primary_category="Events Company"))
    got = _parse([_row("ONP/title-entity-alignment", "/", "Birch Group | Travel and Events Company",
                       page_type="other"),
                  _row("ONP/title-entity-alignment", "/about", "About the Birch Group - Birch Group",
                       page_type="other")], rules)
    assert [r.page for r in got.rows] == [BASE + "/about"]
    assert got.dropped[0]["reason"] == 'replacement uses "|" where the triple strategy says "-"'
    # Under `neighbourhood` the separator rule does not apply.
    got = _parse([_row("ONP/title-entity-alignment", "/", "Birch Group | Travel and Events Company",
                       page_type="other")], rules, strategy="neighbourhood")
    assert len(got.rows) == 1 and not got.dropped


# --- the reparse, the record and the screen ------------------------------

BIRCH_ROWS = [
    # As the Birch run stored them, in shape: an alignment row with a pipe
    # and no category on the record, two `[TO CONFIRM` descriptions, one
    # short description, one that passes.
    {"check": "ONP/title-entity-alignment", "dimension": "ONP", "check_id": "title-entity-alignment",
     "page": BASE + "/", "status": "FAIL", "severity": "medium", "evidence": "x",
     "replacement": "Birch Group | Travel & Events", "note": "", "extra": {"page_type": "other"}},
    {"check": "ONP/meta-desc-missing", "dimension": "ONP", "check_id": "meta-desc-missing",
     "page": BASE + "/events", "status": "FAIL", "severity": "medium", "evidence": "x",
     "replacement": "[TO CONFIRM: page has enough distinct content to describe]", "note": ""},
    {"check": "ONP/meta-desc-missing", "dimension": "ONP", "check_id": "meta-desc-missing",
     "page": BASE + "/richmond", "status": "FAIL", "severity": "medium", "evidence": "x",
     "replacement": "[TO CONFIRM: page has enough distinct content to describe]", "note": ""},
    {"check": "ONP/meta-desc-missing", "dimension": "ONP", "check_id": "meta-desc-missing",
     "page": BASE + "/team", "status": "FAIL", "severity": "medium", "evidence": "x",
     "replacement": DESC_SHORT, "note": ""},
    {"check": "ONP/meta-desc-missing", "dimension": "ONP", "check_id": "meta-desc-missing",
     "page": BASE + "/about", "status": "FAIL", "severity": "medium", "evidence": "x",
     "replacement": DESC_OK, "note": ""},
]


def _plant(conn: sqlite3.Connection, site_id: str) -> str:
    """A run with the five pages, a sweep row on /about, and a stored
    Title & description contract with the rows as the old parser kept them."""
    from clauditseo.persistence.repo import create_id, now_iso
    run_id = runs.create_run(conn, site_id, ["ONP"], "T2")
    runs.store_evidence(conn, run_id, {"pages": [{"url": u, "status": 200} for u in PAGES]})
    runs.mark_complete(conn, run_id, now_iso())
    with conn:
        conn.execute(
            "INSERT INTO findings (id, run_id, dimension, check_id, severity, source, summary,"
            " affected_urls, fingerprint, created_at) VALUES (?, ?, 'ONP', 'meta-desc-missing',"
            " 'medium', 'deterministic', 'no description', ?, 'sweep-about', ?)",
            (create_id(), run_id, json.dumps([BASE + "/about"]), now_iso()))
        # The sweep also raised /events, whose row moves to not_assessable:
        # an answer about the page, so not an omission of it.
        conn.execute(
            "INSERT INTO findings (id, run_id, dimension, check_id, severity, source, summary,"
            " affected_urls, fingerprint, created_at) VALUES (?, ?, 'ONP', 'meta-desc-missing',"
            " 'medium', 'deterministic', 'no description', ?, 'sweep-events', ?)",
            (create_id(), run_id, json.dumps([BASE + "/events"]), now_iso()))
    runs.store_expert_report(conn, run_id, "title-desc", {
        "model": "stub", "report": "### Title & description — assessment\nfive rows.", "findings": [],
        "contract": {"status": "read", "part": "title-desc", "strategy": "triple",
                     "rows": BIRCH_ROWS, "dropped": [], "assumptions": [], "not_assessable": [],
                     "uncovered": []}})
    runs.record_contract_findings(conn, run_id, "title-desc", "stub", BIRCH_ROWS)
    runs.recompute_contract_states(conn, site_id, "title-desc")
    return run_id


def test_the_reparse_rewrites_the_stored_contract_the_record_and_the_states(tmp_path):
    conn = connect(tmp_path / "reparse.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Birch Co")
    site_id = repo.create_site(conn, client, "birch.fixture")
    run_id = _plant(conn, site_id)
    assert len([s for s in runs.site_states(conn, site_id) if s["source_word"] == "brief"]) == 5

    got = reparse_contract(conn, run_id, "title-desc", Site(domain="birch.fixture"))
    assert got["reparsed"] is True
    assert [r["page"] for r in got["rows"]] == [BASE + "/about"]
    assert [(n["page"], n["needs"]) for n in got["not_assessable"]] == [
        ("/", "GBP primary category"),
        ("/events", "page has enough distinct content to describe"),
        ("/richmond", "page has enough distinct content to describe")]
    assert [d["reason"] for d in got["dropped"]] == [f"replacement outside bounds ({len(DESC_SHORT)} < 120)"]
    assert got["uncovered"] == [], got["uncovered"]
    # The report row carries the same contract out, and only the kept row
    # is a finding in the record - corroborated by the sweep, so open.
    stored = runs.expert_report(conn, run_id, "title-desc")
    assert stored["contract"]["dropped"] == got["dropped"] and len(stored["findings"]) == 1
    brief = [s for s in runs.site_states(conn, site_id) if s["source_word"] == "brief"]
    assert [(s["affected_urls"][0], s["state"]) for s in brief] == [(BASE + "/about", "open")]
    # The part page counts what the table will not show.
    cat = next(c for c in runs.anatomy_view(conn, site_id)["categories"] if c["key"] == "title-desc")
    assert cat["brief_dropped"] == 1 and cat["brief_not_assessable"] == 3
    # A second reparse is stable: nothing is dropped or listed twice.
    again = reparse_contract(conn, run_id, "title-desc", Site(domain="birch.fixture"))
    assert again["dropped"] == got["dropped"] and again["not_assessable"] == got["not_assessable"]


@pytest.fixture(scope="module")
def served():
    server, thread, db, base = _serve("enforce")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "Birch Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "birch.fixture"}, timeout=30).json()
        conn = connect(db)
        run_id = _plant(conn, site["id"])
        reparse_contract(conn, run_id, "title-desc", Site(domain="birch.fixture"))
        conn.close()
        yield base, site["id"], run_id
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_the_stored_report_route_carries_the_contract(served):
    base, _, run_id = served
    got = httpx.get(f"{base}/api/runs/{run_id}/expert/title-desc", timeout=30).json()
    assert got["contract"]["reparsed"] and len(got["contract"]["dropped"]) == 1
    assert len(got["contract"]["not_assessable"]) == 3


@NEEDS_BROWSER
@pytest.mark.skipif(not (DIST / "index.html").is_file(), reason="dashboard not built")
def test_the_part_page_names_the_dropped_rows_and_the_report_lists_them(served):
    from playwright.sync_api import sync_playwright
    base, site_id, _ = served
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page(viewport={"width": 1568, "height": 1080})
        try:
            pg.goto(f"{base}/#/sites/{site_id}?tab=findings", wait_until="load", timeout=30_000)
            pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
            open_part(pg, 'Title & description')
            pg.wait_for_selector(".anat-pane .rep-dropped", timeout=15_000)
            # The part page is three blocks since brief v13 step AO: a card
            # per problem rather than a replacement table, and the dropped
            # rows counted beneath rather than listed.
            got = pg.evaluate("""() => ({
              dropped: document.querySelector('.anat-pane .rep-dropped')?.textContent.trim(),
              rows: [...document.querySelectorAll('.anat-pane .fix-card')]
                .filter((c) => c.querySelector('.fix-copy'))
                .map((c) => c.querySelector('.fix-page code')?.textContent),
              copies: document.querySelectorAll('.anat-pane .fix-copy').length,
              held: [...document.querySelectorAll('.anat-pane .fix-held .fix-page code')]
                .map((c) => c.textContent),
              na: [...document.querySelectorAll('.anat-pane .fix-na')]
                .map((p) => p.textContent.replace(/\s+/g, ' ').trim()),
            })""")
            # The reader moved to the catalogue drawer with the Read button.
            pg.click(".anat-catalogue-open")
            pg.wait_for_selector(".catalogue-drawer", timeout=15_000)
            pg.click(".catalogue-drawer tr:has(code:text-is('title-desc')) button.btn-secondary")
            pg.wait_for_selector(".contract-dropped", timeout=15_000)
            report = pg.evaluate("""() => ({
              dropped: [...document.querySelectorAll('.contract-dropped-table tbody tr')]
                .map((tr) => [...tr.querySelectorAll('td')].map((td) => td.textContent.trim())),
              needs: [...document.querySelectorAll('.contract-needs-table tbody tr')]
                .map((tr) => [...tr.querySelectorAll('td')].map((td) => td.textContent.trim())),
            })""")
        finally:
            b.close()
    # Item 209: the rows and their reasons, not a pointer at a report.
    assert got["dropped"].startswith("1 row dropped"), got
    assert "replacement outside bounds (91 < 120)" in got["dropped"], got
    # Only the row that passed every rule has copy on it. The three the brief
    # could not assess are all still said: since item 213 a check held page
    # by page for one reason is one line with its page count, and a hold on a
    # page where the check fired stays a card of its own - so the invariant is
    # that every held page is on the screen once, as a card or in a line.
    assert got["rows"] == ["/about"] and got["copies"] == 1, got
    import re as _re
    in_lines = sum(int(m.group(1)) if (m := _re.search(r"on (\d+) pages", line)) else 1
                   for line in got["na"])
    assert len(got["held"]) + in_lines == 3, got
    assert len(report["dropped"]) == 1 and report["dropped"][0][3].startswith("replacement outside bounds")
    assert [r[1] for r in report["needs"]] == ["/", "/events", "/richmond"], report
