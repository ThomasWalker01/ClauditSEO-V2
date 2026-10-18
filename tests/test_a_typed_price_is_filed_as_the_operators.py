"""A price the operator types over a fetched row is filed as theirs.

CQ-200, reproduced end to end at report 090 and carried at High through
reports 091, 092, 094 and 095. `PUT /api/rates/model-price` upserted the
column list `(model, input_usd, output_usd, entered_at, entered_by)` with an
`ON CONFLICT DO UPDATE` that set four columns and never `source`. A model
nobody had fetched was safe -- `source` is `NOT NULL DEFAULT 'operator'`
(`clauditseo/db/migrations/0014_price_provenance.sql`) -- but an existing row
kept whatever it already had, and every row a real operator would price is an
existing one. Measured read-only on `data/clauditseo.db` on 2026-08-24: 16
rows, all `source='anthropic-pricing-docs'`, all carrying the vendor
`source_url`, **none `operator`**.

So a figure the operator invented was stored under the vendor's name, holding
the vendor's URL, and the next press of `read Claude prices` destroyed it --
`refresh` decides what to leave alone with `WHERE source='operator'` and the
row never claimed to be.

`QUESTIONS.md` **Q-11** asked whether the row should change hands or the panel
should refuse the overwrite so that "published" and "yours" stayed two rows.
The operator answered **one row that changes hands** (2026-08-24): the schema
forbids two -- `model` is the PRIMARY KEY, and `sqlite_autoindex_model_prices_1`
confirms it on the live database -- and the divergence figure the two-row shape
was argued for has never been reachable on this data.

**That answer's stated cost is not real, and the last test here is why.**
Q-11's options text held that overwriting the published figure leaves `differs`
nothing to compare a kept price against. It does not: `refresh` computes
`differs` against the prices it has *just fetched*, never against a published
figure held on file, so a kept row is still compared with today's list price.
The property the rejected option existed to buy is one this shape already has,
and it is guarded here so that stays true.

Written against the API rather than with literal SQL, which is **CQ-201**: the
two guards that already covered this contract each built the operator row by
hand with `source='operator'` in the INSERT -- a row no route could produce --
so both stood green while the property they named was false. What was missing
was not an assertion but a row the product wrote, and that is what these tests
use.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from clauditseo.api.app import create_app
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.providers import model_prices as mp

PRICES = {"claude-opus-5": (5.0, 25.0), "claude-sonnet-5": (2.0, 10.0)}

#: What the operator types over the vendor's figure. Deliberately nothing like
#: the published number, so a test that silently kept list price cannot pass.
NEGOTIATED = {"model": "claude-opus-5", "input_usd": 1.0, "output_usd": 2.0}


@pytest.fixture
def api(tmp_path, monkeypatch):
    """Open local mode -- the shape this install actually runs in."""
    monkeypatch.delenv("CLAUDITSEO_TOKEN", raising=False)
    db = tmp_path / "api.db"
    c = connect(db)
    migrate(c)
    yield c, TestClient(create_app(db_path=db))
    c.close()


def _fetch(client, monkeypatch) -> dict:
    """Put the ledger in the state all sixteen live rows are in: vendor-sourced,
    stored by a press of `read Claude prices`."""
    monkeypatch.setattr(mp, "fetch", lambda *a, **k: dict(PRICES))
    resp = client.post("/api/rates/fetch-prices", json={})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _row(c, model: str = "claude-opus-5"):
    return c.execute("SELECT * FROM model_prices WHERE model=?",
                     (model,)).fetchone()


# --- the defect --------------------------------------------------------


def test_a_typed_price_over_a_fetched_row_claims_the_row(api, monkeypatch):
    conn, client = api
    _fetch(client, monkeypatch)
    before = _row(conn)
    assert before["source"] == mp.SOURCE and before["source_url"], (
        "precondition: the row the operator is about to price is the vendor's")

    resp = client.put("/api/rates/model-price", json=NEGOTIATED)
    assert resp.status_code == 200, resp.text

    row = _row(conn)
    assert (row["input_usd"], row["output_usd"]) == (1.0, 2.0)
    assert row["source"] == "operator", (
        "a number the operator invented is on file as the vendor's published "
        "figure, under every client cost quote the product computes")
    assert row["source_url"] is None, (
        "the vendor's URL is still cited for a price the vendor never published")
    assert row["entered_by"] == "api:set-model-price", (
        "WF-33's column must not regress while this one is repaired")


def test_the_next_fetch_keeps_a_price_the_operator_typed_at_the_panel(
        api, monkeypatch):
    """The button's own caption promises this: "Your own entries are never
    overwritten." Before CQ-200 it was false for every row that had ever been
    fetched, which on the live database is all of them."""
    conn, client = api
    _fetch(client, monkeypatch)
    assert client.put("/api/rates/model-price",
                      json=NEGOTIATED).status_code == 200

    out = _fetch(client, monkeypatch)

    row = _row(conn)
    assert (row["input_usd"], row["output_usd"]) == (1.0, 2.0), (
        "the negotiated rate was replaced by list price")
    assert "claude-opus-5" in out["kept"], "the operator is told what was kept"
    assert _row(conn, "claude-sonnet-5")["input_usd"] == 2.0, (
        "the models the operator did not price still track the vendor")


def test_a_kept_price_is_still_compared_with_todays_published_figure(
        api, monkeypatch):
    """Q-11's rejected option was argued for on the claim that this figure is
    unreachable once the row changes hands. It is not: `differs` compares the
    kept row against the prices the fetch has just read, not against a
    published figure held on file."""
    conn, client = api
    _fetch(client, monkeypatch)
    assert client.put("/api/rates/model-price",
                      json=NEGOTIATED).status_code == 200

    out = _fetch(client, monkeypatch)

    assert out["differs"] == [{"model": "claude-opus-5",
                               "yours": [1.0, 2.0],
                               "published": [5.0, 25.0]}], (
        "a kept price that disagrees with list price must say by how much")


# --- the must-not-change direction -------------------------------------


def test_a_price_for_a_model_never_fetched_is_filed_the_same_way(api):
    """Already correct before CQ-200, by the column default rather than by the
    route -- which is exactly why the defect was invisible: the easy case to
    try by hand is the one that worked."""
    conn, client = api
    resp = client.put("/api/rates/model-price",
                      json={"model": "claude-negotiated-1",
                            "input_usd": 0.5, "output_usd": 1.5})
    assert resp.status_code == 200, resp.text

    row = _row(conn, "claude-negotiated-1")
    assert row["source"] == "operator" and row["source_url"] is None
