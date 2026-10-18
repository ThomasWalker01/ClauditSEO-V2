"""Prove a guard fails before its fix — DISCIPLINE rule 1, as one command.

    .venv/Scripts/python.exe scripts/prove_fail.py tests/test_x.py::test_y

Runs the named test against the PARENT commit's source with the CURRENT test
file, so the question it answers is exactly the one the rule asks: does this
assertion fail against the code as it was before the fix?

Why it exists. Rule 1 has been conventional rather than enforced, and the cost
is on the record: three of four consecutive audit rounds left a High finding
invisible to the guard written beside it, and round 012's guard checked one of
its two stated directions. Each time the guard was written honestly and each
time nobody could cheaply show it had ever been red. Four manual steps —
stash, checkout, run, restore — is enough friction to skip when tired.

Exit codes are the point, so a fix commit can quote the output:

    0   the test FAILED against the parent — the guard is real
    1   the test PASSED against the parent — it proves nothing about this fix
    2   could not answer (dirty tree, no parent, runner produced no result)

Exit 2 is deliberately not 1. A run that told you nothing is not a run that
told you the guard is weak, and DISCIPLINE rule 6 draws that same line for the
suite: red and no-result are different states.

CAVEAT, stated because a silent wrong answer here is worse than no answer.
This reverts SOURCE only. A test whose subject is the built dashboard bundle
(`dashboard/dist`, which is what the rendered axe sweep loads) will still run
against whatever bundle is on disk, so reverting `dashboard/src` proves
nothing about it. Those tests are rejected up front rather than answered
wrongly — see `needs_build` below, which derives that set from the
import graph rather than holding a list of it.
"""

from __future__ import annotations

import argparse
import ast
import os
import shutil
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
#: The gate's entry-point KIND, not merely its flags. `.claude/loop/PROFILE.md`
#: states it in one line - "a console-script pytest, never python -m pytest" -
#: and `.claude/DISCIPLINE.md` rule 11 records what the difference cost: the
#: module form puts the working directory on `sys.path` and the console script
#: does not, which is why `242d94a` had to make `tests/` a package before the
#: gate could resolve `tests.conftest`. A rule-1 proof taken under the other
#: regime is a confident answer to a question the gate never asks, which is
#: the one failure mode this script is built not to have. CQ-177.
PYTEST = ROOT / ".venv" / "Scripts" / "pytest.exe"
#: Resolved rather than passed bare, for the reason in
#: tests/test_packaging.py::_resolve_runnable.
#:
#: No `or "git"` fallback: it handed subprocess a bare name at exactly the
#: moment resolution failed, which is the case the line above exists to
#: prevent. `None` here is the CANNOT ANSWER state — this script reverts the
#: tree with git, so without it there is no answer to give, and exit 2 is
#: already what that means.
GIT = shutil.which("git")

def _parse(source: str) -> ast.AST:
    """`ast.parse` with the compiler's own warnings silenced.

    Parsing every test file surfaces each one's `SyntaxWarning` — this tree
    has invalid escape sequences in two regex literals — and they arrive on
    stderr ahead of the CANNOT ANSWER line the operator is here to read.
    Nineteen warnings above a one-line answer is the answer being hidden by a
    diagnostic about a file the operator did not ask about.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return ast.parse(source)


def _binds_the_bundle(source: str) -> bool:
    """Whether this module's own code builds a path reaching `dashboard/dist`.

    Over the AST rather than the text, and the difference is not academic.
    Two test files in this tree carry the sentence "Pure Python, deliberately.
    Nothing here loads `dashboard/dist`, so [prove_fail can answer for it]" —
    written to record that this script works for them. A substring scan reads
    those two docstrings and refuses exactly the files whose prose says it
    need not, which is the dead end this comment exists to stop being re-tried.
    """
    try:
        tree = _parse(source)
    except SyntaxError:
        # A file that will not parse cannot be reasoned about, and guessing is
        # the one thing this script refuses to do. Treated as needing the
        # build: over-refusal costs a hand proof, under-refusal is a wrong
        # answer about whether a guard was ever red.
        return True
    for node in ast.walk(tree):
        # `ROOT / "dashboard" / "dist"` — pathlib's division, which is how
        # every binder in this tree spells it.
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            for side in (node.left, node.right):
                if isinstance(side, ast.Constant) and side.value == "dist":
                    return True
    return False


def _imported_test_modules(source: str) -> set[str]:
    try:
        tree = _parse(source)
    except SyntaxError:
        return set()
    return {node.module.split(".", 1)[1]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module and node.module.startswith("tests.")}


def needs_build(test_file: Path, _seen: set[str] | None = None) -> bool:
    """Whether this test's subject is the compiled bundle rather than source.

    Reverting `dashboard/src` does not rebuild `dashboard/dist`, so for these
    the answer would be about the bundle currently on disk and not about the
    parent commit at all. Refused rather than guessed at.

    **Derived, not listed.** This was a hand-kept tuple of one file for the
    whole of the script's life, while twenty-two test files bind to the bundle
    — so it answered wrongly for twenty-one, and twenty-two commits proved
    their guards by hand and recorded the workaround in their own bodies
    rather than the tool being repaired. Report 078 raised it as CQ-164 and
    four consecutive reports proposed the same remedy. A hand-kept population
    inside a guard is the failure class; the fix is the property, not a longer
    list.

    The property is transitive because most binders are: a file taking `DIST`
    or `served` from `tests.test_a11y_rendered` never names `dist` itself, and
    that is nineteen of the twenty-two. `_seen` bounds the walk — test modules
    do import each other, and `test_real_data_scale` and `test_heading_fault`
    are a cycle today.
    """
    seen = _seen if _seen is not None else set()
    relative = str(test_file).replace("\\", "/")
    stem = relative.rsplit("/", 1)[-1].removesuffix(".py")
    if stem in seen:
        return False
    seen.add(stem)

    source_path = ROOT / "tests" / f"{stem}.py"
    if not source_path.is_file():
        # Not a test file this repository holds. Nothing to read, so nothing
        # to claim — the caller's later checks decide what happens to it.
        return False
    source = source_path.read_text(encoding="utf-8", errors="replace")
    if _binds_the_bundle(source):
        return True
    return any(needs_build(Path(f"tests/{module}.py"), seen)
               for module in _imported_test_modules(source))


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([GIT, *args], cwd=ROOT, capture_output=True, text=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("node_id", help="pytest node id, e.g. tests/test_x.py::test_y")
    ap.add_argument("--parent", default="HEAD~1",
                    help="revision to run the source against (default HEAD~1)")
    args = ap.parse_args()

    if not GIT:
        print("CANNOT ANSWER: git is not resolvable on PATH. This script "
              "checks out the parent commit's source and restores it "
              "afterwards, so without git there is nothing it can safely do.")
        return 2

    test_file = Path(args.node_id.split("::", 1)[0])
    if needs_build(test_file):
        print(f"CANNOT ANSWER: {test_file} runs against dashboard/dist, which this "
              "script does not rebuild. Reverting dashboard/src would leave the "
              "current bundle in place and the result would be about neither commit.")
        return 2

    if _git("status", "--porcelain").stdout.strip():
        print("CANNOT ANSWER: working tree is dirty. This script reverts the whole "
              "tree to the parent and restores it; uncommitted work would be at "
              "risk, so it refuses rather than stashing on your behalf.")
        return 2

    parent = _git("rev-parse", "--short", args.parent)
    if parent.returncode != 0:
        print(f"CANNOT ANSWER: no revision {args.parent} — {parent.stderr.strip()}")
        return 2
    parent_sha = parent.stdout.strip()

    if not PYTEST.is_file():
        print(f"CANNOT ANSWER: no runner at {PYTEST}. This script names the "
              "gate's entry point by path — a console-script pytest, never "
              "`python -m pytest` — and on a tree whose virtualenv was built by "
              "`scripts/dev.sh` that path cannot exist. Refused here rather "
              "than at the spawn, so a run that cannot answer leaves the "
              "working tree exactly as it found it. CQ-22.")
        return 2

    kept = Path(tempfile.mkdtemp()) / test_file.name
    absolute = ROOT / test_file
    if absolute.is_file():
        shutil.copy2(absolute, kept)

    # The mtimes of everything the revert is about to rewrite, so they can be
    # put back with the content. CQ-42, and KI-45 is what it costs: a run left
    # `dashboard/src/deliverable.tsx` newer than the `dashboard/dist` built
    # minutes earlier, `scripts/restart-service.ps1` refused to start, and
    # `tests/test_bundle_identity.py` compares the same two mtimes — so the
    # tool that exists to make rule-1 evidence trustworthy could turn the
    # pinned suite red, which under DISCIPLINE rule 6 is a commit refused.
    #
    # **A dead end recorded rather than left for the next reader.** CQ-42 is
    # worded as "rewrites every tracked file's mtime", and the obvious remedy
    # is to narrow the checkout to the changed paths. Measured on 23 August
    # 2026 in a two-commit scratch repository: git already does that — a file
    # byte-identical in both commits is not written and keeps its mtime, and
    # only files that genuinely differ are touched. Narrowing buys nothing and
    # would reverse the whole-tree decision argued in the comment below. The
    # set that moves is the round's own diff, which is exactly where the
    # dashboard source sits, so the consequence the finding names is real and
    # only the word "every" was wrong.
    #
    # Restoring the timestamps is the honest promise: the tree is byte-identical
    # to how this script found it, so it should be timestamp-identical too.
    # `git diff --name-only` bounds the work to what the two checkouts can
    # touch, derived from git rather than from a list that would go stale.
    touched = _git("diff", "--name-only", args.parent, "HEAD")
    stamps: dict[Path, os.stat_result] = {}
    for line in touched.stdout.splitlines():
        if line.strip():
            path = ROOT / line.strip()
            if path.is_file():
                stamps[path] = path.stat()

    restore = None
    run = None
    spawn_error: OSError | None = None
    try:
        # Whole tree to the parent, then the test file back on top. Checking
        # out only the source paths would need a list of them, and a list is
        # what goes stale — the same reason the sweep's route list was
        # inverted to read the dispatcher rather than be maintained by hand.
        _git("checkout", args.parent, "--", ".")

        # `git checkout <rev> -- .` restores content but never deletes: a file
        # ADDED at HEAD survives the revert. Left alone, a fix that landed a
        # new module would leave that module importable and the guard could
        # pass against "the parent" for a reason the parent never had. Remove
        # the additions explicitly so the revert means what it says.
        added = _git("diff", "--name-only", "--diff-filter=A", args.parent, "HEAD")
        for line in added.stdout.splitlines():
            path = ROOT / line.strip()
            if line.strip() and path != absolute and path.is_file():
                path.unlink()

        if kept.is_file():
            absolute.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(kept, absolute)

        # No `-q` here: `pyproject.toml`'s addopts already supplies one, and a
        # second makes `-qq`, which removes the `N passed` line — so the three
        # lines printed as this tool's evidence became the `--durations` table
        # (CQ-179, PROFILE.md:18-19). The exit code was never affected, which is
        # why it went unnoticed: the verdict stayed right and its proof went
        # blank. Guarded by
        # `tests/test_the_proof_tool_does_not_repeat_a_configured_flag.py`,
        # which derives the forbidden flags from addopts rather than listing
        # them, so the next flag added there cannot be doubled here either.
        #
        # `OSError` and not just the existence check above: a `pytest.exe` that
        # is present and cannot be started — a truncated install, a stub, a
        # file that is not an executable image — produced no test result either,
        # and today it leaves this process dying on a traceback at exit 1. Exit
        # 1 is NOT PROVEN, the verdict reserved for "the parent already
        # satisfied your guard", which is a claim about the code. CQ-22.
        try:
            run = subprocess.run([str(PYTEST), args.node_id],
                                 cwd=ROOT, capture_output=True, text=True)
        except OSError as exc:
            spawn_error = exc
    finally:
        # Restore before reporting, so a failure to restore is never masked by
        # an interesting result. `git checkout HEAD -- .` returns every tracked
        # file, line endings included; the copy is only for a test file that is
        # untracked, which checkout cannot know about. Copying back
        # unconditionally is what the first run of this script did, and it left
        # the file LF in a CRLF worktree — a diff with no content, reported as
        # modified, from a script whose whole promise is to restore cleanly.
        #
        # The return code is kept rather than dropped. This call is the only
        # thing standing between the script and a tree left at the parent
        # commit, and a failure here is the one outcome an operator has to be
        # told about before any verdict — so it is reported after the block,
        # ahead of everything else. CQ-21.
        restore = _git("checkout", "HEAD", "--", ".")
        if kept.is_file() and not absolute.is_file():
            shutil.copy2(kept, absolute)
        if restore.returncode == 0:
            for path, was in stamps.items():
                if path.is_file():
                    os.utime(path, ns=(was.st_atime_ns, was.st_mtime_ns))

    if restore is not None and restore.returncode != 0:
        print(f"CANNOT ANSWER: the restore failed — `git checkout HEAD -- .` "
              f"exited {restore.returncode}. The working tree may still be at "
              f"{parent_sha}; check `git status` before doing anything else.\n"
              f"{restore.stderr.strip()}")
        return 2

    if run is None:
        print(f"CANNOT ANSWER: could not start the runner at {PYTEST} — "
              f"{spawn_error}. The tree was reverted and restored; no test "
              "result exists, which is not the same as a guard that proves "
              "nothing.")
        return 2

    tail = "\n".join(run.stdout.strip().splitlines()[-3:])

    # pytest's own exit codes, not a search for "error" in the output. The
    # string test read ReportCheckError in a perfectly good failure and called
    # it a no-result: 1 is tests-failed, 2-5 are interrupted, internal error,
    # bad usage and nothing-collected.
    if run.returncode not in (0, 1):
        print(f"CANNOT ANSWER: the runner exited {run.returncode} against "
              f"{parent_sha} — no test result.\n{tail}\n"
              "Collection may have aborted; a test that cannot run is not a "
              "test that passed.")
        return 2

    if run.returncode == 1:
        print(f"PROVEN: {args.node_id} FAILS against {parent_sha}.\n{tail}")
        return 0

    print(f"NOT PROVEN: {args.node_id} PASSES against {parent_sha}, so it does not "
          f"demonstrate the fix at HEAD.\n{tail}\n"
          "Either the guard asserts something the parent already satisfied, or it "
          "asserts one direction of a two-direction claim.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
