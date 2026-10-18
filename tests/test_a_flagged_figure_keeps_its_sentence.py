r"""Every figure the verification panel flags arrives with the sentence it came from.

CQ-30. The panel exists to say "spot-check these before quoting them to a
client", and `figure_context`'s own docstring records why a bare digit is
worse than no caution at all: shown without their sentence, standard
thresholds read as fabrications and train the operator to dismiss the control.

The panel had two definitions of "a number in this text" and they disagreed.
Verification extracts whole tokens through `clauditseo.numbers` and
**normalises** them — `1,532,933` becomes `1532933`, `1.50` becomes `1.5`.
Formatting then searched the prose for that normalised string behind
`(?<![\d.])…(?![\d.])`, which cannot match a separator-carrying token at all
and refuses any digit run with a `.` on either side. So verification flagged a
figure formatting could not find, and the operator was handed the digits alone.

Measured on the operator's database at round 080: **33 of 189 stored flagged
figures across 13 briefs** carried no context whatsoever — 17 lost to
normalisation and 16 to the boundary rule. The six shapes below are those two
causes as they actually occur in stored briefs, not invented ones.

The cases are a table rather than six functions because rule 3's warning
applies: a hard-coded list of three is how a partial fix passes. The invariant
is asserted over the whole table and over its concatenation, so a fix that
repairs one cause and not the other cannot go green.
"""

from __future__ import annotations

import pytest

from clauditseo.analysts.expert import (figure_context, ungrounded_figures,
                                        ungrounded_figure_details)

#: (name, prose, the value the panel flags, a phrase its sentence must carry).
#: Every prose body is the shape of a real stored brief — the tool that
#: produced each is named, so a case that stops reproducing can be traced back
#: to the brief rather than deleted as mysterious.
MEASURED_SHAPES = [
    # `image-optimisation`: normalisation drops the separators the prose keeps.
    ("thousands separator",
     "Images sum to approximately **1,532,933 bytes (~1.50 MB)** of confirmed weight.",
     "1532933", "bytes"),
    # The same sentence, the other half of normalisation: 1.50 -> 1.5.
    ("trailing decimal zero",
     "Images sum to approximately **1,532,933 bytes (~1.50 MB)** of confirmed weight.",
     "1.5", "MB"),
    # `eeat-analyst`: a currency figure written the way a client reads it.
    ("dollar amount",
     "Median advance $47,000; most common use of funds is equipment.",
     "47000", "Median advance"),
]


# --------------------------------------------------------------------------
# CQ-173. Three of the shapes above were the wrong way round.
#
# The table used to assert that an ordered-list index, a numbered heading and
# the digits of a standards reference are figures the panel MUST flag - the
# right assertion for the defect it was written against (all three reached the
# operator as bare digits) and the wrong one about the figures themselves.
# None of the three is a measurement. `14.` is the fourteenth item in a list,
# `## 12.` is a section number, and `164` is the second half of `E.164`.
#
# It is not a display nuisance. `_declares_a_figure` unions the brief's
# flagged values against the numbers in a finding's summary, so a value that
# is only structure makes the deliverable print
# `[TO CONFIRM: figure derived by the analyst, not measured]` beside a finding
# that quotes no derived number. Renderer 1.23.0 did exactly that to
# `local-signals/nap-inconsistent` in the client document generated on
# 22 August 2026, on the strength of `164` alone. A caveat that fires without
# cause costs more than one that fails to fire: it teaches the reader to
# discount the one mark the product uses to separate measured from derived.
#
# So the three move here and the assertion inverts. Each prose body keeps a
# real measurement on the same line, and the test asserts BOTH directions -
# the structure number is not flagged AND the measurement beside it still is.
# Without the second half, masking the whole line would pass.
# --------------------------------------------------------------------------

#: (name, prose, the structural number that must NOT be flagged, a real
#: measurement in the same prose that must still be).
STRUCTURE_SHAPES = [
    # `js-rendering`: nine bare digits, every one an ordered-list index.
    ("ordered list numbering",
     "13. `https://example.com/led-lighting/` - 47 internal links\n"
     "14. `https://example.com/heat-pump/` - 31 internal links\n",
     "14", "31"),
    # `content-brief` and `site-architecture`: a numbered section heading.
    ("numbered heading",
     "## 12. IMPLEMENTATION SEQUENCE\n\nSequence the remediation across 18 pages.",
     "12", "18"),
    # `entity-graph`: a standards reference, where the `.` precedes the digits.
    ("standard reference",
     'The `tel` value is `"+61130092"` - an E.164 string, and 23 listings repeat it.',
     "164", "23"),
]


@pytest.mark.parametrize("name, prose, structural, measured",
                         STRUCTURE_SHAPES,
                         ids=[c[0] for c in STRUCTURE_SHAPES])
def test_markdown_structure_is_not_a_figure_the_operator_must_verify(
        name, prose, structural, measured):
    flagged = ungrounded_figures(prose, "")
    assert structural not in flagged, (
        f"{name}: {structural!r} is structure, not a measurement, and the "
        f"panel asks the operator to verify it. Flagged: {flagged}")
    # The other direction, so a mask that swallowed the line would fail here.
    assert measured in flagged, (
        f"{name}: masking the structure also blinded the extractor to "
        f"{measured!r}, which is a real figure on the same line. "
        f"Flagged: {flagged}")


def test_the_structural_shapes_reach_the_panel_the_way_the_screen_does():
    """Through `ungrounded_figure_details`, not only `ungrounded_figures`.

    The two are separate entry points and only the second is what the Brief
    panel and `record_expert_findings` call. CQ-171 is the standing proof that
    they can disagree - for several rounds one masked and the other did not -
    so the invariant is asserted at both rather than at the owner alone.
    """
    prose = "\n\n".join(shape[1] for shape in STRUCTURE_SHAPES)
    details, _withheld, _uncapped = ungrounded_figure_details(prose, [], "")
    flagged = [d["value"] for d in details]
    assert flagged, "nothing was flagged, so the invariant was not exercised"
    structural = [s[2] for s in STRUCTURE_SHAPES]
    assert [v for v in flagged if v in structural] == [], (
        f"the panel asks the operator to verify structure: {flagged}")


@pytest.mark.parametrize("name, prose, value, phrase",
                         MEASURED_SHAPES,
                         ids=[c[0] for c in MEASURED_SHAPES])
def test_each_measured_shape_reaches_the_panel_with_its_sentence(name, prose, value, phrase):
    details, _withheld, _uncapped = ungrounded_figure_details(prose, [], "")
    flagged = [d["value"] for d in details]
    # If this fails the case has stopped exercising the defect — the figure is
    # no longer flagged, so its missing context proves nothing. Say that
    # rather than letting the assertion below pass vacuously.
    assert value in flagged, (
        f"{name}: {value!r} is no longer flagged, so this case no longer "
        f"exercises the defect. Flagged: {flagged}")
    context = next(d["context"] for d in details if d["value"] == value)
    assert context.strip(), f"{name}: the panel offers {value!r} as a bare digit"
    assert phrase in context, (
        f"{name}: {value!r} was given a sentence, but not the one it came "
        f"from — expected {phrase!r} in {context!r}")


def test_no_shape_in_the_corpus_produces_a_figure_without_a_sentence():
    """The invariant over the whole table, not one row of it.

    A fix that repairs normalisation and leaves the boundary rule, or the
    reverse, passes half the cases above and fails here.
    """
    prose = "\n\n".join(shape[1] for shape in MEASURED_SHAPES + STRUCTURE_SHAPES)
    details, _withheld, _uncapped = ungrounded_figure_details(prose, [], "")
    assert details, "nothing was flagged, so the invariant was not exercised"
    bare = [d["value"] for d in details if not (d["context"] or "").strip()]
    assert bare == [], (
        f"{len(bare)} of {len(details)} flagged figures reached the panel as "
        f"bare digits: {bare}")


def test_verification_and_context_agree_on_what_a_number_is():
    """The finding itself, stated as the property rather than the symptom.

    Whatever the extractor is willing to call a figure, the locator must be
    able to find. Asserted across the corpus so it cannot be satisfied by the
    six values the panel test names, and asserted through the two public
    functions so it pins the property rather than the shape of the fix.
    """
    prose = "\n\n".join(shape[1] for shape in MEASURED_SHAPES + STRUCTURE_SHAPES)
    flagged = ungrounded_figures(prose, "")
    assert flagged, "nothing was flagged, so the invariant was not exercised"
    unlocatable = [v for v in flagged if not figure_context(prose, v).strip()]
    assert unlocatable == [], (
        f"verification flagged {unlocatable} that the locator cannot find")


def test_a_value_the_text_does_not_hold_still_has_no_sentence():
    """The other half: sharing one rule must not make everything match.

    Without this, returning the whole report for any value would pass every
    assertion above.
    """
    prose = "Images sum to approximately **1,532,933 bytes (~1.50 MB)**."
    assert figure_context(prose, "99999") == ""


def test_the_sentence_is_the_one_the_figure_sits_on_not_the_first_that_matches():
    """`1.5` occurs twice; the panel must show the occurrence, not a scan
    that stopped at the first digit run it could parse."""
    prose = "Budget is 1.5 hours.\n\nImages weigh ~1.50 MB after conversion."
    assert "hours" in figure_context(prose, "1.5")


def test_the_sentence_is_not_a_fragment_of_a_longer_number():
    """`numbers.py` fixed this for extraction and left it in the locator.

    Its module docstring records why extraction reads whole tokens: a
    fabricated `43` passed because `1043` appeared in a hash. The locating
    half kept the substring behaviour, because `(?<![\d.])388(?![\d.])` is
    satisfied by the `,` after `388` in `388,517`. So the panel could point
    the operator at the prefix of a number that is grounded, under a caution
    about a different figure entirely. Sharing the owner closes both halves at
    once, which is the point of the change rather than a side effect of it.

    Seen in the operator's `image-optimisation` brief at round 080.
    """
    prose = ("| 29 | Blog hero | PNG | 388,517 B |\n"
             "\n"
             "Compression could drop #29 to under 388 KB.")
    assert figure_context(prose, "388") == "Compression could drop #29 to under 388 KB."
    # And the whole token is still findable under its own normalised value.
    assert "Blog hero" in figure_context(prose, "388517")


# --------------------------------------------------------------------------
# CQ-171: the panel decided which figures to flag from one text and found
# their sentences in another.
#
# `ungrounded_figures` blinds itself to vocabulary before extracting — caveat
# blocks, dates, times, standards references, heading levels — and
# `ungrounded_figure_details` then handed `figure_context` the UNSTRIPPED
# scan. So a figure visible only because a `[TO CONFIRM: …]` block was
# discarded could be shown the sentence inside that very block. Measured
# read-only over the operator's corpus at report 081: 3 of 189 stored flagged
# figures have their first occurrence inside a caveat block.
#
# **Report 081's item 3 said "strip once and pass the stripped text to both",
# and that is not what landed — recorded here so it is not re-attempted.**
# Stripping fixes the location and mangles the quotation: measured on the four
# shapes below, it renders "We measured 47 broken links on  across the site."
# and "Contrast fails  on 12 templates." The panel's whole reason for showing
# a sentence, per `figure_context`'s own docstring, is that a bare digit reads
# as a fabrication — and a sentence with holes punched in it is a quotation
# the report never contained. So the vocabulary is MASKED to same-length
# spaces rather than removed: the extractor still cannot see it, offsets are
# preserved, and the sentence displayed is the one on disk.
# --------------------------------------------------------------------------

#: (name, prose, value, phrase the sentence must carry, phrase it must NOT).
VOCABULARY_SHAPES = [
    ("a caveat block supplies the sentence",
     "[TO CONFIRM: the sitemap index listed 253 URLs, unverified]\n"
     "The crawl found 253 orphan pages under /blog/.",
     "253", "orphan pages", "TO CONFIRM"),
    ("a date on the claim line survives in the quotation",
     "[TO CONFIRM: 2026-08-14 baseline showed 47 issues]\n"
     "We measured 47 broken links on 2026-08-14 across the site.",
     "47", "2026-08-14", "TO CONFIRM"),
    ("a heading level survives in the quotation",
     "The h2 -> h4 skip affects 19 pages, every one a blog post.",
     "19", "h2 -> h4", "  "),
    ("a standards reference survives in the quotation",
     "Contrast fails WCAG 1.4.3 on 12 templates in the theme.",
     "12", "WCAG 1.4.3", "  "),
]


@pytest.mark.parametrize("name, prose, value, must, must_not",
                         VOCABULARY_SHAPES,
                         ids=[c[0] for c in VOCABULARY_SHAPES])
def test_no_figure_is_given_a_sentence_from_text_the_extractor_discarded(
        name, prose, value, must, must_not):
    details, _withheld, _uncapped = ungrounded_figure_details(prose, [], "")
    flagged = [d["value"] for d in details]
    assert value in flagged, (
        f"{name}: {value!r} is no longer flagged, so this case no longer "
        f"exercises the defect. Flagged: {flagged}")
    context = next(d["context"] for d in details if d["value"] == value)
    assert must in context, (
        f"{name}: expected {must!r} in the sentence shown for {value!r}, "
        f"got {context!r}")
    assert must_not not in context, (
        f"{name}: the sentence shown for {value!r} came from text the "
        f"extractor discarded, or has a hole where that text was — "
        f"{must_not!r} in {context!r}")


def test_masking_does_not_join_two_numbers_into_one():
    """Why same-length spaces rather than deletion, in the extraction half.

    Removing a span closes the gap, so text on either side becomes adjacent
    and two separate digit runs can be read as one figure that appears nowhere
    in the report. `numbers.py` exists because a fabricated `43` passed on a
    `1043` in a hash; a stripper that manufactures `1234` out of `12` and `34`
    is that same class, introduced by the fix for a different one.
    """
    prose = "Sections 12[TO CONFIRM: unverified]34 were reviewed."
    assert "1234" not in ungrounded_figures(prose, "")
