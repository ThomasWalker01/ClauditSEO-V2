"""Reconcile a report's carried findings against its predecessor — mechanically.

Relay 029, following relay 028's discovery: CQ-35, CQ-76 and WF-40 left the
tracked register between reports 038 and 039 with no disposition, and both
039 and 040's own accounting claimed "Nothing is disproved and nothing is
not-re-found" — false both times. Under opus this could not happen: report
038 individually re-verified all 124 carried findings with a stated method,
so the `/audit-fix` step 2 Carried-line diff was a redundancy that never
fired. Under sonnet it fired twice, by hand, at real session cost each time,
before this script existed.

A comparison, not a judgement. This finds the arithmetic gap between two ID
sets; it does not decide whether a drop was legitimate. Only the auditor
examining the current code can say that — fixed, disproved or not-re-found —
which is why this reports a disagreement rather than resolving one.

Usage:

    .venv\\Scripts\\python.exe scripts\\reconcile_findings.py

Exit 0 with "nothing to compare" if fewer than two reports exist yet. Exit 0
with "clean" if every prior finding is accounted for. Exit 1, naming every
unaccounted ID, otherwise. The two zero-exit messages are deliberately
different text — "nothing to compare" is not the same claim as "nothing
dropped", and this must not read as the second when it means the first.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ID = re.compile(r"\b(CQ|WF|UX|UI)-[0-9]+\b")
PILLAR_ROW = re.compile(r"^\| ((?:CQ|WF|UX|UI)-[0-9]+) \|", re.M)

#: Section boundaries within a report, matched by heading text rather than
#: position — a template that reorders sections still resolves correctly.
_PHASE1 = re.compile(r"^## PHASE 1", re.M)
_NOT_CARRIED = re.compile(r"^### Prior findings not carried forward", re.M)
_NEXT_SECTION = re.compile(r"^#{2,3} ", re.M)


def _section(text: str, start_pat: re.Pattern,
             end_pat: re.Pattern | None = None) -> str:
    m = start_pat.search(text)
    if not m:
        return ""
    start = m.end()
    m2 = (end_pat.search(text, start) if end_pat
          else _NEXT_SECTION.search(text, start))
    end = m2.start() if m2 else len(text)
    return text[start:end]


def pillar_finding_ids(report_text: str) -> set[str]:
    """Every finding ID with its own row in one of the four pillar tables
    (Code Quality / Workflow / UX / UI) — the report's live, currently-
    tracked findings.

    Bounded from `## PHASE 1` to `### Prior findings not carried forward`
    (or the next section heading if that one is absent), so a row inside
    Cross-pillar findings or Not assessable — which reuse the same `| ID |`
    shape for a different purpose — is not counted as a tracked finding. A
    plain grep over the whole document returns 124 rows for report 038;
    bounded this way it returns 117, which is what that report's own audit
    commit (`5133a5f`) states as `m`.
    """
    section = _section(report_text, _PHASE1, _NOT_CARRIED)
    return {m.group(1) for m in PILLAR_ROW.finditer(section)}


def not_carried_forward_ids(report_text: str) -> set[str]:
    """Every finding ID mentioned anywhere in the "Prior findings not
    carried forward" section — prose included, not only the `| ID |`
    column, because a folded-together disposition ("X and Y merged into Z")
    names an ID inside a sentence rather than as its own row.
    """
    section = _section(report_text, _NOT_CARRIED)
    return {m.group(0) for m in ID.finditer(section)}


def unaccounted_drops(previous_text: str, current_text: str) -> set[str]:
    """Findings tracked in the previous report that are neither still
    tracked in the current one nor named in its own "not carried forward"
    accounting.

    Anything returned here is a silent loss — the exact failure mode relay
    028 found by hand in reports 038 to 041, twice, on a report that itself
    claimed there was nothing to find. Deliberately not permissive: a
    finding also present in `DISPOSITIONS.md`'s aged cohort is not excused
    by that alone — CQ-35 was both, and treating cohort membership as a
    disposition would have missed exactly the drop this exists to catch.
    """
    dropped = pillar_finding_ids(previous_text) - pillar_finding_ids(current_text)
    return dropped - not_carried_forward_ids(current_text)


def _newest_reports(audits_dir: Path) -> list[Path]:
    return sorted(audits_dir.glob("[0-9][0-9][0-9]-*.md"))


def main(argv: list[str], audits_dir: Path | None = None) -> int:
    audits_dir = audits_dir or Path(__file__).resolve().parent.parent / "audits"
    reports = _newest_reports(audits_dir)
    if len(reports) < 2:
        print("nothing to compare — fewer than two reports exist")
        return 0

    previous, current = reports[-2], reports[-1]
    unaccounted = unaccounted_drops(previous.read_text(encoding="utf-8"),
                                     current.read_text(encoding="utf-8"))
    if unaccounted:
        print(f"UNACCOUNTED DROPS between {previous.name} and {current.name}:")
        for fid in sorted(unaccounted):
            print(f"  {fid}")
        return 1

    print(f"clean: every finding in {previous.name} is either still tracked "
          f"in {current.name} or named in its own not-carried-forward table")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
