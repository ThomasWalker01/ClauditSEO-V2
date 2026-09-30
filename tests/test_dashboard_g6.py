"""Gate G6 e2e smoke via the API the dashboard consumes:
create client → add site → launch ONP+TEC audit → view findings → second and
third runs → compare by fingerprint → regression surfaced → analyst band
separate (mock provider) → history chat answers citing the correct run.
Auth: token mode returns 401 without the bearer token.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from clauditseo.api.app import create_app
from tests.conftest import FixtureSite
from tests.test_history_g4 import BROKEN_PROMO, GOOD_PROMO, _routes


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDITSEO_LLM_PROVIDER", "mock")
    monkeypatch.delenv("CLAUDITSEO_TOKEN", raising=False)
    # Tests audit local fixture servers whose host can't match the site domain.
    monkeypatch.setenv("CLAUDITSEO_ALLOW_ARBITRARY_START_URL", "1")
    return TestClient(create_app(db_path=tmp_path / "g6.db"))


def test_start_url_containment(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDITSEO_TOKEN", raising=False)
    monkeypatch.delenv("CLAUDITSEO_ALLOW_ARBITRARY_START_URL", raising=False)
    api = TestClient(create_app(db_path=tmp_path / "contain.db"))
    client_id = api.post("/api/clients", json={"name": "Contain Co"}).json()["id"]
    site_id = api.post(f"/api/clients/{client_id}/sites",
                       json={"domain": "contain.example"}).json()["id"]

    off_host = api.post(f"/api/sites/{site_id}/audits",
                        json={"dims": ["TEC"], "tier": "T1",
                              "start_url": "https://elsewhere.example/"})
    assert off_host.status_code == 422
    loopback = api.post(f"/api/sites/{site_id}/audits",
                        json={"dims": ["TEC"], "tier": "T1",
                              "start_url": "http://127.0.0.1:9/"})
    assert loopback.status_code == 422
    subdomain = api.post(f"/api/sites/{site_id}/audits",
                         json={"dims": ["TEC"], "tier": "T1",
                               "start_url": "https://www.contain.example/"})
    assert subdomain.status_code == 202


def _wait_complete(api: TestClient, run_id: str, timeout: float = 60) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = api.get(f"/api/runs/{run_id}").json()
        if run["status"] in ("complete", "failed"):
            return run
        time.sleep(0.3)
    raise AssertionError("run did not finish in time")


def _launch(api: TestClient, site_id: str, promo_html: str, analyst: bool = False) -> dict:
    server = FixtureSite(_routes(promo_html)).start()
    try:
        resp = api.post(f"/api/sites/{site_id}/audits",
                        json={"dims": ["ONP", "TEC"], "tier": "T2",
                              "analyst": analyst,
                              "start_url": server.base_url + "/"})
        assert resp.status_code == 202, resp.text
        run = _wait_complete(api, resp.json()["run_id"])
    finally:
        server.stop()
    assert run["status"] == "complete", run
    return run


def test_g6_full_dashboard_flow(api):
    # create client -> add site
    client_id = api.post("/api/clients", json={"name": "Gate Six Pty Ltd"}).json()["id"]
    site_id = api.post(f"/api/clients/{client_id}/sites",
                       json={"domain": "gatesix.example"}).json()["id"]

    # run 1 (defect present) — findings visible, analyst band separate
    run1 = _launch(api, site_id, BROKEN_PROMO, analyst=True)
    det = run1["deterministic_findings"]
    ana = run1["analyst_findings"]
    assert any(f["check_id"] == "title-missing" for f in det)
    assert ana, "mock provider should produce analyst insights"
    assert all(f["source"] == "model-judgement" and f["model_id"] for f in ana)
    assert not any(f["source"] == "model-judgement" for f in det)
    assert run1["composite_score"] is not None

    # runs 2 (fixed) and 3 (broken again) -> regression
    run2 = _launch(api, site_id, GOOD_PROMO)
    run3 = _launch(api, site_id, BROKEN_PROMO)

    # compare by fingerprint
    diff = api.get("/api/compare", params={"a": run2["id"], "b": run3["id"]}).json()
    assert any(f["check_id"] == "title-missing" for f in diff["new"])
    diff12 = api.get("/api/compare", params={"a": run1["id"], "b": run2["id"]}).json()
    assert any(f["check_id"] == "title-missing" for f in diff12["resolved"])

    # regression banner data on site detail
    site = api.get(f"/api/sites/{site_id}").json()
    regressed = site["regressions"]
    assert any(s["check_id"] == "title-missing" for s in regressed)
    assert regressed[0]["changed_by_run"] == run3["id"]
    assert regressed[0]["affected_urls"], "states must link to the affected page"
    assert regressed[0]["affected_urls"][0].endswith("/promo")

    # client list rolls up the regression count
    detail = api.get(f"/api/clients/{client_id}").json()
    assert detail["sites"][0]["regressions"] >= 1
    assert detail["sites"][0]["latest_score"] == run3["composite_score"]

    # trend has three points
    trend = api.get(f"/api/sites/{site_id}/trend").json()
    assert len(trend) == 3

    # history chat: seeded question cites the correct (regression) run
    chat = api.post("/api/chat", json={"site_id": site_id,
                                       "question": "What regressed for Gate Six?"}).json()
    assert run3["id"] in chat["cited_runs"]
    assert "title-missing" in chat["answer"]

    # scores/weights visible per dimension
    assert set(run3["subscores"]) == {"ONP", "TEC"}
    assert run1["costs"], "analyst run should have cost log entries"


def test_delete_run_cleans_findings_and_trend(api):
    client_id = api.post("/api/clients", json={"name": "Delete Co"}).json()["id"]
    site_id = api.post(f"/api/clients/{client_id}/sites",
                       json={"domain": "delete.example"}).json()["id"]
    run1 = _launch(api, site_id, BROKEN_PROMO)
    run2 = _launch(api, site_id, BROKEN_PROMO)
    assert len(api.get(f"/api/sites/{site_id}/trend").json()) == 2

    assert api.delete(f"/api/runs/{run1['id']}").status_code == 200
    assert api.get(f"/api/runs/{run1['id']}").status_code == 404
    assert len(api.get(f"/api/sites/{site_id}/trend").json()) == 1
    assert api.get(f"/api/runs/{run2['id']}").json()["status"] == "complete"
    assert api.delete("/api/runs/nonexistent").status_code == 404


def test_delete_client_cascades_all_history(api):
    client_id = api.post("/api/clients", json={"name": "Doomed Co"}).json()["id"]
    site_id = api.post(f"/api/clients/{client_id}/sites",
                       json={"domain": "doomed.example"}).json()["id"]
    run = _launch(api, site_id, BROKEN_PROMO)

    assert api.delete(f"/api/clients/{client_id}").status_code == 200
    assert api.get(f"/api/clients/{client_id}").status_code == 404
    assert api.get(f"/api/sites/{site_id}").status_code == 404
    assert api.get(f"/api/runs/{run['id']}").status_code == 404
    assert api.delete(f"/api/clients/{client_id}").status_code == 404  # already gone
    names = {c["name"] for c in api.get("/api/clients").json()}
    assert "Doomed Co" not in names


def test_g6_meta_and_launcher_validation(api):
    meta = api.get("/api/meta").json()
    codes = {d["code"] for d in meta["dimensions"]}
    assert {"TEC", "ONP", "PRF", "CNT", "OFP", "LOC", "AIS"} <= codes
    assert meta["analyst_available"] is True  # mock provider counts
    providers = meta["providers"]
    assert providers["LLM analyst"]["configured"] is True   # mock counts
    assert providers["Moz"]["configured"] is False          # keyless env
    for status in providers.values():                       # never leak values
        # A whitelist, not a spot check: the point is that nothing
        # else is in there, so a value can never be added by accident.
        assert set(status) == {"configured", "detail", "env",
                               "managed", "source"}
    assert meta["dimension_providers"]["PRF"] == ["PageSpeed", "CrUX"]
    assert "claude-fable-5" in meta["models"]
    client_id = api.post("/api/clients", json={"name": "V"}).json()["id"]
    site_id = api.post(f"/api/clients/{client_id}/sites",
                       json={"domain": "v.example"}).json()["id"]
    bad = api.post(f"/api/sites/{site_id}/audits", json={"dims": ["NOPE"], "tier": "T2"})
    assert bad.status_code == 422


def test_analyst_model_override():
    import dataclasses

    from clauditseo.analysts.layer import provider_from_settings
    from clauditseo.config import Settings

    cfg = dataclasses.replace(Settings(), anthropic_api_key="k",
                              llm_provider="anthropic", llm_model="claude-sonnet-5")
    assert provider_from_settings(cfg).model_id == "claude-sonnet-5"
    assert provider_from_settings(cfg, "claude-fable-5").model_id == "claude-fable-5"


def test_g6_token_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDITSEO_TOKEN", "s3cret")
    api = TestClient(create_app(db_path=tmp_path / "auth.db"))
    assert api.get("/api/health").status_code == 200          # health stays open
    assert api.get("/api/clients").status_code == 401
    ok = api.get("/api/clients", headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200


# --- item 169: a site can be deleted, and the cascade is the schema's ---------

def test_delete_site_cascades_its_history(api, tmp_path):
    from clauditseo.db.connection import connect
    from clauditseo.persistence import runs as _runs
    client_id = api.post("/api/clients", json={"name": "Two Sites Co"}).json()["id"]
    doomed = api.post(f"/api/clients/{client_id}/sites", json={"domain": "doomed.example"}).json()["id"]
    kept = api.post(f"/api/clients/{client_id}/sites", json={"domain": "kept.example"}).json()["id"]
    run = _launch(api, doomed, BROKEN_PROMO)
    other = _launch(api, kept, BROKEN_PROMO)
    assert api.post(f"/api/sites/{doomed}/notes", json={"note": "remove me"}).status_code == 201
    # An expert report on the doomed run: foreign keys are on, and the old
    # client cascade never deleted these, so it would have failed here.
    conn = connect(tmp_path / "g6.db")
    _runs.store_expert_report(conn, run["id"], "crawl", {"status": "ok", "report": "", "model": "m"})
    conn.close()

    assert api.delete(f"/api/sites/{doomed}").status_code == 200
    assert api.get(f"/api/sites/{doomed}").status_code == 404
    assert api.get(f"/api/runs/{run['id']}").status_code == 404
    assert api.get(f"/api/sites/{kept}").status_code == 200
    assert api.get(f"/api/runs/{other['id']}").status_code == 200
    assert api.get(f"/api/clients/{client_id}").status_code == 200
    assert api.delete(f"/api/sites/{doomed}").status_code == 404

    conn = connect(tmp_path / "g6.db")
    for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        if "site_id" in cols:
            assert not conn.execute(f"SELECT 1 FROM {table} WHERE site_id=?", (doomed,)).fetchone(), table
        if "run_id" in cols:
            assert not conn.execute(f"SELECT 1 FROM {table} WHERE run_id=?", (run["id"],)).fetchone(), table
    conn.close()
    assert api.delete(f"/api/clients/{client_id}").status_code == 200


def test_the_cascade_names_every_table_keyed_by_a_site_or_a_run(tmp_path):
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.persistence import repo
    conn = connect(tmp_path / "schema.db")
    migrate(conn)
    for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        if table in ("audit_runs", "sites"):
            continue
        if "run_id" in cols:
            assert table in repo.RUN_TABLES or table in repo.SITE_TABLES, table
        if "site_id" in cols:
            assert table in repo.SITE_TABLES, table
    conn.close()
