"""Exchange rates, so a token count can become money the client understands.

Two problems live near each other and both turn out to be lookups.

Exchange rates are the obvious one. The ECB publishes daily reference rates,
free and without a key, and several hosts serve them over HTTPS.

Model prices were asserted here not to be, on the grounds that no vendor
publishes a machine-readable feed. That was wrong — Anthropic serves its
pricing page as `text/markdown` and the model table parses without heuristics
— and it was wrong in the expensive direction: the hand-typed price for
`claude-sonnet-5` sat at $3/$15 while the published figure was $2/$10. See
`model_prices.py`. What survives of the original rule is the part that was
actually load-bearing: a price is never invented, always carries its source
and date, and a fetched figure never overwrites one a human typed.

Everything here degrades in one direction: when a rate is missing or stale the
figure falls back to USD and says so. It never converts with a guessed rate and
never presents a rate without its age — a conversion whose provenance is
invisible is worse than no conversion, because the reader cannot tell.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

#: Free, keyless rate feeds, tried in order. More than one because a single
#: free endpoint is a single point of failure, and it is: frankfurter answered
#: 520 and then timed out while this was being written, which is exactly the
#: outage that would otherwise leave an operator with no conversion and no
#: explanation.
#:
#: Each entry is (name, url, extractor). The name is stored with the rate, so
#: a figure can always be traced to who said it — the sources do not agree to
#: the fourth decimal and pretending they are one feed would hide that.
RATE_SOURCES: tuple[tuple[str, str], ...] = (
    ("ecb-via-frankfurter", "https://api.frankfurter.dev/v1/latest?base=USD"),
    ("open-er-api", "https://open.er-api.com/v6/latest/USD"),
)
SOURCE = RATE_SOURCES[0][0]

#: Beyond this a rate is still shown but called old. The ECB publishes on
#: working days, so a Monday reading a Friday rate is normal and three days is
#: the first age that means something went wrong rather than it being a
#: weekend.
STALE_AFTER_DAYS = 3

#: What an operator can pick. Deliberately short: these are the currencies an
#: agency quotes in, and a list of 170 turns a decision into a search.
CURRENCIES = ("USD", "AUD", "NZD", "GBP", "EUR", "CAD", "SGD", "ZAR", "INR")

#: The currency every stored rate is quoted against, and the one costs are
#: recorded in. Named rather than spelled `"USD"` at four sites, because the
#: two rules below are about *the base*, not about this particular code.
BASE = "USD"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fetch_rates(timeout_s: float = 15.0) -> tuple[dict[str, float], str]:
    """Today's rates against USD, and which feed said so.

    Tries each source in turn and raises only when all of them fail — the
    error names every attempt, because "rates unavailable" without saying
    what was tried is an unactionable message.

    Deliberately raises rather than returning a failure value: a scheduled
    refresh wants to log and carry on with the rate it already has, while an
    operator pressing "refresh now" wants to be told. `refresh` turns it into
    a value for both.
    """
    import httpx

    attempts = []
    for name, url in RATE_SOURCES:
        try:
            payload = httpx.get(url, timeout=timeout_s).raise_for_status().json()
            rates = {k: float(v) for k, v in (payload.get("rates") or {}).items()
                     if isinstance(v, (int, float))}
            if not rates:
                raise ValueError("no rates in response")
            # USD against itself is arithmetic, not an approximation, and is
            # absent from a feed based on USD.
            rates["USD"] = 1.0
            return rates, name
        except Exception as exc:                    # noqa: BLE001
            attempts.append(f"{name}: {type(exc).__name__}")
    raise RuntimeError("no rate source answered — " + "; ".join(attempts))


def store_rates(conn: sqlite3.Connection, rates: dict[str, float],
                source: str = SOURCE) -> int:
    stamp = _now()
    with conn:
        conn.executemany(
            "INSERT INTO fx_rates (currency, rate, source, fetched_at)"
            " VALUES (?, ?, ?, ?) ON CONFLICT(currency) DO UPDATE SET"
            " rate=excluded.rate, source=excluded.source,"
            " fetched_at=excluded.fetched_at",
            [(c, r, source, stamp) for c, r in rates.items()])
    return len(rates)


def refresh(conn: sqlite3.Connection) -> dict:
    """Fetch and store. Returns what happened, including the failure.

    **Two counts, because a screen states one directly above a list of the
    other.** `stored` is the write: every currency the chosen feed sent, plus
    the base row `fetch_rates` adds. `shown` is the length of the list
    `reference_rates` will hand the same panel — the display currencies, less
    the base. The two are routinely different and are not bounded against each
    other in either direction: a feed returning 170 currencies makes `stored`
    much the larger, and a feed that answers with two currencies after an
    earlier press stored eight leaves `shown` the larger.

    UX-70. Round 075 put the bound on the read side and left this function
    reporting `store_rates(...)` alone, so the confirmation an operator reads
    after pressing "refresh reference rates" counted rows they cannot see,
    one line above the rows they can, with nothing saying which was the
    answer. `RATE_SOURCES` holds two feeds of different breadths, so it was
    not even stable between presses.

    Derived here rather than in the renderer for the reason
    `reference_rates`' own docstring gives: a renderer that re-applies a
    server-side bound is how the two drift apart. This calls that function, so
    there is one owner of what the panel can show and the count cannot
    disagree with the list it describes.
    """
    try:
        rates, source = fetch_rates()
    except Exception as exc:                       # noqa: BLE001
        # No `shown` on this branch, deliberately. The write did not happen,
        # so the table is whatever it already held — and a `0` here would
        # claim an empty panel to a screen that is still rendering rows.
        return {"ok": False, "error": str(exc), "stored": 0}
    stored = store_rates(conn, rates, source)
    return {"ok": True, "stored": stored, "shown": len(reference_rates(conn)),
            "source": source, "at": _now()}


def reference_rates(conn: sqlite3.Connection) -> list[dict]:
    """The stored rates a screen may state: bounded, and without the identity.

    Two rules, applied here rather than in the renderer because there is no
    reading of `fx_rates` for which either is wrong.

    **The base is excluded.** `fetch_rates` writes `rates[BASE] = 1.0` on
    every press, because the feed is base-relative and does not send it. A
    renderer mapping that row produces `1 USD = 1 USD`, a sentence whose
    grammar claims a conversion and whose content is that none happened —
    WF-04, which survived a fix aimed at it because the row is created by the
    write and the guard staged a table that deleted it.

    **The rest is bounded by `CURRENCIES`.** That tuple already decides what
    `set_display_currency` accepts; it did not decide what the fetch stored or
    what the panel showed, so the number of clauses on the operator's Money
    card was whatever the upstream feed's response body happened to contain —
    and `RATE_SOURCES` holds two feeds of different breadths, so it was not
    even stable between presses (UI-17, and the render half of CQ-158).

    Deliberately a read-side bound. Applying `CURRENCIES` in `fetch_rates` as
    well is CQ-158's remaining half and is a separate change: it decides what
    is *kept*, and a table that already holds unlisted rows still has to
    render correctly today.
    """
    wanted = [c for c in CURRENCIES if c != BASE]
    if not wanted:
        return []
    rows = conn.execute(
        "SELECT * FROM fx_rates WHERE currency IN"
        f" ({','.join('?' * len(wanted))}) ORDER BY currency", wanted)
    return [dict(r) for r in rows]


def rate_for(conn: sqlite3.Connection, currency: str) -> dict | None:
    """The stored rate and how old it is, or None if it was never fetched.

    None is a real answer: it means "we cannot convert", not "the rate is 1".
    """
    if currency == "USD":
        return {"currency": "USD", "rate": 1.0, "source": "identity",
                "fetched_at": None, "age_days": 0, "stale": False}
    row = conn.execute("SELECT * FROM fx_rates WHERE currency=?",
                       (currency,)).fetchone()
    if not row:
        return None
    age = None
    try:
        then = datetime.fromisoformat(row["fetched_at"])
        age = (datetime.now(timezone.utc) - then).days
    except (TypeError, ValueError):
        pass
    return {"currency": row["currency"], "rate": row["rate"],
            "source": row["source"], "fetched_at": row["fetched_at"],
            "age_days": age,
            "stale": age is None or age > STALE_AFTER_DAYS}


def display_currency(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT display_currency FROM app_prefs WHERE id=1").fetchone()
    return (row["display_currency"] if row else "USD") or "USD"


def set_display_currency(conn: sqlite3.Connection, currency: str) -> None:
    if currency not in CURRENCIES:
        raise ValueError(f"currency must be one of {', '.join(CURRENCIES)}")
    with conn:
        conn.execute("UPDATE app_prefs SET display_currency=?, updated_at=?"
                     " WHERE id=1", (currency, _now()))


def convert(conn: sqlite3.Connection, usd: float | None) -> dict:
    """A USD figure in the operator's currency, with why it is what it is.

    Always answers with the USD value too, so a caller that cannot use the
    conversion still has the number rather than nothing.
    """
    want = display_currency(conn)
    out = {"usd": usd, "currency": "USD", "value": usd, "converted": False,
           "rate": None, "fetched_at": None, "stale": False}
    if usd is None or want == "USD":
        return out
    found = rate_for(conn, want)
    if not found:
        # No rate: the figure stays in USD and the caller can say why.
        out["reason"] = f"no stored rate for {want}"
        return out
    return {**out, "currency": want, "value": round(usd * found["rate"], 2),
            "converted": True, "rate": found["rate"],
            "fetched_at": found["fetched_at"], "stale": found["stale"],
            "age_days": found["age_days"]}


def price_for(conn: sqlite3.Connection, model: str,
              cfg_prices: dict | None = None) -> tuple[float, float] | None:
    """$USD per million tokens for a model, or None if nobody has said.

    The stored table wins over the environment variable: a price typed into
    the app is a deliberate act with a date against it, while the env var is
    deployment configuration that nobody looks at again. None stays None —
    an unknown price shows as tokens, which is what this system did before
    prices existed and is still the honest answer.
    """
    row = conn.execute(
        "SELECT input_usd, output_usd FROM model_prices WHERE model=?",
        (model,)).fetchone()
    if row:
        return (float(row["input_usd"]), float(row["output_usd"]))
    found = (cfg_prices or {}).get(model)
    return (float(found[0]), float(found[1])) if found else None


#: Prompt-caching multipliers on the base input rate, from the published
#: pricing page. A 5-minute write costs 1.25x and a read 0.1x, which is why
#: caching pays for itself after a single re-read.
CACHE_WRITE_MULTIPLIER = 1.25
CACHE_READ_MULTIPLIER = 0.1


def cost_of(conn: sqlite3.Connection, model: str, tokens_in: int,
            tokens_out: int, cfg_prices: dict | None = None,
            cache_write: int = 0, cache_read: int = 0) -> float | None:
    """USD for a call, or None when the model has no price.

    Four buckets, not two. `tokens_in` is the uncached remainder the API
    reports; cache writes and reads are billed separately at multiples of the
    base input rate. Pricing only the first two would under-state a cached
    call — and it is under-statement, not over: the cached tokens are absent
    from `input_tokens` rather than folded into it.
    """
    prices = price_for(conn, model, cfg_prices)
    if not prices:
        return None
    base, out = prices
    return round(
        tokens_in / 1e6 * base
        + cache_write / 1e6 * base * CACHE_WRITE_MULTIPLIER
        + cache_read / 1e6 * base * CACHE_READ_MULTIPLIER
        + tokens_out / 1e6 * out, 6)
