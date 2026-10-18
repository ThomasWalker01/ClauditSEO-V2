"""Structured data's rows are held to their own check (item 270, row 3).

On twenty22 an "Article without a modified date" row's evidence read
`dateModified=2026-08-15`; nine "Article without an author" rows' evidence
was "BlogPosting node has no @id property listed", which is not about an
author; and rows whose evidence was "same pattern" named nothing a reader
could check. Each is now dropped with its reason.
"""

from __future__ import annotations

import json

from clauditseo.analysts import contract

B = "https://t.fixture"
PAGES = [B + "/", B + "/blog/a/"]
CHECKS = ["ONP/schema-datemodified-missing", "ONP/schema-author-missing", "ONP/schema-sameas-missing"]


def _row(check, evidence):
    return {"check": check, "page": B + "/blog/a/", "status": "FAIL", "severity": "MEDIUM",
            "evidence": evidence, "replacement": "", "note": ""}


def _parse(*rows):
    block = json.dumps({"part": "schema", "rows": list(rows), "not_assessable": []})
    return contract.parse("```json\n" + block + "\n```\n", CHECKS, PAGES, rules=contract.Rules())


def test_a_row_its_own_evidence_refutes_is_dropped():
    got = _parse(_row("ONP/schema-datemodified-missing",
                      "BlogPosting dateModified=2026-08-15, later than the run date"))
    assert not got.rows and got.dropped[0]["reason"] == \
        "the row's own evidence shows dateModified present", got.dropped
    got = _parse(_row("ONP/schema-author-missing", "BlogPosting node has no @id property listed"))
    assert not got.rows and got.dropped[0]["reason"] == \
        "the row's evidence does not mention author", got.dropped
    got = _parse(_row("ONP/schema-sameas-missing", "same pattern"))
    assert not got.rows and "names no property or value" in got.dropped[0]["reason"]


def test_a_row_that_names_its_fault_stays():
    assert _parse(_row("ONP/schema-datemodified-missing", "BlogPosting has no dateModified")).rows
    assert _parse(_row("ONP/schema-author-missing", "BlogPosting carries no author")).rows
    assert _parse(_row("ONP/schema-sameas-missing", "Organization has no sameAs")).rows
