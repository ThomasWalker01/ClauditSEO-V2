"""The instructions that drive the loop are checked the way the code is.

Round 037's cohort sweep. Two of the eight findings it closes are properties a
grep can decide, and both had survived seventeen rounds of people reading the
files:

  WF-23 — `audit-fix/SKILL.md`'s `TIMINGS.md` template is a GFM table whose
          delimiter row has seven cells under an eight-cell header. GFM renders
          a mismatched table as prose, so the one place the row format is
          specified does not render as a table at all. (The real file's table
          has nine columns, so the template was also missing `work`.)

  WF-20 — the pinned suite command is stated at four sites and one of them
          disagrees. `auditor.md` omitted `-ra`. The rule whose entire content
          is "match the flags exactly" was stated four times with two answers.

Both are guards in the DISCIPLINE rule 1 sense and both were observed to fail
before the fix: the table test reported `707: header 8, delimiter 7` and the
command test reported `auditor.md:68` missing `-ra`.

Not a style checker. Each assertion is a property some finding was raised
about; nothing here polices prose, heading depth or line length, because a
test that fires on things nobody decided is a test people learn to edit around.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
from tests.needs_repo import skip_unless_repo
from tests.private_register import needs_register

ROOT = Path(__file__).resolve().parent.parent

#: The files that tell the loop what to do. A defect in one of these is a
#: defect in every round that follows it, which is why they are in audit scope
#: at all.
def _in_nested_checkout(p: Path) -> bool:
    """Under a directory holding its own `.git` - a git worktree a parallel
    session made at `.claude/worktrees/*` - which is a second copy of this
    repository, not instructions this loop reads. Found 2026-09-14, when one
    appeared mid-suite and every one of its audit reports joined the scope."""
    return any((q / ".git").exists() for q in p.parents
               if q != ROOT and ROOT in q.parents)


INSTRUCTION_FILES = sorted(
    p for p in (ROOT / ".claude").rglob("*.md")
    if p.is_file() and not _in_nested_checkout(p))


#: The registers the loop writes and then reads back: what is already known
#: broken, what was done to the running product, how long each round took, and
#: which aged findings were dispositioned. A defect in one of these is a defect
#: in every round that reads it, which is the same reason `INSTRUCTION_FILES`
#: is in scope at all.
#:
#: The audit reports under `audits/` are deliberately absent. A report is an
#: untouched record committed on its own and a round may not edit one, so a
#: guard that fired on a report could only be satisfied by breaking that rule.
REGISTER_FILES = tuple(ROOT / p for p in (
    "KNOWN_ISSUES.md",
    "OPERATOR_ACTIONS.md",
    "TIMINGS.md",
    "NEXT_UP.md",
    "CHANGELOG.md",
    "audits/DISPOSITIONS.md",
))

#: Every file whose tables are checked for shape. Both shape rules run over the
#: same set: a table is malformed for the same reason wherever it lives.
#: The register files that are actually here. `REGISTER_FILES` stays the
#: WRITTEN list - `test_every_register_named_exists` is about that list being
#: honest - but the shape guards below run over what exists, so they still
#: cover `KNOWN_ISSUES.md` and `CHANGELOG.md` in a tree that carries no
#: `audits/` (item 187: the operator's working record does not ship).
PRESENT_REGISTERS = tuple(p for p in REGISTER_FILES if p.is_file())

TABLE_FILES = tuple(INSTRUCTION_FILES) + PRESENT_REGISTERS


def _rel(p: Path) -> str:
    """Repo-relative path for a message, falling back to the bare name.

    The guards below are run against `tmp_path` fixtures as well as against
    real files, and a fixture is not under `ROOT`. Without the fallback a
    guard that *found* something in a fixture would raise `ValueError` from
    here instead of reporting it — the failing branch crashing on its way to
    saying what it found.
    """
    try:
        return p.relative_to(ROOT).as_posix()
    except ValueError:
        return p.name


def test_there_are_instruction_files_to_check():
    """Guards the collector, not the content.

    Every assertion below iterates `INSTRUCTION_FILES`, so a glob that stopped
    matching would turn this whole module green while checking nothing — the
    exact shape of the check-that-cannot-fail this repository has now paid for
    five times.
    """
    assert len(INSTRUCTION_FILES) >= 5, [_rel(p) for p in INSTRUCTION_FILES]


@needs_register
def test_every_register_named_exists():
    """The same guard for `REGISTER_FILES`, which is a written list not a glob.

    A rename drops a file out of scope silently otherwise - the
    check-that-cannot-fail shape again, one `git mv` away.
    """
    missing = [_rel(p) for p in REGISTER_FILES if not p.is_file()]
    assert missing == [], missing


# The three guards below read the audit log itself, which does not ship.


# --------------------------------------------------------------------------
# WF-23 — a table whose delimiter row does not match its header is not a table
# --------------------------------------------------------------------------

#: What a column boundary is. `\|` is a GFM-escaped pipe — one character
#: sitting inside a cell, not a boundary — and this is the same lookbehind
#: `scripts/check_anchors.py:137` already splits on, so the repository's two
#: cell splitters now answer the question the same way.
_BOUNDARY = re.compile(r"(?<!\\)\|")


def _cells(line: str) -> int:
    r"""Cell count of a GFM row. A row is `| a | b |`, so splitting on the
    boundary leaves an empty string at each end; both are dropped.

    CQ-86 — this split on *every* pipe, escaped or not, and the cost was not
    theoretical. Two writes were lost to it: KI-19 was refused for quoting a
    JavaScript `||`, and rewritten to spell the operator out in words; and the
    20:31 entry in `OPERATOR_ACTIONS.md` had its fifth cell rewritten from a
    literal table of measurements into prose. The second rewrite is what
    stranded the row half that `_stranded_row_halves` below now catches, so
    this defect and that one are the same incident twice.

    Escaped pipes are legal in a cell from here on. The rows that spell a pipe
    out in words are therefore unnecessary rather than wrong, and are left
    alone: they are an append-only record of what was written at the time, not
    a convention anybody has to keep following.
    """
    parts = _BOUNDARY.split(line.strip())
    if parts and not parts[0].strip():
        parts = parts[1:]
    if parts and not parts[-1].strip():
        parts = parts[:-1]
    return len(parts)


_DELIM = re.compile(r"^\s*\|[\s:|-]+\|\s*$")


def _table_mismatches(path: Path) -> list[str]:
    """Every delimiter row whose cell count differs from the header above it.

    Fenced code blocks are *not* skipped, deliberately: WF-23's table lives
    inside a fence in `audit-fix/SKILL.md`, and a reader copies it from there.
    A template that renders wrong when pasted is the defect.
    """
    bad = []
    lines = path.read_text(encoding="utf-8").split("\n")
    for i, line in enumerate(lines[1:], start=1):
        if not _DELIM.match(line) or "-" not in line:
            continue
        header = lines[i - 1]
        if "|" not in header:
            continue
        if _cells(header) != _cells(line):
            bad.append(f"{_rel(path)}:{i} header {_cells(header)} cells, "
                       f"delimiter {_cells(line)}")
    return bad


@pytest.mark.parametrize("path", TABLE_FILES, ids=_rel)
def test_every_table_delimiter_matches_its_header(path):
    assert _table_mismatches(path) == []


# --------------------------------------------------------------------------
# WF-41, CQ-79 — a body row that does not match its header is not a row
# --------------------------------------------------------------------------

def _row_width_mismatches(path: Path) -> list[str]:
    """Every table body row whose cell count differs from its own header.

    `_table_mismatches` above compares the header with the delimiter beneath it
    and stops there, so a table whose header and delimiter agree passes however
    its body rows are shaped. Both live instances were exactly that: round 036's
    entry in `KNOWN_ISSUES.md` was filed as a five-cell open-defect row under the
    four-column `Fixed` table, and `OPERATOR_ACTIONS.md` carried a restart row
    whose `evidence` cell was missing altogether. The guard written to end a
    table-shape defect could see neither.

    A blank line ends a table, per GFM. Without that, one table's width would be
    carried onto whatever pipe-prefixed line came next.
    """
    bad = []
    lines = path.read_text(encoding="utf-8").split("\n")
    width = header = None
    for i, line in enumerate(lines):
        if (_DELIM.match(line) and "-" in line
                and i > 0 and "|" in lines[i - 1]):
            width, header = _cells(line), i
            continue
        if width is None:
            continue
        if not line.strip().startswith("|"):
            width = header = None
            continue
        if _cells(line) != width:
            bad.append(f"{_rel(path)}:{i + 1} row {_cells(line)} cells, "
                       f"header at :{header + 1} has {width}")
    return bad


@pytest.mark.parametrize("path", TABLE_FILES, ids=_rel)
def test_every_table_row_matches_its_header_width(path):
    assert _row_width_mismatches(path) == []


def test_an_escaped_pipe_is_not_a_column_boundary():
    r"""CQ-86, and the reason this round exists at all.

    `\|` is one character inside a cell, per GFM. Counting it as a boundary
    made a correct row look one cell too wide, and the guard's only remedy is
    to rewrite the cell — which is how the 20:31 entry came to be rewritten,
    and how its first draft's tail came to be stranded beneath it. The
    counterpart in `scripts/check_anchors.py` has answered this correctly
    since `bdcb06d`; the two splitters disagreed until now.
    """
    assert _cells(r"| CQ-99 | matches `a \| b` | High | x |") == 4
    assert _cells(r"| a | b | c | d | e |") == 5


# --------------------------------------------------------------------------
# Relay 046 — half a row is not prose, and the width guard cannot see it.
# Reported by the operator against a live file rather than raised by an audit,
# so it carries no finding id; `212cad7` records the incident in full.
# --------------------------------------------------------------------------

#: What may legally follow a table row without being one. A blank line ends a
#: table per GFM; a heading ends the section; a fence close ends a template,
#: which is the only live instance — `audit-fix/SKILL.md`'s `TIMINGS.md` header
#: is the last thing inside its code fence.
_ENDS_A_TABLE = re.compile(r"^\s*(#|```|~~~|$)")


def _stranded_row_halves(path: Path) -> list[str]:
    r"""Every non-row line sitting directly beneath a table row.

    `_row_width_mismatches` above inspects only lines that begin with a pipe,
    so the one defect class that matters in an append-only record is the one
    class it cannot see: a row broken in half stops looking like a row, reads
    as prose, and per GFM a non-pipe line ends the table — which that guard
    implements faithfully and is therefore blind to.

    Found live rather than reasoned about. `OPERATOR_ACTIONS.md` carried the
    tail of a discarded draft from `ab37b85` until it was removed by hand in
    `212cad7`, and the width guard was green across every commit in between,
    including the one that introduced it. Note the near miss: had the break
    fallen one character earlier, the tail would have begun with a pipe and
    been caught immediately. It escaped on where the break happened to land.

    The rule, stated so it fits GFM rather than fights it: inside a table, a
    line that does not begin with a pipe must be blank, a heading, or a code
    fence. A bare prose line directly beneath a row is a broken row. Prose
    that genuinely follows a table has a blank line before it, which is the
    normal shape and stays legal.
    """
    bad = []
    lines = path.read_text(encoding="utf-8").split("\n")
    in_table = False
    for i, line in enumerate(lines):
        if (_DELIM.match(line) and "-" in line
                and i > 0 and "|" in lines[i - 1]):
            in_table = True
            continue
        if not in_table:
            continue
        if line.strip().startswith("|"):
            continue
        in_table = False
        if _ENDS_A_TABLE.match(line):
            continue
        bad.append(f"{_rel(path)}:{i + 1} does not begin with a pipe and is "
                   f"not blank, a heading or a fence: {line.strip()[:60]!r}")
    return bad


@pytest.mark.parametrize("path", TABLE_FILES, ids=_rel)
def test_no_table_row_is_stranded_in_half(path):
    assert _stranded_row_halves(path) == []


#: The file state at `ab37b85`, cut to the table it broke: the header, the
#: delimiter, the finished 20:31 row, and the tail of the draft it replaced.
#: Copied out of that commit rather than written for the test — a fixture
#: invented for the occasion proves the guard catches what its author already
#: had in mind, which is the thing this one is not allowed to be.
_STRANDED = Path(__file__).parent / "fixtures" / \
    "operator_actions_ab37b85_stranded.md"


def test_the_stranded_guard_fires_on_the_real_case():
    """DISCIPLINE rule 1, watched against the file that actually broke.

    Two assertions, and the second is the point: the width guard is silent on
    the same bytes. That is not incidental — it is why a second guard was
    written instead of the first one being widened.
    """
    if not _STRANDED.exists():
        pytest.skip("the real-case fixture is ClauditSEO's; this repo carries the kit without it")
    assert _row_width_mismatches(_STRANDED) == []

    stranded = _stranded_row_halves(_STRANDED)
    assert len(stranded) == 1, stranded
    assert "estart-service.ps1" in stranded[0]


def test_the_stranded_guard_passes_once_the_tail_is_removed(tmp_path):
    """The other half of rule 1: green on the repair, which is what `212cad7`
    did by hand. A guard that fires on the bad file and also on the good one
    has not located the defect."""
    if not _STRANDED.exists():
        pytest.skip("the real-case fixture is ClauditSEO's; this repo carries the kit without it")
    lines = _STRANDED.read_text(encoding="utf-8").split("\n")
    repaired = tmp_path / "repaired.md"
    repaired.write_text("\n".join(line for line in lines
                                  if not line.startswith("estart-service")),
                        encoding="utf-8")

    assert _stranded_row_halves(repaired) == []
    assert _row_width_mismatches(repaired) == []


def test_prose_after_a_blank_line_is_still_prose(tmp_path):
    """The guard's whole risk is over-firing on the normal shape, in which a
    table is followed by a blank line and then a paragraph. Every table in the
    four registers is written that way; if this were wrong the parametrised
    test above would be unfixable without reformatting files the item that
    asked for this guard explicitly put out of scope."""
    ok = tmp_path / "ok.md"
    ok.write_text("| a | b |\n| --- | --- |\n| one | two |\n\n"
                  "A paragraph that follows the table.\n", encoding="utf-8")

    assert _stranded_row_halves(ok) == []


# --------------------------------------------------------------------------
# B-26 — a BUILT entry records what shipped, and names where the rest went
# --------------------------------------------------------------------------

#: `FEATURES.md`, named on its own rather than appended to `REGISTER_FILES`.
#: That tuple feeds `TABLE_FILES`, so widening it would put this file's tables
#: under two shape guards as a side effect of a step scoped to one rule. Worth
#: someone's time separately — the planner reads this file back every run,
#: which is the stated reason `REGISTER_FILES` exists — but not worth taking
#: here.
FEATURES = ROOT / "FEATURES.md"

#: An entry heading: `## F-09 — <title>`, with `— **BUILT**` once it shipped.
_FEATURE_HEADING = re.compile(r"^## (F-\d+)\b")

#: The language of *naming future work*, as against *bounding present work*.
#:
#: That distinction is the whole defensibility of this guard, and everything
#: below sits on one side of it. "Not in scope.", "Only the front card, as the
#: entry scoped it", "this entry does not touch that reasoning" are honest
#: statements about what an entry **is**; they are most of what makes a BUILT
#: entry worth reading, and none of them appear here. What appears here is
#: prose that names work somebody still has to do — which, written inside an
#: entry the planner skips by definition, is work no queue can reach.
#:
#: Deliberately under-inclusive. There are unbounded ways to defer something in
#: English, and a guard reaching for all of them would fire on honest prose —
#: worse than no guard at all, because the cost of a false fire is paid by
#: every future entry that describes its own boundary correctly. The rule in
#: `.claude/skills/feature/SKILL.md` is what has to be followed; this catches
#: the shape the failure actually took, once, in F-09.
_DEFERRAL = (
    "recommended as",
    "further entry",
    "further entries",
    "not covered here",
    "remain unbuilt",
    "remains unbuilt",
    "follow-on piece",
)

#: What counts as having placed it: the id of the register entry the work was
#: filed as. An id and not a filename, because "see `BACKLOG.md`" is not
#: something a reader can follow in one hop, and every register this repository
#: routes work to issues ids — `F-`, `B-`, `KI-`, and the auditor's own series.
_REGISTER_ID = re.compile(r"\b(?:F|B|KI|UX|CQ|UI|WF)-\d+\b")

_COLLAPSE = re.compile(r"\s+")


def _unplaced_deferrals(path: Path) -> list[str]:
    r"""Every paragraph of a **BUILT** entry that names unshipped work without
    saying where that work was filed.

    `FEATURES.md` holds "capability the product does not have" (its line 2), so
    the moment an entry is marked `**BUILT**` anything still missing from it is
    by that same definition not a feature — it is a new entry, a defect, or a
    backlog item, and none of the three belongs inside the record of what
    shipped. The trap is mechanical rather than stylistic:
    `.claude/skills/backlog-plan/SKILL.md` selects "every entry not marked
    **BUILT**", so marked-ness *is* the selector, and prose inside a marked
    entry cannot be reached by the one skill whose job is to see every queue at
    once. Work written there is not deprioritised; it is unreachable.

    Found by the operator going to look for two pieces of F-09 and finding them
    in no queue at all — filed as B-26, and the older half of it has a visible
    symptom on the client screen today.

    Paragraphs rather than lines, because both halves of the shape wrap: F-09
    breaks "Recommended as / two further entries" across a line ending, so a
    line-at-a-time reader sees neither phrase whole, and the id that would
    discharge the paragraph is just as free to sit on a different line from the
    sentence that owes it.

    An entry's own id does not discharge its own deferral. F-09's paragraph
    ends "— F-09 delivers the first visible piece", which names an id and
    places nothing; without that exclusion the guard would read its subject's
    signature as its destination and pass on the exact text it was written for.
    """
    bad: list[str] = []
    lines = path.read_text(encoding="utf-8").split("\n")

    fid: str | None = None
    built = False
    para: list[tuple[int, str]] = []

    def close(block: list[tuple[int, str]]) -> None:
        if not block or fid is None or not built:
            return
        joined = " ".join(text for _, text in block)
        flat = _COLLAPSE.sub(" ", joined).lower()
        named = [phrase for phrase in _DEFERRAL if phrase in flat]
        if not named:
            return
        if {m for m in _REGISTER_ID.findall(joined) if m != fid}:
            return
        bad.append(
            f"{_rel(path)}:{block[0][0]} — {fid} is **BUILT** and this "
            f"paragraph names work it did not ship "
            f"({', '.join(named)}) without naming the entry it was "
            f"filed as: {flat[:70]!r}")

    for i, line in enumerate(lines):
        heading = _FEATURE_HEADING.match(line)
        if heading:
            close(para)
            para = []
            fid = heading.group(1)
            built = "**BUILT**" in line
            continue
        if line.strip():
            para.append((i + 1, line))
        else:
            close(para)
            para = []
    close(para)
    return bad


def test_no_built_entry_holds_unplaced_work():
    """The live assertion. Every other test in this section exists to keep this
    one honest — on its own it is a check that passes while `FEATURES.md` holds
    no entries at all, or while the heading pattern has quietly stopped
    matching."""
    assert _unplaced_deferrals(FEATURES) == []


def test_the_entry_scan_actually_reaches_the_entries():
    """Guards the collector, not the content — the same reason
    `test_there_are_instruction_files_to_check` exists. A heading regex that
    stopped matching would turn the assertion above green while reading
    nothing."""
    lines = FEATURES.read_text(encoding="utf-8").split("\n")
    raw = [line for line in lines if line.startswith("## F-")]
    if not raw:
        # A repo that carries the kit with the register template has no
        # entries yet; the collector guard applies the day it writes one.
        pytest.skip("FEATURES.md has no F-NN entries in this repo yet")
    headings = [line for line in lines if _FEATURE_HEADING.match(line)]
    assert len(headings) == len(raw), (
        f"the heading regex matched {len(headings)} of {len(raw)} F- entries", headings)


#: F-09 as it stood at `d25f509`, copied out of `FEATURES.md` rather than
#: written for the occasion — a fixture invented by the guard's own author
#: proves only that the guard catches what its author already had in mind,
#: which is what rounds 027 through 030 spent four levers removing.
_UNPLACED = Path(__file__).parent / "fixtures" / \
    "features_F-09_unplaced.md"


def test_the_unplaced_guard_fires_on_the_real_case():
    """DISCIPLINE rule 1, kept permanently against the entry that did it.

    Three paragraphs, and the count is asserted rather than the truthiness: the
    entry defers in three separate places, and a guard that found one of them
    would read as working while missing two thirds of the instance it was
    written for.
    """
    if not _UNPLACED.exists():
        pytest.skip("the real-case fixture is ClauditSEO's; this repo carries the kit without it")
    found = _unplaced_deferrals(_UNPLACED)
    assert len(found) == 3, found
    assert all("F-09" in message for message in found), found


def test_the_unplaced_guard_clears_once_the_destination_is_named(tmp_path):
    """The other half of rule 1: green on the repair. A guard that fires on the
    bad text and also on the repaired text has not located anything.

    The repair is a pointer, not a rewrite — which is the point of the rule
    being about placement rather than about prose. A BUILT entry may say
    whatever it likes about what it did not build, as long as it says where
    that went.
    """
    if not _UNPLACED.exists():
        pytest.skip("the real-case fixture is ClauditSEO's; this repo carries the kit without it")
    repaired = tmp_path / "repaired.md"
    repaired.write_text(
        _UNPLACED.read_text(encoding="utf-8")
        .replace("remain unbuilt", "remain unbuilt (filed as B-26)")
        .replace("Recommended as", "Filed as B-26, and recommended as")
        .replace("are deliberately not built as part of this entry.",
                 "are deliberately not built as part of this entry, and are "
                 "registered as B-26."),
        encoding="utf-8")

    assert _unplaced_deferrals(repaired) == []


def test_bounding_prose_in_a_built_entry_is_not_a_deferral(tmp_path):
    """The guard's whole risk is over-firing on an entry describing its own
    edges, which is exactly what a good BUILT entry does. Every phrase below is
    lifted from F-09's real text and every one of them must stay legal."""
    ok = tmp_path / "ok.md"
    ok.write_text(
        "## F-42 — a thing that shipped — **BUILT**\n\n"
        "**Only the front card, as the entry scoped it.**\n\n"
        "**Not in scope.** No weight in `scoring.py` changes, and no A11Y "
        "check is\nadded, removed or altered — what is detected does not "
        "change.\n\n"
        "**This entry does not touch that reasoning, and does not touch any "
        "weight.**\n",
        encoding="utf-8")

    assert _unplaced_deferrals(ok) == []


def test_an_unmarked_entry_may_defer_as_freely_as_it_likes(tmp_path):
    """Marked-ness is the whole rule. An entry not yet marked **BUILT** is one
    the planner can still select, so prose inside it is reachable and there is
    nothing to enforce — and enforcing it anyway would fire on entries that are
    simply not finished yet."""
    ok = tmp_path / "ok.md"
    ok.write_text(
        "## F-43 — a thing not yet built\n\n"
        "The second half is not covered here and is recommended as two "
        "further entries.\n",
        encoding="utf-8")

    assert _unplaced_deferrals(ok) == []


# --------------------------------------------------------------------------
# WF-20 — one rule, one wording
# --------------------------------------------------------------------------

_PYTEST_LINE = re.compile(
    r"^[^\n]*?(?:^|[\\/\s])pytest(?:\.exe)?\s+(-[^\n`'\"]*)", re.M)


def _pytest_invocations(path: Path) -> list[tuple[int, str]]:
    """Every `pytest <flags...>` statement in the file, flags only.

    Flags first: `pytest -ra tests/unit` is collected, `pytest tests/unit -ra`
    is not (the regex anchors on the first `-`). The kit's profile and the CI
    workflow must both be written flags-first for the same reason.
    """
    out = []
    for n, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
        if "pytest" not in line:
            continue
        m = _PYTEST_LINE.search(line)
        if m:
            out.append((n, m.group(1).strip().rstrip("`").strip()))
    return out


def _pinned_flags() -> str:
    """The flags CI runs. `ci.yml` is the authority: it is the gate, and every
    other statement is a copy of it. Only the entry point may differ — CI has
    no `.venv` and resolves `pytest` from PATH. Read from the workflow rather
    than pinned as a constant: the constant was ClauditSEO's flags, and the
    kit's second repo (2026-08-22) runs a different suite. Falls back to the
    profile's suite_command, then to ClauditSEO's flags, when there is no
    workflow to read."""
    ci = ROOT / ".github" / "workflows" / "ci.yml"
    if ci.exists():
        inv = _pytest_invocations(ci)
        if inv:
            return inv[0][1]
    profile = ROOT / ".claude" / "loop" / "PROFILE.md"
    if profile.exists():
        inv = _pytest_invocations(profile)
        if inv:
            return inv[0][1]
    return "-n auto --dist loadfile -ra"


PINNED_FLAGS = _pinned_flags()


def test_the_pinned_suite_command_is_stated_once():
    """Four sites, and they must give one answer.

    `ci.yml` is included as the authority rather than assumed: a test that
    checked the three copies against a constant would pass while all three
    drifted away from the gate together, which is the failure mode this rule
    exists for.
    """
    sites = [ROOT / ".github" / "workflows" / "ci.yml", *INSTRUCTION_FILES]
    found = {f"{_rel(p)}:{n}": flags
             for p in sites if p.exists()
             for n, flags in _pytest_invocations(p)}

    assert found, "no pinned suite command found anywhere — the collector broke"
    disagreeing = {k: v for k, v in found.items() if v != PINNED_FLAGS}
    assert not disagreeing, (
        f"these state the pinned command differently from "
        f"{PINNED_FLAGS!r}: {disagreeing}")


# --------------------------------------------------------------------------
# WF-15 — the cohort register is counted by a machine or not at all
# --------------------------------------------------------------------------

DISPOSITIONS = ROOT / "audits" / "DISPOSITIONS.md"

#: Every `| finding | anchor | rounds |` table in the file. There are four, and
#: that is the whole reason this test exists: round 037 "fixed" WF-15 by
#: sweeping every `| `-prefixed line from the FIRST such header to end of file,
#: which summed all four tables and produced 34 rows where the engineering
#: table holds 23. A wrong count replaced a wrong count, and the new one was
#: recorded in the commit as a measured signal.
_ENGINEERING_HEADING = "### Engineering"


def _engineering_rows() -> list[str]:
    """The engineering table's body rows, bounded at both ends.

    Bounded is the point. The previous count had a start and no end, so it ran
    into the two tables below it. This one starts at the heading that names the
    set and stops at the first line that is not a table row.
    """
    lines = DISPOSITIONS.read_text(encoding="utf-8").split("\n")
    start = next(i for i, ln in enumerate(lines)
                 if ln.startswith(_ENGINEERING_HEADING))
    header = next(i for i, ln in enumerate(lines[start:], start=start)
                  if ln.startswith("| finding |"))
    rows = []
    for line in lines[header + 2:]:          # +2 skips header and delimiter
        if line.startswith("| "):
            rows.append(line)
        elif line.strip() == "":
            continue
        else:
            break
    return rows


@needs_register
def test_the_engineering_set_is_counted_from_its_own_table():
    """The loop's one quantitative commitment to its oldest findings.

    `audit-fix/SKILL.md` step 4 promises one round in three to this set, so its
    size is load-bearing — and it was written by hand, wrong, twice. Both
    figures the file states must come from the rows.
    """
    rows = _engineering_rows()
    live = [r for r in rows if "~~" not in r]
    text = DISPOSITIONS.read_text(encoding="utf-8")
    if not rows and "live," not in text:
        # The kit's register template: an Engineering heading with an empty
        # table and no counted figures yet. The guard applies the day the
        # loop dispositions its first cohort here.
        pytest.skip("no engineering cohort in this repo's DISPOSITIONS.md yet")

    assert len(rows) >= 1, f"the collector broke: {len(rows)} rows"
    assert f"({len(live)} live, {len(rows)} rows, " \
           f"{len(rows) - len(live)} struck)" in text, (
        f"the Engineering heading must state the counted figures — "
        f"{len(live)} live, {len(rows)} rows, {len(rows) - len(live)} struck")
    assert f"| stays with the loop | {len(live)} |" in text, (
        f"the summary table must say {len(live)}, the live count — a set whose "
        "size includes rows struck through as done is not the set the "
        "one-round-in-three promise is made against")


#: Each mechanically-derived table: heading, and the destination cell the
#: routing summary uses for it. A second one was added at round 045 when
#: WF-45's row-level match exposed eleven anchors the containment test had
#: been discharging on prose and struck-through rows.
_DERIVED_TABLES = [
    ("### Engineering, derived mechanically at round 044",
     "stays with the loop (derived)"),
    ("### Engineering, derived mechanically at round 045",
     "stays with the loop (derived, 045)"),
]


def _derived_rows(heading: str) -> list[str]:
    """The mechanically-derived table's body rows, bounded the same way.

    Same collector shape as `_engineering_rows`, deliberately not shared with
    it: the two tables have different columns and different keys, and folding
    them into one parameterised helper is how round 037's unbounded scan came
    to sum four tables as one.
    """
    lines = DISPOSITIONS.read_text(encoding="utf-8").split("\n")
    start = next(i for i, ln in enumerate(lines)
                 if ln.startswith(heading))
    header = next(i for i, ln in enumerate(lines[start:], start=start)
                  if ln.startswith("| anchor |"))
    rows = []
    for line in lines[header + 2:]:          # +2 skips header and delimiter
        if line.startswith("| "):
            rows.append(line)
        elif line.strip() == "":
            continue
        else:
            break
    return rows


@pytest.mark.parametrize("heading,destination", _DERIVED_TABLES,
                         ids=lambda v: v.split()[-1])
@needs_register
def test_the_derived_set_is_counted_from_its_own_table(heading,
                                                      destination):
    """WF-43's rows, held to the standard the hand-written set is held to.

    This register has been counted by hand three times and been wrong three
    times, which is why the set above states no figure a test does not
    reproduce. A second table added by the round that fixed the gate is
    exactly where that lesson gets forgotten, so it states its figure the same
    way — in the heading and in the routing summary, both read from the rows.
    """
    text = DISPOSITIONS.read_text(encoding="utf-8")
    if heading not in text:
        # The derived tables are ClauditSEO's registers (rounds 044/045). A
        # repo that carries the kit with the template DISPOSITIONS.md has no
        # such table yet; the guard applies the day it writes one.
        pytest.skip(f"no {heading!r} table in this repo's DISPOSITIONS.md")
    rows = _derived_rows(heading)

    assert len(rows) >= 10, f"the collector broke: {len(rows)} rows"
    assert f"{heading} ({len(rows)} anchors)" in text, (
        f"the heading must state the counted figure — {len(rows)} anchors")
    assert f"| {destination} | {len(rows)} |" in text, (
        f"the routing summary must say {len(rows)} against {destination}")


# --------------------------------------------------------------------------
# WF-42 — an instruction file the harness cannot parse is worse than a wrong
# one: it disappears from the registry with no error anywhere in this repo
# --------------------------------------------------------------------------

_BOM = b"\xef\xbb\xbf"


def _bom_carriers(paths) -> list[Path]:
    """Every path whose first three bytes are a UTF-8 BOM. A free function
    rather than inlined in the test, so the fail-first proof below can call
    the same logic the real guard uses instead of restating it."""
    return [p for p in paths if p.read_bytes()[:3] == _BOM]


def test_the_bom_check_actually_detects_one(tmp_path):
    """DISCIPLINE rule 1, watched against a reconstructed bad file rather
    than a reverted one — the real defect (`.claude/agents/auditor.md`) is
    already fixed in the tree by `717d850`, so asserting the guard passes
    today would never have exercised the failing branch. Proves the checker
    itself, not merely that today's tree happens to be clean."""
    clean = tmp_path / "clean.md"
    clean.write_bytes(b"---\nname: x\n---\n")
    bomd = tmp_path / "bomd.md"
    bomd.write_bytes(_BOM + b"---\nname: x\n---\n")

    assert _bom_carriers([clean, bomd]) == [bomd]


def test_no_instruction_file_carries_a_byte_order_mark():
    """WF-42. A BOM ahead of `auditor.md`'s frontmatter deregistered the
    `auditor` subagent entirely — not a parse error, not a warning, just
    absent from the Agent tool's list, and round 039's first attempt failed
    twice against a file that `ls`, `cat` and every text-mode reader in this
    repo showed as perfectly normal. `Set-Content -Encoding utf8` on
    PowerShell 5.1 writes that BOM by default; the fix (`717d850`) rewrote
    the file with `[System.Text.UTF8Encoding]::new($false)` instead. This is
    what keeps the next `-Encoding utf8` habit from doing it again, to this
    file or another `.claude/**/*.md` file the guard did not exist to watch
    when this one broke.

    Not the same file `provenance.py:99-110` already guards. `round.json` is
    JSON, gitignored, and read by one Python function that already opens it
    `utf-8-sig` — a different consumer, already tolerant. This guard's
    subject is `.md` instruction files read by something outside this
    codebase that is not tolerant, which is the whole reason the failure
    mode here was silent instead of an exception.
    """
    carrying = _bom_carriers(INSTRUCTION_FILES)
    assert carrying == [], [_rel(p) for p in carrying]


# --------------------------------------------------------------------------
# WF-16 / WF-39 — the rule that would have caught a bad anchor
# --------------------------------------------------------------------------

def test_the_auditor_is_told_to_check_an_anchor_before_writing_it():
    """WF-39: two anchors in report 034's CQ-68 row point past the end of the
    file they name. The loop re-verifies each round from the previous report's
    anchors, so a wrong one is carried rather than caught, and nothing checked
    one against the file's length before it was written."""
    text = (ROOT / ".claude" / "agents" / "auditor.md").read_text(encoding="utf-8")

    assert "wc -l" in text, (
        "auditor.md must say how to check an anchor resolves before writing it")


def test_the_auditor_is_told_how_a_finding_is_aged():
    """WF-16: the ten-round disposition rule fires on a survival count, and
    `auditor.md` contained none of `survival`, `Nth round` or `evidence
    anchor` — so the rule turned on a key the auditor was never told to
    produce."""
    text = (ROOT / ".claude" / "agents" / "auditor.md").read_text(encoding="utf-8")

    assert "evidence anchor" in text.lower(), (
        "auditor.md must name the evidence anchor as what ages a finding")


# --------------------------------------------------------------------------
# The accounting contract, stated where the party bound by it reads
# --------------------------------------------------------------------------
#
# `scripts/reconcile_findings.py` refuses a report that drops a prior finding
# without accounting for it, and it looks for one specific heading. That
# contract was stated in `audit-fix/SKILL.md` step 2 and in the script — both
# read by the *consumer* of the report — and nowhere in `auditor.md`, which is
# the only file the party that must satisfy it reads. Report 058 is the
# measured cost: it accounted for all six drops (CQ-109, CQ-111, CQ-94,
# CQ-96, WF-67, WF-69) in prose under ASSUMPTIONS and in its per-pillar
# "Accounted for" paragraphs, which is honest work in the wrong shape, and the
# gate reported six unaccounted drops against a report that had dropped none
# silently. A gate that can only be red is not a gate.
#
# Third of the family above: WF-39 put the anchor check in `auditor.md`, WF-16
# put the ageing key there, and this puts the accounting contract there. The
# same defect three times — a rule the loop enforces, stated everywhere except
# to the party who has to obey it.

def test_the_auditor_is_told_to_account_for_every_finding_it_drops():
    """The heading is read from the parser rather than quoted, so the two
    cannot drift: if `reconcile_findings` ever changes what it looks for, this
    fails until `auditor.md` says the new thing. A quoted copy here would have
    been a fourth statement of the contract and a fourth thing to keep in
    step."""
    # Loaded by path, not by package: `scripts/` is a plain directory in a repo
    # that carries the kit, not necessarily an importable package.
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "kit_reconcile_findings", ROOT / "scripts" / "reconcile_findings.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _NOT_CARRIED = module._NOT_CARRIED

    text = (ROOT / ".claude" / "agents" / "auditor.md").read_text(encoding="utf-8")

    assert _NOT_CARRIED.search(text), (
        "auditor.md must state the heading reconcile_findings.py looks for — "
        f"{_NOT_CARRIED.pattern!r} — so a report can satisfy the gate that "
        "judges it")
    assert "reconcile_findings" in text, (
        "auditor.md must name the script that checks the accounting, so the "
        "auditor can run it rather than be told about it after the fact")


# --------------------------------------------------------------------------
# CQ-111 / KI-21 — a bare 0x0D anywhere in the tree, not in two named files
# --------------------------------------------------------------------------
#
# KI-21: something in the loop's writing path emits a real 0x0D where a
# literal backslash-r was meant, in Windows paths written into markdown.
# `462d795` repaired four bytes across `TIMINGS.md` and `OPERATOR_ACTIONS.md`
# and recorded its fix as "idempotent - running the tool a second time would
# find zero bare CRs". True of those two files and of nothing else: a
# tree-wide scan at round 055 found a fifth (CQ-111), in `.claude/DISCIPLINE.md`
# inside a `powershell` fence the file tells an operator to copy and run.
#
# Why the existing guards could not see it. The table-row and delimiter checks
# above notice a 0x0D only when it happens to land in a table cell and change
# that row's width - which is how the four in KI-21 were caught, and why the
# fifth was not. A CR inside a fenced code block breaks no table.
#
# The file list is `git ls-files`, not a path tuple and not an extension
# whitelist. Both of those are the shape this repository keeps paying for -
# `_DERIVED_TABLES` is two entries against four tables (CQ-89), the narrow-run
# detector is one sentence against a class (CQ-110) - and a scan scoped to the
# two files that happened to break CI is the defect CQ-111 names. Anything
# tracked is in scope by construction, including files added after this was
# written.

# A CR that is not the first half of a CRLF, which is what makes this safe
# on both CI legs. `core.autocrlf` is true here, so a Windows checkout holds
# CRLF where an Ubuntu one holds LF - and neither produces a 0x0D that is
# not followed by 0x0A. Only a corrupted byte does.
#: The two bytes, built from their numbers rather than written as escapes.
#: KI-21 is a class of corruption that eats backslashes on the way into a
#: file, so a test about it that spells its own payload with backslashes is
#: one heredoc away from being the defect. Measured, not feared: the first
#: draft of the detector below landed holding four real 0x0D bytes.
_CR = bytes([0x0D])
_NL = bytes([0x0A])


def _bare_cr(blob: bytes) -> int | None:
    """Offset of the first bare 0x0D, or None."""
    for i, ch in enumerate(blob):
        if ch == 0x0D and (i + 1 >= len(blob) or blob[i + 1] != 0x0A):
            return i
    return None


def _tracked_text_files() -> list[Path]:
    """Every tracked file that is not binary.

    `git ls-files` is the registry. A failure to run it raises rather than
    returning a short list: a scan that silently narrows is the thing this
    guard exists to replace, and DISCIPLINE rule 5 says a check whose evidence
    cannot disagree with it is not a check.

    Outside a repository - the public export, a downloaded zip - there is no
    registry to ask, and every caller skips saying so (`tests/needs_repo.py`).
    That is not a short list either: nothing is scanned and nothing passes.
    """
    skip_unless_repo()
    git = shutil.which("git")
    if git is None:
        pytest.fail("git is not resolvable, so the tracked-file list cannot "
                    "be built and this guard cannot answer")
    out = subprocess.run([git, "ls-files", "-z"], cwd=ROOT,
                         capture_output=True, check=True).stdout
    files = []
    for name in out.split(b"\0"):
        if not name:
            continue
        path = ROOT / name.decode("utf-8")
        if not path.is_file():
            continue
        try:
            with path.open("rb") as fh:
                head = fh.read(4096)
        except OSError:
            continue
        if b"\0" in head:          # binary: the vendored axe build, images
            continue
        files.append(path)
    return files


def test_the_tracked_file_list_is_not_vacuously_short():
    """The guard below asserts an empty result, so it passes for free if the
    enumeration returns nothing. This is the half that can disagree.

    Measured at the time of writing: 364 tracked text files in ClauditSEO. The
    bound is the kit's own footprint plus a margin - the kit installs 21 text
    files, so any repo that carries it and has a guard to run has more than 30
    - because the guard exists to catch an enumeration that broke, not to
    count the repository, and a repo-sized figure would fail in a small repo.
    """
    files = _tracked_text_files()

    assert len(files) > 30, (
        f"only {len(files)} tracked text files enumerated - the file list is "
        "broken, and a scan over it proves nothing")


def test_the_bare_cr_check_actually_detects_one():
    """CQ-233, and the clause `test_the_bom_check_actually_detects_one`
    has had since round 039 while this scan went without one.

    The guard below asserts an empty list over the real tree, so it is
    green on a `_bare_cr` that never returns anything - and the one time
    this corruption class reached an audit report,
    `audits/103-2026-08-29.md` at byte 8759, nothing showed the guard
    caught it. The byte was repaired the very next commit as an incidental
    side effect of a whole-file line-ending normalisation (`25f5c78`),
    which neither its message nor that round's `OPERATOR_ACTIONS.md` row
    mentions. Luck is not a passing guard.

    Both shapes KI-21 records, because they are different bytes in
    different company and a detector that found only one would still be
    half blind: the doubled carriage return (0x0D 0x0D 0x0A), which is what
    landed in report 103, and the collapsed escape (`scripts` 0x0D
    `ound-marker.ps1`), which is what landed in the four path fragments.

    The clean cases are asserted in the same test, and the two above
    assert an exact offset rather than merely "something". Measured
    against a detector stubbed to answer 6 for every input: it fails on
    the collapsed case and not on the clean ones, so the offsets carry
    that direction and the clean clauses carry the narrower one - a
    detector that reads an ordinary CRLF or LF line ending as corrupt
    and turns the scan into a permanent red on one of the two CI legs.

    Every byte here is built from `_CR` and `_NL` rather than written as an
    escape, and that is the subject rather than a style choice: the first
    draft of this test was written through a shell heredoc, the doubled
    backslashes collapsed exactly as KI-21 describes, and the file landed
    holding four real 0x0D bytes - the corruption, inside the test for the
    corruption. KI-21 records the workaround and it is the one used here:
    no backslash anywhere in the payload.
    """
    doubled = b"a line" + _CR + _CR + _NL + b"the next" + _NL
    collapsed = b"-File scripts" + _CR + b"ound-marker.ps1 -Read" + _NL

    assert _bare_cr(doubled) == 6, (
        "the doubled carriage return report 103 carried is not detected; "
        "a 0x0D whose successor is another 0x0D is bare by definition")
    assert _bare_cr(collapsed) == 13, (
        "the collapsed escape KI-21 records in four path fragments is not "
        "detected")
    assert _bare_cr(b"crlf" + _CR + _NL + b"throughout" + _CR + _NL) is None, (
        "a plain CRLF file reads as corrupt, which would make the scan a "
        "permanent red on every Windows checkout")
    assert _bare_cr(b"lf" + _NL + b"throughout" + _NL) is None, (
        "a plain LF file reads as corrupt, which would make the scan a "
        "permanent red on the Ubuntu leg")
    assert _bare_cr(b"") is None, (
        "an empty file reads as corrupt; the lookahead runs past the end "
        "rather than stopping at it")


@needs_register
def test_the_scan_reaches_the_audit_reports():
    """CQ-233's other half: the surface the corruption actually landed on.

    `test_the_tracked_file_list_is_not_vacuously_short` proves the
    enumeration is not empty, which is a different question from whether it
    reaches `audits/`. It does, because `git ls-files` is the registry and a
    report is tracked - but that has been true by construction rather than
    by assertion for the whole time the one real instance went unnoticed,
    and `audits/**` is exactly the path this file's `REGISTER_FILES`
    comment excludes from every other guard here. So the one guard that
    does cover it says so out loud.
    """
    covered = {_rel(path) for path in _tracked_text_files()}
    reports = sorted(p for p in covered if p.startswith("audits/"))

    assert len(reports) > 10, (
        f"the scan reaches {len(reports)} files under audits/ - the audit "
        "reports are outside the one guard that watches them, and report "
        "103's bare 0x0D at byte 8759 would land unseen again")


def test_no_tracked_file_holds_a_bare_carriage_return():
    """CQ-111. A 0x0D not followed by 0x0A, anywhere in the tracked tree.

    Reported with the byte offset and its surrounding bytes rather than as a
    count, because the four instances in KI-21 were each a path fragment
    (`scripts` + 0x0D + `ound-marker.ps1`) and the repair is byte-literal.

    If this fails on a file you just wrote: the payload passed through a shell
    heredoc, a doubled backslash collapsed, and the surviving backslash-r was
    read as a control character. KI-21 records the workaround, which is the
    only thing that has worked - write the row with a bytes-only writer and no
    backslash in the payload.

    The dead end, met while repairing byte 11992 of `.claude/DISCIPLINE.md`
    and recorded so the next repair does not repeat it: the corruption
    collapses TWO characters into one. `0x5C 0x72` becomes a single `0x0D`, so
    overwriting that byte with `0x5C` restores the backslash and silences this
    guard while leaving the file naming `scripts` + backslash + `ound-marker`
    - a green test over a command still broken in a different way. The repair
    is an insertion of two bytes, not a substitution of one, and the check
    that catches the difference is reading the mended line back and comparing
    it against the same command where it is written correctly
    (`.claude/skills/backlog-plan/SKILL.md:22`).
    """
    hits = []
    for path in _tracked_text_files():
        blob = path.read_bytes()
        at = _bare_cr(blob)
        if at is None:
            continue
        line = blob[:at].count(b"\n") + 1
        context = blob[max(0, at - 30):at + 30]
        hits.append(f"{_rel(path)}:{line} byte {at}: {context!r}")

    assert hits == [], "bare 0x0D bytes:\n" + "\n".join(hits)


#: Vendored third-party bytes, excluded from the scan below.
#:
#: Not an instance list. The subject of that guard is what the loop's own
#: writing path produces, and these are byte-frozen copies of somebody else's
#: build, where a control character inside a string literal is correct.
#: Measured rather than assumed: `clauditseo/vendor/axe.min.js` holds two 0x01
#: bytes and one 0x02, all inside its own minified literals.
#:
#: The guard asserts this exclusion actually excluded something, so a rename
#: cannot quietly turn it into a no-op. If the vendor directory moves, that
#: assertion fails and someone updates this tuple, which is the safe
#: direction: an exemption is honest only while every row in it is true.
VENDORED = ("clauditseo/vendor/",)

#: Every control character below 0x20 except the three that are ordinary text.
#:
#: Derived from the range rather than from the instances seen so far, and that
#: is the whole finding. KI-21 is written about backslash-r, and the guard
#: above was written to match it exactly, so when backslash-b collapsed in
#: `b07ae29` there was no check anywhere that could fail: two 0x08 bytes sat in
#: `tests/test_server_outage_is_named.py` through reports 077 and 078, in a
#: docstring quoting a `grep` command that consequently could not be pasted and
#: run. Report 078 cites that very file and those very lines under CQ-164 and
#: did not see them, because bytes below 0x20 do not render.
#:
#: The three exclusions, each measured against the tracked tree:
#:   0x0A  LF, line endings.
#:   0x0D  CR, owned by the guard above, which reports the two-byte repair
#:         KI-21 needs. A CRLF pair is also ordinary on Windows checkouts.
#:   0x09  TAB, the one control character that is also ordinary text. Five live
#:         instances, all on one line of `OPERATOR_ACTIONS.md`, all inside a
#:         quoted list of alt text read off the product. Captured evidence, not
#:         corruption. The cost of that exclusion is stated rather than hidden:
#:         a collapsed backslash-t is invisible here, and the only thing that
#:         would catch it is a reader noticing the alignment.
COLLAPSED_ESCAPES = frozenset(range(0x00, 0x20)) - {0x09, 0x0A, 0x0D}


def test_no_tracked_file_holds_a_collapsed_escape():
    """KI-21's failure class, rather than KI-21's one character.

    KI-21 records a writing path that turns an intended two-character escape
    into the single control character it names: the payload passes through a
    shell heredoc, a doubled backslash collapses, and what survives is read as
    a control byte. Nothing about that mechanism is specific to backslash-r.
    Backslash-b, backslash-f, backslash-v, backslash-a and backslash-0 all
    collapse the same way, in the same places, for the same reason.

    So this is the population guard for a check that had a population of one.
    The evidence that it was needed is that all three instances found on
    22 August 2026 were found by eye rather than by a test:

      1. `b07ae29` committed two 0x08 bytes into a Python module docstring,
         where backslash-b word boundaries had been written around DIST. They
         survived two audit rounds.
      2. The commit repairing (1) re-introduced both bytes in the paragraph
         explaining them, because that paragraph also passed through a heredoc.
      3. The OPERATOR_ACTIONS row for the same commit collapsed backslash-r in
         `scripts` + backslash + `restart-service.ps1`. That one was caught,
         by the guard above, which is exactly the difference this test closes.

    Reported with the offset, the line and the surrounding bytes, and repaired
    the same way the guard above says: the corruption collapses TWO characters
    into one, so the repair is a two-byte insertion and not a substitution.

    If this fails on something just written: do not escape around it. Write the
    payload with a bytes-only writer, or reword so no backslash escape appears
    in it at all. Both instances above were repaired by rewording, and the
    second is the argument for it - escaping around the trap is what walked
    into it a second time.
    """
    skipped, hits = [], []
    for path in _tracked_text_files():
        rel = _rel(path)
        if rel.startswith(VENDORED):
            skipped.append(rel)
            continue
        blob = path.read_bytes()
        for offset, ch in enumerate(blob):
            if ch in COLLAPSED_ESCAPES:
                line = blob[:offset].count(b"\n") + 1
                context = blob[max(0, offset - 30):offset + 30]
                hits.append(
                    f"{rel}:{line} byte {offset} is 0x{ch:02X}: {context!r}")
                break

    # The exclusion must have excluded something IF this repo has such a
    # directory; a repo with no vendored tree (the kit's second repo) has
    # nothing to exclude and the guard scans everything, which is the honest
    # state, not a stale exemption.
    if any((ROOT / v.rstrip("/")).is_dir() for v in VENDORED):
        assert skipped, (
            "the VENDORED prefixes matched no tracked file, so the exclusion is "
            "either stale or the file list is broken - either way this guard is "
            "no longer scanning what it claims to")

    assert hits == [], (
        "control bytes that a collapsed escape produces:\n" + "\n".join(hits))


# --------------------------------------------------------------------------
# Relay 104 — the auditor's model is chosen by depth, and stated where the
# dispatching session reads
# --------------------------------------------------------------------------
#
# A cost lever, at the operator's direct request: `deep` is the thorough,
# audit-only pass and stays on the strongest tier; `triage` and `standard` run
# many times a day and carry nearly every audit, so they go to Sonnet at
# roughly a third of Opus's token price.
#
# The instruction has to live in `audit-fix/SKILL.md`, because the dispatching
# session is the only party that knows the depth. `auditor.md` cannot choose
# its own model — by the time it runs, the choice has been made.
#
# Verified at the dispatch itself before this was written, out of the harness's
# own record rather than by argument: every `Task` result carries a
# `resolvedModel`, and across 151 recorded dispatches in this project the
# Agent-tool `model` override took in 19 of 19 cases where one was passed
# (`fable` -> `claude-fable-5`), while every auditor dispatch with no override
# resolved to whatever `auditor.md`'s frontmatter said at that moment — opus
# throughout, except three runs on the evening of 2026-08-17 that fall exactly
# between `86b0c56` (frontmatter set to sonnet) and `a540756` (set back to
# opus). So both mechanisms are observed to work, which is what lets the
# fallback below be a real backstop rather than a hope.

def test_the_auditor_s_model_is_chosen_by_depth():
    """Both tiers must be named against their depths, in the file the
    dispatching session reads. Asserting on the tier words alone would pass on
    a paragraph that named them without binding them to a depth, so each depth
    is checked against the tier it must select."""
    text = (ROOT / ".claude" / "skills" / "audit-fix" / "SKILL.md").read_text(
        encoding="utf-8")

    assert "model" in text.lower(), (
        "audit-fix/SKILL.md must tell the dispatching session to set the "
        "auditor's model")

    # The paragraph, not the whole file: `sonnet` and `opus` both appear in
    # unrelated prose further down (the reconcile_findings history at ~line
    # 668), so a file-wide substring check would pass without the instruction
    # existing at all.
    para = [b for b in text.split("\n\n")
            if "sonnet" in b.lower() and "opus" in b.lower()
            and "deep" in b.lower()]
    assert para, (
        "audit-fix/SKILL.md must carry one paragraph that names both tiers "
        "against the depths they serve - no such paragraph was found")

    joined = "\n\n".join(para).lower()
    for depth, tier in (("deep", "opus"), ("standard", "sonnet")):
        assert depth in joined and tier in joined, (
            f"the model-by-depth instruction must say that `{depth}` runs on "
            f"{tier}")

    assert "triage" in joined, (
        "the instruction must say which tier `triage` runs on; a depth left "
        "unnamed falls to the frontmatter default by accident rather than by "
        "decision")


def test_the_auditor_still_defaults_to_the_strongest_tier():
    """Fail toward quality. If the per-depth override is ever dropped or
    mistyped, the dispatch falls to this frontmatter — observed above to be
    what actually happens — and a deep or a CLEAN-declaring audit must never
    silently run on the cheaper tier."""
    text = (ROOT / ".claude" / "agents" / "auditor.md").read_text(
        encoding="utf-8")

    front = text.split("---")[1] if text.startswith("---") else text
    assert "model: opus" in front, (
        "auditor.md's frontmatter must still default to opus, so that a "
        "missing per-depth override fails toward quality")

    skill = (ROOT / ".claude" / "skills" / "audit-fix" / "SKILL.md").read_text(
        encoding="utf-8")
    assert "auditor.md" in skill and "default" in skill.lower(), (
        "audit-fix/SKILL.md must say what the dispatch falls back to, so the "
        "reader of the instruction knows the failure direction")


# --------------------------------------------------------------------------
# Q-39 — one owner for what a red baseline means
# --------------------------------------------------------------------------

#: The phrase `.claude/DISCIPLINE.md` rule 6 carries the re-run carve-out
#: under. A marker phrase rather than a line number, for the reason the
#: profile's anchor invariant gives: a name does not go stale when the file
#: grows around it.
#: The carve-out's own heading, and the handle every guard below uses to
#: find it. Changed 2026-09-06 by `QUESTIONS.md` Q-48, which replaced the
#: mechanism: the carve-out is no longer "a red the re-run clears" but a
#: red that will not reproduce when the node is run alone. The guards are
#: unchanged - one owner for the rule, and the section decides the verify
#: case - because Q-48 moved what the rule says and not where it lives.
CARVE_OUT_MARKER = "A red that will not reproduce"

#: The bullet in a skill's preflight that says what a red suite means. Written
#: as a pattern over the tree rather than as a path, so a second skill growing
#: its own copy of the bullet is inside the population rather than outside it.
_RED_BULLET = re.compile(r"^\s*-\s+\*\*Red\*\*.*?(?=^\s*-\s+\*\*|\Z)",
                         re.M | re.S)


def test_the_re_run_carve_out_is_stated_once():
    """`QUESTIONS.md` Q-39: a green re-run of an unchanged tree is a valid
    baseline only for the filed load-sensitive class.

    The failure this guards is not the rule being wrong, it is the rule being
    stated twice. `DISCIPLINE.md`'s own header records that two copies of one
    rule is how these rules drifted before, and Q-39 exists because the
    handling of an intermittent red was decided per round: rounds 100, relay
    090 and relay 100 took the green re-run, rounds 109 and 115 stopped on the
    red, and nothing in `.claude/` said which was right.
    """
    assert len(INSTRUCTION_FILES) >= 5, [_rel(p) for p in INSTRUCTION_FILES]

    carriers = [_rel(p) for p in INSTRUCTION_FILES
                if CARVE_OUT_MARKER in p.read_text(encoding="utf-8")]

    assert carriers == [".claude/DISCIPLINE.md"], (
        f"{CARVE_OUT_MARKER!r} must appear in .claude/DISCIPLINE.md and "
        f"nowhere else — one owner for the rule, per that file's own header. "
        f"Found in: {carriers}")


def test_every_red_bullet_defers_to_the_rule_rather_than_restating_it():
    """The consumer side of the same property.

    A preflight that says what a red means without pointing at rule 6 is free
    to say something else, which is the state Q-39 was asked from. The
    population is every `**Red**` bullet in the tree rather than the one path
    that has one today: a copy of the bullet in another skill is exactly the
    drift being guarded, so it must be inside the set that is checked.
    """
    bullets = [(_rel(p), m.group(0))
               for p in INSTRUCTION_FILES
               for m in _RED_BULLET.finditer(p.read_text(encoding="utf-8"))]

    assert bullets, (
        "no **Red** bullet found in any instruction file — the collector "
        "broke, or the preflight stopped saying what a red is")

    silent = [rel for rel, body in bullets if "rule 6" not in body]
    assert silent == [], (
        f"these say what a red means without citing DISCIPLINE rule 6, which "
        f"owns the re-run carve-out: {silent}")


# --------------------------------------------------------------------------
# Q-42 — the carve-out answers verify as well as the baseline
# --------------------------------------------------------------------------

#: Everything rule 6 says about the re-run, taken from its marker phrase to
#: the start of the next rule. Sliced by heading rather than by line number so
#: the guard does not go stale when the file grows above it.
def _carve_out_section() -> str:
    body = (ROOT / ".claude" / "DISCIPLINE.md").read_text(encoding="utf-8")
    start = body.index(CARVE_OUT_MARKER)
    end = body.index("\n## 7.", start)
    return body[start:end]


#: The phrases a file uses to say a question is still open. Q-42 was asked
#: because rule 6 carried one of them in terms; once it is answered, an
#: instruction file still saying so sends the next round to ask again.
_UNANSWERED = (
    "does not answer yet",
    "is asking something this file does not answer",
)


def test_the_carve_out_says_what_a_red_verifying_run_means():
    """`QUESTIONS.md` Q-42, answered *extend the carve-out to verify, on the
    same terms* by the operator, 2026-09-01.

    Rule 6 governed the step-5 baseline and said in terms that verify was
    unanswered, so a round whose *verifying* run came back red on a filed
    load-sensitive node had nowhere to go: the work is already done and the
    tree is dirty, which refuses the next preflight in turn. Relay 123 met
    exactly that shape and got past it only because its commit was receipt
    registers alone.

    The property is that the section decides the verify case rather than
    deferring it — not which way it decides, which is the operator's.

    Of the two assertions, the second is the one that was red before the fix.
    The first was already satisfied — the old wording mentioned verify in
    order to defer it — and is kept as a floor, so that a later edit cannot
    satisfy the second by deleting the verify clause outright.
    """
    section = _carve_out_section()

    assert "verif" in section, (
        "DISCIPLINE rule 6's carve-out must say what a red verifying run "
        "means; Q-42 was asked because it did not")

    still_open = [p for p in _UNANSWERED if p in section]
    assert still_open == [], (
        f"rule 6 still records the verify case as unanswered, but Q-42 "
        f"answered it: {still_open}")


def test_no_instruction_file_re_opens_the_answered_verify_question():
    """The consumer side: the answer has to reach the file a round reads.

    A skill that repeats "this file does not answer yet" is a second copy of
    a rule that has since moved, which is the drift `DISCIPLINE.md`'s own
    header exists to prevent. The population is every instruction file, so a
    skill growing its own copy of the sentence is inside the set.
    """
    stale = sorted(
        _rel(p) for p in INSTRUCTION_FILES
        for phrase in _UNANSWERED
        if phrase in p.read_text(encoding="utf-8"))

    assert stale == [], (
        f"these still send a round to ask a question the operator has "
        f"answered (Q-42): {stale}")
