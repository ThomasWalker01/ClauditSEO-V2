"""The scope note says which site a price came from, not what statistic it is.

**CQ-214, carried unbroken from report 097 to report 110 — twelve reports.**
`PriceScopeNote` is the component `tests/test_a_brief_price_says_which_site_
it_was_drawn_from.py` names, and that file's own title states the component's
subject: *which site it was drawn from*. Its rendered sentence nonetheless
opened "Every brief price here is a **median** of what it has cost on ...",
an unconditional claim about the statistic, and on the Tools screen it is
hoisted above `fig.note` — a **sum** (`24 brief(s) · ~4445k tokens ·
~$1.53 USD`), whose own comment at `dashboard/src/tools.tsx:791-799` says so
in as many words. So the largest money figure in the product carried a
caption naming the wrong statistic.

**Why the word goes rather than the placement.** Report 097's remediation
item 1 offered two routes and round 108 took the placement one: hoist the
note above both prices. That fixed the *scope* half and left the statistic
half, because the Tools screen carries a sum **and** per-brief medians under
one note, and no single word is true of both. A prop naming the figure would
push the choice to three call sites and make two of them assert something the
component cannot check. Dropping the claim is the only wording true on every
screen that renders it, and it is the claim the component was built to make.

**Deferred, and named rather than left silent (DISCIPLINE rule 3).** Stating
the statistic *beside its own figure* is the other half and is not taken here:
`schedule.tsx:228` already renders "is a median"/"are medians" over its own
rows, and `components.tsx`'s `BriefPriceFrame` states population rather than
statistic. Making the Tools screen's per-brief prices name theirs is a
separate lever with a separate blast radius.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

#: The component, and the one file that may define it — asserted, not assumed,
#: by `test_a_brief_price_says_which_site_it_was_drawn_from.py`'s own owner
#: clause, which this file deliberately does not repeat.
OWNER = "PriceScopeNote"
COMPONENTS = Path("dashboard/src/components.tsx")

#: Words that name a statistic rather than a population. A note covering a
#: screen that paints both a sum and a set of medians can defend none of them.
STATISTIC_WORDS = ("median", "medians", "mean", "average", "averages",
                   "sum", "summed", "total", "totals")


def _owner_body() -> str:
    """`PriceScopeNote`'s source, from the tree rather than from a literal.

    Split on the export and stop at the first column-zero close brace, which
    is how the sibling guard in
    `tests/test_a_brief_price_says_which_site_it_was_drawn_from.py` reads the
    same component; keeping the two readings identical is deliberate, so a
    change to the component cannot satisfy one and defeat the other.
    """
    source = COMPONENTS.read_text(encoding="utf-8")
    assert f"export function {OWNER}" in source, (
        f"{OWNER} is not defined in {COMPONENTS}; this guard's population is "
        "empty and it would pass by finding nothing")
    return source.split(f"export function {OWNER}", 1)[1].split("\n}", 1)[0]


def _rendered_text(body: str) -> str:
    """The words the operator reads: JSX text with expressions and comments
    removed. A statistic named in a `/** ... */` docstring is documentation
    and is not a claim on the screen — this file's own header names the
    statistic four times and must not fail itself."""
    body = re.sub(r"/\*.*?\*/", " ", body, flags=re.S)
    body = re.sub(r"\{[^{}]*\}", " ", body)
    body = re.sub(r"<[^>]*>", " ", body)
    return " ".join(body.split())


def test_the_note_renders_words_at_all():
    """Population, derived rather than asserted: the component must actually
    render the sentence this guard is about. A body that renders nothing would
    make every clause below vacuously true — the failure mode
    `.claude/loop/PROFILE.md`'s guard-population invariant is written for."""
    text = _rendered_text(_owner_body())
    assert "Every analysis price here" in text, (
        f"{OWNER} no longer renders the scope sentence this guard reads; "
        f"what it renders is {text!r}")


@pytest.mark.parametrize("word", STATISTIC_WORDS)
def test_the_note_claims_no_statistic(word: str):
    """CQ-214. The rendered sentence names a population, never a statistic."""
    text = _rendered_text(_owner_body()).lower()
    assert not re.search(rf"\b{word}\b", text), (
        f"{OWNER} renders the word {word!r}, which is a claim about the "
        f"statistic rather than the population. The Tools screen paints a "
        f"summed forecast under this same note (dashboard/src/tools.tsx), so "
        f"no single statistic word is true of every price it covers. "
        f"Rendered: {_rendered_text(_owner_body())!r}")


# RETIRED with item 188, on this clause's own instruction: it held that the
# summed forecast and the scope note were on one screen, and said that if
# "the Tools screen ever stops rendering both... this guard is about a
# situation that no longer exists and should be revisited rather than
# quietly kept". Tools is gone and no other screen sums that payload.
#
# The clauses above are untouched and are the ones that matter: the note's
# words, and that it claims no statistic. Those are about `PriceScopeNote`
# itself, which `expert.tsx` and `schedule.tsx` still render.
