"""WF-33: the price ledger records who stored a row, and no screen says so.

Carried at High since report 033 — sixty-three reports — and taken once
already, at round 089, which is why this file is about the half that take did
not reach.

**What round 089 did and what it left.** It gave `entered_by` a vocabulary
(`actor_of` at `clauditseo/api/app.py`, `operator:<id>` or `api:<route>`) and
made `model_prices.refresh` demand one rather than default it. CQ-200 then
closed the second writer, the typed-price route. Both are genuinely fixed. But
that docstring also records the measurement that explains why the finding is
still open: at round 089 the column had *"two writers and no reader at all"*.
It still has none. `GET /api/rates` puts it on the wire — the route selects
`*` — and `admin.tsx`'s `Rates` type drops it, so the one screen that renders
the ledger cannot show it and does not.

The consequence is not that the column is unused. It is that the panel paints
a row with no recorded author identically to one with an author: the Source
cell reads `published` either way, which is an attribution the ledger cannot
support. Measured read-only on the operator's own install on 2026-08-24, all
**sixteen** rows of `model_prices` carry `entered_by` NULL against one
`entered_at` of `2026-08-17T02:52:58+00:00`, and every one of them renders as
`published`. That is the provenance invariant: a number's frame travels with
the value, and "who put this in my ledger" is unknown here and says otherwise.

**Why disclosure and not a backfill.** The obvious repair — write
`api:fetch-prices` into the sixteen — invents a specific provenance nobody
observed. Their `source` is `anthropic-pricing-docs` and their `source_url` is
the pricing page, so *where the figure came from* is recorded; what is missing
is who caused the write, and no evidence anywhere in the tree answers it. A
sentinel filling the column would be worse than NULL, because NULL is honestly
absent and a sentinel reads as an answer. So the ledger keeps the NULL and the
screen states it. Retracting the sixteen is a delete of the operator's own
data and is theirs to make; the panel is what makes it a decision they can see.

**The fixture inserts a row the product can no longer create, on purpose.**
Both write paths now supply `entered_by`, so the legacy state cannot be
produced through the API — and it is the state sixteen rows are actually in.
CQ-201 is the standing finding about fixtures built with literal SQL the
product cannot produce; this one is the exception that finding allows, because
the row being staged is a *measured* state of the field install rather than an
invented one, and it is staged with migration 0013's own column list. The
attributed row beside it is written through the product's own route, so the
two halves of the comparison are not both hand-made.
"""

from __future__ import annotations

import socket
import sqlite3
import threading
import time

import httpx
import pytest

from clauditseo import axe
from tests.test_a11y_rendered import DIST


#: The eighth copy of this decorator, and CQ-125 is the standing finding about
#: that. Per-test rather than module-level, for the reason `test_heading_fault`
#: records: a module mark would take the API clauses with it, and those are the
#: ones that must keep running in the browserless job.
def live(fn):
    fn = pytest.mark.skipif(
        not (DIST / "index.html").is_file(),
        reason="dashboard not built (npm run build in dashboard/)")(fn)
    return pytest.mark.skipif(
        not axe.available(),
        reason="needs clauditseo[render] and `playwright install chromium`")(fn)


#: What the operator's install holds, reproduced rather than invented: sixteen
#: rows at one stamp with no author, from the published pricing page. Two are
#: enough to make "how many" a count rather than a boolean.
LEGACY_STAMP = "2026-08-17T02:52:58+00:00"
LEGACY_SOURCE = "anthropic-pricing-docs"
LEGACY_URL = "https://platform.claude.com/docs/en/about-claude/pricing.md"
LEGACY = [("claude-opus-4-1", 15.0, 75.0), ("claude-sonnet-4", 3.0, 15.0)]

#: Written through the route, not into the table, so the attributed side of
#: the comparison is what the product actually stores.
TYPED = {"model": "claude-negotiated-1", "input_usd": 1.25, "output_usd": 6.5}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _stage_legacy(db) -> None:
    """Migration 0013's column list, with `entered_by` left out entirely.

    Left out rather than passed as None, because that is how the sixteen came
    to be: an INSERT that never named the column.
    """
    conn = sqlite3.connect(db)
    conn.executemany(
        "INSERT INTO model_prices (model, input_usd, output_usd, entered_at,"
        " source, source_url) VALUES (?, ?, ?, ?, ?, ?)",
        [(m, i, o, LEGACY_STAMP, LEGACY_SOURCE, LEGACY_URL)
         for m, i, o in LEGACY])
    conn.commit()
    conn.close()


@pytest.fixture(scope="module")
def priced_server(tmp_path_factory):
    """A server whose ledger holds both states: two rows with no author, one
    with the author the product writes today."""
    import uvicorn

    from clauditseo.api.app import create_app
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate

    db = tmp_path_factory.mktemp("price-author") / "clauditseo.db"
    conn = connect(db)
    migrate(conn)
    conn.close()

    app = create_app(db_path=db)
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port,
                            log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 30
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:
        pytest.fail("server did not start")

    base = f"http://127.0.0.1:{port}"
    try:
        put = httpx.put(base + "/api/rates/model-price", json=TYPED, timeout=30)
        assert put.status_code == 200, put.text
        _stage_legacy(db)
        yield base
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def _rows(base: str) -> list[dict]:
    resp = httpx.get(base + "/api/rates", timeout=30)
    assert resp.status_code == 200, resp.text
    return resp.json()["model_prices"]


# --- the floor: true on both trees, and what makes the rest mean anything ---

def test_the_ledger_puts_the_author_column_on_the_wire(priced_server):
    """Not a thing this round changes — the route has always selected `*`.

    It is here because every browser clause below asserts about a value the
    client can only paint if it arrives, so if this ever stops being true they
    would all fail for a reason that is not the finding. It also asserts the
    fixture holds both states, which is the population the clauses below
    decide membership over.
    """
    rows = _rows(priced_server)
    assert rows, "the ledger is empty, so no clause below tested a row"
    missing = [r["model"] for r in rows if "entered_by" not in r]
    assert not missing, (
        f"{missing} reach the client with no `entered_by` key at all, so the "
        "panel could not name an author even once it tried")
    unattributed = sorted(r["model"] for r in rows if r["entered_by"] is None)
    attributed = sorted(r["model"] for r in rows if r["entered_by"])
    assert unattributed == sorted(m for m, _i, _o in LEGACY), (
        f"the staged rows are not in the state this file is about: "
        f"{unattributed!r}")
    assert attributed == [TYPED["model"]], (
        f"the route did not file the typed price with an author, so the "
        f"contrast the clauses below rest on does not exist: {attributed!r}")


# --- the panel, driven, which is where the operator meets this -------------

#: The rendered rows of the Money card's price table, located from the table
#: the panel actually paints rather than from a marker class added for a test
#: — `SELECTED_NOT_PAINTED` carries two open findings about rows going stale
#: in it. The model id is the row key, so it is what the cells are read by.
PRICE_ROWS = """() => {
  const h = [...document.querySelectorAll('h4')].find(
    (e) => /^Model prices/.test(e.innerText.trim()));
  if (!h) return null;
  let n = h.nextElementSibling, table = null;
  while (n && !table) { if (n.tagName === 'TABLE') table = n;
                        n = n.nextElementSibling; }
  if (!table) return null;
  return {
    caption: table.querySelector('caption')
      ? table.querySelector('caption').innerText : '',
    rows: [...table.querySelectorAll('tbody tr')].map(
      (tr) => [...tr.querySelectorAll('td')].map((td) => td.innerText)),
  };
}"""


#: The panel fetches `/api/rates` a round trip after the card paints, so the
#: heading exists before the rows do. This is "the answer has arrived".
PRICE_TABLE_PAINTED = """() => {
  const h = [...document.querySelectorAll('h4')].find(
    (e) => /^Model prices/.test(e.innerText.trim()));
  if (!h) return false;
  let n = h.nextElementSibling, table = null;
  while (n && !table) { if (n.tagName === 'TABLE') table = n;
                        n = n.nextElementSibling; }
  return !!table && table.querySelectorAll('tbody tr').length > 0;
}"""


@pytest.fixture()
def price_table(priced_server):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            pg.goto(priced_server + "/#/admin?tab=prices", wait_until="load")
            pg.wait_for_selector(".card", timeout=15_000)
            pg.wait_for_function(PRICE_TABLE_PAINTED, timeout=15_000)
            painted = pg.evaluate(PRICE_ROWS)
            assert painted, "the price table did not render"
            yield painted, _rows(priced_server)
        finally:
            browser.close()


@live
def test_the_panel_paints_every_row_the_ledger_holds(price_table):
    """The population clause. The two below assert about the text of rows, and
    a table that painted a subset would let either of them pass by omission."""
    painted, rows = price_table
    assert len(painted["rows"]) == len(rows), (
        f"the panel painted {len(painted['rows'])} of the ledger's "
        f"{len(rows)} rows, so a clause below decides membership over a "
        "population smaller than the one it names")


@live
def test_the_panel_says_which_rows_have_no_recorded_author(price_table):
    """The defect, as the operator meets it: a row nobody is recorded as
    having stored is painted exactly like one that has an author."""
    painted, rows = price_table
    want = {r["model"] for r in rows if r["entered_by"] is None}
    silent = [
        cells for cells in painted["rows"]
        if any(m in cells[0] for m in want)
        and "no author recorded" not in " ".join(cells).lower()
    ]
    assert not silent, (
        f"{silent} are rows the ledger has no author for, and the panel says "
        "nothing about it — every one of them reads as `published`, which is "
        "an attribution the stored row does not support")


@live
def test_the_panel_names_the_author_where_there_is_one(price_table):
    """The other half, and the reason the clause above is not satisfiable by
    marking every row. CQ-200's fix writes an author on every new row; until
    something renders it, that fix is invisible on the only screen that shows
    the ledger."""
    painted, rows = price_table
    authors = {r["model"]: r["entered_by"] for r in rows if r["entered_by"]}
    unnamed = [
        (cells[0], author) for cells in painted["rows"]
        for model, author in authors.items()
        if model in cells[0] and author not in " ".join(cells)
    ]
    assert not unnamed, (
        f"{unnamed} carry a recorded author that reaches no cell of the row, "
        "so the column has a writer and still no reader")


@live
def test_the_panel_counts_the_rows_it_cannot_attribute(price_table):
    """One row at a time does not tell an operator whether this is a stray or
    the whole ledger. On the live install it is sixteen of sixteen, and the
    count is what makes retracting them a decision rather than a discovery."""
    painted, rows = price_table
    n = sum(1 for r in rows if r["entered_by"] is None)
    caption = painted["caption"]
    assert str(n) in caption and str(len(rows)) in caption, (
        f"the table's note is {caption!r}, which does not state that {n} of "
        f"{len(rows)} prices have no recorded author")


# --- the counter-assertion: it passes on both trees ------------------------

@live
def test_a_fully_attributed_ledger_is_not_told_it_is_missing_anything(
        priced_server, tmp_path):
    """A panel that always says "no author recorded" would satisfy the clauses
    above and be useless. This is the direction that must not change: with
    every row attributed, the note is absent and no cell claims otherwise."""
    import uvicorn

    from clauditseo.api.app import create_app
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from playwright.sync_api import sync_playwright

    db = tmp_path / "attributed.db"
    conn = connect(db)
    migrate(conn)
    conn.close()
    app = create_app(db_path=db)
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port,
                            log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 30
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:
        pytest.fail("server did not start")
    base = f"http://127.0.0.1:{port}"
    try:
        assert httpx.put(base + "/api/rates/model-price", json=TYPED,
                         timeout=30).status_code == 200
        rows = _rows(base)
        assert rows and all(r["entered_by"] for r in rows), (
            f"this clause needs a fully attributed ledger and has {rows!r}")
        with sync_playwright() as p:
            browser = p.chromium.launch()
            pg = browser.new_page(viewport={"width": 1280, "height": 900})
            try:
                pg.goto(base + "/#/admin?tab=prices", wait_until="load")
                pg.wait_for_selector(".card", timeout=15_000)
                pg.wait_for_function(PRICE_TABLE_PAINTED, timeout=15_000)
                painted = pg.evaluate(PRICE_ROWS)
            finally:
                browser.close()
        assert painted, "the price table did not render"
        text = (painted["caption"] + " "
                + " ".join(" ".join(c) for c in painted["rows"])).lower()
        assert "no author recorded" not in text, (
            f"the panel tells an operator whose ledger is fully attributed "
            f"that it is not: {painted!r}")
    finally:
        server.should_exit = True
        thread.join(timeout=10)
