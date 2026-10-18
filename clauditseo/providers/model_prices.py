"""Claude model prices, read from Anthropic's published pricing page.

This exists because the first version of the cost work asserted that no vendor
publishes a machine-readable price feed, and therefore that every price had to
be typed in by hand. That was wrong. Anthropic serves

    https://platform.claude.com/docs/en/about-claude/pricing.md

as `text/markdown`, and the model table in it is a plain pipe table that parses
without heuristics.

The assertion was not just wrong, it was expensively wrong. The operator's
hand-entered price for `claude-sonnet-5` was $3/$15 while the published figure
was $2/$10 — the introductory rate had quietly become the standard one, and
the scheduled increase was cancelled. A hand-typed price is wrong the moment
the vendor changes theirs, and nothing about it looks wrong.

Three rules hold the honesty the hand-entry rule was protecting:

  - Every stored price records where it came from and when. A number in a
    client quote has to be traceable to something.
  - A fetch never overwrites an `operator` row. A negotiated rate is a fact
    about this customer that list price does not know, and replacing it with
    the public figure is the same class of error in the other direction.
  - A parse that finds nothing is an error, not an empty success. Silently
    storing zero prices would leave the interface showing tokens with no
    indication that the lookup had failed.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

#: The markdown rendering of the pricing page. `text/markdown`, no key, no
#: account. The HTML page at the same path without `.md` is a 1.1 MB
#: application shell whose prices are wrapped in layout spans — parseable in
#: principle and a liability in practice.
PRICES_URL = "https://platform.claude.com/docs/en/about-claude/pricing.md"
SOURCE = "anthropic-pricing-docs"

#: The table lives under this heading and ends at the next one. Anchoring to
#: the headings rather than to the first table in the document keeps the
#: batch-pricing and tool-token tables further down the page from being read
#: as model prices — they have the same row shape and half the values.
SECTION_START = "## Model pricing"
SECTION_END = "## Cloud platform pricing"

#: `| Claude Opus 5 | $5 / MTok | ... | $25 / MTok |`
#: Columns are model, base input, 5m cache write, 1h cache write, cache read,
#: output. Only the first and last are wanted: this system records total input
#: and output tokens and does not split cache reads out, so a cache-aware
#: figure would be arithmetic on numbers nobody measured.
_MONEY = re.compile(r"\$\s*([0-9]+(?:\.[0-9]+)?)")
#: A row's model cell can carry a parenthesised markdown link — "Claude Opus
#: 4.1 ([retired, except on Bedrock…](url))". The note is not part of the name.
_NOTE = re.compile(r"\s*\(\[.*?\]\(.*?\)\)\s*$")

#: Model IDs that do not fall out of the display name. The slug rule below
#: handles every current row; these are the exceptions, and the dated Haiku ID
#: matters because it is the string this install actually sends.
ALIASES: dict[str, tuple[str, ...]] = {
    "claude-haiku-4-5": ("claude-haiku-4-5-20251001",),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def model_id(display_name: str) -> str:
    """"Claude Sonnet 4.6" -> "claude-sonnet-4-6"."""
    slug = _NOTE.sub("", display_name).strip().lower()
    slug = slug.replace(".", "-").replace(" ", "-")
    return slug


def parse(markdown: str) -> dict[str, tuple[float, float]]:
    """{model id: (input $/M, output $/M)} from the pricing page's markdown.

    Raises when the table cannot be found or yields nothing — a pricing page
    that has been restructured must fail loudly, because the alternative is
    storing whatever the new first column happens to contain.
    """
    try:
        body = markdown[markdown.index(SECTION_START):]
        body = body[:body.index(SECTION_END)]
    except ValueError as exc:
        raise ValueError(
            f"pricing page has no '{SECTION_START}' section — the page "
            "changed shape and the parser needs looking at") from exc

    out: dict[str, tuple[float, float]] = {}
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("|") or line.startswith("| ---"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3 or not cells[0].lower().startswith("claude"):
            continue
        money = [_MONEY.search(c) for c in cells[1:]]
        found = [float(m.group(1)) for m in money if m]
        if len(found) < 2:
            continue
        # First money column is base input, last is output. Positional rather
        # than by header text: the cache columns have moved before and the two
        # that matter have always been the ends.
        out[model_id(cells[0])] = (found[0], found[-1])

    if not out:
        raise ValueError("pricing table found but no model rows parsed")
    return out


def expand(prices: dict[str, tuple[float, float]]) -> dict[str, tuple[float, float]]:
    """Add the alias IDs, so the string this install actually sends is priced."""
    out = dict(prices)
    for canonical, others in ALIASES.items():
        if canonical in prices:
            for alias in others:
                out.setdefault(alias, prices[canonical])
    return out


def fetch(timeout_s: float = 20.0) -> dict[str, tuple[float, float]]:
    """Published prices, keyed by model ID. Raises on failure."""
    import httpx

    resp = httpx.get(PRICES_URL, timeout=timeout_s, follow_redirects=True)
    resp.raise_for_status()
    return expand(parse(resp.text))


def refresh(conn: sqlite3.Connection, *, entered_by: str) -> dict:
    """Fetch and store, leaving operator-entered rows alone.

    Returns what happened rather than raising, for the same reason the rate
    refresh does: a scheduled run wants to log and continue, an operator
    pressing the button wants to be told.

    `entered_by` is what to record as having stored these prices, and it is
    required rather than defaulted. WF-33: sixteen rows appeared in this
    install's ledger on 2026-08-17 with `entered_by = NULL`, no commit and no
    `OPERATOR_ACTIONS.md` row, and stood unattributed for fifty-five audit
    reports underneath every cost figure the product quotes. A default here is
    how that returns — the next caller would inherit NULL without ever being
    asked the question. The vocabulary is the caller's to supply and is
    written down at `clauditseo/api/app.py`'s `actor_of`.
    """
    try:
        prices = fetch()
    except Exception as exc:                        # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                "stored": 0, "kept": []}

    # Operator rows are kept — but a kept row that disagrees with the
    # published figure is reported, because the whole failure this module
    # exists for is a hand-typed price that is wrong and does not look it.
    # Keeping it silently would rebuild that failure inside the fix.
    own = {r["model"]: (r["input_usd"], r["output_usd"]) for r in conn.execute(
        "SELECT model, input_usd, output_usd FROM model_prices"
        " WHERE source='operator'")}
    kept = list(own)
    differs = [
        {"model": m, "yours": list(own[m]), "published": list(prices[m])}
        for m in sorted(own) if m in prices and own[m] != prices[m]]
    stamp = _now()
    stored = 0
    with conn:
        for model, (inp, outp) in sorted(prices.items()):
            if model in kept:
                continue
            conn.execute(
                "INSERT INTO model_prices (model, input_usd, output_usd,"
                " entered_at, entered_by, source, source_url)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(model) DO UPDATE SET input_usd=excluded.input_usd,"
                " output_usd=excluded.output_usd, entered_at=excluded.entered_at,"
                " entered_by=excluded.entered_by,"
                " source=excluded.source, source_url=excluded.source_url",
                (model, inp, outp, stamp, entered_by, SOURCE, PRICES_URL))
            stored += 1
    return {"ok": True, "stored": stored, "kept": sorted(kept),
            "differs": differs, "source": SOURCE, "at": stamp}


def copy_prices(dest: sqlite3.Connection, source: Path | str, *,
                entered_by: str) -> dict:
    """Copy `model_prices` out of another database, read-only, into `dest`.

    Written for `scripts/run_golden.py`, which defaults to a scratch database
    so the operator's home screen never grows a "Golden fixture" client — and
    which therefore had no prices at all, so the one instrument for "does the
    deep tier earn its price" recorded six cost rows a run with a correct
    token count and no money against any of them.

    **Reading prices out is not the same act as writing a run in, and this
    function is what makes that true rather than merely claimed.** The source
    is opened through a `mode=ro` URI, not through `connect()`: that helper
    issues `PRAGMA journal_mode = WAL`, which is a write to the header and
    leaves `-wal` and `-shm` files beside the file, so the obvious
    implementation would modify the operator's own database on every golden
    run. `test_copying_prices_leaves_the_source_untouched` compares the
    source's bytes across the call.

    Two rules inherited from `refresh`, for the same reasons it holds them:
    a row already in `dest` is kept rather than overwritten, and `entered_by`
    is required rather than defaulted — WF-33 is sixteen rows that stood
    unattributed under every cost figure the product quoted for fifty-five
    audit reports. `source` and `source_url` travel with the row unchanged:
    moving a number does not change who published it, and only who put it in
    *this* file is new.

    Reports failure rather than raising. A machine with no live database can
    still run the harness; it just cannot price it, and the caller's job is
    to say which — never to show a zero.
    """
    src = Path(source)
    if not src.exists():
        return {"ok": False, "error": f"no database at {src}", "copied": 0,
                "kept": [], "source": str(src)}
    try:
        ro = sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True)
        ro.row_factory = sqlite3.Row
        try:
            rows = ro.execute(
                "SELECT model, input_usd, output_usd, source, source_url"
                " FROM model_prices ORDER BY model").fetchall()
        finally:
            ro.close()
    except sqlite3.Error as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                "copied": 0, "kept": [], "source": str(src)}

    here = {r["model"] for r in dest.execute("SELECT model FROM model_prices")}
    stamp = _now()
    copied = 0
    with dest:
        for row in rows:
            if row["model"] in here:
                continue
            dest.execute(
                "INSERT INTO model_prices (model, input_usd, output_usd,"
                " entered_at, entered_by, source, source_url)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (row["model"], row["input_usd"], row["output_usd"], stamp,
                 entered_by, row["source"], row["source_url"]))
            copied += 1
    return {"ok": True, "copied": copied, "source": str(src),
            "kept": sorted(here & {r["model"] for r in rows}),
            "available": len(rows), "at": stamp}
