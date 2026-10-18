"""Whether this checkout is a git repository.

A handful of guards ask git about the tree rather than reading it: which files
are tracked (`git ls-files`), which paths `export-ignore` reaches
(`git check-attr`), whether the archive name is ignored (`git check-ignore`),
and whether the packaging scripts - which are `git archive` - succeed. Each is
a question only a repository can answer.

The public export is not one. It is `git archive` output, and a stranger who
downloads it as a zip has no `.git` either. Measured on the export of
`7f0c450` (2026-09-24): six failures, every one `fatal: not a git repository`,
and nothing in any of them said so - a `CalledProcessError`, or an assertion
quoting git's stderr. The same shape `needs_build.py` records for the bundle:
a missing prerequisite reported as a defect.

So those guards skip, naming what is missing. This is `.git` on disk rather
than `git rev-parse`, deliberately:

- A tree extracted INSIDE some other repository would pass a `rev-parse`
  check and then have every question answered about the wrong repository -
  `ls-files` from a subdirectory the parent does not track lists nothing,
  and "the tracked list is not vacuously short" fails for a reason that is
  not this tree's. `.git` beside `pyproject.toml` is this tree's own.
- A worktree's `.git` is a file, not a directory; `exists()` takes both.
- Git being absent in a real repository is NOT a skip. The guards that shell
  out keep their own "git is not resolvable" failure: in the repository that
  can fix things, an unanswerable guard is a red, not a quiet one.

Everything here still runs in the repository, and in CI, which checks it out.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def is_repo(root: Path) -> bool:
    """`root` is the top of a git checkout (a `.git` directory or worktree file)."""
    return (root / ".git").exists()


IN_REPO = is_repo(ROOT)

REASON = ("not a git repository (no .git at the tree's root): this guard asks "
          "git about the tree, which an exported or downloaded copy cannot answer. "
          "It runs in a clone.")

#: For a test that shells out to git about ROOT.
needs_repo = pytest.mark.skipif(not IN_REPO, reason=REASON)


def skip_unless_repo() -> None:
    """For a helper several tests share: skip the caller, inside the test."""
    if not IN_REPO:
        pytest.skip(REASON)
