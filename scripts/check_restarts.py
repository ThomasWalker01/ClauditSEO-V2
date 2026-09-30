"""Compare the record the product keeps against the record the loop keeps.

WF-47, first raised at report 046 and carried to report 130 — the second
longest-standing High in the register, and un-gated on 2026-09-01 by
`QUESTIONS.md` Q-41.

**The defect in one sentence.** The running product writes a line to
`data/server-starts.jsonl` every time it starts; `OPERATOR_ACTIONS.md` records
most restarts but not all; and *nothing compares the two* — so an auditor
following its own instruction to read `OPERATOR_ACTIONS.md` before concluding a
finding is fixed can be told the product was untouched while it was in fact
restarted, with the proof sitting unread on the same disk.

That is not hypothetical and it is not history. Report 046 measured two starts
of ten with no matching row. Measured again at round 130, unchanged in
mechanism and worse in degree: **15 of 136 recorded starts have no
`OPERATOR_ACTIONS.md` row within fifteen minutes of them**. `grep -rn
server-starts .claude/ scripts/ tests/ clauditseo/` returned exactly one hit
for eighty-four consecutive reports — `clauditseo/provenance.py:44`, the
constant that writes the file. Nothing read it. This script is the reader.

## Why a script and not a pytest

The same reason `check_anchors.py`'s `resolve` is a script: the subject is not
committed. `data/` is covered by `.gitignore`, so the register this reads does
not exist on the CI gate, and a pytest over it could only be green by checking
nothing — the check-that-cannot-fail shape this repository has paid for
repeatedly. The half of WF-47 that *is* committed — whether the planner's
"every register the loop keeps" table names this file — is a pytest, and lives
in `tests/test_every_register_the_loop_keeps_has_a_row_in_the_planner_table.py`.

## What it does not claim

**A start with no row is a question, not a verdict.** Matching is by time
window against rows whose text names a restart, and both halves are
approximations: an operator can describe a restart in words this does not
match, and a row written fifteen minutes late falls outside the window. So the
output is phrased as *unaccounted*, and the exit code says only whether there
are any. It is the same shape as `context_lines` in `check_anchors.py` — put
the two records side by side and leave the judgement with the person doing the
carry, rather than adding a matcher that guesses and is believed.

**It never says a finding was or was not fixed.** It says the register the
auditor is about to trust is or is not complete over the window it is about to
read.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Read from the product rather than spelled again here, so a rename of the
#: register moves this script with it instead of silently emptying it.
sys.path.insert(0, str(ROOT))
from clauditseo.provenance import FILENAME as STARTS_FILENAME  # noqa: E402

STARTS = ROOT / "data" / STARTS_FILENAME
ACTIONS = ROOT / "OPERATOR_ACTIONS.md"

#: How far from a start a row may sit and still be taken as recording it.
#: Fifteen minutes because the obligation is discharged at the end of a round
#: while the restart happens inside it — WF-47's own first observation, where
#: the loop's own start left no row because "the obligation is discharged at
#: the end of a round while the action happens at the start".
WINDOW = timedelta(minutes=15)

#: A row that could be recording a restart. Deliberately generous: a false
#: match makes this quieter, and quiet is the failure mode it must not have —
#: so the words are checked against the *action* cell only, where a row states
#: what was done, rather than against the prose columns where a round explains
#: what it did not do.
_RESTART_WORDS = re.compile(
    r"restart|reinstall|\bserve\b|start(?:ed|ing)?\b|kill|reboot", re.I)

_ROW = re.compile(r"^\|\s*(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})\s*\|")


def _cells(row: str) -> list[str]:
    r"""The row's cells, split on an unescaped pipe.

    `(?<!\\)` per CQ-86: a `\|` inside a cell is content, not a boundary.
    """
    return [c.strip() for c in re.split(r"(?<!\\)\|", row)]


def starts(path: Path = STARTS) -> list[dict]:
    """Every recorded start, oldest first.

    A line that will not parse is kept as an error rather than skipped: this
    file is append-only and never rewritten, so an unreadable line is a defect
    in the writer and exactly the thing a reader must not swallow.
    """
    out: list[dict] = []
    if not path.is_file():
        return out
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
            when = datetime.fromisoformat(record["started_at"])
        except (ValueError, KeyError) as exc:
            out.append({"line": n, "error": f"{type(exc).__name__}: {exc}"})
            continue
        marker = record.get("marker") or {}
        out.append({
            "line": n,
            "at": when,
            "pid": record.get("pid"),
            "kind": marker.get("kind"),
            "subject": marker.get("subject"),
        })
    return out


def action_rows(path: Path = ACTIONS) -> list[tuple[datetime, str]]:
    """`(when, action cell)` for every dated row of the register."""
    out: list[tuple[datetime, str]] = []
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _ROW.match(line)
        if not m:
            continue
        cells = _cells(line)
        action = cells[3] if len(cells) > 3 else ""
        out.append((datetime.fromisoformat(f"{m[1]}T{m[2]}:00"), action))
    return out


def unaccounted(started: list[dict], rows: list[tuple[datetime, str]],
                since: datetime | None = None,
                window: timedelta = WINDOW) -> list[dict]:
    """Starts in the window with no register row that could be recording them.

    Compared naive-to-naive. The register writes local wall clock with no
    offset and the product writes an offset-aware timestamp; converting either
    way would need a rule for which zone the register meant, and there is none
    written down. Both are produced on this machine, so dropping the offset
    compares like with like — and a fifteen-minute window would absorb nothing
    a zone error could produce anyway, since a zone error is whole hours.
    """
    restarts = [when for when, action in rows if _RESTART_WORDS.search(action)]
    out: list[dict] = []
    for record in started:
        if "error" in record:
            out.append(record)
            continue
        naive = record["at"].replace(tzinfo=None)
        if since is not None and naive < since.replace(tzinfo=None):
            continue
        if any(abs((naive - when).total_seconds()) <= window.total_seconds()
               for when in restarts):
            continue
        out.append(record)
    return out


def commit_date(ref: str) -> datetime | None:
    """The commit's author date, for `--since <commit>`.

    Returns `None` rather than raising when the ref does not resolve, so a
    typo bounds nothing instead of aborting a gather step.
    """
    # Resolved, not handed over as a bare name — the rule
    # `test_no_program_is_handed_to_subprocess_by_bare_name` enforces, and it
    # caught this line on this round's verifying run. On Windows a bare name
    # resolves through System32 before PATH, so "usually the right one" is not
    # what a bound on an evidence window may be built on. Same shape as
    # `clauditseo/provenance.py`'s `_resolve_parent`, which learned it first.
    git = shutil.which("git")
    if not git:
        return None
    try:
        out = subprocess.run(
            [git, "log", "-1", "--format=%aI", ref],
            cwd=ROOT, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    try:
        return datetime.fromisoformat(out.stdout.strip())
    except ValueError:
        return None


def render(started: list[dict], rows: list[tuple[datetime, str]],
           gaps: list[dict], since: datetime | None) -> list[str]:
    bound = ("the whole register" if since is None
             else f"since {since.replace(tzinfo=None).isoformat(sep=' ')}")
    in_window = [r for r in started if "error" in r or since is None
                 or r["at"].replace(tzinfo=None) >= since.replace(tzinfo=None)]
    out = [f"{len(in_window)} recorded start(s) {bound}, "
           f"{len(rows)} dated row(s) in {ACTIONS.name}"]
    if not gaps:
        out.append("clean: every recorded start has a register row that could "
                   "be recording it")
        return out
    out.append(f"unaccounted: {len(gaps)} start(s) with no row within "
               f"{int(WINDOW.total_seconds() // 60)} minutes")
    for record in gaps:
        if "error" in record:
            out.append(f"  line {record['line']}: unreadable — "
                       f"{record['error']}")
            continue
        who = record["kind"] or "no marker — nobody claimed the tree"
        subject = f" {record['subject']}" if record.get("subject") else ""
        out.append(f"  {record['at'].isoformat(timespec='seconds')} "
                   f"pid {record['pid']} ({who}{subject})")
    out.append("A start with no row is a question, not a verdict: read the "
               "rows around it before treating a finding's disappearance as "
               "a repair.")
    return out


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Recorded server starts with no OPERATOR_ACTIONS.md row.")
    parser.add_argument(
        "--since", metavar="COMMIT_OR_DATE", default=None,
        help="bound the window, as the auditor's step 4b bounds its read of "
             "OPERATOR_ACTIONS.md: a commit-ish, or an ISO date")
    args = parser.parse_args(argv)

    since = None
    if args.since:
        try:
            since = datetime.fromisoformat(args.since)
        except ValueError:
            since = commit_date(args.since)
        if since is None:
            print(f"--since {args.since!r} is neither an ISO date nor a "
                  "commit this repository resolves; reading the whole "
                  "register instead", file=sys.stderr)

    if not STARTS.is_file():
        print(f"no result: {STARTS} does not exist, so nothing says whether "
              f"{ACTIONS.name} is complete. This is not a clean run.")
        return 2

    # Passed explicitly rather than left to the defaults: a default argument
    # is bound once, when the function is defined, so a caller that rebinds
    # `STARTS` or `ACTIONS` — a test, or a future `--register` flag — would be
    # silently reading the real files instead. Caught by
    # `test_the_exit_code_says_whether_anything_is_unaccounted`, which passed
    # its first assertion for the wrong reason before this line existed.
    started = starts(STARTS)
    rows = action_rows(ACTIONS)
    gaps = unaccounted(started, rows, since=since)
    for line in render(started, rows, gaps, since):
        print(line)
    return 1 if gaps else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
