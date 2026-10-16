"""Every card and Now block says when what it draws was measured, the checks
table ranks by that date, and the dossier reads the Latest View (item 251,
steps 1, 2 and 3).

Round-2 screen audits, cross-cutting item 4 of 5. The Latest View existed
and the blocks read it, but a fix card sat beside an analysis dated "7
audits older" with no date of its own, so a 29 Sept sweep card could not be
told from an 18 Sept model card; a 23 Sept analysis's hold outranked the 29
Sept sweep on three free checks; and the dossier picked the newest row per
check over every run, reviving a retired check.
"""

from __future__ import annotations

import json

import httpx
import pytest

from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo, runs
from clauditseo.persistence.repo import create_id, now_iso
from tests.needs_build import needs_build
from tests.parts import ANATOMY_READY
from tests.test_a_brief_only_finding_waits_for_the_operator import (
    ABOUT, BRIEF_ONLY, HOME, _audit_and_brief, _row)
from tests.test_triage_ranks_the_section_rail import _serve


@pytest.fixture
def db(tmp_path):
    conn = connect(tmp_path / "dated.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site_id = repo.create_site(conn, repo.create_client(conn, op, "Dated Co"), "confirm.fixture")
    yield conn, site_id
    conn.close()


def _sweep_finding(conn, run, check, url, dim="ONP", sev="medium"):
    conn.execute(
        "INSERT INTO findings (id, run_id, dimension, check_id, severity, source, summary,"
        " affected_urls, fingerprint, created_at) VALUES (?, ?, ?, ?, ?, 'deterministic', 's', ?, ?, ?)",
        (create_id(), run, dim, check, sev, json.dumps([url]), f"{dim}:{check}:{url}", now_iso()))
    conn.execute(
        "INSERT INTO finding_states (site_id, fingerprint, state, changed_by_run, updated_at)"
        " SELECT site_id, ?, 'open', id, ? FROM audit_runs WHERE id=?"
        " ON CONFLICT(site_id, fingerprint) DO UPDATE SET state='open'",
        (f"{dim}:{check}:{url}", now_iso(), run))
    conn.commit()


# ---- the payload ------------------------------------------------------------------

def test_a_row_carries_the_date_and_tier_of_its_measurement(db):
    conn, site_id = db
    run = _audit_and_brief(conn, site_id, [_row(BRIEF_ONLY, HOME)])
    conn.execute("UPDATE audit_runs SET finished_at='2026-09-18T07:50:00+00:00', tier='T3' WHERE id=?", (run,))
    _sweep_finding(conn, run, "title-length", HOME)
    states = {s["check_id"]: s for s in runs.site_states(conn, site_id)}
    sweep = states["title-length"]
    assert sweep["measured_at"] == "2026-09-18T07:50:00+00:00" and sweep["measured_tier"] == "T3"
    assert sweep["analysed_at"] is None
    brief = states[BRIEF_ONLY]
    assert brief["measured_at"] == "2026-09-18T07:50:00+00:00"
    assert brief["analysed_at"], "an analysis row does not say when the analysis ran"


def test_the_dossier_names_only_what_the_ledger_holds(db):
    """A finding from an older run whose state the ledger no longer holds -
    a retired check, a dropped row - is not on the page."""
    conn, site_id = db
    run = _audit_and_brief(conn, site_id, [_row(BRIEF_ONLY, HOME)])
    _sweep_finding(conn, run, "title-length", HOME)
    # An orphan: a finding row that names the page and has no state.
    conn.execute(
        "INSERT INTO findings (id, run_id, dimension, check_id, severity, source, summary,"
        " affected_urls, fingerprint, created_at) VALUES (?, ?, 'PRF', 'lcp-poor', 'high',"
        " 'deterministic', 'retired', ?, 'PRF:lcp-poor:/', ?)",
        (create_id(), run, json.dumps([HOME]), now_iso()))
    conn.commit()

    got = runs.page_dossier(conn, site_id, HOME)
    checks = {f["check_id"] for f in got["findings"]}
    ledger = {s["check_id"] for s in runs.site_states(conn, site_id)}
    assert checks <= ledger, checks - ledger
    assert "lcp-poor" not in checks, "a check with no row in the ledger was revived"
    assert {"title-length", BRIEF_ONLY} <= checks
    row = next(f for f in got["findings"] if f["check_id"] == "title-length")
    assert row["measured_at"] and row["state"] == "open"
    # Another page's finding is not this page's.
    assert runs.page_dossier(conn, site_id, ABOUT)["findings"] == []


# ---- the screen --------------------------------------------------------------------

@pytest.fixture(scope="module")
def served():
    server, thread, dbpath, base = _serve("dated")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "Dated Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "confirm.fixture"}, timeout=30).json()
        conn = connect(dbpath)
        run = _audit_and_brief(conn, site["id"], [_row(BRIEF_ONLY, HOME), _row(BRIEF_ONLY, ABOUT)])
        _sweep_finding(conn, run, "title-length", HOME)
        conn.close()
        yield base, site["id"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@needs_build
def test_every_fix_card_and_the_now_block_carry_a_date(served):
    from playwright.sync_api import sync_playwright
    base, site_id = served
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            pg = b.new_page(viewport={"width": 1568, "height": 1080})
            pg.goto(f"{base}/#/sites/{site_id}?tab=findings&part=title-desc",
                    wait_until="load", timeout=30_000)
            pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
            pg.wait_for_selector(".part-fixes .fix-card", timeout=15_000)
            for btn in pg.query_selector_all("button:has-text('show all')"):
                btn.click()
            pg.wait_for_timeout(400)
            got = pg.evaluate("""() => ({
              cards: [...document.querySelectorAll('.part-fixes .fix-card')].map((c) => ({
                check: c.querySelector('.fix-check')?.textContent || '',
                dated: (c.querySelector('.fix-measured')?.textContent || '').trim(),
                at: c.querySelector('.fix-measured')?.getAttribute('data-measured') || '',
              })),
              now: (document.querySelector('.now-measured')?.textContent || '').trim(),
              nowAt: document.querySelector('.now-measured')?.getAttribute('data-measured') || '',
            })""")
        finally:
            b.close()
    assert got["cards"], "no fix card was drawn"
    undated = [c["check"] for c in got["cards"] if not c["dated"] or not c["at"]]
    assert not undated, f"cards with no date: {undated}"
    by = {c["check"]: c["dated"] for c in got["cards"]}
    assert "measured" in by["ONP/title-length"], by
    assert "analysed" in by[f"ONP/{BRIEF_ONLY}"], by
    assert got["now"].startswith("What is drawn below was measured") and got["nowAt"], got["now"]


@needs_build
def test_a_newer_sweep_reading_outranks_an_older_hold_in_the_checks_table(tmp_path):
    """Crawl, on twenty22: a 23 Sept analysis held three free checks over
    the 29 Sept sweep that had measured each and raised nothing."""
    from playwright.sync_api import sync_playwright
    server, thread, dbpath, base = _serve("ranked")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "Rank Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "confirm.fixture"}, timeout=30).json()
        conn = connect(dbpath)
        # The analysis runs against the first audit and HOLDS a free check.
        first = _audit_and_brief(conn, site["id"], [_row(BRIEF_ONLY, HOME)])
        held = {"check": "ONP/meta-desc-length", "page": None, "needs": "the page's own copy",
                "reason": ""}
        contract = json.loads(conn.execute(
            "SELECT contract FROM expert_reports WHERE run_id=?", (first,)).fetchone()[0])
        contract["not_assessable"] = [held]
        conn.execute("UPDATE expert_reports SET contract=?, created_at='2026-09-23T11:26:00+00:00'"
                     " WHERE run_id=?", (json.dumps(contract), first))
        # The analysis's crawl is not one the sweep measured ONP on, so the
        # hold stands until a reading of the part arrives. Since screen
        # audits round 3 (Indexability AC-01) the sweep's reading of the very
        # crawl the analysis read outranks the hold at once.
        conn.execute("UPDATE audit_runs SET started_at='2026-09-18T07:39:00+00:00',"
                     " finished_at='2026-09-18T07:50:00+00:00', dimensions='[\"TEC\"]'"
                     " WHERE id=?", (first,))
        conn.commit()

        def state_of_row(pg):
            return pg.evaluate("""() => {
              const tr = [...document.querySelectorAll('.checks-table tbody tr')]
                .find((r) => (r.querySelector('code')?.textContent || '').includes('meta-desc-length'));
              return tr ? (tr.lastElementChild?.textContent || '').trim() : null;
            }""")

        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            try:
                pg = b.new_page(viewport={"width": 1568, "height": 1080})
                url = f"{base}/#/sites/{site['id']}?tab=findings&part=title-desc"
                pg.goto(url, wait_until="load", timeout=30_000)
                pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
                pg.wait_for_selector(".checks-table tbody tr", timeout=15_000)
                before = state_of_row(pg)
                # A later audit measures the part and raises nothing on that check.
                later = runs.create_run(conn, site["id"], ["ONP"], "T2", scan_scope="site")
                runs.store_evidence(conn, later, {"start_url": HOME, "pages": [
                    {"url": HOME, "status": 200, "title": "Home"},
                    {"url": ABOUT, "status": 200, "title": "About"}]})
                from clauditseo.engine.core import AuditResult
                from clauditseo.engine.types import Site, Tier
                result = AuditResult(site=Site(domain="confirm.fixture"), tier=Tier.T2,
                                     dimensions=["ONP"])
                result.crawled_paths = {"/", "/about/"}
                runs.complete_run(conn, later, result)
                pg.reload(wait_until="load")
                pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
                pg.wait_for_selector(".checks-table tbody tr", timeout=15_000)
                pg.wait_for_timeout(500)
                after = state_of_row(pg)
                clean = pg.evaluate("""() => [...document.querySelectorAll('.cause-clean-line')]
                  .map((p) => p.textContent).join(' ')""")
            finally:
                b.close()
        conn.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
    assert before and before.startswith("not assessable"), before
    # Item 275: the newer reading's pass is a pass - the check leaves the
    # table for the clean line with the others the sweep measured.
    assert after is None, after
    assert "meta-desc-length" in clean, clean
