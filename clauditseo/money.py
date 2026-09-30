"""One owner for every money figure Python renders — CQ-43.

Round 027's lever was called "one owner for a money figure" and closed the
TypeScript half: fifteen hard-coded dollar signs became `money()` in
`dashboard/src/components.tsx`, which decides the currency and the precision
in one place. The Python half was never done. Four sites went on hand-building
their own — `app.py` twice, `expert.py` twice — and the guard beside them,
`test_every_money_figure_goes_through_one_formatter`, checked Python only for
a `${` inside an f-string. That is the absence of a dollar sign, not the
presence of a formatter, so `f"USD {cost:.2f}"` passed it four times over and
the finding was carried from report 027 to report 079.

Two properties this file owns, and neither was owned anywhere before:

**The currency is named in what the value returns.** Costs are recorded in USD
and, by the operator's decision of 16 August 2026, are never converted, so the
currency is not implied by a setting and has to travel on the figure.

**Precision is decided here, not at the call site.** All four Python sites used
two places. A per-brief cost of USD 0.0004 renders `USD 0.00` at two places and
reads as free — and `app.py`'s copy is the price string the dispatcher model
reads when choosing what to spend, so the reader that a rounded-to-free figure
misleads is not only the operator. `components.tsx`'s `money` already decided the
*precision* rule for the same numbers on the other side of the wire; this is
that rule, spelled once for Python rather than a second opinion about it.

**That claim was wider than it should have been, and CQ-168 is what it cost.**
It held for `money` and never for `amount`: this one returns the digits alone
and the TypeScript one returned `$2.18`, so the shared owner the sentence
describes agreed on how many places to keep and disagreed on everything else.
Eighteen rounds of guards read both files and asked each whether it named a
currency; both answered yes, in different sentences, and neither guard could
ask whether the two answers matched. Closed by giving the TypeScript owner
this one's shape - currency in front, no symbol, thousands grouped - under
`test_the_two_money_owners_spell_a_figure_the_same_way`, which runs the
TypeScript source rather than reading it.

`amount` is public because the budget warning renders two figures under one
currency mention — the "one currency for the pair, not one each" rule
`moneyPair` states on the TypeScript side. A caller composing a pair reaches
for `money` once and `amount` for the rest, which keeps precision here even
where the currency word is not repeated.
"""

from __future__ import annotations

MONEY_CURRENCY = "USD"


def amount(value: float) -> str:
    """The number half of a money figure, with no currency on it.

    Sub-cent amounts keep four places, because two rounds a per-call cost of
    0.0004 to `0.00`. Zero is not sub-cent for this purpose — a figure that is
    genuinely nothing reads better as `0.00` than as `0.0000`, and the
    TypeScript owner draws the line in the same place.

    Thousands are grouped, and the TypeScript owner now groups them too.
    This paragraph used to record the divergence as deliberate - "the two
    render different populations; `money()` there is a per-call cost, the
    figures here include a monthly budget cap, which an operator sets in
    hundreds or thousands." The population split was never real: `admin.tsx`
    renders `cap_usd` through the *TypeScript* owner, so the one screen that
    draws both drew a capped figure on the side the justification said would
    never see one. Recorded rather than deleted, because that justification
    read well and was checkable from source, and nothing checked it for
    eighteen rounds - CQ-168.
    """
    places = 4 if value != 0 and abs(value) < 0.01 else 2
    return f"{value:,.{places}f}"


def money(value: float) -> str:
    """A money figure with its currency, for every Python renderer."""
    return f"{MONEY_CURRENCY} {amount(value)}"
