"""WF-04: the reference-rate line reads as a conversion and states an identity.

`rate_for(conn, "USD")` returns `{"rate": 1.0, "source": "identity"}` by
construction, and it is the only answer this screen can ever get: the display
currency defaults to USD, CQ-16 records that no screen can change it, and the
selector that once could was removed when conversion was closed **won't-fix**
(`audits/DISPOSITIONS.md`, 16 August 2026 - client figures state the currency
they were recorded in and are never converted). So the line has always
rendered

    Reference only: 1 USD = 1 USD - identity - today

read from the operator's own instance at `GET /api/rates` before this was
written. A line whose whole grammar is `1 X = n Y` says a conversion happened;
this one says nothing at all, to the operator who would be the person needing
the rate.

**Why the stored rates are in scope and the rest of the panel is not.** The
button beside the line is labelled "refresh reference rates" and its only
output is the `fx_rates` table, which `data.stored` carries to the client and
nothing renders - measured at 0 rows on the live instance, and
`grep -c data.stored dashboard/src/admin.tsx` returning 0. Correcting the line
without this leaves the panel's own comment false: "The reference rate stays.
It is genuinely useful for an operator invoicing in their own currency by
hand." A control whose only output is rendered nowhere is the affordance
invariant, and shipping that in order to close a line is not a trade worth
making.

**What is deliberately not here.** Making the display currency settable is
CQ-16 and stays open; nothing in this file asks for a second currency to
exist. The clauses below hold whether one ever does - the identity is refused
because it says nothing, not because USD is special.
"""

from __future__ import annotations

import re
import sqlite3

import pytest

from clauditseo import axe
from tests.test_a11y_rendered import DIST, served  # noqa: F401  (reused fixture)


#: A seventh copy of this decorator, and CQ-125 is the standing finding about
#: that. Taken knowingly: the alternative is CQ-153's cost on the other side -
#: a branch that ships unpainted because no file in the sweep can reach it -
#: and this project has already ruled which of the two it prefers.
def live(fn):
    fn = pytest.mark.skipif(
        not (DIST / "index.html").is_file(),
        reason="dashboard not built (npm run build in dashboard/)")(fn)
    return pytest.mark.skipif(
        not axe.available(),
        reason="needs clauditseo[render] and `playwright install chromium`")(fn)


@pytest.fixture()
def browser_page():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            yield pg
        finally:
            browser.close()


#: The Money card's rendered text, located by its own heading rather than by a
#: class - a marker class existing only so a test can select it has to be
#: recorded in `SELECTED_NOT_PAINTED`, which carries two open findings of its
#: own about rows going stale in it.
MONEY = """() => {
  const h = [...document.querySelectorAll('h3')].find(
    (e) => e.innerText.trim().toUpperCase() === 'MONEY');
  return h ? h.closest('.card').innerText : null;
}"""

#: `1 AUD = 1.52 USD`, in whichever direction it is written. Both currency
#: codes are captured so the clause can ask whether they are the same one.
RATE_LINE = re.compile(r"\b1\s+([A-Z]{3})\s*=\s*[\d.]+\s+([A-Z]{3})\b")


def money_card(pg, base: str) -> str:
    # Money is a tab of its own since 2026-09-03.
    pg.goto(f"{base}/#/admin?tab=prices", wait_until="load")
    pg.wait_for_selector(".card", timeout=15_000)
    pg.wait_for_timeout(400)
    text = pg.evaluate(MONEY)
    assert text, "the Money card did not render, so no clause below tested it"
    return text


def stage_rates(db: str, rows) -> list:
    """Put reference rates in the table the button writes to, handing back what
    was there.

    The live instance holds none, so the populated branch cannot be reached any
    other way, and a branch nothing can reach is CQ-153.
    """
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    before = [dict(r) for r in conn.execute("SELECT * FROM fx_rates")]
    conn.execute("DELETE FROM fx_rates")
    for cur, rate in rows:
        conn.execute(
            "INSERT INTO fx_rates (currency, rate, source, fetched_at)"
            " VALUES (?, ?, ?, ?)",
            (cur, rate, "ECB", "2026-08-20T00:00:00+00:00"))
    conn.commit()
    conn.close()
    return before


def restore_rates(db: str, before: list) -> None:
    conn = sqlite3.connect(db)
    conn.execute("DELETE FROM fx_rates")
    for row in before:
        conn.execute(
            "INSERT INTO fx_rates (currency, rate, source, fetched_at)"
            " VALUES (?, ?, ?, ?)",
            (row["currency"], row["rate"], row["source"], row["fetched_at"]))
    conn.commit()
    conn.close()


@live
def test_the_panel_never_states_a_rate_from_a_currency_to_itself(
        served, browser_page):
    """The finding itself, asserted on what the screen says rather than on the
    branch that produces it.

    Written as "no `X = X` anywhere in this card" rather than as "the string
    `1 USD = 1 USD` is absent", so it still holds if the display currency ever
    becomes settable: the defect is a line claiming a conversion when the two
    sides are the same unit, and that is true of every currency rather than of
    this one.

    **Staged with the base row present, which is round 075's correction.**
    As written this clause read the live table, which holds zero rows, so
    the only sentence it could ever refuse was one nothing produced. The
    table it is handed here is what a single press of `refresh reference
    rates` leaves behind: `fetch_rates` writes `rates["USD"] = 1.0` beside
    whatever the feed returned, and the clause named
    `test_the_press_really_does_write_the_row_the_filter_has_to_remove` is
    what keeps that true.
    """
    base, ids = served
    before = stage_rates(ids["db"],
                         [("USD", 1.0), ("AUD", 1.52), ("EUR", 0.91)])
    try:
        text = money_card(browser_page, base)
    finally:
        restore_rates(ids["db"], before)
    assert "1.52" in text, (
        "the staged rates did not reach the panel, so the clause below "
        f"refused an identity in a card that rendered nothing: {text!r}")
    # `finditer` over the whole card, not `search` per line. The panel joins
    # every clause with " · " into one `muted` span, so the card is a single
    # line and `search` returned only its first clause - with the rows sorted
    # by currency, that is `1 USD = 1.52 AUD`, and the identity sitting third
    # in the same line was never looked at. Measured: staged with the base row
    # present, the per-line form still passed.
    same = [m.group(0) for m in RATE_LINE.finditer(text)
            if m.group(1) == m.group(2)]
    assert not same, (
        "the panel states a rate from a currency to itself, which is a "
        f"conversion that did not happen: {same!r}")


@live
def test_the_panel_says_which_currency_costs_are_in(served, browser_page):
    """The negative clause's other half, and what keeps the fix from being a
    deletion.

    Removing the identity line satisfies the clause above and leaves the
    operator with a Money card that never names the unit its figures are in -
    the frame clause of the provenance invariant, traded away to close a
    workflow finding.
    """
    base, ids = served
    text = money_card(browser_page, base)
    assert "USD" in text, (
        "the Money card does not name the currency its figures are recorded "
        f"in: {text!r}")


@live
def test_a_fetched_reference_rate_is_shown_to_the_operator(
        served, browser_page):
    """The button's only output, rendered.

    `refresh reference rates` writes `fx_rates` and nothing read it back, so
    the control acted on nothing an operator could see - the affordance
    invariant, on the screen whose own comment says the rate is kept because
    it is "genuinely useful for an operator invoicing in their own currency by
    hand".
    """
    base, ids = served
    before = stage_rates(ids["db"], [("AUD", 1.52), ("EUR", 0.91)])
    try:
        text = money_card(browser_page, base)
        for currency, rate in (("AUD", "1.52"), ("EUR", "0.91")):
            assert currency in text and rate in text, (
                f"a stored reference rate ({currency} {rate}) is fetched and "
                f"shown to nobody: {text!r}")
    finally:
        restore_rates(ids["db"], before)


@live
def test_the_empty_state_says_so_rather_than_showing_nothing(
        served, browser_page):
    """No stored rate is the live instance's actual state - `GET /api/rates`
    returns zero rows today - so it is the branch the operator meets first, and
    a panel that simply omits the section reads as one that failed to load.
    """
    base, ids = served
    before = stage_rates(ids["db"], [])
    try:
        text = money_card(browser_page, base)
        assert "reference rate" in text.lower(), (
            "with nothing stored the panel says nothing about reference "
            f"rates at all: {text!r}")
    finally:
        restore_rates(ids["db"], before)


# --- The list the panel renders, asserted at the boundary that produces it ---
#
# Round 075. The clauses above drive the browser and are the operator's own
# view, but every one of them reads the *live* `fx_rates` table, which holds
# zero rows - so the row that produces WF-04 could not appear in any of them.
# `fetch_rates` writes `rates["USD"] = 1.0` on every press, under a comment
# saying it does so because the feed is USD-based, and `stage_rates` deletes
# the table before inserting, so the one clause written to refuse an identity
# staged away the only data that can produce one. These four ask the API
# instead: it is where the list is built, it needs no browser, and it can be
# handed exactly the table a press would leave behind.


@pytest.fixture()
def rates_api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from clauditseo.api.app import create_app

    monkeypatch.delenv("CLAUDITSEO_TOKEN", raising=False)
    db = tmp_path / "rates.db"
    client = TestClient(create_app(db_path=db))
    client.get("/api/rates")            # force the schema before writing to it
    return client, db


def _put_rates(db, rows) -> None:
    conn = sqlite3.connect(db)
    conn.executemany(
        "INSERT INTO fx_rates (currency, rate, source, fetched_at)"
        " VALUES (?, ?, ?, ?) ON CONFLICT(currency) DO UPDATE SET"
        " rate=excluded.rate",
        [(c, r, "ecb-via-frankfurter", "2026-08-22T00:00:00+00:00")
         for c, r in rows])
    conn.commit()
    conn.close()


def test_the_press_really_does_write_the_row_the_filter_has_to_remove():
    """The non-vacuity clause, and the reason the two below are not theatre.

    Every clause that asserts an absence is worthless if the thing is never
    produced, which is exactly how the browser clause above passed while the
    defect stood. So this one asserts the *presence* of the base row at the
    only place it is created: `fetch_rates` puts `USD` into the dict it hands
    `store_rates`, whatever the feed said. If that ever stops being true this
    fails, and the two clauses below stop being evidence about anything.
    """
    from clauditseo.providers import fx

    class _Resp:
        @staticmethod
        def raise_for_status():
            return _Resp

        @staticmethod
        def json():
            return {"rates": {"AUD": 1.52, "EUR": 0.91}}

    import httpx
    real = httpx.get
    httpx.get = lambda *a, **k: _Resp                    # noqa: E731
    try:
        rates, _source = fx.fetch_rates()
    finally:
        httpx.get = real
    assert fx.BASE in rates and rates[fx.BASE] == 1.0, (
        "the fetch no longer writes the base row, so the clauses below assert "
        f"the absence of something nothing creates: {rates!r}")


def test_the_reference_list_never_carries_the_currency_it_is_quoted_from(
        rates_api):
    """WF-04 at the boundary: `1 USD = 1 USD` cannot be rendered from a list
    that does not contain USD.

    Staged with the base row *present*, which is the whole correction - the
    browser clause above stages a table that deletes it.
    """
    client, db = rates_api
    from clauditseo.providers import fx

    _put_rates(db, [(fx.BASE, 1.0), ("AUD", 1.52), ("EUR", 0.91)])
    stored = client.get("/api/rates").json()["stored"]
    seen = [r["currency"] for r in stored]
    assert fx.BASE not in seen, (
        "the reference list carries the currency every rate is quoted from, "
        f"so the panel states a conversion that did not happen: {seen!r}")
    assert "AUD" in seen and "EUR" in seen, (
        "the filter emptied the list instead of removing one row, which "
        f"closes the finding by deleting the feature: {seen!r}")


def test_the_reference_list_is_bounded_by_what_the_setter_accepts(rates_api):
    """UI-17 and the render half of CQ-158: the panel's size is decided by
    `CURRENCIES`, not by a third party's response body.

    `CURRENCIES` bounds what an operator may choose and did not bound what the
    screen shows, so a feed returning 170 currencies produced 170 clauses in
    one `muted` span. The two staged here are outside that list and the feeds
    in `RATE_SOURCES` both return them.
    """
    client, db = rates_api
    from clauditseo.providers import fx

    unlisted = [c for c in ("JPY", "CHF", "SEK") if c not in fx.CURRENCIES]
    assert len(unlisted) >= 2, (
        "the currencies this clause stages are now inside CURRENCIES, so it "
        f"no longer tests a bound: {unlisted!r}")
    _put_rates(db, [("AUD", 1.52)] + [(c, 1.0) for c in unlisted])
    seen = [r["currency"] for r in client.get("/api/rates").json()["stored"]]
    assert not [c for c in seen if c not in fx.CURRENCIES], (
        "the reference list renders currencies the setter would refuse, so "
        f"its length is set by the feed rather than by the product: {seen!r}")
    assert "AUD" in seen, (
        f"the bound dropped a currency CURRENCIES lists: {seen!r}")


# --- UX-70: the confirmation counts one set and the list beneath it another ---
#
# Round 085's lever, and the second half of what round 075 started. That round
# put the bound on the read side — `reference_rates` drops the base row and
# keeps only `CURRENCIES` — and left `refresh` returning `store_rates(...)`,
# which is `len(rates)`: every currency the feed sent. So the sentence the
# operator reads after pressing the button counts rows they cannot see, one
# line above the list of the rows they can, and nothing says which is the
# answer. `RATE_SOURCES` holds two feeds of different breadths, so the number
# is not stable between presses either.
#
# Two clauses because the sentence has two halves and they fail differently.
# The first asks the boundary whether both counts are on the wire at all; the
# second drives the browser and asks whether the sentence states them. Neither
# alone is the finding: a server that reports both under a panel that renders
# one is still the defect, and a panel rendering a number the server never
# sends cannot happen but would be invisible to the browser clause if it did.


def test_the_refresh_answer_counts_the_rows_the_panel_will_list(rates_api):
    """The server half. `refresh` must report the size of the list the panel
    is about to draw, not only the size of the write.

    The feed staged here is the real shape rather than a contrived one: both
    entries in `RATE_SOURCES` return currencies outside `CURRENCIES`, which is
    exactly why round 075 had to bound the read at all. With this feed the two
    counts genuinely differ, so a fix that aliased one to the other — the
    cheapest wrong answer available here — fails this clause rather than
    passing it.
    """
    import httpx

    from clauditseo.providers import fx

    client, _db = rates_api

    unlisted = [c for c in ("JPY", "CHF", "SEK") if c not in fx.CURRENCIES]
    assert len(unlisted) >= 2, (
        "the currencies this clause stages are now inside CURRENCIES, so the "
        f"feed no longer produces a gap for the sentence to mis-state: {unlisted!r}")

    sent = {"AUD": 1.52, "EUR": 0.91} | {c: 1.0 for c in unlisted}

    class _Resp:
        @staticmethod
        def raise_for_status():
            return _Resp

        @staticmethod
        def json():
            return {"rates": sent}

    real = httpx.get
    httpx.get = lambda *a, **k: _Resp                    # noqa: E731
    try:
        out = client.post("/api/rates/refresh", json={}).json()
    finally:
        httpx.get = real

    listed = client.get("/api/rates").json()["stored"]
    assert out["ok"], f"the staged feed did not answer, so nothing below is evidence: {out!r}"
    assert out["stored"] == len(sent) + 1, (
        "the write count is no longer every currency the feed sent plus the "
        f"base, so this clause is measuring something else: {out!r}")
    assert "shown" in out, (
        "the refresh answer reports what it wrote and not what the panel can "
        "show, so the only number the confirmation sentence has is a count of "
        f"rows the operator cannot see: {out!r}")
    assert out["shown"] == len(listed), (
        "the count the answer offers the panel is not the length of the list "
        f"the panel renders: {out['shown']} against {len(listed)}")
    assert out["shown"] != out["stored"], (
        "the two counts are equal for a feed that returns currencies outside "
        "CURRENCIES, which means one has been aliased to the other rather "
        f"than measured: {out!r}")


#: Where `setNote` lands: the last `p.muted` in the Money card *above* the
#: Model prices sub-heading. Located by position rather than by class, because
#: the card opens with `data.note` in a `p.muted` of its own and the reference
#: rate note has no marker of its own — and a marker class existing only for a
#: test has to be recorded in `SELECTED_NOT_PAINTED`, which the note at the top
#: of this file is already about.
#:
#: The `h4.money-sub` bound is not decoration. Written as "the card's last
#: `p.muted`" this returned the Model prices empty state — "None known yet, so
#: every cost shows as tokens" — and the clause failed against unfixed source
#: for the wrong reason, reading a paragraph two sections below the one the
#: button writes. Measured, not reasoned: the first run printed that sentence.
MONEY_NOTE = """() => {
  const h = [...document.querySelectorAll('h3')].find(
    (e) => e.innerText.trim().toUpperCase() === 'MONEY');
  if (!h) return null;
  const card = h.closest('.card');
  const sub = card.querySelector('h4.money-sub');
  const ps = [...card.querySelectorAll('p.muted')].filter(
    (p) => !sub || (sub.compareDocumentPosition(p) & 2));
  return ps.length ? ps[ps.length - 1].innerText : null;
}"""


@live
def test_the_confirmation_names_both_counts_and_the_listed_one_is_the_list(
        served, browser_page):
    """The renderer half, read where the operator reads it.

    The answer is stubbed rather than fetched: this clause is about what the
    panel does with two counts, and putting a third party's live response body
    inside a suite run would make the assertion depend on what a free feed
    happened to return. The stub is the shape the clause above proves the
    server produces — `stored` larger than `shown`, which is what a feed
    returning unlisted currencies leaves behind.

    The staged table is three rows, all inside `CURRENCIES`, so the list the
    panel draws is three clauses long and the `shown` count is checkable
    against something rendered rather than against itself.
    """
    import json

    base, ids = served
    before = stage_rates(ids["db"],
                         [("AUD", 1.52), ("EUR", 0.91), ("GBP", 0.78)])

    def answer(route):
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps({"ok": True, "stored": 12, "shown": 3,
                                       "source": "ecb-via-frankfurter"}))

    try:
        browser_page.route("**/api/rates/refresh", answer)
        card = money_card(browser_page, base)
        browser_page.click("button:has-text('refresh reference rates')")
        browser_page.wait_for_timeout(1_000)
        note = browser_page.evaluate(MONEY_NOTE)
        card = browser_page.evaluate(MONEY)
    finally:
        browser_page.unroute("**/api/rates/refresh")
        restore_rates(ids["db"], before)

    assert note and "ecb-via-frankfurter" in note, (
        "the press produced no confirmation, so the clauses below read a "
        f"sentence nothing wrote: {note!r}")
    clauses = RATE_LINE.findall(card)
    assert len(clauses) == 3, (
        "the staged rates did not reach the list, so 'the count matches the "
        f"list' is a comparison against nothing: {clauses!r}")
    assert re.search(r"\b3\b", note), (
        "the confirmation never states how many rates are listed below it, "
        "so its only number is a count of rows the operator cannot see: "
        f"{note!r}")
    assert re.search(r"\b12\b", note), (
        "the confirmation dropped the count of what was written, which "
        "closes the finding by deleting half the answer rather than by "
        f"framing it: {note!r}")
