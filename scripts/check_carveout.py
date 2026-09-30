"""Compare the suite runs that happened against what the record says about them.

WF-98, raised at report 132.

**The defect in one sentence.** `.claude/DISCIPLINE.md` rule 6 requires a round
that meets a red suite to quote the run's `.claude/run/` path, and *nothing
compares the logs on disk with the commits*, so a red met and passed over
leaves no trace anyone can find.

**Rewritten in part, 2026-09-06, by `QUESTIONS.md` Q-48.** The carve-out is
now decided by whether the failing node reproduces when run alone, not by
whether it is in a filed class, so the second half of this script no longer
describes a rule violation. The quoted-path half is unchanged and still
enforces rule 6 exactly. The class count is kept and reported as a count,
because a population that grew by eight nodes in one sitting is worth
watching — but it is not a verdict, and this script now says so. Nothing
here checks the new clauses: "the node passes alone" and "the diff cannot
reach it" are claims in a commit body, and this script's own docstring
records why prose matchers over commit bodies were measured and rejected.

Measured on first run, 2026-09-01: `.claude/run/` held 47 captures — 14 red, 31
green, 2 no-result — and **7 of the 16 runs that owed a quoted path are quoted
nowhere in the repository**: not in a commit body, not in a register, not in an
audit report. A further 6 reds name no node KI-22 or KI-51 files, so no lawful
carve-out was available for any of them.

Both figures moved while this was being written, and the movement is the point.
Against commit bodies alone the first count was 11; adding the registers and the
reports — which rule 6 never excluded — took it to 7. A check that had shipped
at 11 would have been crying wolf about a record that carries the evidence.

## Why a script and not a pytest

The same reason `check_restarts.py` is a script and `check_anchors.py`'s
`resolve` is: the subject is not committed. `.gitignore` covers `.claude/run/`,
so these logs do not exist on the CI gate, and a pytest over them could only be
green there by checking nothing — the check-that-cannot-fail this repository
has paid for repeatedly. The guard on *this* tool is
`tests/test_a_red_suite_run_the_record_does_not_carry_is_reported.py`, which
drives every function below against synthetic logs.

## Why nothing here reads commit prose

Two prose matchers were measured against the real history before this shape was
chosen, and both were rejected — the same rejection round 129 recorded for
CQ-240:

- *"the body mentions a re-run or the carve-out"* matches **55** commits, nearly
  all of them merely discussing the rule.
- *"the body contains a `N failed` pytest summary"* matches **110**, because a
  guard proved fail-first quotes its own red in exactly that form.

Neither can separate a carve-out from a commit talking about one, and shipping
either would be the weaker-matcher defect the loop profile names: a derived
population whose membership is decided by a matcher that cannot carry it. So
both of rule 6's conditions are read from machine-written evidence at both
ends — the failing node from pytest's own `FAILED` line inside the log, and the
quote from an exact filename match against the written record.

## What it does not claim

**It never says which commit invoked the carve-out.** It says a red run
happened, and the record does or does not carry it. Whether a particular commit
leaned on a particular red is a judgement, and it is left with the person doing
the carry — the `context_lines` shape in `check_anchors.py`, which puts two
records side by side rather than adding a matcher that guesses and is believed.

**An unquoted red is a question, not a verdict.** Some are rounds that stopped
and recorded the failure by node id instead of by path; some are `/backlog-plan`
or relay runs. The exit code says only whether there are any.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Written by `scripts/run-suite.ps1`, which names every capture this way.
#: Read from a glob rather than a list: a run this script has never heard of
#: is exactly the run it must not miss.
RUN_DIR = ROOT / ".claude" / "run"
LOG_GLOB = "suite-*.log"

REGISTER = ROOT / "KNOWN_ISSUES.md"

#: pytest's own summary tail. Anchored at the count so `3 xfailed` cannot be
#: read as a failure — the substring `failed` is inside `xfailed`, and taking
#: it as one classified all 45 real logs as red on this script's first draft.
#: `in ` is required because pytest only prints the elapsed clause on the real
#: summary line, which is what tells it from a `-ra` section heading.
_SUMMARY = re.compile(
    r"^(?:=+ )?(?P<counts>\d+ (?:failed|passed)[^\n]*? in [^\n]*?)(?: =+)?$",
    re.M)

#: The node ids pytest names in its `short test summary info` section. `-ra`
#: is in the pinned flags, so this section is always present on a red.
_FAILED_LINE = re.compile(r"^(?:FAILED|ERROR)\s+(\S+::\S+?)(?:\s+-.*)?$", re.M)

#: A pytest node id anywhere in a register row. The register writes them in
#: backticks; the backticks are not required here, because a row that names
#: one without them still files it.
_NODE = re.compile(r"[\w./\\-]+\.py::[\w\[\]-]+")


@dataclass
class Run:
    """One captured suite run: what it was, and which nodes it named."""

    name: str
    outcome: str          # "red" | "green" | "no result"
    summary: str = ""
    nodes: list[str] = field(default_factory=list)

    @property
    def owes_a_quote(self) -> bool:
        """Rule 6 puts the obligation on a red and on a no-result alike.

        A no-result "is not a pass and not a failure"; it blocks the commit
        exactly as a red does, so the record owes it the same path. A green
        owes nothing — 31 of the 45 real logs are green, and requiring each to
        be cited would make this permanently loud and so permanently ignored.
        """
        return self.outcome in ("red", "no result")


def read_log(path: Path) -> Run:
    """Classify one capture from its own tail.

    The last summary wins: a run repaired and re-run inside one capture
    appends its second summary below the first, and the later one is the one
    that decided whether the round could commit.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    summaries = _SUMMARY.findall(text)
    if not summaries:
        return Run(name=path.name, outcome="no result")
    last = summaries[-1].strip()
    if not re.match(r"\d+ failed", last):
        return Run(name=path.name, outcome="green", summary=last)
    # Deduplicated, order preserved: `-ra` can name a node in both the
    # summary section and a rerun block, and a node counted twice would
    # overstate a class this script reports counts for.
    nodes: list[str] = []
    for node in _FAILED_LINE.findall(text):
        if node not in nodes:
            nodes.append(node)
    return Run(name=path.name, outcome="red", summary=last, nodes=nodes)


def runs(run_dir: Path) -> list[Run]:
    return [read_log(p) for p in sorted(run_dir.glob(LOG_GLOB))]


def commit_bodies(since: str | None = None) -> list[str] | None:
    """Every commit body, as the record of what was said about these runs.

    Resolved rather than handed over as a bare name — the rule
    `test_no_program_is_handed_to_subprocess_by_bare_name` enforces, and the
    one `check_restarts.py` was caught by on its own verifying run. Returns
    `None` when git cannot be reached, so the caller reports a no-result
    rather than an empty record that would flag every red.
    """
    git = shutil.which("git")
    if not git:
        return None
    argv = [git, "log", "--format=%b"]
    if since:
        argv.append(f"{since}..HEAD")
    try:
        out = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return [out.stdout]


def written_record(root: Path) -> list[str]:
    """The Markdown the loop keeps, as the other half of the record.

    Rule 6 says *quote both runs' paths*; it does not say only in a commit
    body, and three real cases are quoted somewhere else — two in
    `KNOWN_ISSUES.md` KI-51's instance rows, one in an `OPERATOR_ACTIONS.md`
    row. Reading commits alone reported all three as unaccounted, which is a
    check crying wolf about a record that carries the evidence perfectly well.
    Measured before this function existed: 11 unaccounted against commits
    alone, 8 against commits and registers together.

    **Derived from a glob, never a list.** A register added to the loop and
    not to a hand-written list here would silently start over-reporting, which
    is the failure `test_every_register_the_loop_keeps_has_a_row_in_the_planner_table`
    records three times over in a different register. Root Markdown is the
    shape a register has in this repository; `audits/` is included because a
    report quoting a log path is equally the record carrying it.
    """
    out = []
    for path in sorted(root.glob("*.md")) + sorted(root.glob("audits/*.md")):
        try:
            out.append(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return out


def unaccounted(captured: list[Run], record: list[str]) -> list[Run]:
    """Runs that owe a quoted path and did not get one anywhere.

    Matched on the log's own filename, in full. A check written as "some
    `.claude/run/` path appears in the record" would be discharged by any
    commit quoting any log — the containment defeat `register_anchor_paths`
    records under WF-45, in a different register.
    """
    text = "\n".join(record)
    return [r for r in captured if r.owes_a_quote and r.name not in text]


def filed_class(register: Path) -> set[str]:
    """The node ids KI-22 and KI-51 file, read from the register's open rows.

    Read rather than copied. Rule 6 says so in as many words — *"do not copy
    their node ids into this file or a skill, because a copy goes stale the
    round a node joins the class or is fixed out of it"* — and names the case
    it went stale on: a node sat under KI-51 through sixteen instances and was
    a deterministic port collision all along, fixed in round 127.

    Bounded to `## Open` for the same reason. A node moved to `## Resolved` has
    left the class, and a collector that kept reading it would keep authorising
    a carve-out the register has withdrawn.
    """
    if not register.is_file():
        return set()
    text = register.read_text(encoding="utf-8", errors="replace")
    # Matched at line start rather than on a leading newline: `## Open` at
    # byte 0 has no newline before it, and a `find("\n## Open")` missed it —
    # caught by `test_a_node_the_register_files_is_recognised` on this
    # script's first run against its guard.
    opening = re.search(r"^## Open\b", text, re.M)
    if not opening:
        return set()
    rest = text[opening.start():]
    end = re.search(r"^## (?!Open)", rest[1:], re.M)
    section = rest[:end.start() + 1] if end else rest
    filed: set[str] = set()
    for line in section.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        if not re.search(r"\bKI-(?:22|51)\b", line):
            continue
        filed.update(_NODE.findall(line))
    return filed


def outside_class(captured: list[Run], filed: set[str]) -> list[Run]:
    """Red runs whose failing nodes are none of them in the filed class.

    **This is a count and no longer a finding** (`QUESTIONS.md` Q-48,
    2026-09-06). It used to mean "a red that could not lawfully have been
    carved out", because membership of KI-22/KI-51 was the carve-out's gate.
    It is not any more: a red stands aside when it does not reproduce alone,
    which has nothing to do with where it is filed.

    Kept, and kept computed the same way, because the number is how the
    population is watched: brief v16a's AT-a added eight node names in one
    sitting, and a register growing at that rate is exactly the evidence that
    retired it as a gate. A run with at least one filed node is still not
    listed — this script has never had the standing to decide a mixed one.
    """
    return [r for r in captured
            if r.outcome == "red" and r.nodes
            and not any(n in filed for n in r.nodes)]


def render(captured: list[Run], unheld: list[Run], unfiled: list[Run],
           filed: set[str]) -> list[str]:
    reds = [r for r in captured if r.outcome == "red"]
    blank = [r for r in captured if r.outcome == "no result"]
    out = [f"{len(captured)} captured run(s) in {RUN_DIR.name}/: "
           f"{len(reds)} red, "
           f"{len(captured) - len(reds) - len(blank)} green, "
           f"{len(blank)} no-result; "
           f"{len(filed)} node(s) filed under KI-22/KI-51"]
    if not unheld and not unfiled:
        out.append("clean: every red or no-result run has its path quoted by "
                   "a commit. Whether each carve-out was lawful is not "
                   "decided here — read the bodies for the three clauses "
                   "rule 6 asks for.")
        return out
    if unheld:
        out.append(f"unquoted: {len(unheld)} run(s) that owed a quoted path "
                   "and no commit carries")
        for r in unheld:
            out.append(f"  {r.name} [{r.outcome}] {r.summary or '(no summary)'}")
            for node in r.nodes:
                out.append(f"      {node}")
    if unfiled:
        out.append(f"not in the filed class: {len(unfiled)} red run(s) naming "
                   "no node KI-22/KI-51 files — a count, not a finding "
                   "(Q-48): the register stopped being the carve-out's gate "
                   "on 2026-09-06")
        for r in unfiled:
            out.append(f"  {r.name} {', '.join(r.nodes)}")
    out.append("An unquoted red is a question, not a verdict: some are rounds "
               "that stopped and recorded the failure by node id instead of "
               "by path. Read the commits around it before concluding that a "
               "carve-out was taken.")
    return out


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Red suite runs the commit record does not carry.")
    parser.add_argument("--since", metavar="COMMIT", default=None,
                        help="bound the commit record to <COMMIT>..HEAD")
    parser.add_argument("--run-dir", default=None,
                        help="where the captures live (default .claude/run)")
    parser.add_argument("--register", default=None,
                        help="the KI-22/KI-51 register (default "
                             "KNOWN_ISSUES.md)")
    parser.add_argument("--bodies-from", default=None,
                        help="read the commit record from this file instead "
                             "of git; the guard drives the tool this way")
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir) if args.run_dir else RUN_DIR
    register = Path(args.register) if args.register else REGISTER

    if not run_dir.is_dir():
        print(f"no result: {run_dir} does not exist, so nothing says which "
              "suite runs happened. This is not a clean run.")
        return 2

    if args.bodies_from:
        record = [Path(args.bodies_from).read_text(encoding="utf-8",
                                                   errors="replace")]
    else:
        bodies = commit_bodies(args.since)
        if bodies is None:
            print("no result: the commit record could not be read, so nothing "
                  "says what was said about these runs. This is not a clean "
                  "run.")
            return 2
        record = bodies + written_record(ROOT)

    # Passed explicitly rather than left to module defaults: a default bound
    # at definition would have these functions silently reading the real
    # `.claude/run` while the guard believed it was driving a fixture — the
    # exact bug `check_restarts.py` records against its own first assertion.
    captured = runs(run_dir)
    filed = filed_class(register)
    unheld = unaccounted(captured, record)
    unfiled = outside_class(captured, filed)
    for line in render(captured, unheld, unfiled, filed):
        print(line)
    return 1 if (unheld or unfiled) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
