"""A brief's default model is chosen once, on Admin > Brief defaults, from
the priced models; the catalogue shows it and the next run uses it; no
per-brief default is hard-coded in the dashboard.

Brief v4 Item 3g (`_plans/site-screen-brief-v4-2026-09-03.md`). The
default was whatever the catalogue's select pre-picked - the tier's model,
set in code and invisible - and the sixteen-option select on every row
bound nothing.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from clauditseo import tiers
from clauditseo.analysts.expert import model_for_tool
from clauditseo.config import Settings

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"


def test_the_resolver_reads_the_briefs_own_default_before_its_tier():
    cfg = Settings(llm_model_fast="fast-m", llm_model="std-m", llm_model_deep="deep-m")
    assert model_for_tool(cfg, "crawl") == "std-m"
    assert model_for_tool(cfg, "crawl", chosen={"crawl": "picked-m"}) == "picked-m"
    # A per-run override still wins over the brief's default.
    assert model_for_tool(cfg, "crawl", "once-m", {"crawl": "picked-m"}) == "once-m"


def _api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from clauditseo.api.app import create_app
    monkeypatch.delenv("CLAUDITSEO_TOKEN", raising=False)
    monkeypatch.setenv("CLAUDITSEO_LLM_PROVIDER", "mock")
    return TestClient(create_app(db_path=tmp_path / "briefs.db"))


def test_a_default_set_on_admin_is_what_the_catalogue_shows_and_the_run_uses(tmp_path, monkeypatch):
    import httpx

    from clauditseo.db.connection import connect
    from clauditseo.persistence import runs
    from tests.test_coverage import DIMS, _Hub, _run

    client = _api(tmp_path, monkeypatch)
    # Only a priced model may be a default.
    refused = client.put("/api/models/briefs/crawl", json={"model": "claude-nowhere-1"})
    assert refused.status_code == 422 and "price" in refused.json()["detail"]
    conn = connect(tmp_path / "briefs.db")
    if not tiers.priced_models(conn):
        with conn:
            conn.execute("INSERT INTO model_prices (model, input_usd, output_usd, entered_at, source)"
                         " VALUES ('claude-sonnet-5', 3, 15, '2026-09-03T00:00:00', 'test')")
    table = client.get("/api/models/briefs").json()
    assert {m["model"] for m in table["models"]} == set(tiers.priced_models(conn))
    row = next(b for b in table["briefs"] if b["tool"] == "crawl")
    assert row["chosen"] is False and row["tier"] == "standard" and row["why"], row

    cid = client.post("/api/clients", json={"name": "C"}).json()["id"]
    site = client.post(f"/api/clients/{cid}/sites", json={"domain": "briefs.test"}).json()["id"]
    run_id = runs.create_run(conn, site, DIMS, "T2")
    runs.complete_run(conn, run_id, _run(_Hub()))
    before = client.get(f"/api/runs/{run_id}/analyses").json()
    tier_model = next(a["model"] for a in before["ready"] + before["available"]
                      if a["tool"] == "crawl")

    picked = tiers.priced_models(conn)[0]
    assert client.put("/api/models/briefs/crawl", json={"model": picked}).status_code == 200
    after = client.get("/api/models/briefs").json()
    row = next(b for b in after["briefs"] if b["tool"] == "crawl")
    assert row["chosen"] is True and row["model"] == picked
    lanes = client.get(f"/api/runs/{run_id}/analyses").json()
    assert next(a["model"] for a in lanes["ready"] + lanes["available"]
                if a["tool"] == "crawl") == picked

    # The run resolves the same model where the money is committed.
    seen: list[str | None] = []
    import clauditseo.api.app as app_mod
    real = app_mod.provider_from_settings

    def spy(cfg, model=None):
        seen.append(model)
        return real(cfg, model)
    monkeypatch.setattr(app_mod, "provider_from_settings", spy)
    ran = client.post(f"/api/runs/{run_id}/expert/crawl", json={})
    assert ran.status_code in (200, 201), ran.text
    assert seen == [picked], (seen, tier_model)

    # Cleared, the tier decides again.
    client.delete("/api/models/briefs/crawl")
    row = next(b for b in client.get("/api/models/briefs").json()["briefs"] if b["tool"] == "crawl")
    assert row["chosen"] is False and row["model"] == tier_model
    conn.close()


def test_no_per_brief_default_is_hard_coded_in_the_dashboard():
    for name in ("analyses.tsx", "catalogue.tsx"):
        text = (SRC / name).read_text(encoding="utf-8")
        # Code, not comments: `shortModel`'s doc shows an id as an example.
        code = re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.S)
        assert not re.search(r"claude-(haiku|sonnet|opus)", code), f"{name} names a model"
    catalogue = (SRC / "catalogue.tsx").read_text(encoding="utf-8")
    assert "#/admin?tab=briefs" in catalogue, "the catalogue's default-model text does not link to Admin"
