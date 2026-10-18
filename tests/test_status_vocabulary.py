"""`status='complete'` meant two different things, and both were spelled the same.

Adding `blocked` made the ambiguity visible: nineteen query sites compared the
literal, four were updated to include the new status and fifteen were not, so
one column meant "this run produced a score" in some queries and "an audit
happened" in others depending on which one a screen called. Home showed a
stale score and flagged a site Overdue while the scheduler declined to run it;
the assistant denied any audit had run while answering questions about that
audit's findings.

Two concepts, two names, and no query spelling either one itself:

  SCORED_STATUSES   the run produced a score to compare — trends, composites,
                    deltas, "vs previous", and anything reading fetched pages.
  AUDITED_STATUSES  an audit happened — scheduling, current_state, run lists,
                    deliverable and analysis staleness.

A blocked run is the second and not the first. It refused-crawl evidence is
real history; its composite rests on robots.txt alone.
"""

from __future__ import annotations

import pathlib
import re

from clauditseo.persistence import runs

#: The module that owns the vocabulary: it defines the constants, decides a
#: run's terminal status and writes it. The literal belongs here and nowhere
#: else.
OWNER = "clauditseo/persistence/runs.py"

#: Quoted `complete` in any form — SQL comparison, SQL IN-list, or a Python
#: equality against a row's status.
LITERAL = re.compile(r"""['"]complete['"]""")


def test_the_two_concepts_are_distinct_and_named():
    assert runs.SCORED_STATUSES == ("complete",)
    assert runs.AUDITED_STATUSES == ("complete", "blocked")
    assert set(runs.SCORED_STATUSES) < set(runs.AUDITED_STATUSES), \
        "every scored run is an audit that happened; the reverse does not hold"


def test_no_query_spells_the_status_literal_itself():
    """Enumerated from source, not from a list kept by hand — the list by hand
    is how four sites were updated and fifteen were missed."""
    offenders = []
    for path in sorted(pathlib.Path("clauditseo").rglob("*.py")):
        if path.as_posix() == OWNER:
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            # Prose may name the status — the ENGINE_VERSION note explains what
            # 'complete' meant at 0.6.0, and that sentence is the record. Only
            # code that compares it is the defect.
            if line.lstrip().startswith("#"):
                continue
            if LITERAL.search(line):
                offenders.append(f"{path.as_posix()}:{i}  {line.strip()[:72]}")
    assert not offenders, (
        "these compare the status literal instead of naming a concept "
        f"(SCORED_STATUSES / AUDITED_STATUSES in {OWNER}):\n  "
        + "\n  ".join(offenders))


def test_the_sql_helper_builds_a_clause_for_each_concept():
    assert runs.status_in(runs.SCORED_STATUSES) == "status IN ('complete')"
    assert runs.status_in(runs.AUDITED_STATUSES) == "status IN ('complete', 'blocked')"
    assert runs.status_in(runs.AUDITED_STATUSES, "a.status") == \
        "a.status IN ('complete', 'blocked')"
