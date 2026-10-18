"""CQ-230: a count whose population changed says so where the count is read.

`clauditseo/modules/onp.py`'s duplicate-title and duplicate-description checks
stopped counting a URL that is an alternate form of another crawled page — the
same page under a tracking query, declaring the other as canonical. That is
the right population. What was missing is any way for a reader to know it is
the population: the summary still says *"3 pages share the title …"* with no
word for which three, and the excluded members were recorded under
`evidence["canonical_aliases"]`, which was written at two sites and read at
none.

The cost is not cosmetic. A site that adds canonicals between two runs sees
the count fall, and a falling count in a client document reads as a fix. It is
the same defect class as a silent zero: a number that is right about its own
population and silent about which population that is.

**Both renderers, enumerated rather than taken from the report's list**
(DISCIPLINE rule 3). `_finding_line` prints a finding's own summary; so does
`_group_line` when a group holds exactly one finding; and a group of more than
one prints a page count over the same narrowed population, so the note is
summed across the group there. The negative clause below is what stops the
note appearing on findings that excluded nothing.
"""

from __future__ import annotations

from clauditseo.reporting import render


def _finding(**over) -> dict:
    f = {
        "severity": "Medium", "dimension": "ONP", "source": "deterministic",
        "model_id": None, "confidence": "high", "check_id": "title-duplicate",
        "fingerprint": "abc123",
        "summary": '3 pages share the title "Apply" — they compete for the '
                   "same query.",
        "recommendation": None,
        "evidence": {"paths": ["/a", "/b", "/c"],
                     "canonical_aliases": ["/b?utm_source=x", "/c?ref=y"]},
        "affected_urls": ["https://x.test/a", "https://x.test/b"],
    }
    f.update(over)
    return f


def _group(findings: list[dict], **over) -> dict:
    g = {
        "severity": "Medium", "dimension": "ONP", "source": "deterministic",
        "model_id": None, "confidence": "high", "check_id": "title-duplicate",
        "recommendation": None, "findings": findings,
        "pages": 3, "page_list": ["/a", "/b", "/c"],
    }
    g.update(over)
    return g


def test_a_finding_line_states_the_urls_its_count_excluded():
    line = render._finding_line(_finding(), "client")
    assert "Excludes 2" in line, (
        "the summary states a count taken over a narrowed population and says "
        f"nothing about the narrowing, so a later fall reads as a fix: {line}")
    assert "alternate URL forms" in line, line


def test_a_group_of_one_states_it_too_because_it_prints_the_summary():
    line = render._group_line(_group([_finding()]), "client")
    assert "Excludes 2" in line, (
        "a group of one prints its finding's summary verbatim and dropped the "
        f"frame that summary needs: {line}")


def test_a_group_of_several_sums_the_exclusions_across_it():
    other = _finding(
        summary="2 pages share the same meta description.",
        check_id="meta-desc-duplicate",
        evidence={"paths": ["/d", "/e"], "canonical_aliases": ["/e?utm=z"]})
    line = render._group_line(_group([_finding(), other], pages=5), "client")
    assert "Excludes 3" in line, (
        "the grouped headline counts pages over the same narrowed population "
        f"and states no frame for it: {line}")


def test_the_count_sits_on_a_line_the_honesty_gate_can_source():
    """Gate G7 is line-scoped: a digit must share its line with a `source:`.

    The summary's own "3 pages" has always been covered by the line's trailing
    provenance tag rather than by an inline `m()`, and this clause is inside
    the same sentence. Asserted rather than assumed, because a note that later
    moved onto a sub-line of its own would silently leave the gate's reach —
    and the failure would show up as a client document that cannot be
    generated at all, which is CQ-130's shape.
    """
    line = render._finding_line(_finding(), "client").splitlines()[0]
    assert "Excludes 2" in line and "source:" in line, (
        "the excluded-count figure is not on a line carrying a source tag, "
        f"so gate G7 will refuse the document that holds it: {line!r}")


def test_the_paths_are_internal_only():
    client = render._finding_line(_finding(), "client")
    internal = render._finding_line(_finding(), "internal")
    assert "/b?utm_source=x" not in client, (
        "the client document lists the excluded URLs; it is being told the "
        f"frame of a count, not handed a second list to act on: {client}")
    assert "/b?utm_source=x" in internal, (
        f"the internal document drops the paths it is entitled to: {internal}")


def test_a_finding_that_excluded_nothing_says_nothing():
    """The negative, so the note cannot spread to counts it is false about."""
    plain = _finding(evidence={"paths": ["/a", "/b", "/c"]})
    assert "Excludes" not in render._finding_line(plain, "internal")
    assert "Excludes" not in render._group_line(_group([plain]), "internal")
    missing = _finding(evidence=None)
    assert "Excludes" not in render._finding_line(missing, "internal")


def test_the_key_is_read_outside_the_module_that_writes_it():
    """The finding's own terms: two writes, one assertion, and no reader.

    Kept as a source-level clause and not only as the behavioural ones above,
    because the defect was never that the sentence was wrong — it was that
    nothing anywhere consumed the key, so the evidence existed and reached no
    one.
    """
    src = (render.__file__)
    with open(src, encoding="utf-8") as fh:
        assert "canonical_aliases" in fh.read(), (
            "the renderer no longer reads `canonical_aliases`; the key is "
            "back to being written at two sites and read at none")
