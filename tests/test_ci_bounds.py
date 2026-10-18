"""Every CI job carries a `timeout-minutes`.

GitHub's default is 360 minutes, so a job that stops making progress holds the
run for six hours. That cost nothing while a hung run read as green. It stopped
being free when `_relay/watch.ps1` (fed3356) began reading an `in_progress` run
as pending rather than green: rounds now wait on CI, so one unbounded job parks
every round behind it. Run 32095774919 sat 47m56s in `playwright install-deps
chromium` and was cancelled by hand — the loop's first observed bill for that
coupling, and the reason these bounds exist.

The jobs are enumerated from the file rather than listed here, per DISCIPLINE
rule 3: a hard-coded list of five is exactly how job six ships unbounded.

Parsed by indentation rather than with a YAML library. Nothing else in this
repository depends on PyYAML, and the only shape asserted — a key at job level —
is one an indentation walk reads reliably.
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

#: A job name: exactly two spaces, then a key, then nothing else on the line.
#: Comments at the same indent (`  # axe against …`) do not match, and neither
#: does anything deeper — `strategy:`'s children sit at four spaces and up.
JOB = re.compile(r"^  ([A-Za-z][\w-]*):\s*$")
BOUND = re.compile(r"^    timeout-minutes:\s*(\d+)\s*$")

#: What the bound replaces. A "bound" at or above this is the default wearing a
#: number, which is the state this file was written to leave.
GITHUB_DEFAULT_MINUTES = 360


def _jobs() -> dict[str, int | None]:
    """Map every job in ci.yml to its `timeout-minutes`, or None if it has none."""
    found: dict[str, int | None] = {}
    current: str | None = None
    in_jobs = False
    for line in WORKFLOW.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line[:1].isspace():
            in_jobs = line.startswith("jobs:")
            current = None
            continue
        if not in_jobs:
            continue
        if match := JOB.match(line):
            current = match.group(1)
            found[current] = None
        elif current and (match := BOUND.match(line)):
            found[current] = int(match.group(1))
    return found


def test_the_parser_sees_every_job_that_exists():
    """Rule 5: the evidence must be able to disagree with the check.

    `every job has a bound` passes vacuously over an empty dict, so a parser
    that quietly matched nothing would report the unbounded state as green.
    `runs-on` is the independent count — one per job, written in a different
    place and shape than the key this walk keys on.
    """
    jobs = _jobs()
    runs_on = len(re.findall(r"^    runs-on:", WORKFLOW.read_text(encoding="utf-8"),
                             flags=re.MULTILINE))
    assert runs_on > 0, f"{WORKFLOW} declares no jobs at all — read it before trusting this file"
    assert len(jobs) == runs_on, (
        f"the indentation walk found {sorted(jobs)} ({len(jobs)}) but the file has "
        f"{runs_on} `runs-on:` lines. The walk is wrong, so every other assertion "
        f"in this module is about a subset it happened to see.")


def test_every_ci_job_is_bounded():
    unbounded = sorted(name for name, minutes in _jobs().items() if minutes is None)
    assert not unbounded, (
        f"{unbounded} have no `timeout-minutes`, so GitHub's "
        f"{GITHUB_DEFAULT_MINUTES}-minute default applies. A job that stops making "
        f"progress then holds CI for six hours, and the round waiting on that run "
        f"waits with it. Measure the job's real spread and set a bound above it.")


def test_no_bound_is_the_default_in_disguise():
    """A number is not a bound if it is not shorter than the thing it replaces.

    60 rather than 360 as the tripwire: the point of a bound is to turn a hang
    into a red result inside the time somebody would actually wait for it. A job
    that genuinely needs longer may raise this — after saying, here, why.
    """
    too_loose = {name: minutes for name, minutes in _jobs().items()
                 if minutes is not None and minutes > 60}
    assert not too_loose, (
        f"{too_loose} are bounded above an hour. The observed maximum for the "
        f"slowest job in this workflow is 13m58s; a bound this far above it "
        f"detects nothing a person would still be waiting to hear about.")
