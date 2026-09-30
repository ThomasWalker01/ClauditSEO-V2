"""WF-47's committed half — the table that promises to name every register.

`.claude/skills/backlog-plan/SKILL.md` carries a section headed *Every register
the loop keeps, and whether this skill reads it*, and states its own purpose in
as many words:

    Twice a register has been added to the system and not to the list above —
    `FEATURES.md` at `12f93e9`, `DISPOSITIONS.md` here — and both times the
    omission was found by an auditor rather than by anyone maintaining the
    planner. This table exists so the third one is caught when it is added. **A
    register added to the loop is a row added here**, with the answer argued
    either way; a register absent from this table is the defect repeating.

Nothing enforced that. WF-47 (report 046, carried to report 130) named the
third omission — `data/server-starts.jsonl`, the register the *product* writes
on every start — and it was still missing eighty-four reports later. Deriving
the population from the tree found a fourth at the same time: `QUESTIONS.md`,
the register that holds every open operator decision, and the one register that
can change what a finding *means*.

**The population is derived, never listed.** A hand-written list of registers
is the same artefact as the table, checked against itself, which is how the
first three omissions survived. Root-level Markdown is the shape a register has
in this repository; the two exclusions below are named individually with the
reason, so adding a third is a visible decision rather than a quiet one.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from clauditseo.provenance import FILENAME as STARTS_FILENAME  # noqa: E402
from tests.private_register import needs_register

PLANNER = ROOT / ".claude" / "skills" / "backlog-plan" / "SKILL.md"

_TABLE_HEADING = "## Every register the loop keeps"

#: Root Markdown that records nothing the loop appends to. Both describe the
#: product to a reader; neither has entries, a status, or a round that writes
#: one. Named one at a time on purpose — a pattern here would let the next
#: register be excluded by accident.
_NOT_REGISTERS = {
    "README.md": "how to run the product",
    "ARCHITECTURE.md": "how the product is built",
}

#: Registers the loop keeps outside the repository root. `audits/NNN-*.md` is
#: not here: the reports are a series rather than a register, and the table
#: names the series itself.
_ELSEWHERE = (
    "audits/DISPOSITIONS.md",
    f"data/{STARTS_FILENAME}",
)


def _registers() -> list[str]:
    """Every register this repository keeps, derived from the tree."""
    root_md = sorted(p.name for p in ROOT.glob("*.md")
                     if p.name not in _NOT_REGISTERS)
    return root_md + list(_ELSEWHERE)


def _table() -> str:
    """The section's text, bounded at the next heading of the same level.

    Bounded because the file continues into prose that names registers in
    sentences, and a containment test over the whole document would be
    discharged by a mention — the defeat `register_anchor_paths` in
    `scripts/check_anchors.py` records under WF-45.
    """
    text = PLANNER.read_text(encoding="utf-8")
    start = text.index(_TABLE_HEADING)
    after = text.find("\n## ", start + 1)
    return text[start:] if after == -1 else text[start:after]


def _rows(section: str) -> list[list[str]]:
    out = []
    for line in section.split("\n"):
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", line)]
        if len(cells) > 2 and not set(cells[1]) <= set(" -:"):
            out.append(cells)
    return out


def test_the_planner_still_has_a_register_table_to_check():
    """Guards the collector.

    A heading renamed, or a table moved, would make every assertion below
    iterate nothing and pass — the check-that-cannot-fail shape this
    repository has now paid for six times.
    """
    assert PLANNER.is_file(), f"{PLANNER} is missing"
    assert _TABLE_HEADING in PLANNER.read_text(encoding="utf-8"), (
        f"{PLANNER.name} no longer carries a {_TABLE_HEADING!r} section")
    assert len(_rows(_table())) >= 10, (
        f"only {len(_rows(_table()))} rows found in the register table")


@needs_register
def test_the_derived_population_is_not_empty():
    """The other half of the same guard: the tree side.

    A glob that stopped matching would leave nothing to look for, and the
    assertion below would pass against a table with no rows at all.
    """
    found = _registers()
    assert len(found) >= 8, f"only {len(found)} registers derived: {found}"
    assert "QUESTIONS.md" in found and f"data/{STARTS_FILENAME}" in found, (
        f"the derivation lost a register it is known to reach: {found}")


def test_every_register_this_repository_keeps_has_a_row():
    """WF-47's own assertion.

    A register is present when its path appears in the row's first cell. The
    *answer* is deliberately not checked: the table's rule is that a register
    is named with the read/do-not-read decision argued either way, and which
    way it was argued is a judgement this cannot make.
    """
    section = _table()
    first_cells = [cells[1] for cells in _rows(section)]
    missing = [name for name in _registers()
               if not any(name in cell for cell in first_cells)]
    assert missing == [], (
        "the planner's register table promises that a register added to the "
        "loop is a row added there, and these are absent, so a plan can rest "
        f"on a register it never knew existed: {missing}")


def test_the_excluded_root_files_are_still_the_two_named_here():
    """The exclusions, held visible.

    If a genuine register is ever added under one of these names, or one of
    these is deleted, this fails and the exclusion has to be re-argued rather
    than inherited.
    """
    present = {name for name in _NOT_REGISTERS if (ROOT / name).is_file()}
    assert present == set(_NOT_REGISTERS), (
        "a file excluded from the register population no longer exists, so "
        "the exclusion is describing something that is not there: "
        f"{sorted(set(_NOT_REGISTERS) - present)}")
