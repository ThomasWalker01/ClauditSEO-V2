"""A price in the ledger says what put it there.

WF-33, carried from report 033 and reproduced on the live database at every
audit since. The measurement, taken again at round 089 and unchanged in
fifty-five reports:

    SELECT COUNT(*), SUM(entered_by IS NULL) FROM model_prices  ->  16, 16

Sixteen rows appeared on 2026-08-17 with `entered_by = NULL`, no commit
touching them and no row in `OPERATOR_ACTIONS.md`. That file's own preamble
states the test it has to pass -- "a round should be able to *attribute* a
finding's disappearance to a recorded action, rather than deduce one" -- and
these rows sit underneath every cost figure the product quotes an operator.

**Why an authenticated operator alone is not the fix.** `auth` returns the
operator dict *or None for full-access contexts*, and this install is one:
one operator row, no token hash, no `CLAUDITSEO_TOKEN`, so `any_operator_tokens`
is false and every request runs in open local mode with `operator = None`.
Recording `operator["id"] if operator else None` would therefore have written
NULL sixteen more times and closed nothing. The column records an actor
either way -- `operator:<id>` when a person is identified, `api:<route>` when
the caller is a full-access context and the honest answer is which route
wrote the row.

`entered_by` had two writers and, measured by grep across `.py`, `.ts`,
`.tsx` and `.sql`, **no reader** -- so there is no consumer to migrate and the
column's vocabulary is settled here.

`refresh` takes `entered_by` as a required keyword rather than a defaulted
one. A default is how this defect comes back: the next caller inherits NULL
without being asked.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from clauditseo.api.app import create_app
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo
from clauditseo.providers import model_prices as mp

PRICES = {"claude-opus-5": (5.0, 25.0), "claude-sonnet-5": (2.0, 10.0)}


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "prices.db")
    migrate(c)
    yield c
    c.close()


@pytest.fixture
def api(tmp_path, monkeypatch):
    """Open local mode -- the shape this install actually runs in."""
    monkeypatch.delenv("CLAUDITSEO_TOKEN", raising=False)
    db = tmp_path / "api.db"
    c = connect(db)
    migrate(c)
    yield c, TestClient(create_app(db_path=db))
    c.close()


def _actors(c) -> list:
    return [r[0] for r in c.execute(
        "SELECT entered_by FROM model_prices ORDER BY model")]


# --- the defect --------------------------------------------------------


def test_a_fetched_price_records_what_stored_it(conn, monkeypatch):
    monkeypatch.setattr(mp, "fetch", lambda *a, **k: dict(PRICES))
    out = mp.refresh(conn, entered_by="operator:abc123")
    assert out["ok"] and out["stored"] == 2
    assert _actors(conn) == ["operator:abc123", "operator:abc123"], (
        "a stored price does not say what put it there")


def test_a_second_fetch_records_the_actor_that_overwrote_the_row(conn,
                                                                 monkeypatch):
    """`ON CONFLICT DO UPDATE` refreshed the figure, the date, the source and
    the source URL and left `entered_by` at whatever the first write said. A
    row that names the wrong actor is worse than one that names none."""
    monkeypatch.setattr(mp, "fetch", lambda *a, **k: dict(PRICES))
    mp.refresh(conn, entered_by="operator:first")
    mp.refresh(conn, entered_by="operator:second")
    assert _actors(conn) == ["operator:second", "operator:second"]


def test_the_route_records_itself_when_no_operator_is_identified(api,
                                                                 monkeypatch):
    """The case this install is in, and the reason the fix is not
    `operator["id"] if operator else None`."""
    conn, client = api
    monkeypatch.setattr(mp, "fetch", lambda *a, **k: dict(PRICES))
    resp = client.post("/api/rates/fetch-prices", json={})
    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is True
    assert _actors(conn) == ["api:fetch-prices", "api:fetch-prices"], (
        "sixteen unattributed rows is the finding; this is the seventeenth")


def test_an_authenticated_operator_is_recorded_by_id(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDITSEO_TOKEN", raising=False)
    db = tmp_path / "op.db"
    c = connect(db)
    migrate(c)
    op_id, token = repo.create_operator(c, "Olive Owner", role="owner")
    client = TestClient(create_app(db_path=db))
    monkeypatch.setattr(mp, "fetch", lambda *a, **k: dict(PRICES))
    resp = client.post("/api/rates/fetch-prices", json={},
                       headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    assert _actors(c) == [f"operator:{op_id}"] * 2
    c.close()


def test_a_hand_typed_price_records_its_actor_in_the_same_vocabulary(api):
    """Both writers or neither. A column whose two writers disagree about
    what it holds cannot be read back by anything."""
    conn, client = api
    resp = client.put("/api/rates/model-price",
                      json={"model": "claude-opus-5",
                            "input_usd": 4.0, "output_usd": 20.0})
    assert resp.status_code == 200, resp.text
    assert _actors(conn) == ["api:set-model-price"]


def test_refresh_will_not_store_a_price_without_being_told_who(conn):
    """A defaulted `entered_by` is how this returns: the next caller inherits
    NULL without ever being asked the question."""
    with pytest.raises(TypeError):
        mp.refresh(conn)          # type: ignore[call-arg]


# --- the must-not-change directions ------------------------------------


def test_a_fetch_still_never_overwrites_a_price_the_operator_typed(conn,
                                                                   monkeypatch):
    """CQ-201, as above: the operator row here is built by hand, and no route
    could write one until CQ-200 landed. The shape is now the route's own —
    `tests/test_a_typed_price_is_filed_as_the_operators.py` pins it against a
    row the API created, so this fixture stops being a claim about a state the
    product cannot reach.
    """
    from clauditseo.persistence.repo import now_iso
    conn.execute("INSERT INTO model_prices (model, input_usd, output_usd,"
                 " entered_at, entered_by, source) VALUES ('claude-opus-5',"
                 " 1.5, 7.5, ?, 'operator:mine', 'operator')", (now_iso(),))
    conn.commit()
    monkeypatch.setattr(mp, "fetch", lambda *a, **k: dict(PRICES))
    out = mp.refresh(conn, entered_by="api:fetch-prices")

    row = conn.execute("SELECT * FROM model_prices WHERE"
                       " model='claude-opus-5'").fetchone()
    assert (row["input_usd"], row["output_usd"]) == (1.5, 7.5), "operator wins"
    assert row["entered_by"] == "operator:mine", (
        "a kept row keeps its actor too -- the fetch did not write it")
    assert "claude-opus-5" in out["kept"]


def test_a_failed_fetch_still_reports_it_and_changes_nothing(conn,
                                                             monkeypatch):
    monkeypatch.setattr(mp, "fetch", lambda *a, **k: (_ for _ in ()).throw(
        OSError("no route to host")))
    out = mp.refresh(conn, entered_by="api:fetch-prices")
    assert out["ok"] is False and out["stored"] == 0
    assert "no route to host" in out["error"]
    assert conn.execute("SELECT COUNT(*) FROM model_prices").fetchone()[0] == 0


def test_the_source_and_date_a_row_already_carried_are_unchanged(conn,
                                                                 monkeypatch):
    """The panel renders `source` and `entered_at`. Adding an actor must not
    disturb the two provenance fields that already reach a screen."""
    monkeypatch.setattr(mp, "fetch", lambda *a, **k: dict(PRICES))
    mp.refresh(conn, entered_by="api:fetch-prices")
    row = conn.execute("SELECT * FROM model_prices WHERE"
                       " model='claude-sonnet-5'").fetchone()
    assert row["source"] == mp.SOURCE
    assert row["source_url"] == mp.PRICES_URL
    assert row["entered_at"], "a price without a date cannot be called stale"
