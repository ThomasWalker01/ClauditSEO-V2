"""A re-check of some parts is not the site's audit (screen audits round 3).

On twenty22.co the 3 Oct run `9e5bd434` re-checked Links alone over 45 pages.
By kind and scope it was a site-wide audit, so every picker that asked only
those two questions took it as the site's: Home read "87.4, good, up 15.99 on
the previous T2 audit" (a Links score against the full 71.45), every Client
tab's header said "scored 87.44" under a bar reading 71.45, and Reports and
the Analyses shop aimed the plan and paid runs at it. Five of the round's six
Criticals.

The rule is the Latest View's reference composite's, replayed over the
history (`runs.part_only_runs`): a reading that does not cover the dimensions
of the reading it follows is part-only.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from clauditseo.api.app import create_app
from clauditseo.db.connection import connect
from clauditseo.persistence import runs

FULL = ["A11Y", "LNK", "ONP", "SEC", "TEC"]
PATHS = json.dumps([f"/p{i}/" for i in range(60)])


def _store(conn, site_id, dims, score, at):
    run_id = runs.create_run(conn, site_id, dims, "T2")
    conn.execute(
        "UPDATE audit_runs SET status='complete', composite_score=?, started_at=?,"
        " created_at=?, crawled_paths=?, known_paths=60 WHERE id=?",
        (score, at, at, PATHS, run_id))
    conn.commit()
    return run_id


@pytest.fixture
def site(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDITSEO_LLM_PROVIDER", "mock")
    db = tmp_path / "c.db"
    api = TestClient(create_app(db_path=db))
    client_id = api.post("/api/clients", json={"name": "Twenty"}).json()["id"]
    site_id = api.post(f"/api/clients/{client_id}/sites",
                       json={"domain": "https://t.example/"}).json()["id"]
    conn = connect(db)
    ids = {
        "older": _store(conn, site_id, FULL, 60.0, "2026-09-20T00:00:00+00:00"),
        "onp": _store(conn, site_id, ["ONP"], 46.67, "2026-09-23T00:00:00+00:00"),
        "full": _store(conn, site_id, FULL, 71.45, "2026-10-02T00:00:00+00:00"),
        "lnk": _store(conn, site_id, ["LNK"], 87.44, "2026-10-03T00:00:00+00:00"),
    }
    yield api, conn, site_id, ids
    conn.close()


def test_the_rule_names_the_two_rechecks(site):
    _api, conn, site_id, ids = site
    assert runs.part_only_runs(conn, site_id) == {ids["onp"]: ["ONP"], ids["lnk"]: ["LNK"]}


def test_a_reading_that_covers_more_is_never_part_only(site):
    _api, conn, site_id, ids = site
    later = _store(conn, site_id, FULL + ["PRF"], 70.0, "2026-10-05T00:00:00+00:00")
    assert later not in runs.part_only_runs(conn, site_id)


def test_home_scores_the_full_audit_and_names_the_recheck(site):
    api, _conn, site_id, _ids = site
    card = next(r for r in api.get("/api/overview").json()["sites"]
                if r["site_id"] == site_id)
    assert card["score"] == 71.45, card
    # Against the earlier full audit, not the ON-page re-check between them.
    assert card["delta"] == 11.45, card
    assert card["recheck_label"] and card["recheck_label"].endswith(" only"), card
    assert card["recheck_at"].startswith("2026-10-03"), card
    # "Audited N days ago" dates the score, not the re-check.
    assert card["score_at"].startswith("2026-10-02"), card


def test_the_landing_reads_the_full_audit(site):
    api, _conn, site_id, ids = site
    view = api.get(f"/api/sites/{site_id}/anatomy").json()
    assert view["latest_run"] == ids["full"], view["latest_run"]


def test_run_lists_label_the_rechecks(site):
    api, _conn, site_id, ids = site
    listed = {r["id"]: r.get("part_only") for r in api.get(f"/api/sites/{site_id}").json()["runs"]}
    assert listed[ids["lnk"]] and listed[ids["onp"]], listed
    assert listed[ids["full"]] is None and listed[ids["older"]] is None, listed
    reports = {r["id"]: r.get("part_only")
               for r in api.get(f"/api/sites/{site_id}/reports").json()["runs"]}
    assert reports[ids["lnk"]] and reports[ids["full"]] is None, reports


def test_the_plan_is_refused_on_a_recheck(site):
    api, _conn, _site_id, ids = site
    r = api.post(f"/api/runs/{ids['lnk']}/expert/plan", json={"for_audience": "operator"})
    assert r.status_code == 409, r.text
    assert "full audit" in r.json()["detail"]
