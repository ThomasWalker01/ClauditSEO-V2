"""What an analysis returned, kept, held and dropped is said, and said plainly
(items 209, 210, 211 - the contract and server halves).

**209.** "N rows dropped — see report" linked nothing on every part with an
analysis; the AI surface run returned 29 rows, kept 10, and the reasons for
19 were stored and shown nowhere. And a kept Speed row whose Change read "see
/<slug>/ article-like template row" - a pointer at a row the contract had
dropped - was offered with `copy change`.

**210.** "Analysis summary" was the assessment's first three sentences printed
at data weight under the table. It was written before the contract kept,
merged, held and dropped rows, so it described another set, and it cut
Speed's summary at "(e.g." on the full stop in "e.g.". The whole section now
travels as the model's words, for a disclosure.

**211.** A hold's reason was a prompt variable ("LOCATION_PAGES"), a pass
("nothing further to assess"), or attached to no check at all.
"""

from __future__ import annotations

import json

from clauditseo.analysts import contract
from clauditseo.persistence.runs import brief_assessment

BASE = "https://t.fixture"
PAGES = [BASE + "/", BASE + "/a/", BASE + "/b/"]


def _parse(block: dict, checks):
    return contract.parse("```json\n" + json.dumps(block) + "\n```\n", checks, PAGES,
                          rules=contract.Rules())


# --- 209 -----------------------------------------------------------------------

def test_a_change_that_only_points_at_another_row_is_held_not_copyable():
    got = _parse({"rows": [{"check": "PRF/lcp-cause", "page": "/a/", "status": "FAIL",
                            "severity": "MEDIUM", "evidence": "x",
                            "replacement": "see /<slug>/ article-like template row"}]},
                 ["PRF/lcp-cause"])
    assert not got.rows, f"a pointer was kept as a change to copy: {got.rows}"
    assert any(n["check"] == "PRF/lcp-cause" for n in got.not_assessable), got.not_assessable


# --- 210 -----------------------------------------------------------------------

REPORT = """## Speed — assessment

Two templates carry the cost (e.g. the /seo/ pages). The logo is not the LCP.

### Patterns

- `/seo/<slug>/`: render-blocking CSS.

## Replacement copy

| a | b |
"""


def test_the_assessment_travels_whole_and_as_markdown():
    got = brief_assessment(REPORT)
    assert got is not None
    assert "(e.g. the /seo/ pages)" in got, "the section was cut at the full stop in e.g."
    assert "### Patterns" in got and "`/seo/<slug>/`" in got, (
        "the sections the brief exists to produce were cut off")
    assert "Replacement copy" not in got, "the next section at the same level leaked in"


def test_no_assessment_heading_is_no_prose():
    assert brief_assessment(None) is None
    assert brief_assessment("### Replacement copy\nNothing.") is None


# --- 211 -----------------------------------------------------------------------

def _holds(entries):
    parsed = contract.Parsed(status=contract.READ, not_assessable=entries)
    return contract.clean_holds(parsed)


def test_a_variable_name_as_a_reason_is_said_as_words():
    got = _holds([{"check": "HDG/h3-geo-map", "page": "/a/", "needs": "LOCATION_PAGES"},
                  {"check": "HDG/h3-sub-service", "page": "/a/", "needs": "SUB_SERVICES"}])
    assert [n["needs"] for n in got.not_assessable] == ["location pages", "sub-services"]


def test_a_hold_with_no_check_is_dropped_with_a_reason():
    got = _holds([{"check": "", "page": "/a/", "needs": "authors"}])
    assert got.not_assessable == []
    assert got.dropped and "no check named" in got.dropped[0]["reason"]


def test_a_pass_filed_as_a_hold_is_no_hold_and_is_counted():
    got = _holds([{"check": "IDX/noindex-intent", "page": "/b/",
                   "needs": "no conflicting forms observed; nothing further to assess"}])
    assert got.not_assessable == [], "a pass is shown as something waiting on an input"
    # The channel (20260924-0220-211): removed, but counted, so the page's
    # accounting of what the analysis returned still sums.
    assert [d["reason"] for d in got.dropped] == ["a pass, not a hold"], got.dropped


def test_a_reason_that_names_a_missing_input_is_a_hold_whatever_else_it_says():
    got = _holds([{"check": "IMG/old-format", "page": "/a/",
                   "needs": "PLATFORM not set; nothing further to assess"},
                  {"check": "IDX/noindex-intent", "page": "/b/",
                   "needs": "nothing further to assess without the intended-noindex list"}])
    assert len(got.not_assessable) == 2, got.not_assessable
    assert got.dropped == [], got.dropped


def test_a_reason_ends_once():
    got = _holds([{"check": "CNT/eeat-author", "page": "/a/", "needs": "authors."}])
    assert got.not_assessable[0]["needs"] == "authors"


def test_cleaning_twice_changes_nothing():
    """A re-parse runs it again over what it already cleaned."""
    first = _holds([{"check": "HDG/h3-geo-map", "page": "/a/", "needs": "LOCATION_PAGES"}])
    again = contract.clean_holds(first)
    assert again.not_assessable == [{"check": "HDG/h3-geo-map", "page": "/a/",
                                     "needs": "location pages"}]
