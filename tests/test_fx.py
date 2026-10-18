"""Money is only shown when it can be justified.

The rule this file holds, in three parts:

  - a token count becomes USD only when the operator has entered a price,
    because no vendor publishes one and inventing it puts a wrong number in a
    client quote;
  - USD becomes another currency only when a rate has actually been fetched;
  - a converted figure always carries the rate's age, because a rate without
    its date is a number that silently becomes wrong.

Every failure falls back to the more honest figure rather than the prettier
one, and says why.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.providers import fx


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "fx.db")
    migrate(c)
    return c


def test_usd_needs_no_rate_and_is_never_a_lookup(conn):
    """One times one. Making USD depend on a fetch would mean a network
    failure stopped the operator seeing their own costs."""
    assert fx.rate_for(conn, "USD")["rate"] == 1.0
    assert fx.convert(conn, 10.0) == {
        "usd": 10.0, "currency": "USD", "value": 10.0, "converted": False,
        "rate": None, "fetched_at": None, "stale": False}


def test_without_a_stored_rate_the_figure_stays_in_usd_and_says_why(conn):
    """The alternative is converting at a guessed rate, which is the one
    outcome worse than not converting."""
    fx.set_display_currency(conn, "AUD")
    out = fx.convert(conn, 10.0)
    assert out["converted"] is False
    assert out["currency"] == "USD" and out["value"] == 10.0
    assert "no stored rate for AUD" in out["reason"]


def test_a_stored_rate_converts_and_carries_its_age(conn):
    fx.store_rates(conn, {"AUD": 1.52, "GBP": 0.79})
    fx.set_display_currency(conn, "AUD")
    out = fx.convert(conn, 10.0)
    assert out["converted"] is True
    assert (out["currency"], out["value"], out["rate"]) == ("AUD", 15.2, 1.52)
    assert out["fetched_at"] and out["stale"] is False
    assert out["usd"] == 10.0, "the USD figure survives the conversion"


def test_an_old_rate_still_converts_but_is_marked(conn):
    """Refusing to convert on a four-day-old rate would be unhelpful; showing
    it as current would be dishonest. It converts and says how old it is."""
    fx.store_rates(conn, {"AUD": 1.52})
    old = (datetime.now(timezone.utc) - timedelta(days=9)).isoformat()
    conn.execute("UPDATE fx_rates SET fetched_at=? WHERE currency='AUD'", (old,))
    conn.commit()
    fx.set_display_currency(conn, "AUD")
    out = fx.convert(conn, 10.0)
    assert out["converted"] is True and out["stale"] is True
    assert out["age_days"] >= fx.STALE_AFTER_DAYS


def test_a_refresh_that_fails_reports_it_rather_than_raising(conn, monkeypatch):
    """A scheduled refresh wants to log and carry on with the rate it has; an
    operator pressing the button wants to be told. Both need the failure as a
    value, not an exception escaping into the request."""
    def boom(*_a, **_k):
        raise OSError("the read operation timed out")
    monkeypatch.setattr(fx, "fetch_rates", boom)
    out = fx.refresh(conn)
    assert out["ok"] is False and out["stored"] == 0
    assert "timed out" in out["error"]


def test_a_failed_refresh_leaves_the_rate_it_already_had(conn, monkeypatch):
    """The worst outcome of a network blip would be losing a good rate."""
    fx.store_rates(conn, {"AUD": 1.52})
    monkeypatch.setattr(fx, "fetch_rates",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("down")))
    fx.refresh(conn)
    assert fx.rate_for(conn, "AUD")["rate"] == 1.52


def test_only_offered_currencies_can_be_chosen(conn):
    """A free-text currency would convert against a rate that is never
    fetched, which is a silent no-op the operator cannot see."""
    with pytest.raises(ValueError):
        fx.set_display_currency(conn, "XYZ")
    assert fx.display_currency(conn) == "USD"


def test_the_feed_parses_into_rates_including_usd(monkeypatch):
    """USD is not in an ECB feed based on USD, and adding it is arithmetic
    rather than an assumption."""
    class _Resp:
        @staticmethod
        def raise_for_status():
            return _Resp
        @staticmethod
        def json():
            return {"base": "USD", "date": "2026-08-13",
                    "rates": {"AUD": 1.52, "GBP": 0.79, "JUNK": None}}
    import httpx
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp)
    rates, source = fx.fetch_rates()
    assert rates["USD"] == 1.0 and rates["AUD"] == 1.52
    assert source == fx.RATE_SOURCES[0][0], "the first feed that answers wins"
    assert "JUNK" not in rates, "a non-numeric rate is not a rate"


def test_an_empty_feed_is_an_error_not_an_empty_success(monkeypatch):
    """Storing zero rates would quietly wipe nothing and report success."""
    class _Resp:
        @staticmethod
        def raise_for_status():
            return _Resp
        @staticmethod
        def json():
            return {"rates": {}}
    import httpx
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp)
    with pytest.raises(RuntimeError, match="no rate source answered"):
        fx.fetch_rates()


# --- a price only becomes money when someone has said what it costs --------

def test_no_price_means_tokens_not_a_guess(conn):
    assert fx.price_for(conn, "claude-opus-5") is None
    assert fx.cost_of(conn, "claude-opus-5", 1_000_000, 100_000) is None


def test_an_entered_price_is_used_and_beats_the_environment(conn):
    """A price typed into the app is a deliberate act with a date on it; the
    env var is deployment config nobody looks at again."""
    from clauditseo.persistence.repo import now_iso

    conn.execute("INSERT INTO model_prices (model, input_usd, output_usd,"
                 " entered_at) VALUES ('m', 3.0, 15.0, ?)", (now_iso(),))
    conn.commit()
    env = {"m": (99.0, 99.0)}
    assert fx.price_for(conn, "m", env) == (3.0, 15.0)
    # 1M in at $3 + 200k out at $15 = 3.00 + 3.00
    assert fx.cost_of(conn, "m", 1_000_000, 200_000, env) == 6.0


def test_the_environment_still_works_when_nothing_is_entered(conn):
    assert fx.price_for(conn, "m", {"m": (1.0, 2.0)}) == (1.0, 2.0)


def test_the_scheduler_leaves_usd_alone_and_survives_a_failure(conn, monkeypatch):
    """Nothing to convert means nothing to fetch, and a currency lookup must
    never interrupt an audit schedule."""
    from clauditseo import scheduler

    calls: list[str] = []
    monkeypatch.setattr(fx, "refresh",
                        lambda c: calls.append("fetched") or {"ok": True, "stored": 1})
    scheduler._refresh_rates(conn, lambda _m: None)
    assert calls == [], "USD needs no rate"

    fx.set_display_currency(conn, "AUD")
    scheduler._refresh_rates(conn, lambda _m: None)
    assert calls == ["fetched"], "a non-USD currency with no rate fetches one"

    monkeypatch.setattr(fx, "refresh",
                        lambda c: (_ for _ in ()).throw(OSError("down")))
    scheduler._refresh_rates(conn, lambda _m: None)   # must not raise


def test_a_dead_feed_falls_through_to_the_next_one(monkeypatch):
    """A single free endpoint is a single point of failure, and was one:
    frankfurter answered 520 and then timed out while this was written."""
    import httpx

    class _Good:
        @staticmethod
        def raise_for_status():
            return _Good
        @staticmethod
        def json():
            return {"rates": {"AUD": 1.41}}

    seen: list[str] = []

    def flaky(url, **_k):
        seen.append(url)
        if len(seen) == 1:
            raise httpx.ReadTimeout("first source is down")
        return _Good
    monkeypatch.setattr(httpx, "get", flaky)

    rates, source = fx.fetch_rates()
    assert rates["AUD"] == 1.41
    assert source == fx.RATE_SOURCES[1][0], "the rate is attributed to who gave it"
    assert len(seen) == 2, "it tried the first before falling through"


def test_when_every_feed_fails_the_error_names_what_was_tried():
    """"Rates unavailable" without saying what was attempted is a message
    nobody can act on."""
    import httpx
    import pytest as _pytest

    original = httpx.get
    try:
        httpx.get = lambda *a, **k: (_ for _ in ()).throw(OSError("no route"))
        with _pytest.raises(RuntimeError) as err:
            fx.fetch_rates()
    finally:
        httpx.get = original
    for name, _url in fx.RATE_SOURCES:
        assert name in str(err.value)
