"""No client's name or data is in the tree a public export would ship.

Item 187. The operator is preparing ClauditSEO for a public release. The
database was never the problem - `data/` is gitignored and does not ship - but
real client data was scattered across the tracked tree: audit logs, test
fixtures harvested from live sites, benchmark reports, and client names used as
worked examples in code comments.

This is the acceptance signal for that work, and it is meant to outlive it: a
comment added next year naming a client fails here, which is the only way a
tree stays clean after the round that cleaned it.

**What it reads, and why the lists are not in this file.**

- `PUBLIC_EXCLUDE.txt` - the paths a public export leaves behind, each with its
  reason. The export and this scan read the same manifest, because two lists
  drift and the drift is silent in the direction that matters: a path skipped
  by the scan but still exported is a leak.
- `.client-tokens` - the names and the data fingerprints. Excluded from the
  export itself, because a public file listing "never ship these clients"
  discloses the client relationships it exists to protect. When it is absent -
  which is exactly the case in an exported tree - this skips and says so.

**Fingerprints, not just names.** Renaming a client's domain to `example.com` in
a harvested crawl export leaves the client's marketing copy in the rows. So the
token list carries phrases as well as names, and a fingerprint hit means the
fixture around it was harvested rather than authored - a regeneration, not a
rename. That distinction is the whole of item 187's group A.

**Do not weaken this to make it pass.** If a fixture cannot be rebuilt without
real data, that is a fact about the test that reads it - it was coupled to one
real site's shape - and it is worth surfacing rather than working around.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.needs_repo import needs_repo, skip_unless_repo

ROOT = Path(__file__).resolve().parents[1]
TOKENS_FILE = ROOT / ".client-tokens"
MANIFEST = ROOT / "PUBLIC_EXCLUDE.txt"

#: This file names every client it searches for, so it cannot scan itself, and
#: neither can the two lists it reads. Nothing else is exempt.
SELF = {
    "tests/test_no_client_data_ships.py": "the guard names the tokens it looks for",
    ".client-tokens": "the token list itself, and excluded from the export",
    "PUBLIC_EXCLUDE.txt": "the manifest, which names the excluded paths",
}


def _entries(path: Path) -> dict[str, str]:
    """`token: reason` lines, comments and blanks dropped."""
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        token, _, reason = line.partition(":")
        out[token.strip()] = reason.strip() or "no reason recorded"
    return out


def _excluded(path: Path) -> list[str]:
    globs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            globs.append(line)
    return globs


def _ships(rel: str, excluded: list[str]) -> bool:
    """Is this tracked path part of what a public export would carry?"""
    if rel in SELF:
        return False
    for glob in excluded:
        if glob.endswith("/"):
            if rel == glob.rstrip("/") or rel.startswith(glob):
                return False
        elif rel == glob:
            return False
    return True


def _pattern(token: str) -> re.Pattern[str]:
    """How a token is matched, and the rule is narrower than "substring".

    One client's name was a substring of `exclusive`, so the first run of this
    guard reported axe-core's licence text and its minified source as client
    data. A name bounded by letters on either side is a different word.

    Not `\b` either: that treats `_` as a word character, and the harvested
    fixtures were named `<client>_energy_home_...`, so a `\b`-bounded name would
    miss the very files this exists to find. The boundary is "not a letter",
    which keeps a name followed by `_`, `-` or a digit and drops one that is
    part of a longer word.

    (The examples that used to stand here named the clients, in the one file
    that ships and cannot scan itself. They are gone for the same reason the
    token list is not in this file.)

    A fingerprint is a phrase, not a name, so it is matched literally - its
    own words are the boundary.
    """
    if " " in token:
        return re.compile(re.escape(token.lower()))
    return re.compile(rf"(?<![a-z]){re.escape(token.lower())}(?![a-z])")


def _tracked() -> list[str]:
    """Every tracked path, from git rather than from a directory walk: what
    ships is what is TRACKED, and a walk would scan `data/`, `.venv` and the
    build output, none of which a public export carries.

    `shutil.which` rather than the bare name, which
    `test_program_names.py` caught here on the first full suite: on Windows
    CreateProcess resolves a bare program name through System32 before PATH,
    so the thing that runs need not be the thing that was checked."""
    skip_unless_repo()
    git = shutil.which("git")
    assert git, "git is not on PATH, and the tracked set is read from it"
    out = subprocess.run([git, "ls-files", "-z"], cwd=ROOT, capture_output=True,
                         check=True)
    return [p for p in out.stdout.decode("utf-8").split("\0") if p]


# The strict xfail that stood here through the scrub is gone, in the commit
# that made this pass - which is what strict xfail is for: it would have
# reported XPASS as a failure and refused to let the marker outlive the work.
@pytest.mark.skipif(not TOKENS_FILE.is_file(),
                    reason=".client-tokens is absent, which is what an exported "
                           "tree looks like: the scan belongs to the repository "
                           "that produces the export, not to the export")
def test_no_client_name_or_captured_data_is_in_the_shippable_tree():
    tokens = _entries(TOKENS_FILE)
    assert tokens, ".client-tokens carries no tokens; the guard would pass by default"
    excluded = _excluded(MANIFEST)
    assert excluded, "PUBLIC_EXCLUDE.txt names nothing; every path would be scanned"

    matchers = [(t, _pattern(t)) for t in tokens]
    hits: dict[str, list[str]] = {t: [] for t in tokens}
    scanned = 0
    for rel in _tracked():
        if not _ships(rel, excluded):
            continue
        try:
            text = (ROOT / rel).read_text(encoding="utf-8", errors="strict").lower()
        except (UnicodeDecodeError, FileNotFoundError, OSError):
            continue  # binary, or a path git knows and the disk does not
        scanned += 1
        for token, pattern in matchers:
            if pattern.search(text):
                hits[token].append(rel)

    assert scanned > 100, f"only {scanned} files scanned; the manifest is too wide"

    found = {t: fs for t, fs in hits.items() if fs}
    if found:
        lines = []
        for token, files in sorted(found.items(), key=lambda kv: -len(kv[1])):
            lines.append(f"  {token} — {tokens[token]}")
            lines.append(f"      {len(files)} file(s): "
                         + ", ".join(sorted(files)[:6])
                         + (" …" if len(files) > 6 else ""))
        pytest.fail(
            f"{len(found)} client token(s) in the shippable tree, across "
            f"{len({f for fs in found.values() for f in fs})} file(s):\n"
            + "\n".join(lines)
            + "\n\n  A name is a rename. A fingerprint means the fixture around "
              "it was harvested and needs rebuilding, not renaming.")


def test_the_manifest_and_the_token_list_explain_themselves():
    """Both lists carry a reason per entry, because a bare list of paths is a
    decision with its argument thrown away - and this one is a decision about
    what the public never sees."""
    for path in (MANIFEST,) + ((TOKENS_FILE,) if TOKENS_FILE.is_file() else ()):
        text = path.read_text(encoding="utf-8")
        assert text.lstrip().startswith("#"), f"{path.name} opens with no reason"
        body = [ln for ln in text.splitlines()
                if ln.strip() and not ln.strip().startswith("#")]
        assert body, f"{path.name} is all comment and no content"
    if TOKENS_FILE.is_file():
        for token, reason in _entries(TOKENS_FILE).items():
            assert reason != "no reason recorded", (
                f"{token} is listed with no reason; a red run would not say "
                "whether it is a name to replace or data to rebuild")


@needs_repo
def test_every_excluded_path_is_excluded_by_git_and_not_only_by_a_list():
    """The manifest is prose until git agrees with it.

    `scripts/package.sh` builds the distributable with `git archive HEAD`,
    deliberately - so that git, rather than a glob in a shell script, decides
    what ships. That makes `export-ignore` in `.gitattributes` the mechanism
    and `PUBLIC_EXCLUDE.txt` the argument, and this clause is what stops the
    two from drifting apart: a path reasoned about in one and forgotten in the
    other is exactly the silent half of a leak.

    Checked through `git check-attr` rather than by parsing `.gitattributes`,
    because the file's own opening comment records what parsing costs - its
    paths named a directory that had been renamed ten rounds earlier, so the
    rules parsed, matched nothing, and protected nothing. Only git can say
    whether a rule reaches a path.
    """
    git = shutil.which("git")
    assert git, "git is not on PATH"
    declared = _excluded(MANIFEST)
    assert declared, "the manifest is empty"
    out = subprocess.run([git, "check-attr", "export-ignore", "--"] + declared,
                         cwd=ROOT, capture_output=True, check=True)
    missing = [line for line in out.stdout.decode("utf-8").splitlines()
               if line and not line.endswith(": set")]
    assert not missing, (
        "these are excluded by the manifest and not by git, so `git archive` "
        "would ship them: " + ", ".join(missing))

    # And the other direction: a path git leaves behind with no line in the
    # manifest is an exclusion nobody argued for.
    attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    ignored = {line.split()[0] for line in attrs.splitlines()
               if line.strip() and not line.strip().startswith("#")
               and "export-ignore" in line}
    unexplained = ignored - set(declared)
    assert not unexplained, (
        "these are excluded by .gitattributes with no reason in the manifest: "
        + ", ".join(sorted(unexplained)))
