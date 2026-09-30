"""`scripts/reset_data.py --backup` (brief v11 step AK): the stored runs,
findings, reports, deliverables, prechecks, snapshots and every table
keyed on a run id go; the sites with their local-SEO record, the Admin
settings, brief defaults, prices and schedules stay; a verified snapshot
is taken first and named; and the per-table counts removed are printed.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo, runs

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "reset_data.py"


def _populated(tmp_path):
    db = tmp_path / "data" / "clauditseo.db"
    db.parent.mkdir()
    conn = connect(db)
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Reset Co")
    site_id = repo.create_site(conn, client, "reset.fixture")
    repo.update_site(conn, site_id, brand="Acme", gbp_primary_category="Pest Control Service",
                     location_pages=[{"url": "/richmond", "location_entity": "Richmond"}])
    run_id = runs.create_run(conn, site_id, ["ONP"], "T2")
    runs.store_evidence(conn, run_id, {"pages": [{"url": "https://reset.fixture/", "status": 200}]})
    rows = [{"check": "ONP/title-length", "dimension": "ONP", "check_id": "title-length",
             "page": "https://reset.fixture/", "status": "FAIL", "severity": "low",
             "evidence": "x", "replacement": "y", "note": ""}]
    runs.store_expert_report(conn, run_id, "title-desc",
                             {"model": "stub", "report": "", "findings": [],
                              "contract": {"status": "read", "rows": rows}})
    runs.record_contract_findings(conn, run_id, "title-desc", "stub", rows)
    runs.recompute_contract_states(conn, site_id, "title-desc")
    with conn:
        conn.execute("INSERT INTO cost_entries (id, run_id, provider, operation, units, quantity,"
                     " est_cost, actual_cost, created_at) VALUES ('c1', ?, 'stub', 'expert', 'tokens',"
                     " 1, 0.1, 0.1, '2026-09-05T00:00:00')", (run_id,))
        conn.execute("INSERT INTO prechecks (id, site_id, checked_at, entry_url, took_ms, sitemap_state,"
                     " payload_json) VALUES ('p1', ?, '2026-09-05T00:00:00', 'https://reset.fixture/',"
                     " 10, 'found', '{}')", (site_id,))
        conn.execute("INSERT INTO metric_snapshots (id, site_id, metric_key, value, source, confidence,"
                     " captured_at) VALUES ('m1', ?, 'composite', 50, 'engine', 1, '2026-09-05T00:00:00')",
                     (site_id,))
        conn.execute("INSERT INTO reports (id, site_id, run_ids, template, audience, path, created_at)"
                     " VALUES ('r1', ?, ?, 'audit', 'client', 'x.html', '2026-09-05T00:00:00')",
                     (site_id, json.dumps([run_id])))
        conn.execute("INSERT INTO tool_schedules (site_id, tool_id, cadence, created_at)"
                     " VALUES (?, 'title-desc', 'weekly', '2026-09-05T00:00:00')", (site_id,))
    conn.close()
    return db, site_id


def _counts(db: Path) -> dict[str, int]:
    c = sqlite3.connect(db)
    try:
        return {n: c.execute(f"SELECT COUNT(*) FROM {n}").fetchone()[0]
                for (n,) in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        c.close()


def test_the_reset_backs_up_first_and_keeps_the_record(tmp_path):
    db, site_id = _populated(tmp_path)
    before = _counts(db)
    for t in ("audit_runs", "findings", "expert_reports", "finding_states", "cost_entries",
              "prechecks", "metric_snapshots", "reports"):
        assert before[t] >= 1, (t, before[t])

    out = subprocess.run([sys.executable, str(SCRIPT), "--backup", "--db", str(db)],
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stdout + out.stderr

    backups = sorted((db.parent / "backups").glob("clauditseo-*.db"))
    assert len(backups) == 1 and str(backups[0]) in out.stdout, out.stdout
    assert _counts(backups[0])["findings"] == before["findings"]      # the snapshot opens and is whole

    after = _counts(db)
    gone = ("audit_runs", "findings", "expert_reports", "finding_states", "cost_entries",
            "prechecks", "metric_snapshots", "reports", "page_advice", "probe_results")
    assert all(after[t] == 0 for t in gone), {t: after[t] for t in gone}
    for t in ("sites", "clients", "operators", "tool_schedules", "app_prefs", "model_prices",
              "brief_models", "brand", "schema_migrations"):
        assert after[t] == before[t], t
    # The counts removed are printed per table.
    for t in ("audit_runs", "findings", "expert_reports", "prechecks"):
        assert f"{before[t]:7}  {t}" in out.stdout, out.stdout
    # The record survives with the fields the briefs read.
    c = connect(db)
    rec = repo.site_record(repo.get_site(c, site_id))
    assert rec["brand"] == "Acme" and rec["gbp_primary_category"] == "Pest Control Service"
    assert rec["location_pages"] == [{"url": "/richmond", "location_entity": "Richmond"}]


def test_without_the_flag_the_reset_only_reports(tmp_path):
    db, _ = _populated(tmp_path)
    before = _counts(db)
    out = subprocess.run([sys.executable, str(SCRIPT), "--db", str(db)],
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0 and "Report only" in out.stdout, out.stdout + out.stderr
    assert _counts(db) == before and not (db.parent / "backups").exists()
