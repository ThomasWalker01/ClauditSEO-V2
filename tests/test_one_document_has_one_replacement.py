"""CQ-199: the two doors that answer "what replaced this document" agree.

`reports.supersedes` is written on the **new** row, so a regeneration stays one
INSERT and never rewrites a row a client may already hold
(`0028_report_supersedes.sql`). Both screens need the other direction, and both
derive it — separately:

- `runs.client_reports()` folds the site's rows into a `replaced_by` dict,
  first writer wins, over a list the query ordered;
- `runs.client_report()` asks SQL directly, `ORDER BY ... LIMIT 1`.

Report 088 raised this as CQ-199 and it was carried unchanged through report
107: the two derivations ordered by different rules, so on a tie they named
**different** replacements for the same document. The first site's own comment
said the ambiguity *"is resolved here rather than left to row order"* and then
resolved it by a rule the site sixty lines below did not use.

**A tie is not hypothetical, which is why this is a guard and not a note.**
`created_at` is a whole-second ISO string, written by `repo.now_iso()`, and
report 088 counted nine adopted rows on `www.acme.com.au` already sharing a
date. Two presses inside one second, or two `POST /api/reports` calls naming
the same `supersedes`, is all it takes: the route accepts `supersedes` from any
caller and refuses only a missing or cross-site target
(`tests/test_a_regenerated_deliverable_records_what_it_replaced.py`).

**What is asserted, and why the equality clause is the finding.** The defect is
not that either answer is wrong in isolation — either row is a real
replacement. It is that the Deliverables table and the document screen can name
different ones for the same document, and an operator reading both cannot tell
which. So the first clause asserts the two agree; the second pins *which* row
they agree on, so a later edit cannot make them agree by breaking both the same
way; and the third reads the module source, so the two cannot drift apart again
without the shared name going with them.

Both derivations now take their order from one constant,
`runs._REPLACEMENT_ORDER`, which is the module docstring's own remedy for what
it calls *"two implementations of one rule drifting apart"*.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from clauditseo.persistence import repo, runs

# Reused for the reason the sibling supersedes guard gives: this is the one
# definition of "a database a report can actually be generated from".
from tests.test_reporting_g7 import db_with_runs  # noqa: F401

#: One second, shared by every row this file writes. The defect only exists on
#: a tie, so a fixture that let the clock separate the rows would pass against
#: the unfixed code and prove nothing.
SAME_SECOND = "2026-08-29T04:00:00+00:00"


def _site_of(conn: sqlite3.Connection, run_id: str) -> str:
    return conn.execute("SELECT site_id FROM audit_runs WHERE id=?",
                        (run_id,)).fetchone()["site_id"]


def _report(conn: sqlite3.Connection, site_id: str, out: Path,
            name: str, supersedes: str | None) -> str:
    """One `reports` row at `SAME_SECOND`, inserted in call order.

    Written directly rather than through `generate()` because `generate()`
    stamps `created_at` from the wall clock, and this file's whole subject is
    what happens when two rows carry the same stamp.
    """
    report_id = repo.create_id()
    path = out / name
    path.write_text(f"# {name}\n", encoding="utf-8")
    conn.execute(
        "INSERT INTO reports (id, site_id, run_ids, template, audience, path,"
        " created_at, supersedes) VALUES (?, ?, '[]', 'run', 'client', ?, ?, ?)",
        (report_id, site_id, str(path), SAME_SECOND, supersedes))
    conn.commit()
    return report_id


def _two_replacements(conn: sqlite3.Connection, tmp_path: Path,
                      run_id: str) -> tuple[str, str, str]:
    """An original and two rows superseding it, all stamped the same second."""
    site_id = _site_of(conn, run_id)
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    original = _report(conn, site_id, out, "original.md", None)
    first = _report(conn, site_id, out, "first-replacement.md", original)
    second = _report(conn, site_id, out, "second-replacement.md", original)
    return original, first, second


def test_the_table_and_the_document_name_the_same_replacement(
        db_with_runs, tmp_path):
    """The finding itself: one document, one answer, whichever door asks.

    Proven to fail first, per DISCIPLINE rule 1. Against HEAD before the fix
    the register answered with the *first*-inserted replacement (its list was
    ordered `created_at DESC` alone, so the tie fell to ascending rowid and
    first-writer-wins took it) and the document answered with the
    *second* (`ORDER BY created_at DESC, rowid DESC LIMIT 1`). Two doors, two
    answers, same document.
    """
    conn, run_ids = db_with_runs
    original, first, second = _two_replacements(conn, tmp_path, run_ids[0])
    site_id = _site_of(conn, run_ids[0])

    listed = [r for r in runs.client_reports(conn, site_id)
              if r["id"] == original]
    assert listed, "the original is missing from the register"
    from_table = listed[0]["superseded_by"]
    from_document = runs.client_report(conn, original)["superseded_by"]

    assert from_table == from_document, (
        "the Deliverables table and the document screen name different "
        f"replacements for one document: table says {str(from_table)[:8]}, "
        f"document says {str(from_document)[:8]} (first-inserted is "
        f"{first[:8]}, second is {second[:8]})")


def test_the_replacement_they_agree_on_is_the_later_row(db_with_runs,
                                                        tmp_path):
    """Which row wins, pinned so agreement cannot be reached by breaking both.

    The later row is the answer both sites already claimed to want — the
    register's comment says *"a document regenerated twice reports the newer
    replacement"*, and the document's query says `rowid DESC`. On a
    whole-second tie `rowid` is the only thing left that orders the two, and
    the later INSERT has the higher one.
    """
    conn, run_ids = db_with_runs
    original, first, second = _two_replacements(conn, tmp_path, run_ids[0])
    site_id = _site_of(conn, run_ids[0])

    listed = [r for r in runs.client_reports(conn, site_id)
              if r["id"] == original][0]
    assert listed["superseded_by"] == second, (
        "the register reports the earlier of two same-second replacements; "
        "its own comment promises the newer one")
    assert runs.client_report(conn, original)["superseded_by"] == second, (
        "the document screen reports the earlier of two same-second "
        "replacements")


def test_neither_derivation_carries_its_own_copy_of_the_order():
    """The drift guard, read from source.

    Equality on a fixture is satisfiable by two copies of one rule that happen
    to match today; CQ-199 is precisely two copies that stopped matching. So
    the shared name is asserted at both sites, and no `ORDER BY` over
    `reports` may spell the order out again.
    """
    source = Path(runs.__file__).read_text(encoding="utf-8")

    assert "_REPLACEMENT_ORDER" in source, (
        "the order that decides which row replaced a document is not bound to "
        "a name; CQ-199 was two unnamed copies of it drifting apart")
    uses = source.count("_REPLACEMENT_ORDER")
    assert uses >= 3, (
        "the shared order is defined but not used at both derivations "
        f"({uses} occurrences; expected the definition plus two call sites)")

    for site in ("client_reports", "client_report"):
        body = source.split(f"def {site}(", 1)[1].split("\ndef ", 1)[0]
        assert "_REPLACEMENT_ORDER" in body, (
            f"{site}() spells its own ordering out instead of taking the "
            "shared one, which is the shape CQ-199 named")
