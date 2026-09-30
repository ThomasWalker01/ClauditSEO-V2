"""Published prices are read, not retyped — and never silently.

The claim this file replaces was that no vendor publishes a machine-readable
price feed, so every price had to be entered by hand. Anthropic serves
`/docs/en/about-claude/pricing.md` as text/markdown, and the operator's
hand-typed `claude-sonnet-5` price was $3/$15 within an hour of the published
figure being $2/$10.

What survives is the part of the old rule that was load-bearing: nothing is
invented, everything carries its source and date, and a fetch never overwrites
a number a human typed.

Parses a captured copy of the table rather than the live page. A test that
fetches over the network fails on a train, and a parser needs to be tested
against the shape that broke it, not against whatever is served today.
"""

from __future__ import annotations

import pytest

from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.providers import model_prices as mp

#: Captured from the live page. Kept verbatim, including the parenthesised
#: deprecation links and the ragged column padding — those are exactly what a
#: naive split gets wrong.
PAGE = """---
title: Pricing
---

## Model pricing

| Model | Base Input Tokens | 5m Cache Writes | 1h Cache Writes | Cache Hits & Refreshes | Output Tokens |
| ----- | ----------------- | --------------- | --------------- | ---------------------- | ------------- |
| Claude Fable 5                                             | $10 / MTok   | $12.50 / MTok | $20 / MTok   | $1 / MTok    | $50 / MTok |
| Claude Opus 5                                              | $5 / MTok    | $6.25 / MTok  | $10 / MTok   | $0.50 / MTok | $25 / MTok |
| Claude Opus 4.1 ([retired](https://example.test/deprecs))  | $15 / MTok   | $18.75 / MTok | $30 / MTok   | $1.50 / MTok | $75 / MTok |
| Claude Sonnet 5                                            | $2 / MTok    | $2.50 / MTok  | $4 / MTok    | $0.20 / MTok | $10 / MTok |
| Claude Haiku 4.5                                           | $1 / MTok    | $1.25 / MTok  | $2 / MTok    | $0.10 / MTok | $5 / MTok  |

<Note>MTok = Million tokens.</Note>

## Cloud platform pricing

| Model         | Batch input  | Batch output  |
| ------------- | ------------ | ------------- |
| Claude Opus 5 | $2.50 / MTok | $12.50 / MTok |
"""


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "prices.db")
    migrate(c)
    return c


def test_the_published_table_parses_to_input_and_output():
    prices = mp.parse(PAGE)
    assert prices["claude-opus-5"] == (5.0, 25.0)
    assert prices["claude-fable-5"] == (10.0, 50.0)
    assert prices["claude-haiku-4-5"] == (1.0, 5.0)


def test_sonnet_5_is_read_as_published_not_as_remembered():
    """The concrete failure. A price typed from memory was $3/$15; the
    published figure is $2/$10 because the introductory rate became standard
    and the scheduled increase was cancelled. Nothing about the typed number
    looked wrong."""
    assert mp.parse(PAGE)["claude-sonnet-5"] == (2.0, 10.0)


def test_the_cache_columns_are_not_mistaken_for_the_price():
    """Six columns, and the two that matter are the ends. Reading the second
    money column would price every model at its 5-minute cache-write rate."""
    prices = mp.parse(PAGE)
    for model, (inp, out) in prices.items():
        assert out > inp, f"{model} read its cache column as the output price"
    assert prices["claude-opus-5"][0] != 6.25, "that is the 5m cache write"


def test_a_deprecation_link_is_not_part_of_the_model_name():
    """"Claude Opus 4.1 ([retired](url))" is one model, not a parse failure."""
    assert "claude-opus-4-1" in mp.parse(PAGE)


def test_the_batch_table_below_is_not_read_as_model_pricing():
    """It has the same row shape and half the values, so a parser anchored to
    "the first table" would price Opus 5 at the batch rate."""
    assert mp.parse(PAGE)["claude-opus-5"] == (5.0, 25.0)


def test_the_dated_model_id_this_install_sends_is_priced():
    """`model_for_tool` returns `claude-haiku-4-5-20251001`; the pricing page
    lists "Claude Haiku 4.5". An unpriced alias shows as tokens forever."""
    prices = mp.expand(mp.parse(PAGE))
    assert prices["claude-haiku-4-5-20251001"] == prices["claude-haiku-4-5"]


def test_a_restructured_page_fails_loudly():
    """The alternative is storing whatever the new first column contains."""
    with pytest.raises(ValueError, match="Model pricing"):
        mp.parse("# Pricing\n\nSee the console for current rates.\n")


def test_a_table_with_no_model_rows_is_an_error_not_an_empty_success():
    with pytest.raises(ValueError, match="no model rows"):
        mp.parse("## Model pricing\n\n| a | b |\n| --- | --- |\n\n"
                 "## Cloud platform pricing\n")


# --- storage: provenance, and the human's number wins ----------------------

def test_a_fetch_records_where_each_price_came_from(conn, monkeypatch):
    monkeypatch.setattr(mp, "fetch", lambda *a, **k: mp.expand(mp.parse(PAGE)))
    out = mp.refresh(conn, entered_by="api:fetch-prices")
    assert out["ok"] and out["stored"] >= 5
    row = conn.execute("SELECT * FROM model_prices WHERE model='claude-opus-5'"
                       ).fetchone()
    assert (row["input_usd"], row["output_usd"]) == (5.0, 25.0)
    assert row["source"] == mp.SOURCE
    assert row["source_url"] == mp.PRICES_URL
    assert row["entered_at"], "a price without a date cannot be called stale"


def test_a_fetch_never_overwrites_a_price_the_operator_typed(conn, monkeypatch):
    """A negotiated rate is a fact about this customer that list price does
    not know. Replacing it with the public figure is the same class of error
    as leaving a stale hand-typed one.

    CQ-201: this row is built with literal SQL, and until CQ-200 was fixed no
    route could produce it — the one writer of an operator price never set
    `source`, so this guard was green while the property it names was false
    for every row in the ledger. The row below is now exactly what
    `PUT /api/rates/model-price` writes, and
    `tests/test_a_typed_price_is_filed_as_the_operators.py` is where that is
    asserted end to end, against a row the product wrote rather than one the
    test did. Keep this one at the module level: it covers `refresh` without a
    web layer, and it is only trustworthy while that other file is green.
    """
    from clauditseo.persistence.repo import now_iso

    conn.execute("INSERT INTO model_prices (model, input_usd, output_usd,"
                 " entered_at, source) VALUES ('claude-opus-5', 1.5, 7.5, ?,"
                 " 'operator')", (now_iso(),))
    conn.commit()
    monkeypatch.setattr(mp, "fetch", lambda *a, **k: mp.expand(mp.parse(PAGE)))
    out = mp.refresh(conn, entered_by="api:fetch-prices")

    row = conn.execute("SELECT * FROM model_prices WHERE model='claude-opus-5'"
                       ).fetchone()
    assert (row["input_usd"], row["output_usd"]) == (1.5, 7.5), "operator wins"
    assert row["source"] == "operator"
    assert "claude-opus-5" in out["kept"], "the caller is told what was kept"
    assert conn.execute("SELECT COUNT(*) FROM model_prices WHERE"
                        " model='claude-sonnet-5'").fetchone()[0] == 1, (
        "the other models still got their published price")


def test_a_second_fetch_updates_its_own_rows(conn, monkeypatch):
    """The point of a lookup is that it tracks the vendor."""
    monkeypatch.setattr(mp, "fetch", lambda *a, **k: {"claude-opus-5": (5.0, 25.0)})
    mp.refresh(conn, entered_by="api:fetch-prices")
    monkeypatch.setattr(mp, "fetch", lambda *a, **k: {"claude-opus-5": (6.0, 30.0)})
    mp.refresh(conn, entered_by="api:fetch-prices")
    row = conn.execute("SELECT input_usd, output_usd FROM model_prices"
                       " WHERE model='claude-opus-5'").fetchone()
    assert (row["input_usd"], row["output_usd"]) == (6.0, 30.0)


def test_a_failed_fetch_reports_it_and_changes_nothing(conn, monkeypatch):
    monkeypatch.setattr(mp, "fetch", lambda *a, **k: (_ for _ in ()).throw(
        OSError("no route to host")))
    out = mp.refresh(conn, entered_by="api:fetch-prices")
    assert out["ok"] is False and out["stored"] == 0
    assert "no route to host" in out["error"]
    assert conn.execute("SELECT COUNT(*) FROM model_prices").fetchone()[0] == 0


def test_a_fetched_price_reaches_the_cost_calculation(conn, monkeypatch):
    """The whole point. A price nothing reads is a form that changes nothing."""
    from clauditseo.providers import fx

    monkeypatch.setattr(mp, "fetch", lambda *a, **k: mp.expand(mp.parse(PAGE)))
    mp.refresh(conn, entered_by="api:fetch-prices")
    # 1M in at $2 + 500k out at $10 = 2.00 + 5.00
    assert fx.cost_of(conn, "claude-sonnet-5", 1_000_000, 500_000) == 7.0


def test_a_kept_price_that_disagrees_with_the_published_one_is_reported(
        conn, monkeypatch):
    """Keeping the operator's number is right; keeping it *silently* would
    rebuild the exact failure this module exists for — a hand-typed price that
    is wrong and does not look wrong. The operator is told and decides."""
    from clauditseo.persistence.repo import now_iso

    conn.execute("INSERT INTO model_prices (model, input_usd, output_usd,"
                 " entered_at, source) VALUES ('claude-sonnet-5', 3.0, 15.0,"
                 " ?, 'operator')", (now_iso(),))
    conn.commit()
    monkeypatch.setattr(mp, "fetch", lambda *a, **k: mp.expand(mp.parse(PAGE)))
    out = mp.refresh(conn, entered_by="api:fetch-prices")

    assert out["differs"] == [{"model": "claude-sonnet-5",
                               "yours": [3.0, 15.0], "published": [2.0, 10.0]}]
    row = conn.execute("SELECT input_usd FROM model_prices WHERE"
                       " model='claude-sonnet-5'").fetchone()
    assert row["input_usd"] == 3.0, "still the operator's, until they say so"


def test_an_agreeing_operator_price_is_not_reported_as_a_disagreement(
        conn, monkeypatch):
    """Otherwise every fetch nags about prices that are simply correct."""
    from clauditseo.persistence.repo import now_iso

    conn.execute("INSERT INTO model_prices (model, input_usd, output_usd,"
                 " entered_at, source) VALUES ('claude-sonnet-5', 2.0, 10.0,"
                 " ?, 'operator')", (now_iso(),))
    conn.commit()
    monkeypatch.setattr(mp, "fetch", lambda *a, **k: mp.expand(mp.parse(PAGE)))
    assert mp.refresh(conn, entered_by="api:fetch-prices")["differs"] == []


# --- what a stored brief records about its own cost ------------------------

def test_a_stored_brief_records_the_split_not_only_the_total(conn):
    """Input and output differ by five times in price, so a total alone
    cannot be checked against the cost stored beside it."""
    from clauditseo.persistence import repo, runs

    op = repo.ensure_default_operator(conn)
    site = repo.create_site(conn, repo.create_client(conn, op, "C"), "x.test")
    run_id = runs.create_run(conn, site, ["TEC"], "T2")
    runs.store_expert_report(conn, run_id, "crawl", {
        "model": "claude-sonnet-5", "report": "r", "tokens": 30_000,
        "tokens_in": 25_000, "tokens_out": 5_000, "cost": 0.10})

    row = conn.execute("SELECT * FROM expert_reports WHERE run_id=?",
                       (run_id,)).fetchone()
    assert (row["tokens_in"], row["tokens_out"]) == (25_000, 5_000)
    assert row["tokens_in"] + row["tokens_out"] == row["tokens"]
    # And the stored cost can now be re-derived from what is stored beside it.
    assert round(25_000 / 1e6 * 2.0 + 5_000 / 1e6 * 10.0, 2) == row["cost"]


def test_a_brief_stored_before_the_split_existed_stays_absent(conn):
    """Deriving the split from the total would mean inventing a ratio."""
    from clauditseo.persistence import repo, runs

    op = repo.ensure_default_operator(conn)
    site = repo.create_site(conn, repo.create_client(conn, op, "C"), "x.test")
    run_id = runs.create_run(conn, site, ["TEC"], "T2")
    runs.store_expert_report(conn, run_id, "crawl",
                             {"model": "m", "report": "r", "tokens": 30_000})
    row = conn.execute("SELECT * FROM expert_reports WHERE run_id=?",
                       (run_id,)).fetchone()
    assert row["tokens"] == 30_000
    assert row["tokens_in"] is None and row["tokens_out"] is None
