"""A hold is a hold, once, on a page or on the site (item 271, row 5).

The Links brief wrote two holds both as `rows` (status HELD) and under
`not_assessable`. The rows were dropped and the holds kept, so the accounting
read "3 held · 3 dropped" over four facts. And holds were never held to the
page set: cards drew page "-" and "all service/location pages".
"""

from __future__ import annotations

import json

from clauditseo.analysts import contract

B = "https://t.fixture"
PAGES = [B + "/", B + "/contact/"]
CHECKS = ["LNK/redirect-chain", "LNK/anchor-entity", "LNK/link-suggestion"]


def _parse(rows=(), held=()):
    block = json.dumps({"part": "links", "rows": list(rows), "not_assessable": list(held)})
    return contract.parse("```json\n" + block + "\n```\n", CHECKS, PAGES)


def test_a_held_row_is_a_hold_and_its_twin_is_not_a_second():
    got = _parse(rows=[{"check": "LNK/anchor-entity", "page": B + "/contact/", "status": "HELD",
                        "severity": "LOW", "evidence": "", "note": "location entity unset"}],
                 held=[{"check": "LNK/anchor-entity", "page": "/contact/",
                        "needs": "location entity unset"}])
    assert not got.rows and not got.dropped, got.dropped
    assert [(n["check"], n["needs"]) for n in got.not_assessable] == [
        ("LNK/anchor-entity", "location entity unset")], got.not_assessable


def test_a_hold_on_no_page_is_a_hold_on_the_site():
    got = _parse(held=[{"check": "LNK/redirect-chain", "page": "-", "needs": "no redirect map"},
                       {"check": "LNK/anchor-entity", "page": "all service/location pages",
                        "needs": "location entities"}])
    by = {n["check"]: n for n in got.not_assessable}
    assert by["LNK/redirect-chain"]["page"] == "*"
    assert by["LNK/redirect-chain"]["needs"] == "no redirect map"
    assert by["LNK/anchor-entity"]["page"] == "*"
    assert by["LNK/anchor-entity"]["needs"] == "location entities (on all service/location pages)"
    # A hold on a page the run read keeps it.
    kept = _parse(held=[{"check": "LNK/anchor-entity", "page": "/contact/", "needs": "x"}])
    assert kept.not_assessable[0]["page"] == "/contact/"
