"""The push gate runs the suite on every file the suite asserts on.

CQ-109, report 055. `on.push` carried a `paths-ignore` block listing
`audits/**`, `NEXT_UP.md`, `TIMINGS.md`, `OPERATOR_ACTIONS.md` and then
`'**/*.md'`, which subsumes the rest. The tests it switched off are the ones
that read markdown: `test_loop_instructions.py` runs four row-shape guards over
`KNOWN_ISSUES.md`, `OPERATOR_ACTIONS.md`, `NEXT_UP.md`, `CHANGELOG.md` and
`audits/DISPOSITIONS.md`; `test_release_metadata.py` reads `CHANGELOG.md`;
`test_naming.py` reads `README.md` and `ARCHITECTURE.md`.

That is not hypothetical. Run 32163328377 at `92cf295` failed both python legs
on `test_every_table_row_matches_its_header_width[OPERATOR_ACTIONS.md]`,
`test_no_table_row_is_stranded_in_half[OPERATOR_ACTIONS.md]` and `[TIMINGS.md]`
-- the detector for KI-21, which is open, over two of the four files the block
named. The block had not yet skipped a run only because every push since
`8de7beb` happened to carry code. Its own rationale names `codedash/`,
`receipts/` and `docs/`, three directories that do not exist in this
repository, so it was not written against this tree.

The assertion is not "there is no `paths-ignore`". That would be a guard shaped
like its answer, which is the CQ-83 defect recorded in `audits/DISPOSITIONS.md`
against a different gate. It is the property underneath: for every file the
suite reads as an asserted input, a push touching only that file must still run
the suite. A future narrowing that genuinely excludes nothing the tests read
passes this; one that spells the same mistake differently does not.

The set is enumerated from `test_loop_instructions.TABLE_FILES` and the rename
contract's own two files rather than listed here, per DISCIPLINE rule 3: a
hard-coded list of five is exactly how file six ships unguarded.

Parsed by indentation rather than with a YAML library, for the reason
`test_ci_bounds.py` records: nothing else here depends on PyYAML, and a key
under a known parent is a shape an indentation walk reads reliably.
"""

from __future__ import annotations

import pathlib
import re

from tests.test_loop_instructions import TABLE_FILES

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

#: Files the suite reads as an asserted input, over and above the tables.
#: `test_naming.py` reads both for the rename contract.
NAMING_FILES = (ROOT / "README.md", ROOT / "ARCHITECTURE.md")

#: Every non-Python file a push must not be allowed to hide from the gate.
GUARDED = tuple(sorted({*TABLE_FILES, *NAMING_FILES}))


def _ignore_patterns(text: str) -> list[str]:
    """The `paths-ignore` globs under `on.push`, in file order.

    Walks `on:` then `push:` then `paths-ignore:` by indentation. Returns an
    empty list when the key is absent, which is the state this file holds.
    """
    patterns: list[str] = []
    depth_on: int | None = None
    depth_push: int | None = None
    collecting = False
    for raw in text.splitlines():
        if raw.lstrip().startswith("#"):
            continue
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()
        if collecting:
            if stripped.startswith("- "):
                patterns.append(stripped[2:].strip().strip("'\""))
                continue
            collecting = False
        if indent == 0:
            depth_on = 0 if stripped.strip("'\"").rstrip(":") == "on" else None
            depth_push = None
            continue
        if depth_on is None:
            continue
        if depth_push is None:
            if stripped == "push:":
                depth_push = indent
            continue
        if indent <= depth_push:
            depth_push = indent if stripped == "push:" else None
            continue
        if stripped == "paths-ignore:":
            collecting = True
    return patterns


def _matches(pattern: str, path: str) -> bool:
    """GitHub path-filter glob semantics, narrowed to what this file uses.

    Two stars cross separators, one star does not, and `?` is a single
    non-separator character.

    `**/` is the case that had to be got right rather than assumed: it matches
    *zero* or more leading directories, so `'**/*.md'` covers `README.md` at
    the root and not only `audits/x.md`. Translating it as `.*/` reads the
    pattern as "at least one directory deep", which is how a first draft of
    this file reported four of the eleven hidden files as safe. That is the
    error the block itself invites -- its own comment calls `'**/*.md'` a
    "last-resort catch -- any stray top-level markdown", which is the reading
    a slash-requiring translation contradicts.
    """
    out = ["^"]
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif char == "*":
            out.append("[^/]*")
            i += 1
        elif char == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(char))
            i += 1
    out.append("$")
    return re.match("".join(out), path) is not None


def _repo_relative(path: pathlib.Path) -> str:
    return path.relative_to(ROOT).as_posix()


def test_the_parser_reads_an_ignore_block_when_there_is_one():
    """The detector is proven able to fire before it is trusted to stay quiet.

    Without this, deleting the block and deleting the parser look identical
    from the outside -- a vacuous pass, which is the failure mode a guard over
    an absent key has by construction.
    """
    document = (
        "name: CI\n"
        "on:\n"
        "  push:\n"
        "    branches: [master, main]\n"
        "    # a comment at list indent\n"
        "    paths-ignore:\n"
        "      - 'audits/**'\n"
        "      - TIMINGS.md\n"
        "      - '**/*.md'   # trailing comment\n"
        "  pull_request:\n"
        "jobs:\n"
        "  python:\n"
        "    paths-ignore:\n"
        "      - not-a-trigger.md\n"
    )
    assert _ignore_patterns(document) == ["audits/**", "TIMINGS.md", "**/*.md"]


def test_the_parser_reads_no_block_from_a_trigger_that_has_none():
    document = (
        "name: CI\n"
        "on:\n"
        "  push:\n"
        "    branches: [master, main]\n"
        "  pull_request:\n"
    )
    assert _ignore_patterns(document) == []


def test_the_glob_translation_matches_what_github_would():
    assert _matches("**/*.md", "TIMINGS.md")
    assert _matches("**/*.md", "audits/055-2026-08-19.md")
    assert _matches("**/*.md", ".claude/skills/audit-fix/SKILL.md")
    assert _matches("audits/**", "audits/DISPOSITIONS.md")
    assert _matches("TIMINGS.md", "TIMINGS.md")
    assert not _matches("*.md", "audits/x.md")
    assert not _matches("audits/**", "TIMINGS.md")
    assert not _matches("**/*.md", "clauditseo/api/app.py")
    assert not _matches("**/*.md", "README.mdx")


#: Every file this clause expects to find in the guarded set, and which of
#: them a published tree keeps. Four are the author's working registers, which
#: `PUBLIC_EXCLUDE.txt` withholds with a reason each.
EXPECTED_GUARDED = (
    "OPERATOR_ACTIONS.md",
    "TIMINGS.md",
    "NEXT_UP.md",
    "CHANGELOG.md",
    "KNOWN_ISSUES.md",
    "audits/DISPOSITIONS.md",
    "README.md",
    "ARCHITECTURE.md",
)


def test_the_guarded_set_is_not_empty_and_names_the_files_that_bit():
    """The enumeration is load-bearing; an empty one would pass everything.

    Keyed on what this checkout holds rather than on a count of eight, for the
    reason `tests/private_register.py` records: `TABLE_FILES` is derived from
    the registers that are PRESENT, so in an exported tree the four
    `PUBLIC_EXCLUDE.txt` withholds leave the guarded set legitimately. The
    unconditional form failed there naming `OPERATOR_ACTIONS.md` - a guard
    failing on the deliberate absence of a file it does not guard, which reads
    to a stranger as "this repository is incomplete" rather than "these notes
    are private".

    What is not relaxed is the floor. Keying on existence keeps the assertion
    exact in both trees - all eight where the registers live, the four that
    ship where they do not - and a derivation that has collapsed to nothing
    still fails here, which is the whole reason DISCIPLINE rule 5 asks for
    this clause.
    """
    names = {_repo_relative(p) for p in GUARDED}
    present = [e for e in EXPECTED_GUARDED if (ROOT / e).is_file()]
    assert len(present) >= 4, (
        f"only {len(present)} of {len(EXPECTED_GUARDED)} guarded files exist "
        "in this checkout - a tree without README.md, ARCHITECTURE.md, "
        "CHANGELOG.md and KNOWN_ISSUES.md is not a checkout of this "
        "repository, and every assertion below would pass for free")
    assert len(GUARDED) >= len(present)
    for expected in present:
        assert expected in names, f"{expected} dropped out of the guarded set"


def test_no_push_filter_hides_a_file_the_suite_asserts_on():
    """A push touching only an asserted-on file must still run the gate.

    The failure this catches is a green `master` that was never tested: the run
    does not fail, it is never created, so `gh run list` shows the previous
    commit's result beside the new SHA and nothing anywhere says otherwise.
    """
    patterns = _ignore_patterns(WORKFLOW.read_text(encoding="utf-8"))
    hidden = {
        _repo_relative(path): pattern
        for path in GUARDED
        for pattern in patterns
        if _matches(pattern, _repo_relative(path))
    }
    assert not hidden, (
        "on.push excludes files the suite asserts on, so a commit touching "
        "only these runs no tests at all: "
        + ", ".join(f"{f} (via {g!r})" for f, g in sorted(hidden.items()))
    )
