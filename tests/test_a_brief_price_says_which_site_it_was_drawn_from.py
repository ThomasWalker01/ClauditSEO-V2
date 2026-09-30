"""CQ-198: a brief price says which site's history it was drawn from.

**The reader half of a key that has been on the wire since UX-77 landed.**
`GET /api/playbook` takes an optional `site_id` and answers *both ways on one
path* - install-wide when it is absent, this site's own briefs when it is
present - and `GET /api/sites/{id}/schedule` is always scoped. Both carry
`scoped_to_site` beside the value for exactly that reason, and
`clauditseo/api/app.py` says so in its own comment beside the key. Measured at
the commit that first raised this, `scoped_to_site` had **zero** occurrences
under `dashboard/src/`; it now has three readers, and that comment says so —
it used to read *"Giving this key a reader is CQ-198 and is not done here"*
for nineteen reports after the reader shipped, which was CQ-216.

What that costs was measured against the running product by report 096: the
unscoped call returns 24 tools with 10 priced, `www.acme.com.au` returns 1
priced, `twenty22.co` returns 0. Same label, same component, three populations,
and the only frame rendered stated sample counts and not which site - so two
figures the operator compares beside the control that spends are not comparable
and nothing on screen admitted it. That is the provenance invariant's frame
clause: *a share is stored with the scope it was computed under, in one key
beside the value, rather than left for the reader to re-derive.*

**Once per screen, not once per price.** The scope is constant for every price
on a screen, so repeating it on each row is UI-19's defect - a static
explanation repeating inside one scroll - which this repository already closed
for `ScoreBandKey` (`dashboard/src/components.tsx:86-88`). One note per screen
is the placement UI-19 settled on, and it leaves `BriefPriceFrame`'s deliberate
`costed >= sampled` null rule alone: that span is a *caveat*, which must not
always appear, and this one is a *frame*, which must.

**The note reads the payload's key and never the screen's own site id.** Both
screens already hold the id they issued the fetch with, and rendering that
would be cheaper. It would also be a frame that can never disagree with the
fetch it describes - DISCIPLINE rule 5, a check drawing its evidence from the
thing it checks. `scoped_to_site` is what the estimator recorded the figure was
computed over, which is a different fact from what the caller asked for, and it
is the only one of the two that can contradict the screen.

**Pure source reading, deliberately** - nothing here loads `dashboard/dist`, so
`scripts/prove_fail.py` can answer for this file. The payload half is guarded
separately and non-vacuously by
`tests/test_a_brief_is_priced_from_this_site_on_every_surface.py`, whose fixture
gives three sites deliberately different medians; this file is the render half
and does not restate it.

**CQ-215: two of the clauses that used to live here have gone, and where they
went matters more than that they left.** This file decided *which screens are
in the population* by searching each screen's text for `typical_cost`, and
*how many times the note renders* by counting the component's opening tag in
one screen's text with a regex. Both are decisions about what the product
**rendered**, taken from what its source **says** - so both are satisfiable by
a comment and breakable by a rename.
Neither is hypothetical: `tools.tsx` carries a note recording that someone
broke the count by naming the component in prose, and CQ-214 is the case where
the render site sat inside a branch that never ran while every clause here
passed. Both questions are now settled in
`tests/test_the_sweep_forecast_states_the_population_it_priced.py`, from what a
browser painted on each of the three screens.

What stayed is what is genuinely a source fact: where the component is
*defined*, what class it *names*, which payload key each screen *reads*, and
that the note is not folded into a `title=`. None of those is a claim about
what appeared on a screen. The line above about pure source reading still
holds for what is left - this file still loads no bundle.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"

#: The one component that composes the sentence. Named rather than discovered
#: so a shortfall says what is missing.
OWNER = "PriceScopeNote"

#: The screens that draw a per-brief price, checked below against the tree
#: rather than trusted. Same population as
#: `test_a_brief_price_says_which_runs_it_came_from.py`, and deliberately the
#: same derivation: a screen that draws a price needs both frames or neither.
#: Two since item 188 retired the Tools screen. The list is the point of
#: these clauses - a screen added or removed has to be noticed here - so it
#: shrank rather than the assertion loosening to "any screen that happens
#: to draw one".
DRAWS_A_BRIEF_PRICE = ("expert.tsx", "schedule.tsx")

#: The payload key. Written once so the assertions below cannot drift from the
#: producer at `clauditseo/api/app.py:1172` and `:1705`.
KEY = "scoped_to_site"


def _read(name: str) -> str:
    return (SRC / name).read_text(encoding="utf-8")


def test_the_scope_note_has_exactly_one_owner():
    """One place decides the wording - UI-19's precedent, applied early.

    Three screens each composing "these prices are from X" is how the same
    sentence acquires three different meanings, which is the defect UI-19
    closed for the monthly figures and UX-74's frame avoided for the per-brief
    ones by shipping a component instead of a string.
    """
    definitions = [p.name for p in SRC.glob("*.tsx")
                   if re.search(rf"export function {OWNER}\b",
                                p.read_text(encoding="utf-8"))]
    assert definitions == ["components.tsx"], (
        f"{OWNER} is defined in {definitions}; it belongs in components.tsx "
        "beside BriefPriceFrame, which is the owner of the other half of this "
        "price's frame")


def test_the_owner_distinguishes_install_wide_from_a_named_site():
    """`null` is a population, not an absence.

    The install-wide case is the one the operator cannot infer: a screen with a
    site selected that silently shows install-wide figures looks exactly like
    one showing that site's own. So the absent scope has to be *said*, which is
    the half a `{scope && ...}` guard would quietly drop.
    """
    source = _read("components.tsx")
    body = source.split(f"export function {OWNER}")[1]
    assert "install" in body.lower(), (
        f"{OWNER} never names the install-wide population; a null "
        f"`{KEY}` means 'every site in this install' and rendering nothing for "
        "it leaves the one case the operator cannot infer unstated")


def test_the_owner_names_a_class_the_stylesheet_declares():
    """One owner for the text is only half of UI-19.

    The same reasoning as
    `test_dashboard_a11y.py::test_the_priced_entries_frame_has_a_class_that_styles_css_declares`,
    and it bites harder here: the three screens rendering this note surround it
    with a tool panel, a brief panel and a table caption, so an owner that
    names no class of its own inherits three different weights for one
    sentence. Asserted against the class the owner actually uses rather than a
    literal, so a rename moves both halves together or reddens this.
    """
    src = _read("components.tsx")
    body = src.split(f"export function {OWNER}", 1)[1].split("\n}", 1)[0]
    used = re.findall(r'className="([a-z0-9 -]+)"', body)
    classes = [c for group in used for c in group.split()]
    assert classes, f"{OWNER} names no class: {body!r}"
    css = (SRC / "styles.css").read_text(encoding="utf-8")
    undeclared = [c for c in classes if f".{c}" not in css]
    assert not undeclared, (
        f"{OWNER} names a class the stylesheet does not declare, so its weight "
        f"is whatever surrounds it on each of three screens: {undeclared}")


@pytest.mark.parametrize("name", DRAWS_A_BRIEF_PRICE)
def test_every_screen_that_draws_a_brief_price_names_its_population(name: str):
    source = _read(name)
    assert OWNER in source, (
        f"{name} paints a brief price and never says which site's history it "
        f"came from; `{KEY}` has been on the wire since UX-77 landed")
    assert re.search(rf"<{OWNER}\b", source), (
        f"{name} imports the scope note and never renders it")


@pytest.mark.parametrize("name", DRAWS_A_BRIEF_PRICE)
def test_every_screen_reads_the_payload_key_rather_than_its_own_site_id(
        name: str):
    """DISCIPLINE rule 5, at the JSX.

    Each of these screens holds the site id it issued the fetch with. Feeding
    that to the note would render a frame that agrees with the request by
    construction and so can never report that the answer was scoped
    differently - a check drawing its evidence from the thing it checks.
    """
    source = _read(name)
    assert KEY in source, (
        f"{name} renders the scope note without reading `{KEY}`; the only "
        "other value it could be drawing on is the site id it issued the "
        "fetch with, which cannot disagree with the fetch")


@pytest.mark.parametrize("name", DRAWS_A_BRIEF_PRICE)
def test_the_scope_is_rendered_text_and_not_a_tooltip(name: str):
    """The provenance invariant's extended clause, on the same footing as
    UX-74's frame: a stated limitation on a displayed value appears in rendered
    text, not only in a `title`, an `aria-label` or an `sr-only` element."""
    source = _read(name)
    for attr in ("title", "aria-label"):
        for match in re.finditer(rf"{attr}=\{{[^}}]*{OWNER}", source):
            pytest.fail(
                f"{name}: the scope note appears inside a `{attr}=` attribute "
                f"at offset {match.start()}; the frame has to be in rendered "
                "text")
    for helper in ("function priceHint", "function priceOf"):
        start = source.find(helper)
        if start != -1:
            body = source[start:source.find("\n}", start)]
            assert OWNER not in body, (
                f"{name}: the scope note is inside {helper}, whose return "
                "value also feeds `title=` attributes - it has to be rendered "
                "beside the prices rather than folded into the string")


#: UI-19 - the note is rendered once per screen and not once per price - was
#: asserted here by counting the component's opening tag in each screen's
#: text. That count is CQ-215 and it now lives in
#: `tests/test_the_sweep_forecast_states_the_population_it_priced.py`, taken
#: from the elements a browser painted on each of the three screens. It is not
#: restated here, because a second count over source would be the defect
#: again with a passing neighbour to hide behind.
