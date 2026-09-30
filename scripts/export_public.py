"""Produce the public tree, and refuse to produce one that does not verify.

Item 187 established what a public export may not carry; item 190 established
that it has to be able to run its own suite. Both were then done **by hand** -
`git archive` into a temp directory, a token scan, an exclusion check, a bare
pytest run, each a separate ad-hoc command. That worked twice and is the wrong
shape for a third time: the verification most likely to be skipped is the one
that takes twenty-five minutes, and on 2026-09-22 that was the run which caught
a real defect (`tests/test_ci_triggers.py`'s emptiness floor failing on the
deliberate absence of a private register). A checklist in a person's head is
not a gate.

So this does the export and the checks as one operation, and the ordering is
the whole design: **it builds into a staging directory, verifies that, and
moves it into place only if every check passed.** A failed export leaves no
output at all. There is no state in which a directory exists that looks like an
export but was never checked, because that directory is exactly what a person
in a hurry would push.

## What it checks, and what it deliberately does not

1. **The tree is committed.** `git archive HEAD` reads the commit, not the
   working copy, so an uncommitted edit is silently absent from the export.
   That failure is invisible in the output - the export is simply of the
   previous commit - so it is refused up front rather than reported.
2. **Every path `PUBLIC_EXCLUDE.txt` names is absent from the archive.**
3. **No token in `.client-tokens` appears in any exported file**, matched at
   letter boundaries rather than with `\\b`, because `_` is a word character and
   the fixtures this was written against were named `<client>_energy_home_*`.
4. **The export can be COLLECTED**, unless `--no-collect` is passed. This is
   the check the other three cannot stand in for: a module-level read of an
   excluded path aborts the collection of the *entire* suite rather than
   failing one file, which `tests/private_register.py` records against
   `test_reconcile_findings.py`. A tree that passes 1-3 and cannot collect is
   a tree where `pytest` prints an error and runs nothing.
5. **No token appears in the commit messages being published**, when
   `--with-messages` says messages are part of this publish. A message is not
   a file and never reaches the archive, so checks 2 and 3 cannot see it;
   measured on this repository, 12 of the 14 tokens appear in commit messages
   and all 14 appear somewhere in history. The flag exists because an export
   that writes only a tree publishes no message, and refusing it for content
   it does not carry would teach the operator to reach for a flag to get past
   a check. Declared scope, not an opt-out: when the scan does not run, it
   says so.

It does **not** re-derive whether git excludes those paths by `export-ignore`
or only by the list - `tests/test_no_client_data_ships.py` holds that, and
holds it better, with `git check-attr`. Here the archive is the ground truth:
if a path were not export-ignored it would be *in* the staging tree, and check
2 reads the tree rather than the rules. One caveat worth stating, since the
check is weaker than it looks: a path can also be absent because it is
gitignored and was never committed, which check 2 cannot tell apart from
"correctly excluded". That distinction is the pytest guard's job.

It also does not run the full suite. `--no-collect` exists for the same reason:
collection is seconds and the suite is half an hour, and a tool that always
took half an hour would be run round instead of run. The full bare run remains
a deliberate act before a publish, and `--print-suite-command` prints it.

## Why the token list is read from the repository and not from here

The tokens are client names. A file listing "never ship these clients"
discloses the client relationships it exists to protect, which is why
`.client-tokens` is itself excluded from the export. This script ships; the
names do not. When the list is absent - which is the case when this script is
run *from* an exported tree - the scan cannot run, and that is reported as a
refusal rather than a pass, because "no tokens to look for" and "no tokens
found" are the same output and opposite facts.
"""

from __future__ import annotations

import argparse
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MANIFEST_NAME = "PUBLIC_EXCLUDE.txt"
TOKENS_NAME = ".client-tokens"

#: The bare-tree suite, printed rather than run. Named here so the command in
#: the operator's hand and the command this script describes cannot drift.
#:
#: No `-q`, and the console script rather than `python -m pytest`. Both are
#: `pyproject.toml`'s doing and both are load-bearing:
#:
#:   - addopts already carries `-q`, so passing it again gives `-qq`, which
#:     removes the `N passed, M skipped` summary line - the one line a reader
#:     of a bare-tree run actually needs. `tests/test_the_proof_tool_does_not
#:     _repeat_a_configured_flag.py` is the guard, and it caught this here.
#:   - `python -m pytest` puts the working directory on `sys.path`; the
#:     console script does not. For a run whose whole purpose is to behave
#:     like a stranger's checkout, the interpreter silently adding the root to
#:     the path is the difference between a test and a rehearsal.
SUITE_COMMAND = "pytest -p no:cacheprovider --tb=no -rf"


def _git() -> str | None:
    """Git as a resolved path.

    Never a bare program name handed to `subprocess`: item 187's first leak
    guard did exactly that and passed on a machine where the lookup failed,
    reporting a clean scan it had not performed.
    """
    return shutil.which("git")


def entries(path: Path) -> dict[str, str]:
    """`token: reason` lines; comments and blanks dropped.

    The format `.client-tokens` uses. The reason is carried rather than
    discarded: it is printed when a check fires, so a reader of a refusal
    knows whether they are looking at a name to rename or captured data to
    regenerate.

    `PUBLIC_EXCLUDE.txt` is NOT this shape - it is one glob per line, with the
    reasons in comment blocks above each group, because those reasons run to
    paragraphs. `globs()` reads that one. Two parsers rather than one lenient
    parser, matching `tests/test_no_client_data_ships.py`, which reads the
    same two files the same two ways; a parser loose enough for both would
    read every manifest line as a path with no reason and could not tell that
    from a manifest whose reasons had been deleted.
    """
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, why = line.partition(":")
        out[key.strip()] = why.strip()
    return out


def globs(path: Path) -> list[str]:
    """One withheld glob per line; comments and blanks dropped.

    `dir/` means the directory and everything under it. The reasons live in
    the comment blocks above each group rather than on the lines, so a refusal
    here names the path and points at the manifest instead of quoting a
    one-line reason it does not have.
    """
    return [line.strip() for line in
            path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")]


def pattern(token: str) -> re.Pattern[str]:
    """A token matched at letter boundaries, case-insensitively.

    Not `\\b`: `_` is a word character, so a `\\b`-bounded name misses
    `<name>_energy_home_page.json`, which is the shape the harvested fixtures
    were named in. Not a bare substring either - one client's name was a
    substring of an ordinary English word, and a substring rule rewrote that
    word throughout axe-core's licence text and minified source, caught in a
    dry run. Letters only on each side, so digits still bound: a name with a
    `13` in front of it matches.

    (The examples that would make this concrete are client names, and this
    file ships. `tests/test_no_client_data_ships.py` records the same omission
    for the same reason. The fictional `opal` in this script's guard
    demonstrates all three cases.)
    """
    return re.compile(r"(?<![a-z])" + re.escape(token) + r"(?![a-z])", re.I)


def dirty(root: Path) -> list[str] | None:
    """Tracked files modified since HEAD. `None` if git could not be asked.

    Untracked files are not consulted: `data/`, `dashboard/dist/` and the
    virtualenv are untracked by design and are not in HEAD either, so they
    cannot reach an archive. A modified *tracked* file is the one that matters,
    because the export will carry the committed version of it and look right.
    """
    git = _git()
    if git is None:
        return None
    done = subprocess.run([git, "status", "--porcelain", "--untracked-files=no"],
                          cwd=root, capture_output=True, text=True)
    if done.returncode != 0:
        return None
    return [ln[3:] for ln in done.stdout.splitlines() if ln.strip()]


def archive(root: Path, into: Path) -> str:
    """Extract `git archive HEAD` into `into`. Returns the exported commit.

    Via a zip and `zipfile` rather than `git archive | tar -x`: tar is not
    reliably present on Windows, and a pipe hides the exit status of the half
    that matters.
    """
    git = _git()
    assert git, "git is not on PATH; nothing can be exported"
    sha = subprocess.run([git, "rev-parse", "HEAD"], cwd=root,
                         capture_output=True, text=True, check=True).stdout.strip()
    into.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / "export.zip"
        subprocess.run([git, "archive", "--format=zip", "-o", str(zip_path), "HEAD"],
                       cwd=root, capture_output=True, text=True, check=True)
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(into)
    return sha


def exported_files(root: Path) -> list[Path]:
    """Every file in the export, `.git` excluded.

    `.git` will not exist in a fresh archive, but this function is also used
    against a staging tree that a caller may already have initialised, and a
    scan that walks pack files reports hits inside compressed blobs it cannot
    locate for the reader.
    """
    return [p for p in sorted(root.rglob("*"))
            if p.is_file() and ".git" not in p.parts]


def present_excluded(root: Path, withheld: list[str]) -> list[str]:
    """Globs the manifest withholds that are in the tree anyway.

    `rstrip("/")` before the existence test: the manifest writes a directory
    with a trailing separator, and that separator has bitten path handling in
    this repository before.
    """
    return [g for g in withheld if (root / g.rstrip("/")).exists()]


def token_hits(root: Path, tokens: dict[str, str],
               files: list[Path] | None = None) -> list[tuple[str, str, str, str]]:
    """Every (file, token, reason, context) a scan of the export finds.

    Read as text with replacement rather than skipped when undecodable: a
    harvested fixture saved in another encoding is exactly the file worth
    reading, and a name in it survives replacement of the bytes around it.
    """
    pats = [(tok, why, pattern(tok)) for tok, why in tokens.items()]
    hits = []
    for path in (files if files is not None else exported_files(root)):
        try:
            text = path.read_bytes().decode("utf-8", errors="replace")
        except OSError:
            continue
        for tok, why, pat in pats:
            m = pat.search(text)
            if m:
                context = text[max(0, m.start() - 40):m.end() + 40]
                hits.append((path.relative_to(root).as_posix(), tok, why,
                             " ".join(context.split())))
    return hits


def commit_messages(root: Path, rev: str) -> list[tuple[str, str]] | None:
    """Every `(sha, message)` in `rev`. `None` if git could not be asked.

    `None` rather than an exception or an empty list, matching `dirty()`: an
    empty list is a legitimate answer for an empty range, and a caller that
    could not tell the two apart would read "git failed" as "nothing to
    check" - the vacuous pass this whole script is arranged against.

    Records are separated by `\x1e` and the sha from the body by `\x00`,
    because a commit message can contain any newline arrangement it likes and
    several in this repository run to forty lines with blank lines in them.
    Splitting on anything a message could itself contain would silently merge
    or truncate the text being scanned.
    """
    git = _git()
    if git is None:
        return None
    done = subprocess.run([git, "log", "--format=%H%x00%B%x1e", *shlex.split(rev)],
                          cwd=root, capture_output=True, text=True,
                          errors="replace")
    if done.returncode != 0:
        return None
    out: list[tuple[str, str]] = []
    for record in done.stdout.split("\x1e"):
        if not record.strip():
            continue
        sha, _, body = record.strip("\n").partition("\x00")
        out.append((sha.strip(), body))
    return out


def message_hits(msgs: list[tuple[str, str]], tokens: dict[str, str],
                 ) -> list[tuple[str, str, str, str, str]]:
    """Every `(sha, subject, token, reason, context)` a scan of the messages
    finds.

    The same `pattern()` as the file scan, deliberately: a name is a name
    wherever it is written, and two matching rules over one token list would
    drift in the direction where the looser one is the published surface.

    The subject is carried alongside the sha so a refusal reads as a commit a
    person recognises rather than as a hash they must go and look up.
    """
    pats = [(tok, why, pattern(tok)) for tok, why in tokens.items()]
    hits = []
    for sha, body in msgs:
        subject = next((ln for ln in body.splitlines() if ln.strip()), "")
        for tok, why, pat in pats:
            m = pat.search(body)
            if m:
                context = body[max(0, m.start() - 40):m.end() + 40]
                hits.append((sha, subject.strip(), tok, why,
                             " ".join(context.split())))
    return hits


def collects(root: Path) -> tuple[bool, str]:
    """Whether the export's suite can be collected.

    The console script, not `python -m pytest`: the module form puts the
    working directory on `sys.path` and the console script does not, and for a
    check whose subject is a stranger's checkout that difference is the whole
    point. `tests/test_the_proof_tool_runs_the_gates_entry_point.py` holds the
    same rule over the loop's tools.

    The claim is narrow and is the one the other checks cannot make: that no
    module reads an excluded path at import time. A single such read is not one
    red test, it is zero tests run - collection stops and `pytest` reports an
    error, which is how an export can pass every content check and still be
    unusable.
    """
    exe = shutil.which("pytest")
    if exe is None:
        return False, ("pytest is not on PATH, so the collection check could "
                       "not run. This is not a pass.")
    done = subprocess.run([exe, "--collect-only", "-p", "no:cacheprovider"],
                          cwd=root, capture_output=True, text=True)
    tail = "\n".join((done.stdout + done.stderr).strip().splitlines()[-12:])
    return done.returncode == 0, tail


def published_message(sha: str, msgs: list[tuple[str, str]] | None) -> str:
    """The message the published commit carries.

    `None` - no `--with-messages` - produces a generated line and says so.
    The saying-so is the point: a public repository whose commits are all
    "Export of abc1234" invites the reader to assume the messages were lost,
    when in fact they were withheld, and those are different facts about a
    project.
    """
    if not msgs:
        return (f"Export of {sha[:12]}\n\n"
                "Built and verified by scripts/export_public.py. No commit "
                "message from the source repository is published here.\n")
    if len(msgs) == 1:
        return msgs[0][1].rstrip() + "\n"
    newest, oldest = msgs[0][0][:12], msgs[-1][0][:12]
    body = "\n\n".join(m.rstrip() for _, m in reversed(msgs))
    return (f"Export of {len(msgs)} commits ({oldest}..{newest})\n\n"
            f"{body}\n")


def publish(tree: Path, url: str, branch: str, message: str,
            orphan: bool = False) -> tuple[bool, str]:
    """Put `tree` on `branch` of `url` as one commit. `(ok, report)`.

    Into a temporary clone, never through a remote configured in this
    repository - see this module's docstring for why that distinction is
    structural rather than procedural.

    An identical tree is reported and not committed. Git would make an empty
    commit only if asked, but the useful half is telling the operator that a
    publish they expected to change something did not, which is otherwise
    indistinguishable from success.
    """
    git = _git()
    if git is None:
        return False, "git is not on PATH, so nothing can be published."
    work = Path(tempfile.mkdtemp(prefix="export-publish-"))
    try:
        clone = work / "dest"
        done = subprocess.run([git, "clone", "--quiet", url, str(clone)],
                              capture_output=True, text=True, errors="replace")
        if done.returncode != 0:
            return False, (f"the destination could not be cloned: "
                           f"{done.stderr.strip() or done.stdout.strip()}")

        head = subprocess.run([git, "rev-parse", "--verify", "HEAD"], cwd=clone,
                              capture_output=True, text=True, errors="replace")
        has_history = head.returncode == 0
        if has_history and not orphan:
            current = subprocess.run([git, "rev-parse", "--abbrev-ref", "HEAD"],
                                     cwd=clone, capture_output=True, text=True,
                                     errors="replace").stdout.strip()
            branch = current or branch
        if orphan and has_history:
            # Not `--orphan <branch>`: that branch is the one just cloned, so
            # git refuses and - if the return code is not read, which is how
            # this shipped once - the commit quietly lands on the history it
            # was meant to replace. A name the clone cannot hold, pushed to
            # the target ref below.
            done = subprocess.run(
                [git, "checkout", "--quiet", "--orphan", "publish-root"],
                cwd=clone, capture_output=True, text=True, errors="replace")
            if done.returncode != 0:
                return False, (f"--orphan could not start a new root: "
                               f"{done.stderr.strip() or done.stdout.strip()}")
        elif not has_history:
            done = subprocess.run([git, "checkout", "--quiet", "-b", branch],
                                  cwd=clone, capture_output=True, text=True,
                                  errors="replace")
            if done.returncode != 0:
                return False, (f"the destination is empty and branch "
                               f"{branch!r} could not be started: "
                               f"{done.stderr.strip() or done.stdout.strip()}")

        for entry in clone.iterdir():
            if entry.name == ".git":
                continue
            shutil.rmtree(entry) if entry.is_dir() else entry.unlink()
        shutil.copytree(tree, clone, dirs_exist_ok=True)

        subprocess.run([git, "add", "-A"], cwd=clone, check=True,
                       capture_output=True)
        staged = subprocess.run([git, "diff", "--cached", "--quiet"], cwd=clone,
                                capture_output=True, text=True)
        if staged.returncode == 0 and has_history and not orphan:
            return True, ("the published tree is identical to what is there "
                          "already; nothing was committed or pushed.")

        msg_file = work / "message.txt"
        msg_file.write_text(message, encoding="utf-8")
        done = subprocess.run([git, "commit", "--quiet", "-F", str(msg_file)],
                              cwd=clone, capture_output=True, text=True,
                              errors="replace")
        if done.returncode != 0:
            return False, (f"the publish commit failed: "
                           f"{done.stderr.strip() or done.stdout.strip()}")

        push = [git, "push", "--quiet", "origin", f"HEAD:refs/heads/{branch}"]
        if orphan:
            push.insert(3, "--force")
        done = subprocess.run(push, cwd=clone, capture_output=True, text=True,
                              errors="replace")
        if done.returncode != 0:
            return False, (f"the push failed: "
                           f"{done.stderr.strip() or done.stdout.strip()}")
        sha = subprocess.run([git, "rev-parse", "HEAD"], cwd=clone,
                             capture_output=True, text=True,
                             errors="replace").stdout.strip()
        how = "replacing the root" if orphan else "on top of what was there"
        return True, f"published {sha[:12]} to {branch} ({how})"
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description="Export the public tree, or refuse to.",
        epilog="Produces nothing at all unless every check passes.")
    ap.add_argument("destination", nargs="?", type=Path,
                    help="where to write the export; must not already exist "
                         "unless --force")
    ap.add_argument("--force", action="store_true",
                    help="replace DESTINATION if it exists")
    ap.add_argument("--no-collect", action="store_true",
                    help="skip the collection check (checks 1-3 only)")
    ap.add_argument("--with-messages", nargs="?", const="-1 HEAD",
                    metavar="RANGE",
                    help="the commit messages in RANGE (default: HEAD alone) "
                         "are part of what is being published, so scan them "
                         "for client tokens too and refuse on a hit. Without "
                         "this the export writes a tree and publishes no "
                         "message, and the scan is reported as not run.")
    ap.add_argument("--publish", metavar="URL",
                    help="after every check passes, put the verified tree on "
                         "URL as one commit, from a temporary clone. No "
                         "remote is added to this repository, deliberately.")
    ap.add_argument("--publish-branch", default="main", metavar="NAME",
                    help="branch to publish to when the destination has no "
                         "history yet, or with --orphan (default: main)")
    ap.add_argument("--orphan", action="store_true",
                    help="replace the destination's history with a single "
                         "root commit instead of appending to it")
    ap.add_argument("--print-suite-command", action="store_true",
                    help="print the bare-tree suite command and exit")
    args = ap.parse_args(argv)

    if args.print_suite_command:
        print(SUITE_COMMAND)
        return 0
    if args.destination is None and not args.publish:
        ap.error("a destination is required, or --publish")
    if args.orphan and not args.publish:
        ap.error("--orphan only means anything with --publish")

    dest: Path | None = args.destination.resolve() if args.destination else None
    if dest is not None and dest.exists() and not args.force:
        print(f"refused: {dest} already exists. Pass --force to replace it.")
        return 2
    if _git() is None:
        print("refused: git is not on PATH, so nothing can be exported or "
              "checked. This is not a clean run.")
        return 2

    changed = dirty(ROOT)
    if changed is None:
        print("refused: the working tree's state could not be read, so it is "
              "not known whether HEAD is what you meant to export.")
        return 2
    if changed:
        print("refused: these tracked files are modified, and `git archive` "
              "exports HEAD, so the export would silently be of the previous "
              "commit:")
        for name in changed[:20]:
            print(f"  {name}")
        print("Commit them, or `git stash`, then run this again.")
        return 2

    manifest_path, tokens_path = ROOT / MANIFEST_NAME, ROOT / TOKENS_NAME
    for path in (manifest_path, tokens_path):
        if not path.is_file():
            print(f"refused: {path.name} is missing, so the checks it feeds "
                  "cannot run. An unfound token and an absent token list "
                  "produce the same output and mean opposite things.")
            return 2
    withheld, tokens = globs(manifest_path), entries(tokens_path)
    if not withheld or not tokens:
        print(f"refused: {MANIFEST_NAME} has {len(withheld)} entries and "
              f"{TOKENS_NAME} has {len(tokens)}. An empty list checks nothing "
              "while looking identical to a clean run.")
        return 2

    staging = Path(tempfile.mkdtemp(prefix="export-public-"))
    try:
        sha = archive(ROOT, staging)
        files = exported_files(staging)
        print(f"exported {sha[:7]}: {len(files)} files, staged for checking")

        failures: list[str] = []
        #: The messages that passed the scan, and so the only ones a publish
        #: may carry. Left `None` when the scan did not run, which is what
        #: `published_message` reads to say that none is published - the
        #: payload cannot be prose that was never checked.
        scanned: list[tuple[str, str]] | None = None

        leaked = present_excluded(staging, withheld)
        if leaked:
            failures.append(f"{len(leaked)} withheld path(s) are in the export")
            for path in leaked:
                print(f"  LEAK  {path} - {MANIFEST_NAME} withholds this, and "
                      "says there why")
        else:
            print(f"  ok    all {len(withheld)} withheld paths are absent")

        hits = token_hits(staging, tokens, files)
        if hits:
            failures.append(f"{len(hits)} client token hit(s)")
            for path, tok, why, context in hits[:40]:
                print(f"  LEAK  {path}: {tok} - {why}\n          ...{context}...")
            if len(hits) > 40:
                print(f"  ... and {len(hits) - 40} more")
        else:
            print(f"  ok    none of the {len(tokens)} tokens appear in "
                  f"{len(files)} files")

        if args.with_messages is None:
            print("  --    no commit message is being published, so the "
                  "message scan did not run (--with-messages)")
        else:
            msgs = commit_messages(ROOT, args.with_messages)
            if msgs is None:
                failures.append("the commit messages could not be read")
                print("  FAIL  the commit messages in "
                      f"{args.with_messages!r} could not be read, so it is "
                      "not known what a publish would carry. This is not a "
                      "pass.")
            elif not msgs:
                failures.append("the named range holds no commit")
                print(f"  FAIL  {args.with_messages!r} names no commit, so "
                      "the scan had nothing to read - which prints the same "
                      "as a clean scan and means the opposite.")
            else:
                scanned = msgs
                mhits = message_hits(msgs, tokens)
                if mhits:
                    failures.append(
                        f"{len(mhits)} client token hit(s) in commit messages")
                    for sha, subject, tok, why, context in mhits[:40]:
                        print(f"  LEAK  {sha[:7]} {subject}: {tok} - {why}\n"
                              f"          ...{context}...")
                    if len(mhits) > 40:
                        print(f"  ... and {len(mhits) - 40} more")
                else:
                    print(f"  ok    none of the {len(tokens)} tokens appear "
                          f"in {len(msgs)} commit message(s)")

        if args.no_collect:
            print("  --    collection check skipped (--no-collect)")
        else:
            ok, tail = collects(staging)
            if ok:
                print("  ok    the export collects")
            else:
                failures.append("the export cannot be collected")
                print("  FAIL  the export could not be collected, so pytest "
                      "would run NOTHING there:")
                for line in tail.splitlines():
                    print(f"          {line}")

        if failures:
            print(f"\nrefused: {'; '.join(failures)}. Nothing was written.")
            return 1

        tree = staging
        if dest is not None:
            if dest.exists():
                shutil.rmtree(dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(staging), str(dest))
            staging = dest  # moved; the cleanup below must not delete it
            tree = dest
            print(f"\nexport verified and written to {dest}")
            print(f"Before publishing, run the suite there with no build "
                  f"present:\n  cd {dest} && {SUITE_COMMAND}")

        if args.publish:
            ok, report = publish(tree, args.publish, args.publish_branch,
                                 published_message(sha, scanned),
                                 orphan=args.orphan)
            print(f"\n{'publish: ' if ok else 'PUBLISH FAILED: '}{report}")
            if not ok:
                # 3, not 1: every check passed and the tree is sound. A
                # refusal and an unreachable remote are different facts, and
                # a caller that cannot tell them apart will retry the wrong
                # one.
                return 3
        elif dest is None:
            print("\nnothing to do: no destination and no --publish")
            return 2
        return 0
    finally:
        if staging.exists() and staging != dest:
            shutil.rmtree(staging, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
