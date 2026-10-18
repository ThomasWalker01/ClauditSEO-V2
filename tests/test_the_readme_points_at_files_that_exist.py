"""What the README tells a reader to open, and to run, holds.

The README is the first thing an outside reader opens, and since the
"Reading this repository" section it does more than describe the product: it
sends people to specific guards as the design record. A section that names
three files is a section that can rot, and the failure is worse than a
missing paragraph - a dangling pointer in the document that tells you where
the reasoning lives reads as reasoning that was removed.

The suite command is here for the same reason in a different key: the README
is the only document of six that an outside reader opens, so a command in it
that contradicts a rule the repository enforces everywhere else is the first
thing they meet. That one was wrong until 2026-09-23.

**Scoped to what ships**, deliberately. The README also names
`.venv/Scripts/python` and `dashboard/dist`, which exist on a developer's
machine and in neither a fresh clone nor the public export - and this suite
runs in both. So the check covers repository-relative links and the
`tests/*.py` paths the record section cites, which are committed and are the
ones that carry a promise.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"


def _text() -> str:
    return README.read_text(encoding="utf-8")


def test_every_local_link_in_the_readme_resolves():
    """Markdown links to files in this repository, not to the web."""
    links = re.findall(r"\[[^\]]+\]\(([^)]+)\)", _text())
    local = [x for x in links
             if not x.startswith(("http://", "https://", "mailto:", "#"))]
    assert local, "the README links to no local file at all any more"
    missing = [x for x in local if not (ROOT / x.split("#")[0]).exists()]
    assert not missing, (
        f"the README links to files that are not here: {missing}")


def test_every_guard_the_record_section_cites_is_present():
    """The three files "Reading this repository" sends a reader to.

    Named in backticks rather than linked, so the link check above cannot see
    them. They are the section's whole substance: without them it is a claim
    that the tests are the design record, with nothing to read.
    """
    cited = sorted(set(re.findall(r"`(tests/[\w./-]+\.py)`", _text())))
    assert cited, (
        "the README cites no guard by name, so the record section has lost "
        "the examples that make it checkable")
    missing = [c for c in cited if not (ROOT / c).is_file()]
    assert not missing, (
        f"the README sends readers to guards that are gone: {missing}. They "
        "are cited as the design record, so a dangling name reads as "
        "reasoning that was deleted")


def test_the_readmes_own_anchor_links_have_headings():
    """A `#slug` link that matches no heading fails silently in every
    renderer: the reader presses it and the page does not move."""
    text = _text()
    slugs = {
        re.sub(r"[^a-z0-9 -]", "", h.strip().lower()).replace(" ", "-")
        for h in re.findall(r"^#+\s+(.+?)\s*$", text, re.M)
    }
    anchors = {a.lstrip("#") for a in
               re.findall(r"\[[^\]]+\]\((#[^)]+)\)", text)}
    missing = sorted(a for a in anchors if a not in slugs)
    assert not missing, (
        f"these anchors match no heading in the README: {missing}; the "
        f"headings it has are {sorted(slugs)}")


def test_the_readme_runs_the_suite_through_the_console_script():
    """`python -m pytest` puts the working directory on `sys.path`; the
    console script does not.

    The rule is stated in `.claude/DISCIPLINE.md`, `.claude/loop/PROFILE.md`,
    `.claude/skills/audit-fix/SKILL.md`, `scripts/export_public.py` and
    `scripts/prove_fail.py` - which refuses to run at all rather than use the
    module form. The README told readers to do the opposite until item 197's
    round, and it is the only one of those documents a reader outside this
    repository ever sees.

    Asserted on the README rather than trusted to the five statements,
    because a one-line command inside a code block is exactly the thing a
    well-meaning edit puts back.

    Read from the fenced blocks alone, and not from the prose. The first
    version of this clause scanned every line and failed on the sentence
    directly under the block that explains why the module form is wrong -
    which is the note most likely to stop the command coming back. A rule
    that forbids naming the thing it forbids takes the reasoning out with
    the defect.
    """
    fenced = re.findall(r"^```[^\n]*\n(.*?)^```", _text(), re.M | re.S)
    assert fenced, "the README has no code blocks at all any more"
    bad = [ln.strip() for block in fenced for ln in block.splitlines()
           if "-m pytest" in ln]
    assert not bad, (
        "the README runs the suite through the module form, which puts the "
        "working directory on `sys.path` and makes a stranger's checkout "
        f"behave like this one: {bad}")
    assert "Scripts/pytest" in _text(), (
        "the README no longer shows how to run the suite at all; the "
        "console-script form is what the rest of this repository requires")
