"""UX-74, the render half: what the screens and the prompt say about the frame.

`tests/test_a_brief_price_says_what_it_covers.py` closed the wire half at round
079 and ends by naming this step: *"What the four render sites say about the
frame is a separate step, and one that can be argued about; that a renderer is
given the frame at all cannot."* Measured 23 August 2026, three reports later:
`cost_samples` and `runs_costed` reach `clauditseo/api/app.py:1092` and `:1608`
and `grep -rn cost_samples dashboard/src/` returns **zero**. The frame has been
on the wire for four reports and no screen has read it.

**Five sites, enumerated from source rather than from report 080's list** -
DISCIPLINE rule 3. Grepping `dashboard/src` for the two price helpers and for
`typical_cost` gives: `expert.tsx`'s `priceHint` at two visible sites,
`tools.tsx`'s `priceOf` at two, `schedule.tsx`'s Typical cost cell and its
annual forecast, and `_triage_data`'s `price` string in `clauditseo/api/app.py`.
`tools.tsx`'s working-set forecast is the sixth and is `BACKLOG.md` B-25.

**Two owners, and the difference is the point rather than an oversight.**
`PricedFrame` says *"a floor"*, because its subject is a monthly **sum**: an
entry with no price can only be missing from a total. `BriefPriceFrame` claims
no direction, because its subject is a **median over the priced subset**, and
an unpriced sample might have been dearer or cheaper than the ones that were
costed. Reusing `PricedFrame` for the per-brief figures would have been one
import and would have shipped a false claim about what the number understates.
The one site in this cluster that *is* a sum - B-25's working-set forecast in
`tools.tsx` - uses `PricedFrame`, and that split is asserted below so a later
edit cannot quietly collapse the two owners into one.

**Rendered text, never a `title`.** All three price helpers also feed `title=`
attributes. The provenance invariant's extended clause is that a stated
limitation appears in rendered text and not only in a tooltip, an `aria-label`
or an `sr-only` element, so a fix that appended the frame to `priceHint`'s
return value would have satisfied UX-74's wording and breached the invariant
behind it. The test below reads the JSX, not the helper.

**What is asserted where, and why it is split.** The prompt half is behavioural
and cheap - seed a partly-priced brief, call the endpoint, read the string - so
it is asserted as behaviour. The screen half is three `.tsx` files and asserting
it live would need a browser and a database carrying partly-priced briefs, which
the shipped `served` fixture does not have (it has no `model_prices` row at all,
which is what `test_spend_mark.py` relies on for its own clause 4). So the
screens are asserted from source, on `test_spend_mark.py`'s precedent, and the
live reading is a rule-12 observation recorded in `OPERATOR_ACTIONS.md` rather
than a claim made here. Said plainly because a source assertion that reads as a
rendered one is the inherited-coverage claim rule 4 forbids.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from clauditseo.api.app import _triage_data, settings
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo, runs
from tests.test_a_brief_price_says_what_it_covers import _seed  # one fixture shape

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"

#: The screens that draw a per-brief price, derived below rather than trusted.
#: Kept as a tuple only so a shortfall names which file is missing; the
#: population it is checked against comes from the tree.
#: Two since item 188 retired the Tools screen. The list is the point of
#: these clauses - a screen added or removed has to be noticed here - so it
#: shrank rather than the assertion loosening to "any screen that happens
#: to draw one".
DRAWS_A_BRIEF_PRICE = ("expert.tsx", "schedule.tsx")


def _read(name: str) -> str:
    return (SRC / name).read_text(encoding="utf-8")


def test_the_population_is_the_one_the_tree_reports():
    """Non-vacuity, and the reason it is first.

    Every assertion below is over `DRAWS_A_BRIEF_PRICE`. If a fourth screen
    started drawing `typical_cost` this file would go on passing about three,
    which is exactly the hand-kept-population failure `needs_build` was
    repaired for. The population is re-derived from source here and the tuple
    is checked against it.
    """
    drawing = {p.name for p in SRC.glob("*.tsx")
               if "typical_cost" in p.read_text(encoding="utf-8")}
    assert drawing, "no file reads `typical_cost`; the grep has stopped working"
    assert drawing == set(DRAWS_A_BRIEF_PRICE), (
        f"the set of screens drawing a per-brief price is {sorted(drawing)}, "
        f"not {sorted(DRAWS_A_BRIEF_PRICE)} - a screen was added or removed and "
        "the assertions below no longer cover what they claim to")


def test_the_frame_has_exactly_one_owner():
    """One place decides the wording, on UI-19's precedent for `PricedFrame`."""
    definitions = [p.name for p in SRC.glob("*.tsx")
                   if re.search(r"export function BriefPriceFrame\b",
                                p.read_text(encoding="utf-8"))]
    assert definitions == ["components.tsx"], (
        f"BriefPriceFrame is defined in {definitions}; three screens composing "
        "this sentence themselves is the defect UI-19 closed for the monthly "
        "figures and it must not reopen for the per-brief ones")


@pytest.mark.parametrize("name", DRAWS_A_BRIEF_PRICE)
def test_every_screen_that_draws_a_brief_price_renders_the_frame(name: str):
    source = _read(name)
    assert "BriefPriceFrame" in source, (
        f"{name} draws a per-brief price and never says which runs it came "
        "from; the two counts have been on the wire since round 079")
    assert re.search(r"<BriefPriceFrame\b", source), (
        f"{name} imports the frame and never renders it")


@pytest.mark.parametrize("name", DRAWS_A_BRIEF_PRICE)
def test_the_frame_is_rendered_text_and_not_a_tooltip(name: str):
    """The provenance invariant's extended clause, checked at the JSX.

    The failure this forbids is concrete: appending the frame to `priceHint`'s
    or `priceOf`'s return value would put it inside the `title=` strings those
    helpers already feed, where it is announced to nobody who is looking at the
    screen.
    """
    source = _read(name)
    for match in re.finditer(r"title=\{[^}]*BriefPriceFrame", source):
        pytest.fail(f"{name}: the frame appears inside a `title=` attribute at "
                    f"offset {match.start()}; a stated limitation has to be in "
                    "rendered text")
    for helper in ("function priceHint", "function priceOf"):
        start = source.find(helper)
        if start != -1:
            body = source[start:source.find("\n}", start)]
            assert "BriefPriceFrame" not in body, (
                f"{name}: the frame is inside {helper}, whose return value also "
                "feeds `title=` attributes - it has to be rendered beside the "
                "price rather than folded into the string")


def test_a_sum_keeps_its_direction_and_a_median_does_not():
    """The two owners stay two.

    A sum understates by construction and says so; a median does not and must
    not claim to. A later edit collapsing the two frames would either drop a
    direction that is earned (UX-80's defect) or add one that is not.

    **This clause used to read one file.** `tools.tsx` rendered both frames -
    `PricedFrame` on its working-set forecast and `BriefPriceFrame` on its
    per-brief prices - so "the two owners stay two" could be asserted by
    opening it. Item 188 retired that screen, and the two owners are still two
    but now live apart: the sum is on Admin and Home, over the budget's priced
    entries, and the median is on the screens that price a brief. So the clause
    reads both sides rather than the one file that used to hold them, which is
    a stronger question anyway - it was never about Tools.
    """
    sums = [n for n in ("admin.tsx", "home.tsx") if "<PricedFrame" in _read(n)]
    assert sums, (
        "nothing renders `PricedFrame` any more, so a sum is being drawn "
        "somewhere without the frame that says it understates - B-25 is an "
        "operator reading `~4445k tokens · ~$1.53 USD` and being unable to "
        "reconcile the two")
    medians = [n for n in DRAWS_A_BRIEF_PRICE if "<BriefPriceFrame" in _read(n)]
    assert medians, "nothing renders `BriefPriceFrame`"
    assert "a floor" not in _read("components.tsx").split(
        "export function BriefPriceFrame")[1], (
        "BriefPriceFrame must not claim a direction: an unpriced sample does "
        "not tell you whether the median it was left out of is high or low")


def test_the_price_the_model_is_given_names_its_population(tmp_path,
                                                           monkeypatch):
    """The fifth site, and the only one that is not a screen.

    `_triage_data` hands the dispatcher model a price per available brief and
    asks it for a SPEND NEXT ranking inside a budget. A median over one run of
    three and a median over three of three are the same sentence to a model
    unless the population is in the string.

    Called directly rather than through a route, because there is none: it is
    assembled inside `POST /api/runs/{id}/expert/triage` (`app.py:2369`), which
    would spend against a provider to reach it. The wire guard's sibling file
    calls `expert_estimates` the same way and for the same reason.
    """
    monkeypatch.setenv("CLAUDITSEO_LLM_PROVIDER", "mock")
    conn = connect(tmp_path / "triage-price.db")
    migrate(conn)
    try:
        site_id = _seed(conn)
        site_row = repo.get_site(conn, site_id)
        run_id = runs.create_run(conn, site_id, ["TEC"], "T2")
        run = runs.get_run(conn, run_id)
        data = _triage_data(conn, run, site_row, settings(), {"pages": []})
    finally:
        conn.close()

    brief = next(b for b in data["available_briefs"]
                 if b["tool"] == "indexability")

    assert "1 of 3" in brief["price"], (
        f"the model is given {brief['price']!r} - a price with no population, "
        "which it is then asked to fit a recommendation inside")
