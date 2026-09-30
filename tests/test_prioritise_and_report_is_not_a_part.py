"""Item 238: "Prioritise & report" is retired as a part (supersedes 235).

It was three unrelated things under one label: `categorise()`'s catch-all,
the engine's run-notes (`adaptive-escalation`, the page's one "finding"), and
a slot for tools that write to no part. It had no brief and no renderer, and
the Record's part filter and `rankParts` already left it out.

  1. Out of the screen: the parts strip, the switcher and the part route
     leave it out, by one rule (`isPart`); `?part=workflow` lands where any
     unknown part does. The category row stays, so the fallback has a home.
  2. The engine's notes are notes: coverage notes by id
     (`runs.ENGINE_RUN_NOTES`), in both the Python and the SQL rule.
  3. The catch-all cannot hide a real check: over every check the modules
     and prompts register, `categorise()` returns `workflow` only for those
     notes. Written first, it found ten AI surface analysis checks there.
  4. No tool sits under it; a tool with no playbook status is not a sweep.
  5. The plan's prompt reads the audit's own ranking, not retired Triage's.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

import clauditseo.modules  # noqa: F401  (register dimensions)
from clauditseo import anatomy, briefs
from clauditseo.checks import ENGINE_EXTRA_CHECKS, check_costs
from clauditseo.db.connection import connect
from clauditseo.persistence import runs
from clauditseo.persistence.repo import create_id, now_iso
from tests.needs_build import needs_build
from tests.parts import ANATOMY_READY
from tests.test_triage_ranks_the_section_rail import _serve

ROOT = Path(__file__).resolve().parents[1]


def test_the_catch_all_holds_only_the_engines_own_notes():
    checks = (set(check_costs()) | set(ENGINE_EXTRA_CHECKS)
              | {c for b in briefs.catalogue() for c in b.checks})
    assert len(checks) > 300, len(checks)
    fallen = sorted(c for c in checks
                    if anatomy.categorise(c.split("/")[-1], c.split("/")[0] if "/" in c else "")
                    == "workflow" and c.split("/")[-1] not in runs.ENGINE_RUN_NOTES)
    assert not fallen, ("these register as checks and would be filed under a part the "
                        f"screen no longer shows: {fallen}")


def test_the_engines_notes_are_coverage_notes_in_both_rules(tmp_path):
    for note in runs.ENGINE_RUN_NOTES:
        assert runs.is_coverage_note(note, "info"), note
    from clauditseo.db.migrate import migrate
    conn = connect(tmp_path / "c.db")
    migrate(conn)
    got = conn.execute(
        f"SELECT {runs.coverage_note_sql('c', 's')} FROM"
        " (SELECT 'adaptive-escalation' AS c, 'info' AS s)").fetchone()[0]
    assert got == 1


def test_no_tool_is_placed_under_it():
    assert not [t for t, cats in anatomy.TOOL_CATEGORIES.items() if "workflow" in cats]


def test_the_plan_prompt_names_no_triage():
    text = (ROOT / "clauditseo" / "prompts" / "plan.md").read_text(encoding="utf-8")
    assert "{{TRIAGE_RANKING}}" not in text and "Triage" not in text
    assert "{{AUDIT_RANKING}}" in text


def test_the_plan_is_given_the_audits_own_ranking(tmp_path):
    from clauditseo.analysts.expert import _plan_ranking
    from clauditseo.db.migrate import migrate
    from clauditseo.persistence import repo
    conn = connect(tmp_path / "c.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site = repo.create_site(conn, repo.create_client(conn, op, "C"), "plan.fixture")
    run = runs.create_run(conn, site, ["ONP"], "T2")
    with conn:
        for check, fp in (("title-missing", "p1"), ("meta-desc-missing", "p2")):
            conn.execute(
                "INSERT INTO findings (id, run_id, dimension, check_id, severity, source,"
                " summary, affected_urls, fingerprint, created_at) VALUES (?, ?, 'ONP', ?,"
                " 'high', 'deterministic', 'x', ?, ?, ?)",
                (create_id(), run, check, json.dumps(["https://plan.fixture/"]), fp, now_iso()))
            conn.execute("INSERT INTO finding_states (site_id, fingerprint, state, changed_by_run,"
                         " updated_at) VALUES (?, ?, 'open', ?, ?)", (site, fp, run, now_iso()))
    text = _plan_ranking(conn, site, run)
    assert "title-missing" in text and "meta-desc-missing" in text, text
    assert "Ranked by the audit itself" in text and "triage" not in text.lower(), text


# --- on the screen ------------------------------------------------------------

@pytest.fixture(scope="module")
def served():
    server, thread, db, base = _serve("noworkflow")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "NW Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "noworkflow.fixture"}, timeout=30).json()
        conn = connect(db)
        run = runs.create_run(conn, site["id"], ["TEC"], "T2")
        runs.store_evidence(conn, run, {"start_url": "https://noworkflow.fixture/",
                                        "pages": [{"url": "https://noworkflow.fixture/",
                                                   "status": 200}]})
        runs.mark_complete(conn, run, now_iso())
        conn.execute("UPDATE audit_runs SET crawled_paths=? WHERE id=?", (json.dumps(["/"]), run))
        with conn:
            conn.execute(
                "INSERT INTO findings (id, run_id, dimension, check_id, severity, source,"
                " summary, affected_urls, fingerprint, created_at) VALUES (?, ?, 'ONP',"
                " 'adaptive-escalation', 'info', 'deterministic', 'escalated ONP', '[]', 'esc', ?)",
                (create_id(), run, now_iso()))
            conn.execute("INSERT INTO finding_states (site_id, fingerprint, state, changed_by_run,"
                         " updated_at) VALUES (?, 'esc', 'open', ?, ?)", (site["id"], run, now_iso()))
        conn.close()
        yield base, site["id"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_the_escalation_note_is_not_counted_as_a_finding(served):
    base, site_id = served
    view = httpx.get(f"{base}/api/sites/{site_id}/anatomy", timeout=30).json()
    part = next(c for c in view["categories"] if c["key"] == "workflow")
    assert part["total"]["value"] == 0, part["total"]


@needs_build
def test_the_strip_has_no_prioritise_and_report_and_its_route_opens_no_part(served):
    from playwright.sync_api import sync_playwright
    base, site_id = served
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            pg = b.new_page(viewport={"width": 1568, "height": 1080})
            pg.goto(f"{base}/#/sites/{site_id}?tab=findings&part=workflow",
                    wait_until="load", timeout=30_000)
            pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
            pg.wait_for_timeout(500)
            got = pg.evaluate("""() => ({
              text: document.querySelector('.site-main')?.textContent || '',
              partPage: !!document.querySelector('.part-page'),
            })""")
        finally:
            b.close()
    assert "Prioritise & report" not in got["text"], "the part is still named on screen"
    assert not got["partPage"], "?part=workflow rendered a part page"
