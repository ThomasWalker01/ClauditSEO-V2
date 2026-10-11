""""To confirm" is one word with three answers, on every screen and for every
brief (item 250).

Round-2 screen audits, cross-cutting item 3 of 5: item 237 landed, and
thirteen screens reported it incomplete. The controls were on the part
page's cards and the words were defined nowhere; the state was spelt three
ways ("candidate", "not yet confirmed", "analysis, not yet confirmed"); the
dossier showed the raw word with no controls; the four local briefs were
still promoted by repetition; and a candidate the sweep could never
corroborate had no way to be answered.
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
    ABOUT, BRIEF_ONLY, HOME, SWEPT, _audit_and_brief, _row)
from tests.test_triage_ranks_the_section_rail import _serve

LOCAL_TOOLS = ("gbp-audit", "local-signals", "citations-nap", "review-signals")


@pytest.fixture
def db(tmp_path):
    conn = connect(tmp_path / "toconfirm.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site_id = repo.create_site(conn, repo.create_client(conn, op, "Confirm Co"), "confirm.fixture")
    yield conn, site_id
    conn.close()


# ---- the registry ---------------------------------------------------------------

def test_the_state_and_its_three_answers_are_registered():
    from clauditseo import glossary
    by = {e["id"]: e for e in glossary.entries()}
    assert by["to-confirm"]["word"] == "to confirm"
    assert [by[i]["word"] for i in ("confirm", "accept", "withdraw")] == [
        "Confirm", "Accept", "Withdraw"]
    assert by["seen-once"]["word"] == "seen once" and "automatic checks" in by["seen-once"]["full"]
    # The old rule is gone from the registry and from the Record's sentence.
    assert "dropped if not" not in by["state-candidate"]["full"]
    from pathlib import Path
    fixloop = (Path(__file__).resolve().parents[1] / "dashboard/src/fixloop.tsx").read_text("utf-8")
    meaning = next(ln for ln in fixloop.splitlines() if ln.strip().startswith('"candidate": "'))
    assert "opens if it appears again" not in meaning, meaning


def test_no_screen_spells_the_state_its_old_ways():
    from pathlib import Path
    src = Path(__file__).resolve().parents[1] / "dashboard" / "src"
    for path in sorted(src.glob("*.tsx")):
        text = path.read_text(encoding="utf-8")
        for old in ('"analysis, not yet confirmed"', '"not yet confirmed"'):
            assert old not in text, f"{path.name} still draws {old}"


# ---- step 4: the local briefs ------------------------------------------------------

def _legacy(conn, site_id, tool, code="unclaimed-listing"):
    run = runs.create_run(conn, site_id, ["LOC"], "T2")
    runs.store_evidence(conn, run, {"start_url": HOME, "pages": [{"url": HOME, "status": 200}]})
    runs.mark_complete(conn, run, now_iso())
    conn.execute("UPDATE audit_runs SET crawled_paths=? WHERE id=?", (json.dumps(["/"]), run))
    conn.commit()
    runs.record_expert_findings(conn, run, tool, "m-1", [
        {"code": code, "severity": "high", "summary": "s", "url": HOME}])
    runs.recompute_expert_states(conn, site_id, tool)
    return run


def _fp(tool, code="unclaimed-listing"):
    from clauditseo.engine.types import fingerprint
    return fingerprint(f"EXP:{tool}", code, "site")


@pytest.mark.parametrize("tool", LOCAL_TOOLS)
def test_a_local_brief_row_seen_in_two_runs_stays_to_confirm(db, tool):
    conn, site_id = db
    _legacy(conn, site_id, tool)
    _legacy(conn, site_id, tool)
    state = conn.execute("SELECT state FROM finding_states WHERE site_id=? AND fingerprint=?",
                         (site_id, _fp(tool))).fetchone()
    assert state and state[0] == "candidate", (tool, state and state[0])
    assert _fp(tool) in runs.awaiting_confirmation(conn, site_id)


def test_the_operators_confirmation_of_a_local_row_survives_a_third_run(db):
    conn, site_id = db
    tool = LOCAL_TOOLS[0]
    _legacy(conn, site_id, tool)
    runs.set_state(conn, site_id, _fp(tool), "open")
    _legacy(conn, site_id, tool)
    assert conn.execute("SELECT state FROM finding_states WHERE site_id=? AND fingerprint=?",
                        (site_id, _fp(tool))).fetchone()[0] == "open"


# ---- step 5: a candidate the sweep will never corroborate ---------------------------

def _sweep(conn, site_id, at):
    run = runs.create_run(conn, site_id, ["ONP"], "T2", scan_scope="site")
    runs.store_evidence(conn, run, {"start_url": HOME, "pages": [
        {"url": HOME, "status": 200}, {"url": ABOUT, "status": 200}]})
    conn.execute("UPDATE audit_runs SET status='complete', started_at=?, finished_at=?,"
                 " created_at=?, crawled_paths=? WHERE id=?",
                 (at, at, at, json.dumps(["/", "/about/"]), run))
    conn.commit()
    return run


def test_a_sweep_leg_candidate_the_sweep_read_twice_without_raising_is_to_confirm(db):
    conn, site_id = db
    first = _audit_and_brief(conn, site_id, [_row(SWEPT, HOME)])
    conn.execute("UPDATE audit_runs SET started_at='2026-09-01T00:00:00+00:00',"
                 " finished_at='2026-09-01T00:00:00+00:00' WHERE id=?", (first,))
    conn.commit()
    row = lambda: next(s for s in runs.site_states(conn, site_id)  # noqa: E731
                       if s["check_id"] == SWEPT and s["source_word"] == "brief")
    assert row()["state"] == "candidate" and row()["to_confirm"] is False

    _sweep(conn, site_id, "2026-09-08T00:00:00+00:00")
    assert row()["to_confirm"] is False, "one reading is not two"
    _sweep(conn, site_id, "2026-09-15T00:00:00+00:00")
    got = row()
    assert got["to_confirm"] is True, got
    assert got["fingerprint"] in runs.awaiting_confirmation(conn, site_id)


def test_a_brief_only_candidate_is_to_confirm_at_once(db):
    conn, site_id = db
    _audit_and_brief(conn, site_id, [_row(BRIEF_ONLY, HOME)])
    got = next(s for s in runs.site_states(conn, site_id) if s["check_id"] == BRIEF_ONLY)
    assert got["state"] == "candidate" and got["to_confirm"] is True


# ---- step 3: the dossier ----------------------------------------------------------

def test_the_dossier_row_carries_what_the_three_answers_need(db):
    conn, site_id = db
    _audit_and_brief(conn, site_id, [_row(BRIEF_ONLY, HOME)])
    got = runs.page_dossier(conn, site_id, HOME)
    row = next(f for f in got["findings"] if f["check_id"] == BRIEF_ONLY)
    assert row["state"] == "candidate" and row["to_confirm"] is True
    assert row["fingerprint"], row


# ---- the screens -------------------------------------------------------------------

@pytest.fixture(scope="module")
def served():
    server, thread, dbpath, base = _serve("toconfirm")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "Confirm Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "confirm.fixture"}, timeout=30).json()
        conn = connect(dbpath)
        _audit_and_brief(conn, site["id"], [_row(BRIEF_ONLY, HOME), _row(BRIEF_ONLY, ABOUT)])
        conn.close()
        yield base, site["id"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@needs_build
def test_the_part_pages_legend_defines_the_state_and_its_answers(served):
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
            got = pg.evaluate("""() => ({
              legend: [...document.querySelectorAll('details.legend dt, details.legend .legend-row b, details.legend .legend-word')]
                        .map((e) => e.textContent.trim().toLowerCase()),
              legendText: (document.querySelector('details.legend')?.textContent || '').toLowerCase(),
              pills: [...document.querySelectorAll('.part-fixes .fix-card .tone-state-candidate')]
                        .map((e) => e.textContent.trim()),
              table: [...document.querySelectorAll('.checks-table tbody tr')]
                        .map((tr) => (tr.lastElementChild?.textContent || '').trim()),
            })""")
        finally:
            b.close()
    for word in ("to confirm", "confirm", "accept", "withdraw"):
        assert word in got["legendText"], (word, got["legend"])
    assert got["pills"] and set(got["pills"]) == {"to confirm"}, got["pills"]
    assert "to confirm" in got["table"], got["table"]


@needs_build
def test_the_dossier_offers_the_three_answers_and_one_is_taken(served):
    from playwright.sync_api import sync_playwright
    from urllib.parse import quote
    base, site_id = served
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            pg = b.new_page(viewport={"width": 1568, "height": 1080})
            pg.goto(f"{base}/#/sites/{site_id}/dossier/{quote(ABOUT, safe='')}",
                    wait_until="load", timeout=30_000)
            pg.wait_for_selector("table.findings .fix-confirm", timeout=30_000)
            before = pg.evaluate("""() => ({
              state: [...document.querySelectorAll('table.findings .state')].map((e) => e.textContent.trim()),
              controls: [...document.querySelectorAll('table.findings .fix-confirm button')].map((e) => e.textContent.trim()),
            })""")
            pg.click("table.findings .fix-confirm-withdraw")
            pg.wait_for_function(
                "() => !document.querySelector('table.findings .fix-confirm')", timeout=15_000)
            after = pg.evaluate(
                "() => [...document.querySelectorAll('table.findings .state')].map((e) => e.textContent.trim())")
        finally:
            b.close()
    assert before["state"] == ["to confirm"], before
    assert before["controls"] == ["Confirm", "Accept", "Withdraw"], before
    assert after == ["withdrawn"], after
