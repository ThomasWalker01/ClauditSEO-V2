"""The export tool refuses, and leaves nothing behind when it refuses.

`scripts/export_public.py` replaced a by-hand sequence - archive, scan,
exclusion check, bare suite - and the value of doing that is entirely in the
refusal path. An export tool that produced output *and* printed a warning would
be worse than the checklist it replaced, because the output is what gets
pushed and the warning scrolls past. So the property under test here is not
"it finds a leak"; it is **that a tree which fails a check does not exist when
the tool exits**.

The checks are driven against synthetic repositories rather than this one.
Two reasons, the second the important one:

- this repository is clean, so it can only exercise the passing path;
- a guard whose only subject is the real tree cannot tell "the scan found
  nothing" from "the scan did not run", which is the vacuous-pass shape
  `scripts/check_carveout.py` records against its own first assertion.

Each synthetic repository is a real git repository with a real commit, because
the tool reads HEAD rather than the working copy and that distinction is one of
the things it is meant to catch.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "export_public.py"

#: Loaded by path rather than imported: `scripts/` is not a package, and the
#: neighbouring guards over `check_restarts.py` and `check_carveout.py` load
#: their subjects the same way.
_spec = importlib.util.spec_from_file_location("export_public", SCRIPT)
assert _spec and _spec.loader
ex = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ex)

GIT = shutil.which("git")
needs_git = pytest.mark.skipif(
    GIT is None,
    reason="git is not on PATH; this guard builds real repositories because "
           "the tool reads HEAD, not the working copy")


def _repo(path: Path, files: dict[str, str], message: str = "x") -> None:
    """A git repository holding `files`, all committed under `message`.

    `message` is defaulted rather than required because every clause here
    predates the message scan and none of them is about the message; the
    three that are pass one deliberately.
    """
    path.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        p = path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    assert GIT
    subprocess.run([GIT, "init", "-q"], cwd=path, check=True,
                   capture_output=True)
    subprocess.run([GIT, "add", "-A"], cwd=path, check=True, capture_output=True)
    subprocess.run([GIT, "-c", "user.name=t", "-c", "user.email=t@t",
                    "commit", "-q", "-m", message], cwd=path, check=True,
                   capture_output=True)


#: A repository shaped like this one: a manifest of withheld globs, a token
#: list, and `.gitattributes` rules that actually withhold them.
#:
#: The `.gitattributes` line for `.client-tokens` is not decoration. The first
#: run of this guard left it out and the clean-tree case then FAILED - because
#: the token list is a file containing the token, so an export carrying it
#: leaks by definition. The script was right and the fixture was wrong, which
#: is the half worth recording: a fixture that does not model the
#: `export-ignore` rules is not modelling an export.
CLEAN = {
    "PUBLIC_EXCLUDE.txt":
        "# withheld, one glob per line\nnotes.md\n.client-tokens\n",
    ".client-tokens": "# why\nacmeclient: a client\n",
    ".gitattributes":
        "notes.md export-ignore\n.client-tokens export-ignore\n",
    "README.md": "A tool. Nothing private here.\n",
    "tests/test_x.py": "def test_x():\n    assert True\n",
}


# --- the two content checks, in isolation --------------------------------

def test_a_withheld_path_that_is_in_the_tree_is_found(tmp_path):
    """The check itself, away from git and the staging dance."""
    (tmp_path / "notes.md").write_text("x", encoding="utf-8")
    assert ex.present_excluded(tmp_path, ["notes.md"]) == ["notes.md"]
    assert ex.present_excluded(tmp_path, ["absent.md"]) == []


def test_a_directory_the_manifest_names_with_a_slash_is_found(tmp_path):
    """`PUBLIC_EXCLUDE.txt` writes directories as `audits/`, and a naive
    `(root / "audits/").exists()` is fine on posix but the trailing separator
    has bitten path handling here before."""
    (tmp_path / "audits").mkdir()
    (tmp_path / "audits" / "001.md").write_text("x", encoding="utf-8")
    assert ex.present_excluded(tmp_path, ["audits/"]) == ["audits/"]


def test_a_token_is_matched_at_letter_boundaries_and_not_inside_a_word(tmp_path):
    """The rule item 187 arrived at the hard way, both halves of it.

    A bare substring rule rewrote an ordinary English word throughout
    axe-core's licence text, because one client's name was a substring of it;
    `\\b` misses `<name>_energy_home.json`, because `_` is a word character
    and that is how the harvested fixtures were named.

    Demonstrated with a fictional `opal`, which has both properties - it sits
    inside `opaline` and it takes an underscore suffix. The real names are not
    written here, for the reason the neighbouring guard gives: this file ships,
    and it cannot scan itself.
    """
    (tmp_path / "a.json").write_text('{"page": "opal_energy_home"}',
                                     encoding="utf-8")
    (tmp_path / "b.txt").write_text("an opaline glaze, and opalescent too",
                                    encoding="utf-8")
    (tmp_path / "c.txt").write_text("follow 13opal on socials",
                                    encoding="utf-8")

    hits = ex.token_hits(tmp_path, {"opal": "a client"})
    found = {(path, tok) for path, tok, _why, _ctx in hits}
    assert ("a.json", "opal") in found, "an underscore-suffixed name was missed"
    assert ("c.txt", "opal") in found, "a digit prefix should still bound"
    assert ("b.txt", "opal") not in found, \
        "the token matched inside `opaline`, so the boundary rule is gone " \
        "and a vendored licence file will now be reported as client data"


def test_a_token_hit_carries_the_text_around_it(tmp_path):
    """A path and a token do not tell the reader whether they are looking at a
    name to rename or a harvested fixture to regenerate. The surrounding text
    usually does, and that judgement is the point of item 187's group A."""
    (tmp_path / "f.txt").write_text(
        "Wharfside's Friendliest Lender In Town, apply today",
        encoding="utf-8")
    [(_p, _t, _w, context)] = ex.token_hits(
        tmp_path,
        {"Friendliest Lender In Town": "a slogan; the fixture was harvested"})
    assert "Wharfside" in context and "apply" in context


# --- the refusal path, which is the reason this tool exists ---------------

@needs_git
def test_a_leaking_tree_is_refused_and_nothing_is_written(tmp_path):
    """The load-bearing property. A tree that fails a check must not exist.

    If it did, the next step - a person pushing the directory the tool just
    made - would publish it, and the printed refusal would be scrollback.
    """
    repo = tmp_path / "repo"
    files = dict(CLEAN)
    files["docs/example.md"] = "Worked example: acmeclient's home page.\n"
    _repo(repo, files)
    ex.ROOT = repo

    dest = tmp_path / "out"
    assert ex.main([str(dest), "--no-collect"]) == 1
    assert not dest.exists(), \
        "a refused export left a directory behind, which is the one thing " \
        "this tool must never do"


@needs_git
def test_a_withheld_path_that_was_committed_is_refused(tmp_path):
    """The other leak. `export-ignore` is read from the COMMITTED tree, so a
    rule added to `.gitattributes` and not committed protects nothing - and
    the path then arrives in the archive, which is what this reads."""
    repo = tmp_path / "repo"
    files = dict(CLEAN)
    files["notes.md"] = "private working notes\n"
    # Its rule removed, which is the realistic version of this mistake:
    # `export-ignore` is read from the COMMITTED tree, so a rule added to
    # `.gitattributes` and not committed protects nothing at all.
    files[".gitattributes"] = ".client-tokens export-ignore\n"
    _repo(repo, files)
    ex.ROOT = repo

    dest = tmp_path / "out"
    assert ex.main([str(dest), "--no-collect"]) == 1
    assert not dest.exists()


@needs_git
def test_a_clean_tree_is_exported(tmp_path):
    """The passing path, without which every refusal above could be a tool
    that refuses everything - the shape DISCIPLINE rule 5 asks after."""
    repo = tmp_path / "repo"
    _repo(repo, CLEAN)
    ex.ROOT = repo

    dest = tmp_path / "out"
    assert ex.main([str(dest), "--no-collect"]) == 0
    assert (dest / "README.md").is_file()
    assert not (dest / "notes.md").exists()


@needs_git
def test_an_uncommitted_edit_is_refused_before_anything_is_exported(tmp_path):
    """`git archive` reads HEAD. An export taken with a modified tracked file
    is an export of the previous commit, and it looks entirely normal - so it
    is refused rather than warned about."""
    repo = tmp_path / "repo"
    _repo(repo, CLEAN)
    (repo / "README.md").write_text("edited, not committed\n", encoding="utf-8")
    ex.ROOT = repo

    dest = tmp_path / "out"
    assert ex.main([str(dest), "--no-collect"]) == 2
    assert not dest.exists()


@needs_git
def test_an_empty_token_list_is_refused_rather_than_passed(tmp_path):
    """An empty list finds nothing and a clean tree finds nothing, and they
    print the same thing. This is the vacuous pass CQ-37 is about, one level
    down: the check that cannot fail."""
    repo = tmp_path / "repo"
    files = dict(CLEAN)
    files[".client-tokens"] = "# every line here is a comment\n"
    _repo(repo, files)
    ex.ROOT = repo

    dest = tmp_path / "out"
    assert ex.main([str(dest), "--no-collect"]) == 2
    assert not dest.exists()


@needs_git
def test_an_existing_destination_is_not_replaced_without_being_asked(tmp_path):
    """The destination is 700-odd files somewhere on the operator's disk."""
    repo = tmp_path / "repo"
    _repo(repo, CLEAN)
    ex.ROOT = repo

    dest = tmp_path / "out"
    dest.mkdir()
    (dest / "keep.txt").write_text("mine", encoding="utf-8")
    assert ex.main([str(dest), "--no-collect"]) == 2
    assert (dest / "keep.txt").is_file(), "an existing directory was clobbered"
    assert ex.main([str(dest), "--no-collect", "--force"]) == 0
    assert not (dest / "keep.txt").exists()
    assert (dest / "README.md").is_file()


# --- the tool and this repository agree ----------------------------------

def test_this_repositorys_own_lists_are_readable_by_the_tool():
    """The formats are shared with `tests/test_no_client_data_ships.py`, and
    the two files are NOT the same shape - the manifest is one glob per line,
    the token list is `token: reason`. A reformat of either that the matching
    parser cannot read shows up as an export with nothing withheld and no
    tokens to find, which is to say as a pass."""
    withheld = ex.globs(ROOT / ex.MANIFEST_NAME)
    assert len(withheld) >= 5, f"only {len(withheld)} withheld paths parsed"
    assert not any(":" in g for g in withheld), (
        "a withheld line carries a colon, so the manifest has been rewritten "
        "into `path: reason` form - and `globs()` would then return paths "
        "with a reason stuck on the end, none of which exist, which reads as "
        "a clean export")

    tokens_file = ROOT / ex.TOKENS_NAME
    if not tokens_file.is_file():
        pytest.skip("no .client-tokens: this is an exported tree, and the "
                    "token list is withheld from it by design")
    tokens = ex.entries(tokens_file)
    assert len(tokens) >= 5, f"only {len(tokens)} tokens parsed"
    assert all(why for why in tokens.values()), "a token with no reason"


def test_the_suite_command_the_tool_prints_is_the_one_it_names(capsys):
    """The tool tells the operator what to run before publishing. That string
    and the one in its docstring's promise are the same object, so they cannot
    drift into two different commands."""
    assert ex.main(["--print-suite-command"]) == 0
    printed = capsys.readouterr().out.strip()
    assert printed == ex.SUITE_COMMAND
    for part in ("pytest", "-p no:cacheprovider"):
        assert part in printed, f"the bare-suite command lost {part!r}"


# --- the message scan -----------------------------------------------------
#
# A commit message is not a file. It never enters the archive, so checks 2
# and 3 cannot see it, and a tree can pass every one of them while the
# message a publish would put beside it names a client. Measured on this
# repository on 2026-09-23: 12 of the 14 tokens in `.client-tokens` appear in
# commit messages, and 7 of the last 40 messages carry one.
#
# The scan is therefore about a surface the export does not currently carry,
# which is why the clause below about NOT refusing matters as much as the two
# about refusing.


def test_a_token_in_a_commit_message_is_found():
    """The scan itself, away from git.

    Matched with the same `pattern()` as the file scan, so the letter-boundary
    rule item 187 arrived at the hard way holds here too: a name inside a
    longer word is not a hit, and an underscore does not hide one.
    """
    msgs = [("a" * 40, "fix: a thing\n\nMeasured on acmeclient's home page.\n"),
            ("b" * 40, "fix: another thing\n\nNothing private here.\n")]
    hits = ex.message_hits(msgs, {"acmeclient": "a client"})
    assert len(hits) == 1, hits
    sha, subject, tok, why, context = hits[0]
    assert sha == "a" * 40 and tok == "acmeclient" and why == "a client"
    assert subject == "fix: a thing", (
        "a refusal names the hash and not the commit, so a reader has to go "
        f"and look it up: {subject!r}")
    assert "acmeclient" in context

    # The boundary rule, both directions, as the file scan holds it.
    assert not ex.message_hits([("c" * 40, "about acmeclientele\n")],
                               {"acmeclient": "a client"})
    assert ex.message_hits([("d" * 40, "see acmeclient_home.json\n")],
                           {"acmeclient": "a client"})


@needs_git
def test_a_clean_tree_with_a_dirty_message_is_refused_and_nothing_is_written(tmp_path):
    """The case the file checks cannot reach, and the reason this exists.

    The tree here passes checks 2 and 3 completely - there is no withheld
    path and no token in any file. Only the message names the client. Without
    the scan this exports, and a publish that carries messages would put the
    name beside a tree that was verified clean.
    """
    repo = tmp_path / "repo"
    _repo(repo, CLEAN, message="fix: the thing\n\nFound on acmeclient's site.")
    ex.ROOT = repo

    dest = tmp_path / "out"
    assert ex.main([str(dest), "--no-collect", "--with-messages"]) == 1
    assert not dest.exists(), (
        "a refused export left a directory behind; the message scan has to "
        "refuse the same way every other check does, or it is a warning")


@needs_git
def test_a_dirty_message_does_not_refuse_an_export_that_publishes_no_message(tmp_path, capsys):
    """The scope claim, and it is half the design.

    An export writes a TREE. It publishes no message, so refusing it for a
    name in one would be refusing content it does not carry - and the thing
    an operator learns from a check that fires on the irrelevant is which
    flag silences it. So the same repository that is refused above exports
    cleanly here.

    What it must not do is pass quietly. An unfound token and an absent scan
    print the same and mean opposite things, which is this script's own rule
    about its token list; so the run says the scan did not happen and names
    the flag that would make it.
    """
    repo = tmp_path / "repo"
    _repo(repo, CLEAN, message="fix: the thing\n\nFound on acmeclient's site.")
    ex.ROOT = repo

    dest = tmp_path / "out"
    assert ex.main([str(dest), "--no-collect"]) == 0
    assert (dest / "README.md").is_file()
    out = capsys.readouterr().out
    assert "--with-messages" in out and "did not run" in out, (
        "the export was silent about not scanning the messages, so a reader "
        f"cannot tell this from a scan that found nothing: {out!r}")


@needs_git
def test_a_range_that_names_no_commit_is_refused_rather_than_passed(tmp_path):
    """The vacuous pass, in the shape this script refuses it everywhere else.

    `HEAD..HEAD` is empty, so the scan reads nothing and finds nothing. That
    prints identically to a clean scan of forty messages and means the
    opposite, which is exactly why an empty token list is refused too.
    """
    repo = tmp_path / "repo"
    _repo(repo, CLEAN)
    ex.ROOT = repo

    dest = tmp_path / "out"
    assert ex.main([str(dest), "--no-collect", "--with-messages", "HEAD..HEAD"]) == 1
    assert not dest.exists()


# --- publishing -----------------------------------------------------------
#
# The same property as the rest of this file, moved one step further out. A
# refused export must leave no directory behind because the directory is what
# a person pushes; a refused export must reach no remote at all because a push
# is the step that cannot be undone.
#
# The destinations here are local bare repositories. Git treats a path as a
# URL, so the code under test is the code that runs against GitHub - clone,
# replace, commit, push - with nothing stubbed.


@pytest.fixture(autouse=True)
def _an_identity(monkeypatch):
    """A committer for the publish step's own commit. It uses the operator's
    git identity, as it should; a CI runner has none, and all four publish
    tests failed there on "Author identity unknown" (the V2 fresh start,
    2026-09-26) while passing on a machine with a global `user.name`."""
    for var, value in (("GIT_AUTHOR_NAME", "t"), ("GIT_AUTHOR_EMAIL", "t@t"),
                       ("GIT_COMMITTER_NAME", "t"), ("GIT_COMMITTER_EMAIL", "t@t")):
        monkeypatch.setenv(var, value)


def _bare(path):
    """An empty bare repository, standing in for the public remote."""
    assert GIT
    subprocess.run([GIT, "init", "--bare", "--quiet", "-b", "main", str(path)],
                   check=True, capture_output=True)
    return path


def _commit(path, files, message="x"):
    """A further commit in an existing repository.

    Not `shutil.rmtree` and a fresh `_repo`: git marks its object files
    read-only, so on Windows `rmtree` raises `PermissionError` on
    `.git/objects`. Rebuilding was never the point - these clauses are about
    a SECOND export of a CHANGED tree, which is one more commit.
    """
    for name, text in files.items():
        f = path / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    assert GIT
    subprocess.run([GIT, "add", "-A"], cwd=path, check=True,
                   capture_output=True)
    subprocess.run([GIT, "-c", "user.name=t", "-c", "user.email=t@t",
                    "commit", "-q", "-m", message], cwd=path, check=True,
                   capture_output=True)


def _head(bare):
    """The destination's current commit, or None while it has none."""
    assert GIT
    done = subprocess.run([GIT, "rev-parse", "--verify", "HEAD"], cwd=bare,
                          capture_output=True, text=True)
    return done.stdout.strip() if done.returncode == 0 else None


def _file_at_head(bare, name):
    assert GIT
    done = subprocess.run([GIT, "show", f"HEAD:{name}"], cwd=bare,
                          capture_output=True, text=True)
    return done.stdout if done.returncode == 0 else None


@needs_git
def test_a_refused_tree_reaches_no_remote(tmp_path):
    """The load-bearing property of this flag.

    A directory left behind by a refused export is recoverable - someone has
    to choose to push it. A push is not: the tree is on a server, and on a
    public one it has been read before it can be replaced. So the refusal has
    to happen before the clone, not between the commit and the push.
    """
    repo = tmp_path / "repo"
    files = dict(CLEAN)
    files["docs/example.md"] = "Worked example: acmeclient's home page.\n"
    _repo(repo, files)
    ex.ROOT = repo
    bare = _bare(tmp_path / "remote.git")

    assert ex.main(["--no-collect", "--publish", bare.as_posix()]) == 1
    assert _head(bare) is None, (
        "a tree that failed the token scan was published; the refusal has to "
        "come before the clone, because a push cannot be taken back")


@needs_git
def test_a_message_that_names_a_client_reaches_no_remote(tmp_path):
    """The same, for the surface the file checks cannot see.

    The tree here is clean. Only the message names the client, and only
    `--with-messages` makes that message part of the publish - so this is the
    case where the payload is refused while the tree it would have travelled
    with is perfectly sound.
    """
    repo = tmp_path / "repo"
    _repo(repo, CLEAN, message="fix: a thing\n\nSeen on acmeclient's site.")
    ex.ROOT = repo
    bare = _bare(tmp_path / "remote.git")

    assert ex.main(["--no-collect", "--with-messages",
                    "--publish", bare.as_posix()]) == 1
    assert _head(bare) is None


@needs_git
def test_a_verified_tree_is_published_and_the_remote_carries_it(tmp_path):
    """The passing path, without which every refusal above could be a flag
    that publishes nothing at all."""
    repo = tmp_path / "repo"
    _repo(repo, CLEAN)
    ex.ROOT = repo
    bare = _bare(tmp_path / "remote.git")

    assert ex.main(["--no-collect", "--publish", bare.as_posix()]) == 0
    assert _head(bare), "nothing was published"
    assert _file_at_head(bare, "README.md"), "the published tree has no README"
    assert _file_at_head(bare, "notes.md") is None, (
        "the withheld path was published; the publish must carry the VERIFIED "
        "tree and not the working copy")


@needs_git
def test_a_publish_that_changes_nothing_commits_nothing(tmp_path):
    """An export identical to what is already there makes no commit.

    Git would only make an empty one if asked, so this is really about the
    report: a publish an operator expected to change something and which did
    not is otherwise indistinguishable from one that worked.
    """
    repo = tmp_path / "repo"
    _repo(repo, CLEAN)
    ex.ROOT = repo
    bare = _bare(tmp_path / "remote.git")

    assert ex.main(["--no-collect", "--publish", bare.as_posix()]) == 0
    first = _head(bare)
    assert ex.main(["--no-collect", "--publish", bare.as_posix()]) == 0
    assert _head(bare) == first, (
        "a second publish of an identical tree moved the remote, so the "
        "public history gains a commit per run rather than per change")


@needs_git
def test_a_publish_appends_rather_than_replacing(tmp_path):
    """The destination's history is kept, which is the whole reason a reader
    is being sent there."""
    repo = tmp_path / "repo"
    _repo(repo, CLEAN)
    ex.ROOT = repo
    bare = _bare(tmp_path / "remote.git")
    assert ex.main(["--no-collect", "--publish", bare.as_posix()]) == 0
    first = _head(bare)

    _commit(repo, {"README.md": "A tool. Now with a second paragraph.\n"})
    assert ex.main(["--no-collect", "--publish", bare.as_posix()]) == 0

    assert GIT
    log = subprocess.run([GIT, "rev-list", "HEAD"], cwd=bare,
                         capture_output=True, text=True).stdout.split()
    assert len(log) == 2 and log[-1] == first, (
        f"the publish did not append to what was there: {log}")


@needs_git
def test_orphan_replaces_the_history_when_it_is_asked_to(tmp_path):
    """The older shape, kept for the case the rules tighten and everything
    already published has to be restated."""
    repo = tmp_path / "repo"
    _repo(repo, CLEAN)
    ex.ROOT = repo
    bare = _bare(tmp_path / "remote.git")
    assert ex.main(["--no-collect", "--publish", bare.as_posix()]) == 0

    _commit(repo, {"README.md": "A tool. Restated.\n"})
    assert ex.main(["--no-collect", "--orphan",
                    "--publish", bare.as_posix()]) == 0

    assert GIT
    log = subprocess.run([GIT, "rev-list", "HEAD"], cwd=bare,
                         capture_output=True, text=True).stdout.split()
    assert len(log) == 1, (
        f"--orphan left the previous history in place: {log}")


def test_the_published_message_says_when_it_carries_no_source_message():
    """A public repository whose commits all read "Export of abc1234" invites
    the reader to think the messages were lost. They were withheld, and those
    are different facts about a project - so the generated message says which
    it is."""
    generated = ex.published_message("a" * 40, None)
    assert "aaaaaaaaaaaa" in generated
    assert "No commit message from the source repository is published" in generated

    one = ex.published_message("a" * 40, [("b" * 40, "fix: a thing\n\nWhy.\n")])
    assert one.strip() == "fix: a thing\n\nWhy.".strip(), (
        f"a single source message is not carried verbatim: {one!r}")

    two = ex.published_message("a" * 40, [("b" * 40, "second\n"), ("c" * 40, "first\n")])
    assert "Export of 2 commits" in two
    assert two.index("first") < two.index("second"), (
        "the carried messages are newest-first, which reads backwards against "
        f"every other log: {two!r}")
