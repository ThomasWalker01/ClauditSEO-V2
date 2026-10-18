"""CQ-21, CQ-42, CQ-22: `prove_fail.py` never answers a run it did not finish.

Three findings, one file, one forty-line function - and one consequence, which
is why they are guarded together rather than three files apart. The script's
own docstring states the property it is built to have: *"a rule-1 proof taken
under the other regime is a confident answer to a question the gate never
asks, which is the one failure mode this script is built not to have."* Each of
these three is that failure mode arriving by a different door.

| finding | the door |
| --- | --- |
| CQ-42 | the restore checks out the whole tree, so every tracked file's mtime moves whether its content did or not |
| CQ-21 | the restore's return code is discarded, so a restore that failed is reported as a clean one |
| CQ-22 | `PYTEST` is a Windows console-script path used with no existence check, so where it cannot exist the tool answers anyway |

**CQ-42 is the one with an observed instance rather than a predicted one**, and
it is what put this guard first in the plan of 23 August 2026. `KNOWN_ISSUES.md`
KI-45, measured 20 August: `git checkout HEAD -- .` rewrote the mtime of
`dashboard/src/deliverable.tsx`, whose content had not moved, and
`scripts/restart-service.ps1` then refused to start with *"the build is older
than deliverable.tsx"*. `tests/test_bundle_identity.py` compares the same two
mtimes and would fail the same way in a suite run after a prove_fail - so the
tool that exists to make rule-1 evidence trustworthy can turn the pinned suite
red, which under DISCIPLINE rule 6 is a commit refused.

**A scratch repository, not this one.** `prove_fail.py` reverts the whole
working tree of `Path(__file__).resolve().parents[1]`; pointed at this
repository inside a test run it would check out a parent commit underneath the
suite that is running it. Copying the script into a two-commit repository under
`tmp_path` makes its own `ROOT` resolve there, so every assertion below is
about real exit codes, real `git` and real mtimes rather than about the
script's structure - DISCIPLINE rule 4.

**The runner is a plain file on purpose.** Two of the three cases have to get
*past* the existence check to reach the restore, and none of them cares what
pytest would have said. A file that exists and cannot be spawned is the
cheapest way to buy that without a real interpreter in `tmp_path`, and it is
also the case the CQ-22 remedy has to cover for the same reason existence does:
a runner that cannot start produced no result, and no result is exit 2.

**CQ-42 is worded wrongly and the guard asserts what was measured instead.**
The finding says the restore "rewrites every tracked file's mtime". It does
not, and the first version of this file passed against the unfixed script for
that reason. Measured 23 August 2026 in a two-commit scratch repository and
again against this repository at HEAD: `git checkout <rev> -- .` writes only
the paths whose blob differs from the index, so `untouched.txt` keeps its mtime
with no fix at all. What moves is the parent-to-HEAD diff - which is the round's
own change, which is where `dashboard/src` sits, which is KI-45. So the
consequence the finding names is real and only the word "every" was wrong, and
the remedy is not to narrow the checkout (git has already narrowed it) but to
put the timestamps back: this script promises to restore the tree, the tree
ends byte-identical to how it found it, and a timestamp is what two other tools
in this repository read.

**Non-vacuity, and it costs a coupling worth naming.** Asserting only that
mtimes are preserved would pass against a script that had stopped reverting
altogether. The positive control is the line the tool prints *after* the
revert-and-restore cycle - so this case can only prove the cycle ran by reading
a message that is itself part of the CQ-22 remedy. The three findings are one
commit under DISCIPLINE rule 7 for that reason: the guard reproduces the defect
being fixed rather than standing alone as a net.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "prove_fail.py"

#: The subject file's two states. The point is only that the content differs
#: between the commits, so `moved.txt` is inside what any correct revert has to
#: rewrite and `untouched.txt` is outside it.
_PARENT_BODY = "value = 1\n"
_HEAD_BODY = "value = 2\n"

_TEST_BODY = """\
from subject import value


def test_value():
    assert value == 2
"""


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    done = subprocess.run(("git",) + args, cwd=cwd, capture_output=True, text=True)
    assert done.returncode == 0, f"git {' '.join(args)} -> {done.stderr}"
    return done


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A two-commit repository with `prove_fail.py` inside it.

    `.gitignore` covers `.venv/` because the fake runner is written after the
    commits and the script refuses a dirty tree - an untracked file there would
    make every case below answer CANNOT ANSWER for the wrong reason.
    """
    if shutil.which("git") is None:
        pytest.skip("git is not resolvable; this guard is about what git does")

    work = tmp_path / "repo"
    (work / "scripts").mkdir(parents=True)
    (work / "tests").mkdir()

    (work / ".gitignore").write_text(".venv/\n", encoding="utf-8")
    (work / "untouched.txt").write_text("identical in both commits\n", encoding="utf-8")
    (work / "moved.txt").write_text(_PARENT_BODY, encoding="utf-8")
    (work / "subject.py").write_text(_PARENT_BODY, encoding="utf-8")
    (work / "tests" / "test_subject.py").write_text(_TEST_BODY, encoding="utf-8")
    shutil.copy2(SCRIPT, work / "scripts" / "prove_fail.py")

    _git("init", "-q", cwd=work)
    _git("config", "user.email", "guard@example.invalid", cwd=work)
    _git("config", "user.name", "guard", cwd=work)
    _git("add", "-A", cwd=work)
    _git("commit", "-qm", "parent", cwd=work)

    (work / "subject.py").write_text(_HEAD_BODY, encoding="utf-8")
    (work / "moved.txt").write_text(_HEAD_BODY, encoding="utf-8")
    _git("add", "-A", cwd=work)
    _git("commit", "-qm", "head", cwd=work)

    return work


def _parent_sha(repo: Path) -> str:
    return _git("rev-parse", "--short", "HEAD~1", cwd=repo).stdout.strip()


def _fake_runner(repo: Path) -> Path:
    """A `PYTEST` that exists and cannot be spawned. See the module docstring."""
    runner = repo / ".venv" / "Scripts" / "pytest.exe"
    runner.parent.mkdir(parents=True, exist_ok=True)
    runner.write_bytes(b"not a runnable image\n")
    return runner


def _prove(repo: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(repo / "scripts" / "prove_fail.py"),
         "tests/test_subject.py::test_value", "--parent", _parent_sha(repo)],
        cwd=repo, capture_output=True, text=True, env=env)


def _mtimes(repo: Path) -> dict[str, int]:
    return {name: (repo / name).stat().st_mtime_ns
            for name in ("untouched.txt", "moved.txt")}


def test_a_tree_restored_byte_for_byte_is_restored_stamp_for_stamp(repo: Path):
    """CQ-42, and KI-45's cause.

    `moved.txt` is the one that matters: it differs across the two commits, so
    it is inside what the revert rewrites, and at HEAD it comes back with a new
    mtime over content that is exactly where it started. That is the whole of
    KI-45 - `dashboard/src/deliverable.tsx` newer than a `dashboard/dist` built
    minutes earlier, a restart refused, and `test_bundle_identity.py` reading
    the same two numbers.
    """
    _fake_runner(repo)
    before = _mtimes(repo)
    contents = {name: (repo / name).read_bytes()
                for name in ("untouched.txt", "moved.txt", "subject.py")}

    done = _prove(repo)

    assert "could not start the runner" in done.stdout, (
        "the positive control: this line is printed only after the revert and "
        "the restore have both run, so without it the mtime assertions below "
        f"would be true of a script that never touched the tree — got: "
        f"{done.stdout.strip()}\n{done.stderr.strip()}")
    assert {name: (repo / name).read_bytes() for name in contents} == contents, (
        "the tree must come back byte-identical before its timestamps are worth "
        "discussing")

    after = _mtimes(repo)
    assert after["moved.txt"] == before["moved.txt"], (
        "moved.txt is back to the content it started with, so its mtime should "
        "be back too - this is the number restart-service.ps1 and "
        "test_bundle_identity.py compare against dashboard/dist")
    assert after["untouched.txt"] == before["untouched.txt"], (
        "untouched.txt is byte-identical in both commits; git never writes it "
        "and nothing this script does should either")


def test_a_runner_that_cannot_run_is_cannot_answer_and_not_a_verdict(repo: Path):
    """CQ-22.

    `PYTEST` is `ROOT/.venv/Scripts/pytest.exe` on every platform, so on the
    POSIX tree `scripts/dev.sh` builds it cannot exist. Today that reaches
    `subprocess.run` and the process dies with a traceback at exit 1 - which is
    NOT PROVEN, the verdict reserved for "the parent already satisfied your
    guard". Exit 2 is the only honest answer, and it is owed *before* the
    checkout so a run that cannot answer leaves no footprint.
    """
    before = _mtimes(repo)

    done = _prove(repo)

    assert done.returncode == 2, (
        f"exit {done.returncode} with no runner present: "
        f"{done.stdout.strip()}\n{done.stderr.strip()}")
    assert "CANNOT ANSWER" in done.stdout
    assert _mtimes(repo) == before, (
        "a run that cannot answer must not have reverted anything")


def test_a_restore_that_failed_is_not_reported_as_a_clean_one(repo: Path,
                                                              tmp_path: Path):
    """CQ-21.

    The restore is the last thing the script does and the only thing standing
    between it and a tree left at the wrong commit, and its return code is
    dropped. Forced here with a `git` first on `PATH` that refuses exactly the
    restore - a shim rather than a filesystem trick, because it is the same on
    both CI legs and it fails the real call rather than a stand-in for it.
    """
    shim = tmp_path / "shim"
    shim.mkdir()
    real_git = shutil.which("git")
    body = (
        "import subprocess, sys\n"
        "args = sys.argv[1:]\n"
        "if args[:2] == ['checkout', 'HEAD']:\n"
        "    sys.stderr.write('fatal: forced restore failure (test shim)\\n')\n"
        "    sys.exit(128)\n"
        f"sys.exit(subprocess.run([{real_git!r}, *args]).returncode)\n"
    )
    (shim / "git_shim.py").write_text(body, encoding="utf-8")
    if os.name == "nt":
        (shim / "git.bat").write_text(
            '@echo off\r\n"' + sys.executable + '" "%~dp0git_shim.py" %*\r\n',
            encoding="utf-8")
    else:
        launcher = shim / "git"
        launcher.write_text(f"#!{sys.executable}\n" + body, encoding="utf-8")
        launcher.chmod(0o755)

    _fake_runner(repo)
    env = dict(os.environ)
    env["PATH"] = str(shim) + os.pathsep + env["PATH"]

    done = _prove(repo, env=env)

    assert done.returncode == 2, (
        f"exit {done.returncode} after a restore that failed: "
        f"{done.stdout.strip()}\n{done.stderr.strip()}")
    assert "CANNOT ANSWER" in done.stdout
    assert "restore" in done.stdout.lower(), (
        "the message has to say the tree may be left at the parent; an operator "
        "who is told only 'no result' will not go looking for it")
