"""Item 180, commit 1: two figures the UI audit found wrong that needed no
ruling, because each was a bug.

- 08-1: the run banner read "reached 5743 pages" on a 100-page crawl. The run
  payload carries `crawled_paths` as the stored JSON string, and the banner took
  its `.length` - characters, not pages.
- 01-3: Home read "up 63.03" for a T2 audit measured against a T3 that scored
  0.0. A delta is between audits of the same tier, never against a 0.0, and the
  sentence names what it compares against.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from clauditseo.api.app import create_app
from clauditseo.db.connection import connect
from clauditseo.persistence import runs
from tests.test_coverage import DIMS, _Hub, _run

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"


def _audit(conn, site_id: str, tier: str, score: float, at: str) -> str:
    run_id = runs.create_run(conn, site_id, DIMS, tier)
    runs.complete_run(conn, run_id, _run(_Hub()))
    conn.execute("UPDATE audit_runs SET composite_score=?, started_at=? WHERE id=?",
                 (score, at, run_id))
    conn.commit()
    return run_id


def _row(api: TestClient, site_id: str) -> dict:
    body = api.get("/api/overview").json()
    sites = body["sites"] if isinstance(body, dict) else body
    return next(s for s in sites if s["site_id"] == site_id)


def test_a_delta_compares_audits_of_one_tier_and_never_a_zero(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDITSEO_TOKEN", raising=False)
    db = tmp_path / "delta.db"
    api = TestClient(create_app(db_path=db))
    client = api.post("/api/clients", json={"name": "Delta"}).json()
    site = api.post(f"/api/clients/{client['id']}/sites", json={"domain": "delta.fixture"}).json()
    conn = connect(db)

    _audit(conn, site["id"], "T3", 0.0, "2026-09-09T10:00:00")
    _audit(conn, site["id"], "T2", 63.03, "2026-09-10T10:00:00")
    row = _row(api, site["id"])
    assert row["delta"] is None, f"a T2 compared against a T3 that scored 0.0: {row['delta']}"

    _audit(conn, site["id"], "T3", 70.0, "2026-09-11T10:00:00")
    _audit(conn, site["id"], "T2", 0.0, "2026-09-12T10:00:00")
    row = _row(api, site["id"])
    assert row["delta"] is None, "the newest scored 0.0; nothing is measured from it"

    _audit(conn, site["id"], "T2", 64.0, "2026-09-13T10:00:00")
    row = _row(api, site["id"])
    assert row["delta"] == 0.97 and row["delta_tier"] == "T2", row
    conn.close()


def test_the_home_sentence_names_what_the_delta_compares_against():
    home = (SRC / "home.tsx").read_text(encoding="utf-8")
    assert "on the previous ${s.delta_tier} audit" in home


def test_the_banner_counts_pages_not_characters():
    views = (SRC / "views.tsx").read_text(encoding="utf-8")
    banner = views[views.index("export function ScanBanner"):]
    banner = banner[:banner.index("\n}\n")]
    assert "crawled_paths?.length" not in banner
    assert "crawledCount(run.crawled_paths)" in banner
    helper = views[views.index("export function crawledCount"):]
    assert "JSON.parse" in helper[:600]
