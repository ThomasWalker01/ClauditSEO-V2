"""WF-48 — a strike must silence its own row whatever that table calls its
finding column.

`register_anchor_paths` collects the anchor of every **live** row in
`audits/DISPOSITIONS.md`, and `undispositioned` subtracts that set from the
paths the current report cites at ten reports or more. So a struck row still
counted live is a path the cohort gate reports as covered when nothing covers
it — "closing work adds noise to the gate, and the noise is what hides a real
miss", which is WF-48's own impact line, first raised at report 046 and carried
unchanged to report 130.

**The defect is a header lookup, not a strike parser.** The strike test ran
only where a header cell read exactly ``finding``. The register's
mechanically-derived tables head that column ``findings in report 044``,
``findings in report 119``, ``finding behind it`` and forty-two more spellings,
so on those rows the test never ran at all. Measured on the register at round
130: **172 anchor-bearing rows, of which only 56 sat under an exact
``finding``** — 116 rows across 44 spellings had no strike test.

**Every assertion here is made through `register_anchor_paths` itself**, never
against a private symbol the fix happens to add, so the module is free to
locate its columns however it likes and this guard still measures the thing
that matters. The regexes below read the *register* to build the population;
they are not a copy of the implementation.

**The hole is latent today and this guard is what makes it visible anyway.**
None of those 116 rows is currently struck, so the fix changes no output for
the register as it stands, and `test_the_live_set_is_unchanged_for_the_
register_as_it_stands` asserts exactly that rather than leaving it remembered.
What decides the question is the synthetic case, which strikes a
derived-table row and asks whether its path survives — the same probe report
046 ran by hand ("striking the derived-045 row for `clauditseo/modules/prf.py`
in memory and re-calling the function still reports the path as
dispositioned"). Run against the unfixed lookup, the two struck-row cases fail
naming every spelling; that is why they are written before the fix.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_anchors  # noqa: E402
from tests.private_register import needs_register

DISPOSITIONS = ROOT / "audits" / "DISPOSITIONS.md"

#: How this test reads the register's own tables. Deliberately not imported
#: from `check_anchors`: a guard that borrows the implementation's idea of
#: which column is which cannot notice the implementation getting it wrong.
_ANCHOR_HEADER = re.compile(r"^anchors?\b")
_FINDING_HEADER = re.compile(r"^findings?\b")

_STRUCK_PATH = "clauditseo/modules/prf.py"


def _register() -> str:
    return DISPOSITIONS.read_text(encoding="utf-8")


def _column(header: list[str], pattern: re.Pattern[str]) -> int | None:
    for i, cell in enumerate(header):
        if pattern.match(cell):
            return i
    return None


def _anchor_rows(text: str):
    """`(header, cells)` for every row of every table carrying an anchor column."""
    for header, cells in check_anchors._rows(text):
        at = _column(header, _ANCHOR_HEADER)
        if at is not None and at < len(cells):
            yield header, cells


def _finding_headers() -> list[str]:
    """The finding-column spelling of every anchor-bearing table, deduplicated.

    Read out of the register so a table shape added later is tested the day it
    is added, and so this module cannot pass by exercising a spelling that no
    longer occurs anywhere.
    """
    seen: dict[str, None] = {}
    for header, _cells in _anchor_rows(_register()):
        at = _column(header, _FINDING_HEADER)
        if at is not None:
            seen.setdefault(header[at], None)
    return list(seen)


def _one_table(finding_header: str, struck: bool) -> str:
    mark = "~~" if struck else ""
    return (
        f"| {finding_header} | anchor | rounds |\n"
        "| --- | --- | --- |\n"
        f"| {mark}WF-99{mark} | {_STRUCK_PATH}:21 | 12 |\n"
    )


# --------------------------------------------------------------------------
# The vacuity floor
# --------------------------------------------------------------------------

@needs_register
def test_the_register_still_uses_more_than_one_finding_column_spelling():
    """Without this the module keeps passing while testing nothing.

    Twenty is well under the 45 spellings measured at round 130 and well over
    the one spelling the old lookup handled.
    """
    headers = _finding_headers()
    assert len(headers) >= 20, (
        f"only {len(headers)} finding-column spellings found: {headers}")
    assert any(h != "finding" for h in headers), (
        "every spelling is the exact one the old lookup handled, so the "
        "struck-row cases below prove nothing")


@needs_register
def test_every_anchor_bearing_row_has_a_finding_column_at_all():
    """A row with no finding column has no strike test under any lookup.

    This is a property of the register rather than of the gate, and it is the
    premise the two cases below rest on: they can only speak for tables that
    have such a column.
    """
    unmatched = [header for header, _ in _anchor_rows(_register())
                 if _column(header, _FINDING_HEADER) is None]
    assert unmatched == [], (
        f"{len(unmatched)} anchor-bearing tables name no finding column: "
        f"{unmatched[:5]}")


# --------------------------------------------------------------------------
# The probe report 046 ran by hand
# --------------------------------------------------------------------------

@needs_register
def test_a_struck_row_is_dropped_whatever_its_finding_column_is_called():
    """One check per spelling the register actually uses.

    Not parametrised at collection time on purpose: the spellings come from a
    file, and a collection-time read that raised would remove these tests
    rather than fail them.
    """
    survived = []
    for finding_header in _finding_headers():
        paths = check_anchors.register_anchor_paths(
            _one_table(finding_header, struck=True))
        if _STRUCK_PATH in paths:
            survived.append(finding_header)
    assert survived == [], (
        f"{len(survived)} finding-column spellings still count a struck row "
        "as live, so the cohort gate reads their paths as covered when the "
        f"decision behind them is closed: {survived[:6]}")


@needs_register
def test_a_live_row_is_kept_whatever_its_finding_column_is_called():
    """The half that would catch an over-broad fix.

    A matcher that dropped every row it could not classify would make the
    case above pass by silencing the register entirely.
    """
    missing = []
    for finding_header in _finding_headers():
        paths = check_anchors.register_anchor_paths(
            _one_table(finding_header, struck=False))
        if _STRUCK_PATH not in paths:
            missing.append(finding_header)
    assert missing == [], (
        f"a live row's anchor was dropped under these spellings: {missing}")


def test_the_anchor_column_is_found_by_the_same_rule():
    """The sibling lookup, which has the identical shape and no defect yet.

    Every anchor column in the register at round 130 reads exactly `anchor`,
    so this fires on nothing there. It is here because the two lookups
    implement one rule — find a column by what it is called — and fixing one
    while leaving the other exact is the partial fix DISCIPLINE rule 3 names.
    """
    table = (
        "| finding | anchor (path) | rounds |\n"
        "| --- | --- | --- |\n"
        f"| WF-99 | {_STRUCK_PATH}:21 | 12 |\n"
    )
    assert _STRUCK_PATH in check_anchors.register_anchor_paths(table), (
        "an anchor column named anything but exactly `anchor` is skipped, so "
        "every decision in such a table is invisible to the cohort gate")


# --------------------------------------------------------------------------
# What the fix does and does not change for the register as it stands
# --------------------------------------------------------------------------

@needs_register
def test_the_live_set_is_unchanged_for_the_register_as_it_stands():
    """The honest statement of this fix's reach today: none.

    Every struck row in the register at round 130 sits under an exact
    `finding` header, so a widened lookup returns the same set the narrow one
    did. Asserting it keeps the claim checkable rather than remembered: the
    day a derived row is struck, this test skips with the reason, and the
    commit that struck it has to say what moved.
    """
    text = _register()
    struck_elsewhere = sorted({
        header[at] for header, cells in _anchor_rows(text)
        if (at := _column(header, _FINDING_HEADER)) is not None
        and at < len(cells) and "~~" in cells[at] and header[at] != "finding"
    })
    if struck_elsewhere:
        pytest.skip(
            f"the register now strikes rows under {struck_elsewhere}, so the "
            "widened lookup does change the live set — read the commit that "
            "struck them")

    narrow: set[str] = set()
    for header, cells in check_anchors._rows(text):
        if "anchor" not in header:
            continue
        anchor_at = header.index("anchor")
        if anchor_at >= len(cells):
            continue
        if "finding" in header:
            finding_at = header.index("finding")
            if finding_at < len(cells) and "~~" in cells[finding_at]:
                continue
        for match in check_anchors._PATHISH.finditer(cells[anchor_at]):
            narrow.add(match.group(0))
    narrow |= {Path(p).name for p in narrow}

    assert check_anchors.register_anchor_paths(text) == narrow, (
        "the widened lookup changed the live set for the register as it "
        "stands, which the round that widened it measured as no change")
