"""CQ-237 — a red pinned-suite run must leave its assertion text on disk.

`QUESTIONS.md` Q-36 asks the operator to choose between five ways of handling
an intermittently-red pinned suite. Every one of the five is a decision only
the operator can make, and report 120's remediation item 1 sequences one thing
*before* that decision: **capture one red run's full output to a file first —
no round yet has the assertion text for the failure this class actually
produces.**

That gap is mechanical, not a judgement. Rounds run the pinned suite through a
tool call whose output is truncated before the failure section, so across five
rounds of this class going red the answer to "which assertion fired" has never
been recoverable. Q-36's own `context` records it in as many words: *"Which
assertion fired is not established: the runner's output was truncated before
the assertion text and neither later run reproduced that node."* An
intermittent nobody can read is an intermittent nobody can diagnose, whichever
of the five options is eventually chosen — so this is a precondition of the
decision rather than one of its branches, and taking it pre-empts nothing.

`scripts/run-suite.ps1` closes it: it runs the pinned command **verbatim** and
tees the whole run to a file under `.claude/run/`, which `.gitignore` covers.

Two properties, and they are tested separately because they fail separately:

- **It must not restate the command.** The wrapper reads `suite_command` out
  of `.claude/loop/PROFILE.md` at run time rather than carrying its own copy.
  A fourth hard-coded copy of the flags is exactly the drift
  `test_the_pinned_suite_command_is_stated_once` exists to refuse, and a
  wrapper that quietly ran different flags would make every baseline taken
  through it worthless — rule 11's shape.

- **It must capture a failing run's assertion text.** Driven, not read: the
  test hands the wrapper a temporary profile whose `suite_command` runs a
  deliberately-failing pytest file, and asserts the distinctive assertion
  message reaches the log. Reading the script for the word `Tee-Object` would
  pass against a wrapper that tees only stdout while pytest writes its report
  to stderr, or one that captures a green run and truncates a red one.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts" / "run-suite.ps1"
PROFILE = ROOT / ".claude" / "loop" / "PROFILE.md"

#: The marker the driven test looks for in the captured log. Deliberately not
#: a word that appears anywhere in the wrapper, the profile or pytest's own
#: chrome, so finding it can only mean the failing run's assertion text was
#: carried through.
SENTINEL = "ZQX_ASSERTION_TEXT_MUST_SURVIVE"

def _powershell() -> str | None:
    """The resolved interpreter, or None.

    Written as a loop rather than `which("powershell") or which("pwsh")`
    because `tests/test_program_names.py` refuses the second shape: a
    `which(...) or <fallback>` carries on with an unresolved name at
    exactly the moment resolution failed. Nothing here falls back -- each
    candidate is returned only once it has resolved to a real path.
    """
    for name in ("powershell", "pwsh"):
        found = shutil.which(name)
        if found:
            return found
    return None


powershell = _powershell()

#: The wrapper needs Windows, not merely a PowerShell binary, and the
#: difference is what reddened CI at `6220728`.
#:
#: `scripts/run-suite.ps1` runs the pinned command through `& cmd.exe /c
#: "$command 2>&1"`, deliberately: its own comment records that Windows
#: PowerShell 5.1 wraps a native command's stderr in ErrorRecords and loses the
#: exit status, so the merge is pushed down to the OS. `cmd.exe` does not exist
#: on Linux.
#:
#: `shutil.which` was therefore asking the wrong question. `ubuntu-latest`
#: ships `pwsh`, so the guard resolved, the case ran, the wrapper's `cmd.exe`
#: call produced nothing, and the assertion read
#: `assert 'ZQX_ASSERTION_TEXT_MUST_SURVIVE' in ''` — an empty log, reported as
#: the capture defect this very test exists to catch. A guard that turns a
#: platform it was never meant to run on into a finding is worse than no guard:
#: it spends a round on a fault that is not there.
#:
#: Both conditions are kept rather than collapsing to the platform check. A
#: Windows box with no PowerShell on PATH is a real configuration and the
#: reason it skips is a different one, so the reasons stay separate and each
#: says which it was.
requires_powershell = pytest.mark.skipif(
    powershell is None or sys.platform != "win32",
    reason=(
        "no PowerShell on PATH" if powershell is None else
        "not Windows; scripts/run-suite.ps1 runs the pinned command through "
        "cmd.exe, which is the loop's Windows entry point by construction"
    ),
)


def test_the_wrapper_exists_and_is_the_documented_capture_point():
    assert WRAPPER.exists(), (
        f"{WRAPPER.relative_to(ROOT)} is missing — the loop's instructions "
        "name it as the way a pinned suite run is captured"
    )


def test_the_wrapper_reads_the_pinned_command_rather_than_restating_it():
    """A fourth copy of the flags is the drift, not the safety."""
    text = WRAPPER.read_text(encoding="utf-8")

    # The body, without the comment-based help block: the docstring is allowed
    # to quote the flags when explaining what it runs, and refusing that would
    # make the guard punish documentation.
    body = re.sub(r"(?s)^\s*<#.*?#>", "", text, count=1)

    assert "PROFILE.md" in body, (
        "the wrapper must read the pinned command out of "
        ".claude/loop/PROFILE.md at run time, not carry its own copy"
    )
    assert "suite_command" in body, (
        "the wrapper must select the profile's `suite_command:` key by name"
    )

    for flag in ("--dist", "-n auto", "loadfile"):
        assert flag not in body, (
            f"the wrapper's body states the pinned flag {flag!r} literally — "
            "that is a fourth copy of the gate's command and it will drift; "
            "read it from the profile instead"
        )


@requires_powershell
def test_a_failing_run_s_assertion_text_reaches_the_log(tmp_path: Path):
    """The property CQ-237 needs, driven end to end against a red run."""
    failing = tmp_path / "test_deliberately_red.py"
    failing.write_text(
        "def test_this_one_is_meant_to_fail():\n"
        f"    assert False, {SENTINEL!r}\n",
        encoding="utf-8",
    )

    # A profile of the same shape as the real one, naming a command that runs
    # the failing file and nothing else. `-p no:cacheprovider` keeps the run
    # from writing into the repo's own cache.
    profile = tmp_path / "PROFILE.md"
    command = (
        f"{sys.executable} -m pytest {failing} -p no:cacheprovider "
        f"-p no:xdist --no-header -rA"
    )
    profile.write_text(
        "```yaml\n"
        "profile_schema: 1\n"
        f"suite_command: {command}\n"
        "```\n",
        encoding="utf-8",
    )

    logs = tmp_path / "logs"
    proc = subprocess.run(
        [
            powershell, "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(WRAPPER),
            "-ProfilePath", str(profile),
            "-LogDir", str(logs),
        ],
        capture_output=True,
        text=True,
        # In `tmp_path`, not the repo root, and this is load-bearing: the
        # wrapper runs the pinned command in the caller's working
        # directory rather than pushing to one of its own, so a sub-pytest
        # started from here would take this repository as its rootdir,
        # load its conftest and its Playwright fixtures, and error during
        # collection instead of running the one failing file. Observed:
        # `collected 0 items / 1 error` from a stale Chromium profile
        # directory, under the full suite only.
        cwd=str(tmp_path),
        timeout=300,
    )

    assert proc.returncode != 0, (
        "the wrapper must exit with the suite's own status — it reported "
        f"success for a run that failed:\n{proc.stdout}\n{proc.stderr}"
    )

    written = sorted(logs.glob("*.log")) if logs.exists() else []
    assert written, (
        f"the wrapper wrote no log under {logs}:\n{proc.stdout}\n{proc.stderr}"
    )
    assert len(written) == 1, f"expected one log, got {[p.name for p in written]}"

    captured = written[0].read_text(encoding="utf-8", errors="replace")
    assert SENTINEL in captured, (
        "the failing run's assertion text did not reach the log — which is the "
        "whole finding: a red run nobody can read is a red run nobody can "
        f"diagnose. Log held:\n{captured[:4000]}"
    )

    assert str(written[0]) in (proc.stdout + proc.stderr), (
        "the wrapper must print the log's path, or the round has a capture it "
        "cannot find"
    )
