r"""A digit run inside an identifier is not a number, on both halves of the rule.

CQ-30, carried since report 024 and raised to High at 081. `clauditseo.numbers`
owns what counts as "a number in this text" for six callers, and its token
`\d[\d,]*(?:\.\d+)?` carries no boundary at all. So `x509` holds the number 509,
`FY25` holds 25, and `hero-69a4e135.webp` holds 0, 4, 42, 69 and 135.

That is two defects wearing one regex.

**The panel.** `ungrounded_figures` flags figures an operator is told to
spot-check before quoting them to a client. Measured read-only on the operator's
database at round 081: **13 of 189 stored flagged figures** are identifier
fragments - `135`, `20273` and `3744` out of CDN filename hashes in
`image-optimisation`, `01` through `07` out of `G01`-`G07` in `content-gap`,
`509` out of `x509` in `https-security`, `25` out of `FY25` in `eeat-analyst`.
A caution the operator learns to dismiss is worse than no caution.

**The gate.** The symmetric half is `allowed = extract_numbers(evidence)`, which
inherits the same fragments - so a hashed filename in the evidence *grounds* a
fabricated figure. `numbers.py`'s own docstring says this class is closed ("a
fabricated 43 passed because 1043 appeared somewhere in a hash"); it was closed
for digit neighbours only, and a letter neighbour walks straight through.

**Why the boundary is an identifier shape and not "any abutting letter".**
Measured old-token against new over all 38 stored briefs and the 35 documents
under `reports/out/`: rejecting *any* digit run touching a letter drops 579
numbers, against 409 for the rule below - and the 170 in the difference are
figures with a unit or currency suffix: `0.7s`, `300ms`, `$5K`, `$7.5M`,
`100vh`, `145k`, `3xx`. Those are claims about the site, and dropping them from
the evidence side would make a bare `0.7` in a document read as ungrounded
against an evidence that says `0.7s`. The rule that separates the two is where
the letters sit: letters *before* the digits, or digits again *after* the
letters, is an identifier. Letters only at the end are a unit.

The cost of that rule, named rather than discovered later: `1920x1080` is a
digit-letter-digit alternation and both halves are dropped. Eight such shapes
exist across the whole corpus (`500x300`, `20500x300`, `22X43`).
"""

from __future__ import annotations

import pytest

from clauditseo.analysts.expert import ungrounded_figures
from clauditseo.numbers import extract_numbers, find_number, ungrounded_in_order
from clauditseo.reporting.checks import ungrounded_narrative_numbers

#: (name, text, the fragments that must not be numbers). Every text is the
#: shape of a real stored brief or document, and the tool it was measured in is
#: named, so a case that stops reproducing can be traced rather than deleted.
IDENTIFIER_SHAPES = [
    # `image-optimisation`: CDN filename hashes, the shape CQ-30 was raised on.
    ("cdn filename hash", "hero-69a4e135.webp, logo-c0ffee42.svg",
     {"0", "4", "42", "69", "135"}),
    # `content-gap`: gap ids G01 through G07.
    ("gap identifier", "Gaps G01, G02 and G07 remain open.", {"01", "02", "07"}),
    # `https-security`: a standards name with the digits welded on.
    ("standard name", "The x509 chain terminates at an unknown root.", {"509"}),
    # `eeat-analyst`: a fiscal year.
    ("fiscal year", "FY25 revenue is not published.", {"25"}),
    # Accessibility vocabulary, in every brief that scores the dimension.
    ("numeronym", "A11Y findings are folded into the site score.", {"11"}),
    # Heading levels, which the panel's own strip list already tries to remove.
    ("heading level", "Hierarchy violated: h3 then h2, with no h1.", {"3", "2", "1"}),
    # `site-architecture`: sequenced recommendation ids. The hyphenated tail of
    # `P1-2` is deliberately NOT claimed — see the limit below.
    ("recommendation id", "P1 is done; P2 and P3 are not.", {"1", "2", "3"}),
]

#: The limit, asserted rather than described, so it is a decision on the record
#: instead of a gap someone finds later and reads as a partial fix.
#:
#: A digit after a hyphen is left alone. `P1-2`'s `2` survives, and so does the
#: `01` in `mobile-viewport-01`. That shape cannot be rejected here because it
#: is the same shape as a date (`2026-08-22`) and a range (`120-160
#: characters`, which `figure_context`'s docstring names as the exact kind of
#: real figure the panel must keep). The panel already strips the lowercase
#: form — `ungrounded_figures` removes `[a-z]-\d{1,3}\b` — and that is where a
#: rule about hyphenated ids belongs, because only the panel knows it is
#: reading a report rather than arbitrary evidence.
HYPHEN_TAILS_ARE_NOT_CLAIMED = [
    ("hyphenated id tail", "P1-2 depends on P2-3.", {"2", "3"}),
    # `08`, not `8`: normalisation strips separators and trailing decimal
    # zeros, never a leading one. Unchanged by this round, and pinned here so
    # the next reader does not take it for a boundary effect.
    ("date", "Crawled 2026-08-22.", {"2026", "08", "22"}),
    ("range", "Shorten to 120-160 characters.", {"120", "160"}),
]

#: (name, text, the values that must survive). The other direction: a boundary
#: tight enough to reject identifiers must not reject a figure with a unit.
FIGURES_WITH_A_SUFFIX = [
    ("seconds", "LCP of 0.7s on mobile.", {"0.7"}),
    ("milliseconds", "TTFB is 300ms at the edge.", {"300"}),
    ("currency shorthand", "Loans from $5K to $7.5M.", {"5", "7.5"}),
    ("thousands shorthand", "A 145k line of credit.", {"145"}),
    ("css unit", "Containers exceeding 100vh.", {"100"}),
    ("status class", "No 3xx or 4xx URLs appear in the sitemap.", {"3", "4"}),
    ("thousands separator", "Images sum to 1,532,933 bytes (~1.50 MB).",
     {"1532933", "1.5"}),
    ("ordered list", "13. https://example.com/led-lighting/", {"13"}),
]


@pytest.mark.parametrize("name, text, fragments", IDENTIFIER_SHAPES,
                         ids=[c[0] for c in IDENTIFIER_SHAPES])
def test_no_identifier_fragment_is_extracted_as_a_number(name, text, fragments):
    found = extract_numbers(text)
    assert not (found & fragments), (
        f"{name}: {sorted(found & fragments)} came out of an identifier in "
        f"{text!r}")


@pytest.mark.parametrize("name, text, values", FIGURES_WITH_A_SUFFIX,
                         ids=[c[0] for c in FIGURES_WITH_A_SUFFIX])
def test_a_figure_with_a_unit_is_still_a_number(name, text, values):
    """The half that stops the boundary being paid for by real figures.

    Without this, deleting the regex entirely passes every assertion above.
    """
    found = extract_numbers(text)
    assert values <= found, (
        f"{name}: {sorted(values - found)} is a figure and stopped being one "
        f"in {text!r}")


@pytest.mark.parametrize("name, text, values", HYPHEN_TAILS_ARE_NOT_CLAIMED,
                         ids=[c[0] for c in HYPHEN_TAILS_ARE_NOT_CLAIMED])
def test_a_digit_after_a_hyphen_is_still_a_number(name, text, values):
    """The stated limit, pinned. If a later round wants `P1-2`'s tail gone it
    has to decide what happens to the date and the range in the same breath."""
    found = extract_numbers(text)
    assert values <= found, (
        f"{name}: {sorted(values - found)} stopped being a number in {text!r}, "
        f"which is a wider rule than this change claims")


def test_a_hashed_filename_in_the_evidence_does_not_ground_a_fabricated_figure():
    """Demonstrated failure class 3, at the gate rather than the panel.

    `ungrounded_figures` grounds a report's figures in `extract_numbers` over
    the evidence. Two hashed asset names supplied `135` and `42`, so a report
    claiming 135 broken links and a 42-second LCP passed the check that exists
    to catch exactly that. Run against the operator's own corpus at round 081.
    """
    evidence = "Assets: hero-69a4e135.webp, logo-c0ffee42.svg"
    report = "We found 135 broken links and an LCP of 42 seconds."
    assert ungrounded_figures(report, evidence) == ["135", "42"]


def test_the_narrative_gate_reads_the_same_rule():
    """`assert_report_honest`'s half, through its own entry point.

    Asserted separately from the panel because the two reach `clauditseo.numbers`
    by different callers, and a fix applied to one of them is the partial fix
    DISCIPLINE rule 3 is about.
    """
    evidence = "screenshot-1920a4e135.png"
    assert ungrounded_narrative_numbers("Crawled 135 pages.", evidence) == ["135"]


def test_the_locating_half_agrees_with_the_extracting_half():
    """One rule, both halves - the property CQ-30 has named since report 024.

    `find_number` must not locate a value inside an identifier that
    `extract_numbers` refuses to call a number, or the panel points the
    operator at a hash under a caution about a figure.
    """
    text = "Asset hero-69a4e135.webp weighs 135 KB."
    match = find_number(text, "135")
    assert match is not None, "the real figure became unlocatable"
    assert text[match.start():match.end()] == "135"
    assert match.start() > text.index("weighs"), (
        f"located the fragment inside the filename at {match.start()}, not the "
        f"figure")


def test_the_ordered_half_drops_identifier_fragments_too():
    """`ungrounded_in_order` walks the tokens itself rather than calling
    `extract_numbers`, so it is a third call site of the same regex and would
    keep the old behaviour if the boundary were applied in only one place."""
    text = "Gaps G01 and G07 remain; 135 pages are uncrawled."
    assert ungrounded_in_order(text, set()) == ["135"]


def test_no_shape_in_the_corpus_yields_an_identifier_fragment():
    """The invariant over the whole table.

    A boundary applied to `extract_numbers` and not to the token every caller
    shares passes some rows above and fails here.
    """
    text = "\n\n".join(shape[1] for shape in IDENTIFIER_SHAPES)
    fragments = set().union(*(shape[2] for shape in IDENTIFIER_SHAPES))
    found = extract_numbers(text)
    assert not (found & fragments), (
        f"{sorted(found & fragments)} survived across the concatenated corpus")
