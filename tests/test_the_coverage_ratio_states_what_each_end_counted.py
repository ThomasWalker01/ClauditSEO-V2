"""CQ-70: both ends of the client-facing coverage ratio say what they counted.

Recorded by round 100 as a **strict xfail**, because the finding was blocked
on `QUESTIONS.md` Q-14 at rounds 097 and 098 and `SKILL.md` step 4 forbids a
third blocking. Q-14 is now **answered and acted** (relay item 098, 2026-08-28):
*close it — already satisfied by round 092: one count is stated (235 readable
pages), 224 is named as distinct paths, and no word does two jobs. The ratio
stays 235 of 272.* So the marker is retired here and the assertions are live.

**The defect.** `_scope` (`clauditseo/persistence/runs.py`) puts two counts of
two different things into one ratio. The numerator, `pages_fetched`, is "pages
a check could actually read". The denominator, `discovered`, is
`sitemap_entry_total` — URLs the site declared. `_breadth_phrase`
(`clauditseo/reporting/render.py`) rendered them under a single noun:

    " — measured across 235 of 272 discovered pages (86.4%)"

"discovered pages" governed both numbers while being true of only the second.

**Why the answer did not close this by itself, and why fixing it does not
re-open the answer.** The operator's option rests on the claim that "no word
does two jobs". Round 100 found that claim **false for this clause** — it was
priced against the scope line elsewhere, not against `_breadth_phrase` — and
recorded that every one of Q-14's three options, including the do-nothing one,
needs each end to say what it counted. So this is the answer's own stated
reason made true, not a fourth option: **no stated figure moves.** 235, 272
and 86.4% are the same three numbers before and after.

**The assertion is the one property all three of Q-14's options shared**, which
is what made it honest to write while the question was open: the denominator
states its basis the way the numerator already does. `pages_fetched` has
carried `pages_fetched_basis` since CQ-04 — one key saying which of three ways
the figure was arrived at, because "a consumer that cannot tell a recorded
count from a stood-in one cannot say which it is holding". `discovered` carried
nothing.

**The words are the screen's, not new ones.** `dashboard/src/views.tsx` already
renders "against 272 the sitemap declares" and "272 declared pages this crawl
reached". The document was the one surface that said "discovered pages" over
both ends; this brings it to the wording the screen has used all along.
"""

from __future__ import annotations

from clauditseo.persistence.runs import _scope
from clauditseo.reporting.render import _breadth_phrase

#: A stored run's evidence, in the shape `_scope` reads: a sitemap declaring
#: 272 URLs, of which 235 answered with something a check could read. The
#: figures are the operator's own, from the comparison document Q-14 is about.
EVIDENCE = {
    "stats": {"eligible": 235, "fetched": 240, "blocked_by_robots": 0},
    "sitemap_entry_total": 272,
}


def test_both_ends_of_the_coverage_ratio_say_what_they_counted():
    """The numerator declares its basis; the denominator must too.

    Asserted on the scope dict rather than on the rendered sentence, because
    the sentence is what Q-14 decides and the dict is what every reader of it
    shares — the client document, the operator's scope line and the score all
    read these keys.
    """
    scope = _scope(EVIDENCE)

    # The half that already worked, kept because it is the pattern the other
    # end was missing rather than a second thing to check. This is CQ-04's fix.
    assert scope["pages_fetched"] == 235
    assert scope["pages_fetched_basis"], (
        "the numerator lost the basis CQ-04 gave it")

    assert scope["discovered"] == 272

    # The defect. Any key naming what the denominator counted satisfies this
    # — the name is the implementer's to choose, and pinning one here would
    # be this guard deciding Q-14 by the back door.
    basis = [k for k in scope
             if k.startswith("discovered") and k != "discovered"]
    assert basis, (
        "the ratio's denominator states nothing about what it counted, while "
        "its numerator carries pages_fetched_basis — so "
        f"{scope['pages_fetched']} of {scope['discovered']} renders as one "
        "noun over two different populations")


def test_the_rendered_clause_does_not_put_one_noun_over_both_populations():
    """The dict is what every reader shares; this is what the client reads.

    Asserted as *the numbers are unchanged and the nouns are separate*, which
    is exactly the shape of the operator's answer: `235`, `272` and `86.4%`
    are the same three figures round 092 settled, and the only thing that
    moved is that each end now names its own population. A guard asserting
    only the new wording would pass on a clause that had quietly changed the
    percentage, which is the one thing the answer forbids.
    """
    clause = _breadth_phrase(_scope(EVIDENCE))

    # Nothing the operator answered about has moved.
    assert "235" in clause and "272" in clause and "86.4%" in clause, clause

    # And "discovered pages" no longer governs both of them.
    assert "discovered pages" not in clause, (
        "the ratio still renders one noun over two populations: pages a check "
        f"could read, and URLs the site declared. Clause: {clause!r}")
    assert "the sitemap declares" in clause, (
        f"the denominator does not say what it counted: {clause!r}")
    assert clause.index("235") < clause.index("pages a check could read"), (
        f"the numerator does not say what it counted: {clause!r}")
