"""A measuring instrument that cannot state a price is not one.

`scripts/run_golden.py` calls itself "the instrument for 'does the deep tier
earn its price'". Both paid runs on 2026-08-24 wrote six `cost_entries` rows
each with a correct token count and a NULL cost, because the harness defaults
to `data/golden-scratch.db` — correctly, so the operator's home screen never
grows a fixture client — and nothing ever seeded prices into it. The USD
figures in the relay item that reported this had to be worked out by hand.

Two properties, and the second is the one that keeps the fix honest.

**A scratch database can be given the prices without writing to the live one.**
The harness refuses to *write* a run into `data/clauditseo.db`. Reading prices
out is a different act and does not cross that boundary — but only if it is
really a read. `connect()` issues `PRAGMA journal_mode = WAL`, which is a write
to the header and leaves `-wal`/`-shm` beside the file, so the obvious
implementation would quietly modify the operator's database on every golden
run. That is what `test_copying_prices_leaves_the_source_untouched` measures.

**An absent price says so.** A zero in a money column reads as free. Where the
figure cannot be computed the output has to name the reason, in the same
`priced`/`unpriced` frame `monthly_spend` already uses.
"""

from __future__ import annotations

import sqlite3

import pytest

from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo, runs
from clauditseo.providers import fx
from clauditseo.providers import model_prices as mp


def _live_like(path, rows=(("claude-opus-5", 5.0, 25.0),
                           ("claude-sonnet-5", 2.0, 10.0))):
    """A stand-in for the operator's own database: prices, and deliberately
    NOT in WAL mode, so any write by the reader is visible afterwards."""
    src = sqlite3.connect(path)
    src.execute("CREATE TABLE model_prices (model TEXT PRIMARY KEY,"
                " input_usd REAL NOT NULL, output_usd REAL NOT NULL,"
                " entered_at TEXT NOT NULL, entered_by TEXT,"
                " source TEXT NOT NULL DEFAULT 'operator', source_url TEXT)")
    src.executemany(
        "INSERT INTO model_prices (model, input_usd, output_usd, entered_at,"
        " entered_by, source, source_url) VALUES (?, ?, ?, '2026-08-17',"
        " 'operator@example.test', 'anthropic-pricing-docs', 'https://x.test')",
        rows)
    src.commit()
    src.close()
    return path


@pytest.fixture
def scratch(tmp_path):
    conn = connect(tmp_path / "golden-scratch.db")
    migrate(conn)
    return conn


# --- the copy is a read of the live database, not a write to it -------------

def test_copying_prices_leaves_the_source_untouched(tmp_path, scratch):
    """The boundary the harness set when it refused the live database.

    `connect()` would flip the source to WAL and leave two files beside it.
    The operator's database must come back byte-for-byte as it went in.
    """
    src = _live_like(tmp_path / "live.db")
    before = src.read_bytes()

    mp.copy_prices(scratch, src, entered_by="golden-harness")

    assert src.read_bytes() == before, "the source database was written to"
    assert not (tmp_path / "live.db-wal").exists()
    assert not (tmp_path / "live.db-shm").exists()


def test_the_copy_carries_the_prices_and_says_who_put_them_there(tmp_path,
                                                                 scratch):
    """WF-33: sixteen rows once appeared in this install's ledger with
    `entered_by` NULL and stood unattributed under every cost figure the
    product quoted. A row this code writes names its author."""
    mp.copy_prices(scratch, _live_like(tmp_path / "live.db"),
                   entered_by="golden-harness")

    assert fx.price_for(scratch, "claude-opus-5") == (5.0, 25.0)
    row = scratch.execute(
        "SELECT entered_by, source FROM model_prices WHERE model='claude-opus-5'"
    ).fetchone()
    assert row["entered_by"] == "golden-harness"
    # The provenance of the *number* is unchanged by moving it: the pricing
    # docs still said it. Only who put it in this file is new.
    assert row["source"] == "anthropic-pricing-docs"


def test_a_price_already_in_the_scratch_database_is_not_overwritten(tmp_path,
                                                                    scratch):
    """The same rule `refresh` keeps: a figure somebody put here on purpose
    wins over one arriving from elsewhere."""
    scratch.execute(
        "INSERT INTO model_prices (model, input_usd, output_usd, entered_at,"
        " entered_by, source) VALUES ('claude-opus-5', 99.0, 99.0,"
        " '2026-08-24', 'me', 'operator')")
    scratch.commit()

    out = mp.copy_prices(scratch, _live_like(tmp_path / "live.db"),
                         entered_by="golden-harness")

    assert fx.price_for(scratch, "claude-opus-5") == (99.0, 99.0)
    assert out["kept"] == ["claude-opus-5"]
    assert out["copied"] == 1


def test_a_missing_source_is_reported_rather_than_raised(tmp_path, scratch):
    """A machine with no live database still has to be able to run the
    harness — it just cannot price it, and must say which."""
    out = mp.copy_prices(scratch, tmp_path / "nothing-here.db",
                         entered_by="golden-harness")
    assert out["ok"] is False
    assert out["copied"] == 0
    assert "nothing-here.db" in out["error"]


# --- an absent price is stated, never rendered as zero ----------------------

@pytest.fixture
def run(scratch):
    op = repo.ensure_default_operator(scratch)
    site = repo.create_site(scratch, repo.create_client(scratch, op, "G"),
                            "http://127.0.0.1/")
    run_id = runs.create_run(scratch, site, ["TEC"], "T2")
    runs.store_expert_report(scratch, run_id, "hreflang",
                             {"model": "claude-opus-5", "report": "r",
                              "tokens": 1000})
    return run_id


def test_a_run_nobody_could_price_says_so_instead_of_reporting_zero(scratch,
                                                                    run):
    """The defect exactly as it stood: six rows, a real token count, and a
    money column that reads as free."""
    runs.log_cost(scratch, run, "anthropic", "EXPERT:hreflang", "tokens", 9619)

    spend = runs.run_spend(scratch, run)

    assert spend["tokens"] == 9619
    assert spend["usd"] is None
    assert spend["unpriced"] == 1 and spend["priced"] == 0
    assert "claude-opus-5" in spend["usd_absent_because"]


def test_a_priced_run_reports_the_money(scratch, run):
    runs.log_cost(scratch, run, "anthropic", "EXPERT:hreflang", "tokens", 9619,
                  actual_cost=0.0721)

    spend = runs.run_spend(scratch, run)

    assert spend["usd"] == pytest.approx(0.0721)
    assert spend["usd_absent_because"] is None
    assert spend["is_floor"] is False


def test_a_partly_priced_run_calls_its_figure_a_floor(scratch, run):
    """The gap UX-04 named, one run along: a number covering a minority of
    the rows that produced the token count beside it."""
    runs.log_cost(scratch, run, "anthropic", "EXPERT:a", "tokens", 100,
                  actual_cost=0.01)
    runs.log_cost(scratch, run, "anthropic", "EXPERT:b", "tokens", 900)

    spend = runs.run_spend(scratch, run)

    assert spend["usd"] == pytest.approx(0.01)
    assert spend["is_floor"] is True
    assert spend["priced"] == 1 and spend["unpriced"] == 1
    assert spend["usd_absent_because"], "a floor with no explanation is a lie"


def test_a_run_that_spent_nothing_is_not_confused_with_one_that_was_unpriced(
        scratch, run):
    spend = runs.run_spend(scratch, run)
    assert spend["entries"] == 0 and spend["tokens"] == 0
    assert spend["usd"] is None
    assert "no cost" in spend["usd_absent_because"].lower()
