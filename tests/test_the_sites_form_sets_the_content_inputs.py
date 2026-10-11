"""The Sites form sets the Content briefs' eight inputs (screen audits round 3,
Admin AC-01).

The site record accepted word floors, mandatory formats, authors, proof
assets, competitors, keyword data, the top-10 corpus and publish history; the
engine held every Benchmark row on the last four and sent the operator to
"authors"; and no screen could set any of them.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from clauditseo.api.app import create_app

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "admin.tsx"
FIELDS = ("word_floors", "mandatory_formats", "authors", "proof_assets",
          "competitors", "keyword_data", "top10_corpus", "publish_history")


def test_the_form_has_a_field_for_each():
    src = SRC.read_text(encoding="utf-8")
    for k in FIELDS:
        assert f'"{k}",' in src.split("function SiteRecordForm", 1)[1], k


def test_the_shapes_the_form_sends_are_stored(tmp_path):
    api = TestClient(create_app(db_path=tmp_path / "c.db"))
    client_id = api.post("/api/clients", json={"name": "T"}).json()["id"]
    site_id = api.post(f"/api/clients/{client_id}/sites",
                       json={"domain": "https://t.example/"}).json()["id"]
    body = {"word_floors": {"service": 400},
            "mandatory_formats": {"service": ["FAQ", "pricing table"]},
            "authors": [{"name": "A. Writer", "credentials": "CPA"}],
            "proof_assets": [{"name": "Case study", "detail": "/work/x/"}],
            "competitors": ["rival.example"],
            "keyword_data": {"web design": "1,000"},
            "top10_corpus": {"web design": "a.example, b.example"},
            "publish_history": {"2026-09": "two posts"}}
    assert api.put(f"/api/sites/{site_id}", json=body).status_code == 200
    got = api.get(f"/api/sites/{site_id}").json()
    for k, v in body.items():
        assert got.get(k) == v, (k, got.get(k))
