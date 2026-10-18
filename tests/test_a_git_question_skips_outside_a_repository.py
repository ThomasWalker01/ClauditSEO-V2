"""A guard that asks git about the tree skips where there is no repository.

`needs_repo.py` records why. This holds the two halves that can disagree: the
decision itself, on real directories, and the population - every test file
that puts a tree question to git says what it does without one.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.needs_repo import is_repo

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"

#: The git questions about the tree. `rev-parse`, `show` and the rest address
#: history or a repository the test builds itself, and are not a property of
#: whether THIS tree is a checkout.
TREE_QUESTION = re.compile(r'"ls-files"|"check-ignore"|"check-attr"|scripts/package\.(sh|ps1)')

#: Either this module's skip, or a skip on git's own refusal.
SAYS_SO = re.compile(r"needs_repo|skip_unless_repo|returncode != 0:\s*\n\s*pytest\.skip\(")


def test_a_bare_directory_is_not_a_repository_and_a_checkout_is(tmp_path):
    bare = tmp_path / "bare"
    bare.mkdir()
    (bare / "pyproject.toml").write_text("", encoding="utf-8")
    assert not is_repo(bare)

    git = shutil.which("git")
    if git is None:
        pytest.skip("git is not on PATH, so no checkout can be made to compare")
    subprocess.run([git, "init", "-q", str(tmp_path / "clone")], check=True)
    assert is_repo(tmp_path / "clone")

    # A worktree: `.git` is a file naming the real one.
    wt = tmp_path / "worktree"
    wt.mkdir()
    (wt / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
    assert is_repo(wt)


def test_a_subdirectory_of_a_checkout_is_not_one(tmp_path):
    """The export extracted inside another repository: git would answer, about
    the wrong tree. Only the tree's own `.git` counts."""
    (tmp_path / ".git").mkdir()
    inner = tmp_path / "export"
    inner.mkdir()
    assert not is_repo(inner)


def test_every_tree_question_to_git_says_what_it_does_without_a_repository():
    asking = [p for p in sorted(TESTS.glob("test_*.py"))
              if p.name != Path(__file__).name
              and TREE_QUESTION.search(p.read_text(encoding="utf-8"))]
    assert len(asking) >= 3, f"the population is suspiciously small: {asking}"
    silent = [p.name for p in asking if not SAYS_SO.search(p.read_text(encoding="utf-8"))]
    assert not silent, (
        "these ask git about the tree and fail, rather than skip, in an exported "
        "copy - use `tests.needs_repo`: " + ", ".join(silent))
