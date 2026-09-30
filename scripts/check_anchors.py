"""Make an evidence anchor checkable — the key the whole backlog is filed on.

WF-44 and WF-43, round 044, which the report pairs as "the two halves of an
unverifiable backlog". An anchor is two things at once: the address a fix is
sent to, and the key that ages a finding. Neither use was checked.

  WF-44 — five anchors in the carried set do not resolve. `provenance.py` is
          157 lines and two findings cite `:338-350` and `:285-305,313-335`;
          `test_provenance.py` is 112 and CQ-65 cites `:974-991`; `favicon.ts`
          is 44 and UX-30 cites `:470-486`; `test_packaging.py` is 207 and
          CQ-20 cites `:194-209`. The oldest ran for fifteen reports, and
          `audits/038-2026-08-17.md:166` re-asserts one as "re-read at" a
          range that has never existed in that file.

  WF-43 — the ten-round disposition gate has not run for four rounds, and
          four qualifying findings never entered `audits/DISPOSITIONS.md` at
          all. Its one guard counts the rows it can see, so a row nobody
          wrote is invisible to it by construction.

Both are decidable from `audits/` and neither was being decided, so this
decides them. Three checks, one key:

    resolve — every anchor in a report names a file that exists and a line
              that file reaches.
    cohort  — every anchor at ten or more reports has a row in DISPOSITIONS.
    source  — the same resolve judgement, over the comments in product source
              rather than the Evidence column of a report.

`source` is Q-16, answered by the operator on 25 August 2026, and it is the
same rule pointed at a second corpus rather than a second rule. CQ-151 was
first raised in report 073 and carried by eleven reports; the remedy was given
twice, held neither time, and the count grew in eight of those rounds because
nothing derived the population — a report can only re-list the pointers
somebody typed into the last one. `source_files` walks the tree instead. See
`SOURCE_ROOTS` for why `tests/` is not in it and `unresolvable_source` for
what resolution does not decide.

Why a script and not only a test. `tests/test_loop_instructions.py` states why
`audits/**` is absent from `REGISTER_FILES`: a report is an untouched record
committed on its own and a round may not edit one, so a pytest firing on a
report's own content could only be satisfied by breaking that rule. `resolve`
therefore runs here, at step 2, the way `scripts/reconcile_findings.py`
already does — the established precedent for a per-round mechanical check on
report content. `cohort` is different and is a pytest as well: its remedy is
adding a row to a register, which a round may do. `source` is on the `cohort`
side of that line and for the same reason — the remedy is editing a comment,
which a round may always do — so it is held to zero by
`test_every_source_comment_anchor_resolves` and reported here as well.

Usage:

    .venv\\Scripts\\python.exe scripts\\check_anchors.py
    .venv\\Scripts\\python.exe scripts\\check_anchors.py --context

Exit 0 with "clean" when all three checks pass, 1 naming every failure
otherwise.

`--context` adds a third thing, and it is not a check. WF-96, round 091: a
High whose anchor resolved perfectly was carried by twenty-eight consecutive
reports after the code it described had been repaired. Neither check above
can see that, because both are about the address. The flag prints each row's
lead sentence *and its stated consequence* beside the source line at every
anchor it cites, so the drift is visible to the person doing the carry. Both
cells, because round 131 measured that 172 of the 176 rows emitted from
report 131 lead with a carry note rather than a claim — the lead sentence
alone is what made this flag blind to its own founding case. It never changes
the exit status.

It reports what it skipped, not only what it checked. A report writes bare
filenames — `app.py:629`, `render.py` — as shorthand inside a row whose full
path is stated elsewhere, and those are unresolvable by construction rather
than wrong. They are counted and named in the summary, because DISCIPLINE
rule 4 is that coverage nobody reports is coverage nobody has.

In source, that count turned out to be the question rather than the answer.
`QUESTIONS.md` Q-28 asked whether a bare citation should be resolved or
forbidden and was answered *resolve them*, so `unresolvable_bare_source` puts
each one to the tree: resolved where exactly one file bears the name, refused
loudly where two do, and counted as no address at all where none does. The
audits half still only counts, because a report is a record a round may not
edit and the remedy resolution would create is not available there.
"""

from __future__ import annotations

import os
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: An anchor inside a code span: a repo-relative path, then one or more line
#: references. `path:12`, `path:12-20`, `path:12-20,44-50`, `path:12,44`.
#:
#: The path must contain a directory separator. A bare `app.py:629` cannot be
#: resolved *by this pattern* without guessing which of the several `app.py`
#: files is meant, and guessing is the class of mistake WF-44 is about — so it
#: is skipped here and counted through `BARE`.
#:
#: On the source side that skip is no longer the end of it: Q-28 was answered
#: *resolve them*, and `unresolvable_bare_source` asks the tree which file
#: bears the name. The guess this pattern refuses to make is still refused —
#: it is refused where the ambiguity actually is, on the names two files bear,
#: and that case reddens rather than passing quietly.
ANCHOR = re.compile(
    r"(?P<path>[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)+\.[A-Za-z0-9]+)"
    r":(?P<lines>\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*)")

#: The same shape without a directory, used for the skip count only.
BARE = re.compile(
    r"(?<![A-Za-z0-9_./\-])(?P<path>[A-Za-z0-9_\-]+\.[A-Za-z0-9]+)"
    r":(?P<lines>\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*)")


def _highest_line(lines: str) -> int:
    """The largest line number an anchor reaches.

    A range's end, not its start: `:194-209` against a 207-line file is the
    real CQ-20 defect, and a check reading only the start would pass it.
    """
    return max(int(n) for n in re.findall(r"\d+", lines))


def anchors(text: str) -> list[tuple[str, str]]:
    """Every `(path, lines)` pair with a directory component, deduplicated
    but order-preserving so the first mention is what gets reported."""
    seen: dict[tuple[str, str], None] = {}
    for m in ANCHOR.finditer(text):
        seen.setdefault((m.group("path"), m.group("lines")), None)
    return list(seen)


def bare_anchors(text: str) -> list[tuple[str, str]]:
    """Anchors with no directory — skipped, reported, never resolved."""
    seen: dict[tuple[str, str], None] = {}
    for m in BARE.finditer(text):
        seen.setdefault((m.group("path"), m.group("lines")), None)
    return list(seen)


# --------------------------------------------------------------------------
# Relay 105 — an address a clean checkout can never have
# --------------------------------------------------------------------------


def generated_prefixes(root: Path = ROOT) -> tuple[str, ...]:
    """The directories holding generated output, read from `.gitignore`.

    A path under one of these cannot resolve on a clean checkout, because
    nothing ever commits one. Resolving it anyway makes the guard's answer a
    fact about the machine rather than about the tree: `render.py`'s
    version-history note cites a client document the renderer wrote here on
    22 August 2026, and the guard was green on the operator's disk — where
    that document sits — and red on every CI runner. A check that disagrees
    with itself across two checkouts of one commit is not deciding anything.

    So the exclusion is unconditional, not "skip it when it happens to be
    missing". The conditional form would keep the nondeterminism and only
    change which side of it was quiet, which is KI-15's defect again.

    Derived rather than listed, for CQ-151's reason one level out: a tuple of
    output directories written here would be a second declaration of what
    `.gitignore` already states, and the two would drift the first time a
    build wrote somewhere new. Directory entries only — a line ending in `/`,
    with no negation and no wildcard. The rest of git's matching language is
    deliberately not reimplemented: every line skipped here is a prefix this
    function does not know about, so the failure direction is a citation
    still being resolved, which reddens loudly, rather than one silently
    excused.
    """
    ignore = root / ".gitignore"
    if not ignore.is_file():
        return ()
    found: list[str] = []
    for line in ignore.read_text(encoding="utf-8",
                                 errors="replace").splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#") or entry.startswith("!"):
            continue
        if not entry.endswith("/") or any(ch in entry for ch in "*?["):
            continue
        found.append(entry.strip("/"))
    return tuple(sorted(set(found)))


def is_generated(path: str, prefixes: tuple[str, ...]) -> bool:
    """Whether an anchor's path lies inside one of `prefixes`.

    Read the way git reads the entries it came from: a prefix containing a
    separator (`reports/out`, `dashboard/dist`) is anchored at the repository
    root, and one without (`__pycache__`, `build`) matches a directory at any
    depth. Matching a bare `reports` against `reports/out` would be the
    mistake this is built not to make — `reports/` is committed and only
    `reports/out/` is not.
    """
    parts = path.split("/")
    for entry in prefixes:
        segments = entry.split("/")
        if len(segments) > 1:
            if (len(parts) > len(segments)
                    and parts[:len(segments)] == segments):
                return True
        elif entry in parts[:-1]:
            return True
    return False


def generated_anchors(text: str, root: Path = ROOT) -> list[tuple[str, str]]:
    """Anchors under generated output — skipped, reported, never resolved.

    The sibling of `bare_anchors`, and it exists for the same reason that one
    does: DISCIPLINE rule 4, coverage nobody reports is coverage nobody has.
    Returned rather than counted inside `unresolvable` so `main` can name what
    it declined to check without that function growing a second return value.
    """
    prefixes = generated_prefixes(root)
    return [(path, lines) for path, lines in anchors(text)
            if is_generated(path, prefixes)]


#: The pillar tables' header. All four carry it identically in every report
#: from 026 on, and `Evidence` is column four.
_PILLAR_HEADER = "| ID | Finding | Severity | Evidence | Impact |"
_EVIDENCE_COLUMN = 4
#: `Impact` is column five — the row's own statement of what the defect costs,
#: and the only cell of a carried row that reliably says something about the
#: code rather than about whether the anchor moved. Derived from the evidence
#: column rather than written as `5`, so the two cannot drift apart if the
#: board's table ever gains a column ahead of them.
_IMPACT_COLUMN = _EVIDENCE_COLUMN + 1


def evidence_cells(text: str) -> str:
    """Just the Evidence column of every pillar table, joined.

    The column an anchor is *used* in, which is not the same as everywhere an
    anchor appears — and the difference is the whole reason this function
    exists rather than scanning the document. A row that corrects a bad anchor
    quotes the bad one in its Finding cell to say what was wrong with it —
    this paragraph does the same thing one level up, so it is marked
    `anchor-quote` and `unresolvable_source` skips it for the reason given
    there: report 044's CQ-65 reads "the prior anchor
    `tests/test_provenance.py:974-991` names a file of 112 lines", and
    WF-44's own row quotes all five. Scanning
    the whole report reported those quotations as defects, which would make a
    round's honest account of a mistake indistinguishable from repeating it,
    and would leave the check unsatisfiable by any report that explains
    itself.

    Cells are split on an unescaped pipe. `\\|` inside a code span is a GFM
    escape, not a boundary — CQ-86 is the same defect in the register guard,
    found the same round, and repeating it here would drop the tail of any
    evidence cell quoting a rule with an alternation in it.
    """
    out = []
    in_table = False
    for line in text.split("\n"):
        if line.startswith(_PILLAR_HEADER):
            in_table = True
            continue
        if not in_table:
            continue
        if not line.startswith("|"):
            in_table = False
            continue
        cells = re.split(r"(?<!\\)\|", line)
        if len(cells) > _EVIDENCE_COLUMN:
            out.append(cells[_EVIDENCE_COLUMN])
    return "\n".join(out)


_FINDING_ID = re.compile(r"^(CQ|WF|UX|UI)-\d+$")


def findings_by_path(text: str) -> dict[str, list[tuple[str, str]]]:
    """`path -> [(finding id, severity), ...]` from the pillar tables.

    What a register row is *for*. `undispositioned` answers which paths are
    missing; this answers what would go in the row, so the entries added to
    `DISPOSITIONS.md` name findings that exist in the report rather than a
    file someone believed had one.
    """
    out: dict[str, list[tuple[str, str]]] = defaultdict(list)
    in_table = False
    for line in text.split("\n"):
        if line.startswith(_PILLAR_HEADER):
            in_table = True
            continue
        if not in_table:
            continue
        if not line.startswith("|"):
            in_table = False
            continue
        cells = re.split(r"(?<!\\)\|", line)
        if len(cells) <= _EVIDENCE_COLUMN:
            continue
        fid, severity = cells[1].strip(), cells[3].strip()
        if not _FINDING_ID.match(fid):
            continue
        for path, _ in anchors(cells[_EVIDENCE_COLUMN]):
            out[path].append((fid, severity))
    return dict(out)


def unresolvable(text: str, root: Path = ROOT) -> list[str]:
    """Every anchor naming a file that does not exist, or a line past its end.

    Returns rendered strings rather than tuples: this output is read by a
    person deciding whether a finding's address is real, and the file's true
    length beside the citation is the whole diagnosis.
    """
    prefixes = generated_prefixes(root)
    bad = []
    for path, lines in anchors(text):
        if is_generated(path, prefixes):
            # Never resolvable on a clean checkout — see `generated_prefixes`.
            # Counted and named by `generated_anchors` for the summary.
            continue
        target = root / path
        if not target.exists():
            bad.append(f"{path}:{lines} — no such file")
            continue
        if not target.is_file():
            bad.append(f"{path}:{lines} — not a file")
            continue
        length = len(target.read_text(encoding="utf-8", errors="replace")
                     .splitlines())
        if _highest_line(lines) > length:
            bad.append(f"{path}:{lines} — file is {length} lines")
    return bad


# --------------------------------------------------------------------------
# WF-96 — the claim beside the code, because an address cannot carry it
# --------------------------------------------------------------------------

#: How much of a row's Finding cell is printed. The whole cell is a paragraph
#: in most rows; the first sentence is the claim, and the rest is the account
#: of how it was carried.
_CLAIM_CHARS = 200

_SENTENCE_END = re.compile(r"(?<=[.?!])\s")

#: A `**bold**` delimiter. Paired left to right; an odd one out is not a span.
_EMPHASIS = re.compile(r"\*\*")


def _emphasis_spans(text: str) -> list[tuple[int, int]]:
    """`(start, end)` of each `**...**` run, paired in order of appearance.

    An unpaired trailing `**` opens nothing. The alternative — treating it as
    a span reaching the end of the cell — would make one stray delimiter
    swallow the whole row, which is a worse answer than the one this is
    fixing.
    """
    marks = [m.start() for m in _EMPHASIS.finditer(text)]
    return [(marks[i], marks[i + 1] + 2) for i in range(0, len(marks) - 1, 2)]


def _claim(cell: str) -> str:
    """The row's own first sentence — the thing being re-read.

    **A sentence end inside a bold span is not a claim boundary.** CQ-231:
    this board's house style opens a new row with a short bolded lead, and the
    lead is itself several sentences — so splitting at the first `[.?!]`
    followed by whitespace landed inside it and printed a fragment. Report 100's own CQ-227 row began
    *"**New, measured over the tree. The Q-16 source-anchor check resolves 15
    of the 47 ..."* and `--context` printed the first thirty characters of it,
    for exactly the rows a round is told to check first: the newest Highs. The
    carried rows were served only because their `Claim as first raised in
    report NNN` prefix happens to have no internal sentence end.

    Emphasis-aware rather than style-aware. A rule keyed on "starts with `**`"
    would have to decide how much of a short lead is enough and would carry a
    threshold nobody can defend; skipping boundaries inside any span is one
    rule that leaves every unbolded row reading exactly as it did.
    """
    text = " ".join(cell.split()).strip()
    if not text:
        return ""
    spans = _emphasis_spans(text)
    claim = text
    for m in _SENTENCE_END.finditer(text):
        if any(start <= m.start() < end for start, end in spans):
            continue
        claim = text[:m.start()]
        break
    if len(claim) > _CLAIM_CHARS:
        claim = claim[:_CLAIM_CHARS] + "..."
    return claim


def _range_starts(lines: str) -> list[int]:
    """The first line of each range in an anchor: `12-20,44` -> [12, 44].

    The start, where `_highest_line` takes the end — the two answer different
    questions. Resolution asks whether the file reaches the anchor, so it
    needs the furthest line; reading asks what the row is pointing at, which
    is where the range begins.
    """
    return [int(part.split("-")[0]) for part in lines.split(",")]


def context_lines(text: str, root: Path = ROOT) -> list[str]:
    """The gate's re-read surface: each row's claim beside the source it cites.

    WF-96. An anchor resolving is not evidence the row still describes what is
    there. UX-09 was *"the scope line tags three figures through `m()` in one
    sentence"*; `ca8c02c` repaired it on 20 August 2026 and twenty-eight
    consecutive reports carried the row anyway, at High, counted in every
    `high:` line the loop reads and ranked by anchor age in every cohort walk.
    `unresolvable` could not have caught it: the address was correct the whole
    time, and stayed correct.

    So this does not try to decide whether a sentence still describes a
    function — nothing mechanical can, and a matcher that guessed would add a
    third unverifiable claim to the two already here. It puts the two side by
    side and leaves the judgement where it already lives, with the person
    doing the carry. That is the same shape as `unresolvable` returning
    rendered strings rather than tuples: the output is read by a person
    deciding something, so the diagnosis is what gets printed.

    **Two cells, because one of them is usually not the claim.** Round 131
    measured what this printed: of the 176 rows it emits from report 131,
    **172 lead with a carry note** — 97%, one of the two Highs among them.
    `_claim(cells[2])` takes the first sentence of the Finding cell, and this
    board's house style opens a *carried* row's Finding cell with an account
    of whether the anchor moved since the last report, not of what the row
    says. On UX-09's own row in report 043, three days after `ca8c02c`
    repaired it, the line printed here was `UX-09 (High) — Carried, unchanged
    bytes.` beside a line of `render.py`. The flag built to catch that case
    could not have, at the rows it exists for.

    The `Impact` cell was on the row the whole time and says something about
    the code: for that same row, *"The line written to make the document
    honest is its least readable sentence."* Printing it decides nothing — it
    is a cell the report already wrote — and it is what makes the lead
    sentence beside a source line judgeable rather than merely present.
    Watched failing by
    `tests/test_a_carried_row_is_read_by_more_than_its_carry_note.py`, which
    names all 176 rows before the repair and pins the UX-09 case to
    report 043.

    An anchor that cannot be read is printed as unreadable rather than
    skipped. A row whose address has gone bad is a drifted row by definition,
    so dropping it here would hide exactly the rows most worth looking at.
    """
    out: list[str] = []
    in_table = False
    for line in text.split("\n"):
        if line.startswith(_PILLAR_HEADER):
            in_table = True
            continue
        if not in_table:
            continue
        if not line.startswith("|"):
            in_table = False
            continue
        cells = re.split(r"(?<!\\)\|", line)
        if len(cells) <= _EVIDENCE_COLUMN:
            continue
        fid, severity = cells[1].strip(), cells[3].strip()
        if not _FINDING_ID.match(fid):
            continue
        found = anchors(cells[_EVIDENCE_COLUMN])
        if not found:
            continue
        out.append(f"{fid} ({severity}) — {_claim(cells[2])}")
        if len(cells) > _IMPACT_COLUMN:
            consequence = _claim(cells[_IMPACT_COLUMN])
            if consequence:
                out.append(f"  consequence: {consequence}")
        for path, lines in found:
            out.append(f"  {path}:{lines}")
            out.extend(f"    {rendered}"
                       for rendered in _source_at(root / path, path, lines))
    return out


def _source_at(target: Path, path: str, lines: str) -> list[str]:
    """`   12 | source` for each range start, or one unreadable marker."""
    if not target.is_file():
        return [f"(unreadable — no such file: {path})"]
    body = target.read_text(encoding="utf-8", errors="replace").splitlines()
    out = []
    for start in _range_starts(lines):
        if start < 1 or start > len(body):
            out.append(f"(unreadable — {path} is {len(body)} lines)")
            continue
        out.append(f"{start:>5} | {body[start - 1].rstrip()}")
    return out



# --------------------------------------------------------------------------
# WF-43 — the age of a finding, derived the register's own way
# --------------------------------------------------------------------------

REPORT = re.compile(r"^[0-9]{3}-\d{4}-\d{2}-\d{2}\.md$")


def reports(audits_dir: Path) -> list[Path]:
    return sorted(p for p in audits_dir.glob("*.md") if REPORT.match(p.name))


def anchor_ages(audits_dir: Path) -> dict[str, int]:
    """`path -> how many reports cite it`, over every report in `audits/`.

    Keyed on the path, not on `path:lines`. `DISPOSITIONS.md` says the anchor
    is the stable key, and records that a finding-ID column was proposed twice
    and rejected because the auditor renumbers IDs every round. Line numbers
    move for the same reason IDs do — eighteen carried rows in report 043 cite
    a corrected line number after a diff shifted them — so keying on the range
    would reset an age to one whenever code above it was edited, which is the
    failure this exists to measure rather than to reproduce.
    """
    ages: dict[str, set[str]] = defaultdict(set)
    for report in reports(audits_dir):
        text = report.read_text(encoding="utf-8", errors="replace")
        for path, _ in anchors(evidence_cells(text)):
            ages[path].add(report.name)
    return {path: len(names) for path, names in ages.items()}


#: The threshold `.claude/skills/audit-fix/SKILL.md` step 4 fires on.
COHORT_ROUNDS = 10


#: Anything in a register cell that looks like a repo path. Applied to one
#: table cell, never to the document: that narrowing is WF-45.
_PATHISH = re.compile(r"[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)*\.[A-Za-z0-9]+")


def _rows(text: str):
    """`(header cells, body cells)` for every GFM table in `text`.

    A table is a header line, a delimiter line, then body lines — the same
    shape `evidence_cells` walks, generalised because `DISPOSITIONS.md` has
    six tables under four different headers. Cells are split on an unescaped
    pipe, per CQ-86.
    """
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if not line.startswith("|") or i + 1 >= len(lines):
            continue
        if not re.match(r"^\|[\s:|-]+\|\s*$", lines[i + 1]):
            continue
        header = [c.strip().lower() for c in re.split(r"(?<!\\)\|", line)]
        for body in lines[i + 2:]:
            if not body.startswith("|"):
                break
            yield header, [c.strip() for c in re.split(r"(?<!\\)\|", body)]


#: A table's anchor and finding columns, found by what the column is *called*
#: rather than by an exact string. WF-48: the strike test below used
#: `"finding" in header`, which is exact membership in a list of cells, so it
#: ran only where a header read exactly `finding`. The register's
#: mechanically-derived tables head that column `findings in report 044`,
#: `finding behind it`, `finding in report 111` and forty-two more spellings —
#: measured at round 130, **116 of the register's 172 anchor-bearing rows had
#: no strike test at all**, and the register's own convention is to strike a
#: row the day the loop takes it. So the gate goes quiet for a path exactly
#: when the work on it finishes, which is the self-silencing WF-45 was written
#: to end and this leaves half-ended.
#:
#: `_ANCHOR_COL` has the identical shape and no defect yet — every anchor
#: column in the register reads exactly `anchor` today. It is widened with its
#: sibling because the two implement one rule, and fixing one of a pair is how
#: a partial fix passes (DISCIPLINE rule 3).
_ANCHOR_COL = re.compile(r"^anchors?\b")
_FINDING_COL = re.compile(r"^findings?\b")


def _column(header: list[str], pattern: re.Pattern[str]) -> int | None:
    """The first header cell matching `pattern`, or `None`.

    Anchored at the start of the cell rather than searched anywhere in it: a
    prose column mentioning a finding is not the finding column, and `^` plus
    `\\b` accepts every spelling the register uses without accepting a cell
    that merely contains the word.
    """
    for i, cell in enumerate(header):
        if pattern.match(cell):
            return i
    return None


def register_anchor_paths(register: str) -> set[str]:
    """Every path named in a live row's anchor cell, plus its bare filename.

    WF-45. The predecessor asked `path in register or Path(path).name in
    register` against the whole file as one string, and two live findings
    walked through it: `.claude/agents/auditor.md` at 11 reports discharged
    by a *sentence* mentioning `auditor.md`, and `clauditseo/modules/prf.py`
    at 42 reports — four live findings in report 044 — discharged by a
    `~~struck-through~~` row for a different finding closed at round 031.

    Three narrowings, each answering one of those:

    - **A row, not the document.** Prose about a file is not a decision about
      the findings in it.
    - **The anchor column, found by its header.** The register has two
      engineering tables of different shapes — `finding | anchor | rounds`
      and the derived `anchor | reports citing | ...` — so a positional read
      would silence one of them.
    - **Live rows only.** A strike means *this finding* was disposed of. Read
      as *this file* was, the register silences itself a little more with
      every disposition the loop completes.

    The bare-filename fallback survives, narrowed from the document to the
    anchor cells. Rows predating the derived table name `render.py` and
    `loc.py:21` without a directory while the reports key on full paths, so
    dropping it outright would report live decisions as missing — the false
    alarm the original docstring is right to err away from.
    """
    paths: set[str] = set()
    for header, cells in _rows(register):
        anchor_at = _column(header, _ANCHOR_COL)
        if anchor_at is None or anchor_at >= len(cells):
            continue
        finding_at = _column(header, _FINDING_COL)
        if (finding_at is not None and finding_at < len(cells)
                and "~~" in cells[finding_at]):
            continue
        for match in _PATHISH.finditer(cells[anchor_at]):
            paths.add(match.group(0))
    return paths | {Path(p).name for p in paths}


def undispositioned(audits_dir: Path, current_text: str,
                    threshold: int = COHORT_ROUNDS) -> list[str]:
    """Paths the current report still cites, old enough for the gate, with no
    live row in `DISPOSITIONS.md` naming them.

    Matched against `register_anchor_paths`, not against the register as one
    string — see there for the two live findings the containment test let
    through, and for what the rewrite does and does not narrow.
    """
    register = (audits_dir / "DISPOSITIONS.md").read_text(encoding="utf-8")
    dispositioned = register_anchor_paths(register)
    ages = anchor_ages(audits_dir)
    live = {path for path, _ in anchors(evidence_cells(current_text))}
    missing = []
    for path in sorted(live):
        if ages.get(path, 0) < threshold:
            continue
        if path in dispositioned or Path(path).name in dispositioned:
            continue
        missing.append(f"{path} — cited by {ages[path]} reports, no row")
    return missing


# --------------------------------------------------------------------------
# Q-16 — the same resolve check, pointed at the second corpus
# --------------------------------------------------------------------------

#: The three roots the Q-16 answer names. `tests/` is deliberately absent and
#: the reason is measurable rather than aesthetic: 62 anchors live there and
#: 23 do not resolve, of which 15 are fixtures in `tests/test_check_anchors.py`
#: — a file whose whole job is to hold wrong addresses so the resolver can be
#: shown finding them. A corpus where the defect is the point is not the same
#: corpus as one where it is a mistake, so it is left for its own decision
#: rather than folded in here under an answer that did not consider it.
SOURCE_ROOTS = ("clauditseo", "dashboard/src", "scripts")

#: What counts as source. Extension-keyed rather than "every file", because
#: the roots also carry lockfiles, minified bundles and fixtures where a
#: `path.ext:12` substring is data, not an address a reader is being sent to.
SOURCE_SUFFIXES = frozenset({".py", ".ts", ".tsx", ".js", ".css", ".ps1"})

#: The one escape, and it is the source analogue of `evidence_cells`.
#:
#: A report quotes a bad anchor in its Finding cell to say what was wrong with
#: it, and `evidence_cells` narrows to the Evidence column so that an honest
#: account of a mistake is not read as the mistake. Source has no column to
#: narrow to — a docstring is prose all the way down — so the distinction is
#: declared instead: a comment paragraph carrying this token is discussing an
#: address, not giving one, and its anchors are counted and reported but not
#: resolved.
#:
#: Scoped to the paragraph rather than the line because the case that forced
#: it spans two lines: `evidence_cells`'s own docstring quotes report 044's
#: CQ-65 across a line break, and a same-line rule would have required
#: rewrapping a quotation to satisfy a checker. Scoped to the paragraph rather
#: than the file because file scope would blind this module — the one file in
#: the tree most likely to accumulate quoted bad addresses — to its own rule.
QUOTE_MARKER = "anchor-quote"


def source_files(root: Path = ROOT) -> list[Path]:
    """Every source file under `SOURCE_ROOTS`, walked from the tree.

    The population, derived rather than listed. Q-16's answer requires this in
    as many words, and the requirement is not pedantry: CQ-151 was carried by
    eleven consecutive reports as a list of four or five named files, and the
    count grew in eight of those rounds because a list only knows the
    instances someone typed into it. A walk finds the next one for free.

    Sorted, so the failure list is stable between runs and a diff of two runs
    is a diff of what changed rather than of directory order.
    """
    found: list[Path] = []
    for name in SOURCE_ROOTS:
        base = root / name
        if not base.is_dir():
            continue
        found.extend(p for p in base.rglob("*")
                     if p.is_file() and p.suffix in SOURCE_SUFFIXES)
    return sorted(found)


def source_citations(
        text: str,
        pattern: "re.Pattern[str]" = ANCHOR) -> list[tuple[int, str, str, bool]]:
    """`(line number, path, lines, quoted)` for every anchor in one file.

    `pattern` is `ANCHOR` for the citations that get resolved and `BARE` for
    the ones that get counted, because the two populations are found by one
    walk and differ only in what a citation looks like. CQ-227: the source
    half reported no skip count at all while the audits half three lines
    above printed one, so two thirds of the source population sat behind a
    clean line. Parameterised here rather than given a second paragraph walk,
    so both counts come from one reading of the file — two walks are how the
    two would come to disagree about where a paragraph ends.

    Paragraphs are runs of consecutive non-blank lines, which is the one
    structure `.py`, `.tsx` and `.css` comments share: a docstring paragraph
    and a `/* ... */` block both end at a blank line, and neither needs a
    per-language comment parser to find. `quoted` is whether that paragraph
    carries `QUOTE_MARKER`.

    Not deduplicated, where `anchors` deduplicates. The two answer different
    questions: a report cites one address once and the first mention is what
    gets reported, but the same wrong pointer written into three files is
    three repairs, and collapsing them would report two of them as done.
    """
    out: list[tuple[int, str, str, bool]] = []
    lines = text.split("\n")
    para: list[str] = []
    start = 0
    for i, line in enumerate(lines + [""]):
        if line.strip():
            if not para:
                start = i
            para.append(line)
            continue
        if not para:
            continue
        quoted = QUOTE_MARKER in "\n".join(para)
        for offset, para_line in enumerate(para):
            for m in pattern.finditer(para_line):
                out.append((start + offset + 1, m.group("path"),
                            m.group("lines"), quoted))
        para = []
    return out


def bare_source_citations(root: Path = ROOT) -> list[str]:
    """Every citation in source comments whose path carries no directory.

    CQ-227. The audits half prints `N bare filenames skipped`; the source half
    printed nothing, while `ANCHOR` skips a citation with no directory by
    construction — `runs.py:1820` cannot be resolved without guessing which
    `runs.py` is meant, and guessing is the mistake WF-44 is about. So these
    were unresolvable rather than wrong, exactly as they are on the audits
    side, so counting them was the first defensible thing to do with them.
    (`anchor-quote`: the address in this paragraph is the example, not a
    pointer, and counting it would make this docstring inflate the number it
    describes.)

    **This is now the population and no longer the verdict.** Q-28 asked what
    to do with the 92 this counted and was answered *resolve them*, so
    `unresolvable_bare_source` reads the same population and puts each one to
    the tree. This function stays because a count of what was reached is only
    meaningful beside a count of what there was, and because the two are
    found by one rule — "no directory" — which is worth having in one place.

    The count carries the same noise its audits-side sibling does — a host and
    port, a made-up filename used as an example — because that one rule cannot
    tell them apart, and a matcher clever enough to try would be guessing
    about exactly the thing WF-44 says not to guess about. Reported as what it
    is rather than filtered into looking tidier; which of them are addresses
    is a question the tree answers, one function down.

    Not deduplicated, for `source_citations`' own reason: the same bare
    pointer written into three files is three repairs, and collapsing them
    would report two of them as done.

    Quoted paragraphs are excluded on the same judgement `unresolvable_source`
    makes — a paragraph marked `QUOTE_MARKER` is quoting an address rather
    than giving one, so counting it as a skip would inflate the number with
    text that was never a citation.
    """
    out: list[str] = []
    for source in source_files(root):
        where = source.relative_to(root).as_posix()
        text = source.read_text(encoding="utf-8", errors="replace")
        for line_no, path, lines, quoted in source_citations(text, BARE):
            if quoted:
                continue
            out.append(f"{where}:{line_no} cites {path}:{lines}")
    return out


def tree_basenames(root: Path = ROOT) -> dict[str, list[str]]:
    """Every filename in the tree, indexed by basename to the paths bearing it.

    What `unresolvable_bare_source` resolves against, and the reason Q-28's
    answer is decidable at all: the question "which `render.py` is meant" has
    an answer whenever exactly one file bears the name, and this is what
    computes it.

    **Walked from the whole tree, not from `SOURCE_ROOTS`.** Measured over
    this repository: six of the 41 resolvable bare citations name a file the
    source walk never sees — `OPERATOR_ACTIONS.md` cited from `api/app.py`,
    `views.tsx` and `rotate-registers.ps1`, `clauditseo/prompts/triage.md`
    cited from `expert.py`, and `.claude/loop/PROFILE.md` cited from
    `prove_fail.py`. Indexing only the population the check reads would
    report those six as naming no file, which is a clean line over a real
    gap — CQ-227's own defect, one level in.

    **Generated output is excluded**, on `is_generated`'s judgement and for
    `generated_prefixes`' reason: a name that exists only in a build
    directory would resolve on the machine that built it and not on any
    other, and — worse here than there — a built copy of a source file would
    turn a unique name into an ambiguous one, so the guard's verdict would
    depend on whether anyone had run `npm run build`. `.git` is pruned as
    well; it is not in `.gitignore` because git does not ignore its own
    directory, and its contents are not files anybody cites.

    Sorted, so an ambiguous citation names its candidates in the same order
    on every machine and the failure text is diffable.
    """
    prefixes = generated_prefixes(root)
    index: dict[str, list[str]] = defaultdict(list)
    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath).relative_to(root).as_posix()
        prefix = "" if here == "." else f"{here}/"
        # A directory holding its own `.git` (a file, for a worktree) is a
        # second checkout of this repository - `.claude/worktrees/*` while a
        # parallel session runs - and every file in it would turn a unique
        # name ambiguous. Found 2026-09-14 when one appeared mid-suite and
        # this guard resolved nothing at all.
        dirnames[:] = [d for d in dirnames
                       if d != ".git"
                       and not os.path.exists(os.path.join(dirpath, d, ".git"))
                       and not is_generated(f"{prefix}{d}/x", prefixes)]
        for name in filenames:
            index[name].append(f"{prefix}{name}")
    return {name: sorted(paths) for name, paths in index.items()}


def unresolvable_bare_source(
        root: Path = ROOT) -> tuple[list[str], int, int, int]:
    """`(failures, resolved, ambiguous, unmatched)` over the bare citations.

    Q-28, answered *resolve them* by the operator on 2026-08-31. The source
    half checked 15 citations and skipped 92; this is what closes the gap
    CQ-227 measured, and `bare_source_citations` — which counts the same 92 —
    is what made the gap visible enough to be asked about.

    The tree decides, in three ways, and each is reported as its own number
    because each is a different judgement:

    - **Exactly one file bears the name** — resolved, on the same rule
      `unresolvable_source` applies: the file must exist and must reach the
      line. 41 of the 92 today.
    - **Two or more do** — refused, and it *reddens*. This is the condition
      Q-28's own answer attaches to the widening: it is only safe while the
      ambiguous case is refused loudly. `ANCHOR`'s stated ground for skipping
      every bare citation — that guessing which `app.py` is meant is the
      class of mistake WF-44 is about — is true of this case and only of it,
      so the refusal moves here rather than being dropped. A counted skip
      would not do: the day a second `render.py` lands, every citation to it
      would silently stop being checked while the summary went on printing a
      clean line, which is CQ-227 again with a different population. The
      repair is one word — give the comment its directory. Zero today; the
      five duplicated basenames in the tree are `README.md`, `SKILL.md`,
      `__init__.py`, `base.py` and `types.py`, and none is cited bare.
    - **No file bears it** — not an address, counted and named. 51 of the 92
      today, and 47 of those are CSS contrast ratios written `4.5:1`, the
      rest a host and port, a minified bundle's `t.y:0`, and this module's
      own `path.ext:12` example. (`anchor-quote`: those three are the
      examples, not pointers, and counting them would make this paragraph
      inflate the number it describes — which it did, by exactly three, in
      the first run after it was written.) `BARE` cannot tell those from a
      citation,
      and a matcher clever enough to try would be guessing about exactly what
      WF-44 says not to guess about — so the population is not filtered into
      looking tidier, it is asked of the tree.

    That third number is also why "forbid them outright", Q-28's other
    option, would have been a lint pointed at the wrong text: 51 of the 92 it
    would have demanded a directory for are not filenames.

    A separate function rather than two more return values on
    `unresolvable_source`, whose four-tuple has eleven unpacking sites in
    `tests/test_check_anchors.py` — the judgement `generated_anchors` and
    `bare_source_citations` already record, applied a third time.

    Quoted paragraphs are excluded on `bare_source_citations`' judgement: a
    paragraph marked `QUOTE_MARKER` is quoting an address rather than giving
    one. (`anchor-quote`: every address in this docstring is an example.)
    """
    index = tree_basenames(root)
    failures: list[str] = []
    resolved = 0
    ambiguous = 0
    unmatched = 0
    for source in source_files(root):
        where = source.relative_to(root).as_posix()
        text = source.read_text(encoding="utf-8", errors="replace")
        for line_no, path, lines, quoted in source_citations(text, BARE):
            if quoted:
                continue
            candidates = index.get(path, [])
            if not candidates:
                unmatched += 1
                continue
            if len(candidates) > 1:
                ambiguous += 1
                failures.append(
                    f"{where}:{line_no} cites {path}:{lines} — "
                    f"{len(candidates)} files bear that name "
                    f"({', '.join(candidates)}); say which")
                continue
            resolved += 1
            found = candidates[0]
            target = root / found
            length = len(target.read_text(encoding="utf-8", errors="replace")
                         .splitlines())
            if _highest_line(lines) > length:
                failures.append(f"{where}:{line_no} cites {path}:{lines} "
                                f"— {found} is {length} lines")
    return failures, resolved, ambiguous, unmatched


def unresolvable_source(
        root: Path = ROOT) -> tuple[list[str], int, int, int]:
    """`(failures, resolved, quoted, generated)` over the tree.

    The same judgement `unresolvable` makes for a report, and deliberately
    only that judgement: the file must exist and must reach the line. It does
    **not** decide whether the line still says what the comment claims, and
    that limit is worth stating because CQ-151's own evidence is drift of
    exactly that kind — `dashboard/src/schedule.tsx` cited a live line inside
    the wrong route. What makes the five repairable here is the other half of
    the rule: an address is repo-relative or it is not an address, and
    `api/app.py` resolves from no root in this tree, so re-writing it as
    `clauditseo/api/app.py:1683` forces the author back to the line. WF-96's
    `--context` is the audits-side admission of the same gap; source has no
    equivalent yet, and the honest thing is to say so rather than to imply
    the check is stronger than it is.

    Failures render with the citing file and line first, because the thing
    being repaired is the comment, not the file it points at.

    Two kinds are counted and not resolved, and neither is dropped silently:
    a paragraph marked `QUOTE_MARKER`, which is quoting an address rather than
    giving one, and a path under `generated_prefixes`, which no checkout of
    this commit is obliged to have. They are separate numbers because they are
    separate judgements — one is the author saying so, the other is
    `.gitignore` saying so.
    """
    prefixes = generated_prefixes(root)
    failures: list[str] = []
    resolved = 0
    quoted_count = 0
    generated_count = 0
    for source in source_files(root):
        where = source.relative_to(root).as_posix()
        text = source.read_text(encoding="utf-8", errors="replace")
        for line_no, path, lines, quoted in source_citations(text):
            if quoted:
                quoted_count += 1
                continue
            if is_generated(path, prefixes):
                generated_count += 1
                continue
            resolved += 1
            target = root / path
            if not target.is_file():
                failures.append(f"{where}:{line_no} cites {path}:{lines} "
                                f"— no such file")
                continue
            length = len(target.read_text(encoding="utf-8", errors="replace")
                         .splitlines())
            if _highest_line(lines) > length:
                failures.append(f"{where}:{line_no} cites {path}:{lines} "
                                f"— file is {length} lines")
    return failures, resolved, quoted_count, generated_count

def readable_output() -> None:
    r"""CQ-234. The tool prints what it read, so it must be able to print it.

    `--context` puts a report's own claim text on stdout, and a report is
    prose: em dashes, smart quotes, and the arrows a version bump is written
    with (`1.34.0` arrow `1.35.0`). On Windows a piped stdout takes the
    locale encoding rather than UTF-8, so `print` reaches
    `encodings/cp1252.py` and raises `UnicodeEncodeError` on the first
    character cp1252 has no slot for. The run dies part-way through the
    listing with a traceback and exits 1 - which is also the exit code for
    *"anchors did not resolve"*, so the failure arrives wearing the costume
    of a completed check.

    The encoding is left alone and only the error handler is replaced. Forcing
    UTF-8 would make the bytes undecodable by a consumer reading cp1252, which
    trades a crash for mojibake; `backslashreplace` keeps whatever the stream
    can carry and spells the rest as `\u2192`, so the output is always
    complete and always decodable by whoever asked for that encoding. Nothing
    here decides anything - it is the difference between finishing and not.

    stderr as well as stdout, because a diagnosis this tool cannot print is
    worth no more than a listing it cannot print.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            # Not a `TextIOWrapper` - a caller capturing into `StringIO` -
            # so there is no encode step in it to fail, and nothing to repair.
            continue
        reconfigure(errors="backslashreplace")


def main(argv: list[str], audits_dir: Path | None = None) -> int:
    readable_output()
    audits_dir = audits_dir or ROOT / "audits"
    found = reports(audits_dir)
    if not found:
        print("nothing to check — no reports exist yet")
        return 0

    current = found[-1]
    text = current.read_text(encoding="utf-8", errors="replace")

    evidence = evidence_cells(text)
    bad = unresolvable(evidence, audits_dir.parent)
    missing = undispositioned(audits_dir, text)
    # Q-16. Rooted at `audits_dir.parent` for the reason `unresolvable` is:
    # every caller that passes a temporary corpus gets a tree with no
    # `clauditseo/` in it, so the source half is silent there rather than
    # reaching around the fixture into the real repository.
    source_bad, source_seen, source_quoted, source_generated = (
        unresolvable_source(audits_dir.parent))
    # CQ-227. Counted through its own function rather than as a fifth return
    # value of `unresolvable_source`, whose four-tuple has eleven unpacking
    # sites in `tests/test_check_anchors.py` — the same judgement
    # `generated_anchors` records for the audits half: `main` can name what it
    # declined to check without that function growing another return value.
    source_bare = bare_source_citations(audits_dir.parent)
    # Q-28, answered "resolve them". The 92 above are no longer all skipped:
    # each is put to the tree, and the three answers it can give are three
    # numbers in the summary below. `bare_source_citations` stays as the
    # population's own count, so the line can say what share of it was
    # reached rather than only what was checked.
    (bare_bad, bare_resolved, bare_ambiguous,
     bare_unmatched) = unresolvable_bare_source(audits_dir.parent)

    generated = generated_anchors(evidence, audits_dir.parent)
    print(f"{current.name}: "
          f"{len(anchors(evidence)) - len(generated)} evidence anchors "
          f"checked, {len(bare_anchors(evidence))} bare filenames skipped, "
          f"{len(generated)} under generated output skipped, "
          f"{len(anchors(text)) - len(anchors(evidence))} outside the "
          f"Evidence column not checked")
    if bad:
        print(f"UNRESOLVABLE ANCHORS in {current.name}:")
        for line in bad:
            print(f"  {line}")
    if missing:
        print(f"UNDISPOSITIONED AT {COHORT_ROUNDS}+ REPORTS:")
        for line in missing:
            print(f"  {line}")
    print(f"source: {source_seen} comment anchors checked under "
          f"{', '.join(SOURCE_ROOTS)}, {len(source_bare)} bare filenames of "
          f"which {bare_resolved} resolved to a unique file, "
          f"{bare_ambiguous} refused as ambiguous and "
          f"{bare_unmatched} skipped as naming no file in the tree, "
          f"{source_quoted} quoted as defects and not resolved, "
          f"{source_generated} under generated output skipped")
    if source_bad or bare_bad:
        print("UNRESOLVABLE ANCHORS IN SOURCE:")
        for line in source_bad + bare_bad:
            print(f"  {line}")
    # WF-96. Printed after the two verdicts and before the exit, so it is a
    # reading surface rather than a third check: `--context` never decides
    # anything, and the status below is computed from `bad` and `missing`
    # exactly as it was. Opt-in because the default output is what step 2 and
    # CI read, and 516 anchors of source would bury the two lines that matter.
    if "--context" in argv:
        print(f"\ncontext — each row's lead sentence and stated consequence "
              f"beside the source it cites, for re-reading a carried finding "
              f"in {current.name}:\n")
        for line in context_lines(text, audits_dir.parent):
            print(line)
        print()

    if bad or missing or source_bad or bare_bad:
        return 1

    print(f"clean: every anchor in {current.name} resolves, every source "
          f"comment anchor resolves, and every one at "
          f"{COHORT_ROUNDS}+ reports has a row in DISPOSITIONS.md")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
