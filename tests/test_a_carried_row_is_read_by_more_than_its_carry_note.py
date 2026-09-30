"""WF-96 — the re-read surface must print something there is a judgement in.

`--context` exists because an anchor resolving is not evidence the row still
describes what is there. Its founding case: `UX-09` was *"the scope line tags
three figures through `m()` in one sentence"*, `ca8c02c` repaired that on
20 August 2026, and twenty-eight consecutive reports carried the row anyway,
at High, counted in every `high:` line the loop reads.

The flag was built to catch exactly that and could not have, because of what
it printed. `context_lines` labels each row with `_claim(cells[2])` — the
first sentence of the **Finding** cell — and for a carried row this board's
house style opens that cell with a *carry note*: an account of whether the
anchor moved since the last report, not of what the finding says. Measured on
report 131 at round 131: of the 176 rows `--context` emits, **172 lead with a
carry note** — 97%, including one of the report's two Highs. On UX-09's own
row in report 043, three days after the repair, the line `--context` printed
was:

    UX-09 (High) — Carried, unchanged bytes.

beside a line of `render.py`. Nothing about `m()`, nothing about the scope
line, nothing a reader could hold against the source. The row's **Impact**
cell in that same report said *"The line written to make the document honest
is its least readable sentence"* — a statement about the code that a reader
can check. It was on the row the whole time and the tool did not print it.

So the repair is not a matcher and decides nothing: the row's stated
consequence is printed beside its lead sentence. Round 129 measured two
candidate semantic matchers for the sibling source-comment problem and
rejected both as dominated by false positives, and `context_lines`' own
docstring refuses to guess whether a sentence still describes a function.
Printing one more cell the row already carries adds no judgement — it restores
the one the flag's name promises.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUDITS = ROOT / "audits"
sys.path.insert(0, str(ROOT / "scripts"))

import check_anchors as ca  # noqa: E402
from tests.private_register import needs_register

#: The board's column order — `| ID | Finding | Severity | Evidence | Impact |`
#: — so the consequence sits one past the evidence column the resolver reads.
IMPACT_COLUMN = ca._EVIDENCE_COLUMN + 1

CELL = re.compile(r"(?<!\\)\|")

#: A floor, not a rule. Report 131 emits 176 rows; a collector that silently
#: stopped matching would otherwise pass this file by finding nothing, which
#: is the vacuity `tests/test_loop_instructions.py` holds every derived
#: population to.
ROWS_FLOOR = 50


def _newest_report() -> Path:
    return ca.reports(AUDITS)[-1]


def _rows(text: str):
    """Every row `context_lines` emits, as `(fid, cells)` — the same three
    conditions it applies, in the same order, so the population this file
    asserts over cannot drift from the population it prints."""
    in_table = False
    for line in text.split("\n"):
        if line.startswith(ca._PILLAR_HEADER):
            in_table = True
            continue
        if not in_table:
            continue
        if not line.startswith("|"):
            in_table = False
            continue
        cells = CELL.split(line)
        if len(cells) <= ca._EVIDENCE_COLUMN:
            continue
        fid = cells[1].strip()
        if not ca._FINDING_ID.match(fid):
            continue
        if not ca.anchors(cells[ca._EVIDENCE_COLUMN]):
            continue
        yield fid, cells


@needs_register
def test_every_row_the_surface_prints_carries_the_consequence_it_states():
    """DISCIPLINE rule 1's failing half: run against the tree before the fix,
    `context_lines` emits no consequence line for any row, so this names all
    176 of them rather than passing vacuously."""
    report = _newest_report()
    text = report.read_text(encoding="utf-8")
    shown = "\n".join(ca.context_lines(text, ROOT))

    expected = 0
    missing = []
    for fid, cells in _rows(text):
        impact = ca._claim(cells[IMPACT_COLUMN]) if len(
            cells) > IMPACT_COLUMN else ""
        if not impact:
            continue
        expected += 1
        if f"consequence: {impact}" not in shown:
            missing.append(f"{fid} — {impact[:80]}")

    assert expected >= ROWS_FLOOR, (
        f"only {expected} rows of {report.name} carry a consequence the "
        f"surface could print; the collector has stopped matching the "
        f"board's table shape and this guard would pass on nothing")
    assert not missing, (
        f"{len(missing)} of {expected} rows in {report.name} print no "
        f"consequence, so the surface shows a carry note and nothing to hold "
        f"it against:\n  " + "\n  ".join(missing[:20]))


@needs_register
def test_the_founding_case_is_shown_something_a_reader_could_have_judged():
    """The measured case, pinned to the report it happened in.

    `audits/043-2026-08-18.md` is a committed record and does not change, so
    this asserts on real data rather than a constructed corpus: UX-09's lead
    sentence there is a carry note, and the row still carried a consequence
    the flag never printed. If `context_lines` ever goes back to labelling a
    row with its lead sentence alone, this fails on the exact row the flag
    was built for.
    """
    report = AUDITS / "043-2026-08-18.md"
    text = report.read_text(encoding="utf-8")
    shown = "\n".join(ca.context_lines(text, ROOT))

    rows = {fid: cells for fid, cells in _rows(text)}
    assert "UX-09" in rows, (
        "UX-09 is no longer emitted from report 043, so this guard is "
        "watching nothing; the founding case must stay reachable")

    cells = rows["UX-09"]
    lead = ca._claim(cells[2])
    consequence = ca._claim(cells[IMPACT_COLUMN])

    assert lead.lower().startswith("carried"), (
        f"report 043's UX-09 no longer leads with a carry note ({lead!r}), "
        f"so this row no longer demonstrates the defect")
    assert consequence and consequence != lead, (
        "the row carries no consequence distinct from its carry note, so "
        "there was nothing for the surface to have printed")
    assert f"UX-09 (High) — {lead}" in shown, (
        "the lead sentence is still the row's label and should stay — the "
        "repair adds to the surface rather than replacing what it showed")
    assert f"consequence: {consequence}" in shown, (
        f"UX-09's block prints its carry note {lead!r} and not the "
        f"consequence {consequence!r} that was on the row the whole time — "
        f"this is what twenty-eight reports of --context could not have "
        f"caught the repair with")


@needs_register
def test_the_surface_still_decides_nothing():
    """The repair must not turn a reading surface into a verdict.

    `context_lines` is documented as never deciding anything, and its output
    is printed after both verdicts precisely so it cannot influence them.
    Adding a printed cell keeps that true; a consequence line that changed an
    exit status would be a third check wearing a reading surface's name.
    """
    report = _newest_report()
    text = report.read_text(encoding="utf-8")
    lines = ca.context_lines(text, ROOT)

    assert any(line.lstrip().startswith("consequence: ") for line in lines), (
        "no consequence is printed at all, so the rest of this assertion "
        "would hold vacuously")
    for line in lines:
        if line.lstrip().startswith("consequence: "):
            assert line.startswith("  "), (
                f"the consequence must be indented under its row rather than "
                f"read as a new row: {line!r}")
