"""Spend on a deleted run stays in the month's total and the cap (channel
ruling 20261011-0746; screen audits round 3, Admin IP-01).

Deleting a run deleted its `cost_entries`, so the month total, the per-client
rows and the cap warning all fell by money already billed. The ruling's
acceptance: delete a priced run; the month total and the cap reading are
unchanged, the client's row falls by that run's cost, and a "Deleted runs" row
appears holding exactly that cost.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from clauditseo.api.app import create_app
from clauditseo.db.connection import connect
from clauditseo.persistence import repo, runs
from clauditseo.persistence.spend import local_month


@pytest.fixture
def billed(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDITSEO_LLM_PROVIDER", "mock")
    db = tmp_path / "c.db"
    api = TestClient(create_app(db_path=db))
    client_id = api.post("/api/clients", json={"name": "Gate Six"}).json()["id"]
    site_id = api.post(f"/api/clients/{client_id}/sites",
                       json={"domain": "https://gate-six.example/"}).json()["id"]
    conn = connect(db)
    kept = runs.create_run(conn, site_id, ["ONP"], "T2")
    doomed = runs.create_run(conn, site_id, ["ONP"], "T2")
    for run_id, usd in ((kept, 0.25), (doomed, 0.40)):
        conn.execute("UPDATE audit_runs SET status='complete' WHERE id=?", (run_id,))
        conn.execute(
            "INSERT INTO cost_entries (id, run_id, provider, operation, units, quantity,"
            " est_cost, actual_cost, created_at) VALUES (?, ?, 'anthropic', 'EXPERT:x',"
            " 'tokens', 1000, NULL, ?, ?)",
            (repo.create_id(), run_id, usd, repo.now_iso()))
    conn.commit()
    yield api, conn, site_id, kept, doomed
    conn.close()


def _month():
    return datetime.now().strftime("%Y-%m")


def _ledger(api):
    return [r for r in api.get("/api/admin").json()["spend"] if r["month"] == _month()]


def test_deleting_a_run_keeps_its_spend_in_the_total(billed):
    api, _conn, _site_id, _kept, doomed = billed
    before = api.get("/api/admin").json()["budget"]
    assert before["month_usd"] == pytest.approx(0.65)
    assert api.delete(f"/api/runs/{doomed}").status_code == 200
    after = api.get("/api/admin").json()["budget"]
    assert after["month_usd"] == pytest.approx(0.65), after
    assert after["month_tokens"] == before["month_tokens"] == 2000


def test_the_client_row_falls_and_a_deleted_row_holds_it(billed):
    api, _conn, _site_id, _kept, doomed = billed
    api.delete(f"/api/runs/{doomed}")
    rows = {r["client"]: r for r in _ledger(api)}
    assert rows["Gate Six"]["usd"] == pytest.approx(0.25), rows
    assert rows["Deleted runs"]["usd"] == pytest.approx(0.40), rows
    assert sum(r["usd"] or 0 for r in rows.values()) == pytest.approx(0.65)


def test_a_client_delete_keeps_it_too(billed):
    api, _conn, _site_id, _kept, _doomed = billed
    client_id = api.get("/api/clients").json()[0]["id"]
    assert api.delete(f"/api/clients/{client_id}").status_code == 200
    assert api.get("/api/admin").json()["budget"]["month_usd"] == pytest.approx(0.65)
    rows = {r["client"]: r for r in _ledger(api)}
    assert set(rows) == {"Deleted runs"} and rows["Deleted runs"]["entries"] == 2


def test_a_cost_is_kept_under_the_month_it_was_spent_in():
    assert local_month("2026-09-30T23:30:00+00:00") == \
        datetime.fromisoformat("2026-09-30T23:30:00+00:00").astimezone().strftime("%Y-%m")
    assert local_month("2026-09-30 23:30:00") == local_month("2026-09-30T23:30:00+00:00")


def test_the_backup_counts_it_and_the_confirmations_say_it():
    from pathlib import Path
    from clauditseo.persistence import backup
    assert "deleted_spend" in backup.COUNTED_TABLES
    src = Path(__file__).resolve().parents[1] / "dashboard" / "src"
    assert "export const SPEND_KEPT" in (src / "components.tsx").read_text(encoding="utf-8")
    assert (src / "home.tsx").read_text(encoding="utf-8").count("{SPEND_KEPT}") == 2
    assert "{SPEND_KEPT}" in (src / "pane_audit.tsx").read_text(encoding="utf-8")
