"""The contract's rows and the sweep's are the same shape and the same
vocabulary (brief v11 step AH): the sweep's duplicate checks emit one row
per member page carrying the group; a brief row's severity is the check's
registered default unless the brief raised it with a reason; a brief row
the sweep corroborates opens on first sight and one it does not waits as
a candidate; the pages the sweep raised that the brief did not return are
named; and the part page lists every check of the part, `0` where empty,
with every replacement counted.
"""

from __future__ import annotations

import dataclasses
import json

import httpx
import pytest

from clauditseo.analysts import contract
from clauditseo.checks import default_severities, default_severity
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.engine.types import Severity
from clauditseo.modules.onp import DEFAULT_SEVERITY, OnPageModule
from clauditseo.modules.pagefacts import PageFacts
from clauditseo.persistence import repo, runs
from tests.test_a11y_rendered import DIST
from tests.test_the_first_prompt_is_title_and_description import served  # noqa: F401  (reused fixture)
from tests.parts import ANATOMY_READY, open_part

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")

BASE = "https://fixture.local"


def _facts(path: str, title: str, desc: str | None = None) -> PageFacts:
    f = PageFacts(url=BASE + path, path=path)
    f.title = title
    f.meta_description = desc
    f.headings = [(1, "H")]
    return f


def test_the_sweep_emits_one_duplicate_row_per_member_page_carrying_the_group():
    facts = [_facts("/a", "Acme 2024", "Same words twice over, long enough to be a description of a page here."),
             _facts("/b", "Acme 2024", "Same words twice over, long enough to be a description of a page here."),
             _facts("/c", "Acme 2024"), _facts("/d", "Something else entirely")]
    rows = [f for f in OnPageModule()._duplication_checks(facts) if f.check_id == "title-duplicate"]
    assert [f.affected_urls for f in rows] == [[BASE + "/a"], [BASE + "/b"], [BASE + "/c"]]
    assert {f.evidence["group"] for f in rows} == {"Acme 2024"}
    assert all(f.evidence["paths"] == ["/a", "/b", "/c"] for f in rows)
    assert all(f.severity == DEFAULT_SEVERITY["title-duplicate"] for f in rows)
    assert rows[0].summary.startswith('/a shares its title "Acme 2024" with 2 other pages')
    descs = [f for f in OnPageModule()._duplication_checks(facts) if f.check_id == "meta-desc-duplicate"]
    assert [f.affected_urls for f in descs] == [[BASE + "/a"], [BASE + "/b"]]
    assert descs[0].evidence["group"].startswith("Same words twice")
    # Distinct fingerprints per page, not one per group.
    assert len({f.fingerprint for f in rows}) == 3


def test_a_brief_rows_severity_is_the_registered_default_unless_raised_with_a_reason():
    checks = ["ONP/title-length", "ONP/meta-desc-missing"]
    pages = [BASE + "/a", BASE + "/b", BASE + "/c", BASE + "/d"]
    assert default_severity("ONP/title-length") == "low" and default_severity("ONP/meta-desc-missing") == "medium"
    block = json.dumps({"rows": [
        {"check": "ONP/title-length", "page": "/a", "status": "FAIL", "severity": "HIGH",
         "evidence": "x", "replacement": "y", "note": "three-word title, a placeholder"},
        {"check": "ONP/title-length", "page": "/b", "status": "FAIL", "severity": "HIGH",
         "evidence": "x", "replacement": "y"},
        {"check": "ONP/meta-desc-missing", "page": "/c", "status": "FAIL", "severity": "LOW",
         "evidence": "x", "replacement": "y"},
        {"check": "ONP/meta-desc-missing", "page": "/d", "status": "FAIL",
         "evidence": "x", "replacement": "y", "group": "shared"}]})
    got = contract.parse("```json\n" + block + "\n```\n", checks, pages, defaults=default_severities())
    by = {r.page.rsplit("/", 1)[1]: r for r in got.rows}
    assert by["a"].severity == "high" and by["a"].raised          # raised, with a reason
    assert by["b"].severity == "low" and not by["b"].raised       # raised without one: the default
    assert by["c"].severity == "medium" and not by["c"].raised    # lowered: the default
    assert by["d"].severity == "medium" and by["d"].group == "shared"   # missing: the default


def _site(tmp_path):
    conn = connect(tmp_path / "agree.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Agree Co")
    site_id = repo.create_site(conn, client, "fixture.local")
    return conn, site_id


def _run_with_sweep(conn, site_id, sweep_pages: list[str]):
    """A run whose sweep raised `title-length` on the given pages."""
    from clauditseo.persistence.repo import create_id, now_iso
    run_id = runs.create_run(conn, site_id, ["ONP"], "T2")
    # `content_type` as the crawler stores it: without one the run fetched no
    # page it could read, and its silence clears nothing (item 239 step 4).
    runs.store_evidence(conn, run_id, {"pages": [{"url": BASE + p, "status": 200,
                                                  "content_type": "text/html"}
                                                 for p in ("/a", "/b", "/c")]})
    with conn:
        for p in sweep_pages:
            conn.execute(
                "INSERT INTO findings (id, run_id, dimension, check_id, severity, source, summary,"
                " affected_urls, fingerprint, created_at) VALUES (?, ?, 'ONP', 'title-length', 'low',"
                " 'deterministic', ?, ?, ?, ?)",
                (create_id(), run_id, f"Title on {p} is short", json.dumps([BASE + p]), f"sweep-{p}", now_iso()))
    return run_id


def _brief(conn, run_id, pages: list[str]):
    rows = [{"check": "ONP/title-length", "dimension": "ONP", "check_id": "title-length",
             "page": BASE + p, "status": "FAIL", "severity": "low", "evidence": "x",
             "replacement": f"A better title for {p}", "note": ""} for p in pages]
    runs.store_expert_report(conn, run_id, "title-desc",
                             {"model": "stub", "report": "", "findings": [],
                              "contract": {"status": "read", "rows": rows}})
    runs.record_contract_findings(conn, run_id, "title-desc", "stub", rows)


def test_a_corroborated_row_opens_and_an_uncorroborated_one_waits_as_a_candidate(tmp_path):
    conn, site_id = _site(tmp_path)
    run_a = _run_with_sweep(conn, site_id, ["/a"])
    _brief(conn, run_a, ["/a", "/b"])            # /a corroborated, /b not
    runs.recompute_contract_states(conn, site_id, "title-desc")
    states = {s["affected_urls"][0].rsplit("/", 1)[1]: s["state"]
              for s in runs.site_states(conn, site_id) if s["source_word"] == "brief"}
    assert states == {"a": "open", "b": "candidate"}
    # A second run confirms /b; /a is gone from the brief and is fixed.
    run_b = _run_with_sweep(conn, site_id, [])
    _brief(conn, run_b, ["/b"])
    runs.recompute_contract_states(conn, site_id, "title-desc")
    states = {s["affected_urls"][0].rsplit("/", 1)[1]: s["state"]
              for s in runs.site_states(conn, site_id) if s["source_word"] == "brief"}
    assert states == {"a": "fixed", "b": "open"}


def test_the_pages_the_brief_did_not_return_are_named(tmp_path):
    from clauditseo.analysts.expert import _uncovered
    conn, site_id = _site(tmp_path)
    run_id = _run_with_sweep(conn, site_id, ["/a", "/b"])
    parsed = contract.parse(
        "```json\n" + json.dumps({"rows": [
            {"check": "ONP/title-length", "page": "/a", "status": "FAIL", "severity": "LOW",
             "evidence": "x", "replacement": "y"}]}) + "\n```\n",
        ["ONP/title-length"], [BASE + "/a", BASE + "/b"])
    got = _uncovered(conn, run_id, ["ONP/title-length"], parsed.rows, [BASE + "/a", BASE + "/b"])
    assert got == [{"check": "ONP/title-length", "page": BASE + "/b", "in_page_set": True}]


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
def test_the_part_page_lists_every_check_and_counts_the_replacements(browser, served):
    base, site_id, run_id, got, _ = served
    anatomy = httpx.get(f"{base}/api/sites/{site_id}/anatomy", timeout=30).json()
    td = next(c for c in anatomy["categories"] if c["key"] == "title-desc")
    assert len(td["brief_checks"]) == 7 and "ONP/meta-desc-length" in td["brief_checks"]
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    try:
        pg.goto(f"{base}/#/sites/{site_id}?tab=findings", wait_until="load", timeout=30_000)
        pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
        open_part(pg, 'Title & description')
        pg.wait_for_selector(".anat-pane .fix-card", timeout=15_000)
        # Three blocks since brief v13 step AO: the checks table stands
        # where the causes did, and a card per problem where the
        # replacement table did.
        got = pg.evaluate("""() => ({
          causes: [...document.querySelectorAll('.anat-pane .checks-table tbody tr')].map((tr) => ({
            check: tr.querySelectorAll('td')[1]?.textContent.trim(), clean: false })),
          // One line per section since brief v17 step AV3; joined,
          // because this clause is about every check of the part.
          clean: [...document.querySelectorAll('.anat-pane .cause-clean-line')]
            .map((p) => p.textContent.trim()).join(' '),
          rows: document.querySelectorAll('.anat-pane .fix-card').length,
          copies: document.querySelectorAll('.anat-pane .fix-copy').length,
        })""")
    finally:
        pg.close()
    checks = {c["check"] for c in got["causes"]}
    # The table lists the checks with something open; the rest are the
    # clean line beneath, which names all five.
    assert checks == {"ONP/title-length", "ONP/meta-desc-missing"}, checks
    # Four free and one analysis since brief v17 step AV3: the sections
    # count apart, because a reader asking "what did the free pass find"
    # is owed its own answer rather than a total that mixes the two.
    # The absence claim carries its population too (item 155): clean on
    # every page THIS RUN FETCHED, not over a record that includes pages
    # nobody looked at.
    assert got["clean"].startswith("4 checks clean on every page this audit fetched"), got["clean"]
    assert "1 check clean on every page this audit fetched" in got["clean"], got["clean"]
    assert "title-entity-alignment" in got["clean"], got["clean"]
    for c in ("ONP/title-missing", "ONP/title-duplicate", "ONP/title-entity-alignment",
              "ONP/meta-desc-length", "ONP/meta-desc-duplicate"):
        assert c.split("/")[1] in got["clean"], (c, got["clean"])
    # On this fixture no sweep row corroborates the brief's two, so they
    # wait as candidates: shown and tagged on their cause rows since brief
    # v12 step AM - while the replacement table lists both, since a
    # proposed fix is worth showing before a second run confirms the row.
    assert not any(c["clean"] for c in got["causes"]), got["causes"]
    assert got["rows"] == 2 and got["copies"] == 2, got
