"""Item 221 (URLs, change 2): a free URL check is the sweep's.

Every free URL check is a string function of a URL the sweep already read. On
twenty22 T3 the URLs brief still filed its own rows on them: a `url-depth`
card saying "4 pages exceed depth-3" where the sweep counted 11, two
`url-length` rows on paths under the bound, and a hold on
`url-parameter-unclassified` - "not assessable" - over a check that ran and
measured zero parameters, which also kept it out of the clean line.

The contract now drops, with a reason, a URLs-brief row on a free check the
sweep did not raise on that page, and a hold on a free check the sweep
measured. A row the sweep did raise stays (it merges with the sweep's card),
and the brief's analysis checks are untouched.
"""

from __future__ import annotations

import json

from clauditseo.analysts import contract

BASE = "https://t.fixture"
PAGES = [BASE + "/", BASE + "/a/b/c/d/", BASE + "/short/"]
CHECKS = ["TEC/url-depth", "TEC/url-length", "TEC/url-parameter-unclassified",
          "TEC/url-slug-not-descriptive"]


def _row(check, page, **extra):
    return {"check": check, "page": page, "status": "WARN", "severity": "LOW",
            "evidence": "x", "replacement": "keep", "note": "", **extra}


def _parse(rows, held=(), part="urls", measured=("TEC",)):
    block = json.dumps({"part": part, "rows": rows, "not_assessable": list(held)})
    rules = contract.Rules(sweep_raised={"url-depth": {"/a/b/c/d"}},
                           sweep_measured=set(measured))
    return contract.parse("```json\n" + block + "\n```\n", CHECKS, PAGES, rules=rules)


def test_a_free_row_the_sweep_did_not_raise_is_dropped_with_its_reason():
    got = _parse([_row("TEC/url-length", "/short/")])
    assert got.rows == [], got.rows
    assert [d["reason"] for d in got.dropped] == [
        "TEC/url-length is the automatic checks', and the automatic checks did not raise it on /short"], got.dropped


def test_a_free_row_the_sweep_raised_on_that_page_stands():
    got = _parse([_row("TEC/url-depth", "/a/b/c/d/")])
    assert [r.check for r in got.rows] == ["TEC/url-depth"], got.dropped


def test_a_template_row_stands_only_beside_a_sweep_that_raised_the_check():
    got = _parse([_row("TEC/url-depth", None, url="/a/*/", group="template:deep"),
                  _row("TEC/url-length", None, url="/x/*/", group="template:long")])
    assert [r.check for r in got.rows] == ["TEC/url-depth"], (got.rows, got.dropped)


def test_a_hold_on_a_measured_free_check_is_not_a_hold():
    got = _parse([], held=[{"check": "TEC/url-parameter-unclassified", "page": "*",
                            "needs": "parameter variants in the crawl"},
                           {"check": "TEC/url-slug-not-descriptive", "page": "/short/",
                            "needs": "the page triple"}])
    assert [n["check"] for n in got.not_assessable] == ["TEC/url-slug-not-descriptive"], \
        got.not_assessable
    assert [d["reason"] for d in got.dropped] == [
        "a hold on a free check the automatic checks measured"], got.dropped


def test_an_analysis_check_is_the_briefs():
    got = _parse([_row("TEC/url-slug-not-descriptive", "/short/")])
    assert [r.check for r in got.rows] == ["TEC/url-slug-not-descriptive"], got.dropped


def test_nothing_changes_where_the_sweep_did_not_measure_or_the_part_is_another():
    unmeasured = _parse([_row("TEC/url-length", "/short/")], measured=())
    assert [r.check for r in unmeasured.rows] == ["TEC/url-length"], unmeasured.dropped
    other = _parse([_row("TEC/url-length", "/short/")], part="speed")
    assert [r.check for r in other.rows] == ["TEC/url-length"], other.dropped
