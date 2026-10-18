"""The loop kit's own files are graded, the round a repair lands.

`QUESTIONS.md` Q-27 asked whether `.claude/loop/KIT_MANIFEST.json` is meant to
be enforced in this repository or only in the upstream kit. The operator
answered **enforce it here**, 2026-08-31. This is that enforcement.

What the manifest actually is, read from the installer rather than assumed:
`CodeDash/loop-kit/install-kit.ps1:69-70` writes it as *the hashes recorded at
the last install*, and uses it for a three-way merge on the next one - a file
that hashes to the kit's copy is `unchanged`, one that hashes to its
last-install record is a safe `UPDATE`, and one that matches neither is a
`CONFLICT` the installer refuses to overwrite without `-Force`.

So a file whose hash has left its manifest entry is not a bookkeeping slip. It
is a kit-owned file this repository has repaired locally, which means the next
kit install stops on it and the repair has no route upstream. That is CQ-174,
first raised at report 083 and carried by every report since; measured when
this file landed, **seven of the fifteen entries had left their hash** and the
manifest recorded it nowhere, because nothing read the manifest.

The rule this file enforces is therefore not "never diverge" - this loop
repairs its own instruments, and forbidding that would forbid the work. It is
**never diverge silently**: a deliberate repair is written into
`KIT_LOCAL.json` with the commits that made it and why, in the commit that
makes it, and anything else is drift and goes red.

`KIT_MANIFEST.json` is not touched by any of this. It belongs to the
installer, which rewrites it on every run, and re-baselining it to the working
tree is a specific known mistake: the installer's own comment at
`install-kit.ps1:85-92` records the three loop repairs to
`scripts/prove_fail.py` clobbered on 2026-08-23 04:35 by exactly that. The
local record is a second file for that reason.

Not a style checker, in the sense `test_loop_instructions.py`'s docstring
means: every assertion here is a property CQ-174 was raised about.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

#: Written by `install-kit.ps1` at the last install: target path -> the sha256
#: it had when the kit put it there. Installer-owned; nothing here writes it.
MANIFEST_PATH = ROOT / ".claude" / "loop" / "KIT_MANIFEST.json"

#: This repository's record of the kit-owned files it has deliberately
#: repaired. Loop-owned, and the only one of the three a round may write.
LOCAL_PATH = ROOT / ".claude" / "loop" / "KIT_LOCAL.json"

#: Stamped by `install-kit.ps1` with the kit version it installed.
VERSION_PATH = ROOT / ".claude" / "loop" / "KIT_VERSION"


def kit_sha256(data: bytes) -> str:
    """The digest the manifest speaks in.

    Raw bytes, because that is what `install-kit.ps1`'s `Sha256` takes and the
    manifest is its output. The kit's *own* `manifest.json` is hashed over
    canonical LF bytes instead (`loop-kit/lf-bytes.ps1`), and the two
    conventions belong to different files with different readers - hashing
    this one the other way makes every CRLF file here read as diverged.
    """
    return hashlib.sha256(data).hexdigest()


def kit_digests(data: bytes) -> tuple[str, ...]:
    """Every digest this content has, depending on how the checkout wrote it.

    **The manifest records a hash of bytes that only one platform produces,
    and this is what makes the comparison portable without rewriting it.**

    `install-kit.ps1` hashes the file on disk, and the install that wrote
    `KIT_MANIFEST.json` ran on Windows, where `core.autocrlf` gives a CRLF
    working tree. This repository has no `* text=auto eol=lf` in
    `.gitattributes` - only two `-text` exemptions for vendored files - so the
    blob is LF and CI checks out LF. The same unmodified file therefore hashes
    one way here and another way on `ubuntu-latest`, and the manifest can only
    ever match one of them.

    Measured on `.claude/DISCIPLINE.md`: `f93e1b02...` from the CRLF bytes on
    this disk, which is exactly what the manifest records, and `26e82b01...`
    from the same content as LF. The manifest held fifteen entries when the
    guard shipped.

    **CQ-238, at round 121: the LF digest above read `2e020e62...` and no run
    of this function has ever produced that.** `kit_digests` on the current
    bytes returns the pair quoted, and the CI job that caught the defect
    printed the same one - run `33362654757` names
    `'.claude/DISCIPLINE.md': ('f93e1b02...', None, '26e82b01...')` in its
    assertion. A reader reproducing the worked example by hand got a different
    number from the one written down, with nothing in the docstring to say
    whether that meant a regression or a bad example.

    **The timing in that paragraph was wrong as well, and it is corrected from
    the same record rather than softened.** It said "red on CI within the
    hour". The guard shipped at `4755bbf`, 2026-08-31 01:51:52Z, and GitHub
    ran no workflow for that commit at all; the red is run `33362654757` at
    06:02:59Z against `000593c5`, the *next* push - four hours and eleven
    minutes later, and on a commit that changed only `NEXT_UP.md`. It failed
    on `ubuntu-latest` and on `windows-latest` alike, which is the paragraph
    above holding: an Actions checkout is LF on both. The fifteen-entry count
    is the one part that survives checking - `git show 4755bbf` on the
    manifest returns exactly fifteen.

    Normalising to LF instead is the other obvious move and it is wrong for
    the same reason in the other direction: the recorded digests are of CRLF
    bytes, so every entry would then mismatch on *both* platforms.
    `kit_sha256`'s docstring already says as much.

    So compare against the set. A file is at its recorded hash if any of its
    line-ending forms hashes to it, and content changes still move all three.
    What this deliberately stops detecting is a file whose *only* difference is
    its line endings - which on this repo is a property of the checkout, not a
    repair, and is not what CQ-174 is about.

    The reconstruction assumes no lone CR, which `test_loop_instructions.py`'s
    bare-carriage-return scan already enforces over every tracked file.
    """
    lf = data.replace(b"\r\n", b"\n")
    forms, seen = [], set()
    for form in (data, lf, lf.replace(b"\n", b"\r\n")):
        digest = kit_sha256(form)
        if digest not in seen:
            seen.add(digest)
            forms.append(digest)
    return tuple(forms)


def divergences(manifest, local, read):
    """Kit-owned paths whose content matches neither the kit nor the record.

    Split out from the test that calls it so the detection can be run against
    a tree it does not have to break to demonstrate - DISCIPLINE rule 5, a
    check's evidence must be able to disagree with it.

    `read` takes a repo-relative path and returns its bytes. Returns
    ``{path: (installed, recorded, actual)}``, empty when the tree is clean.
    Matching is over `kit_digests`, so a checkout's line endings do not read
    as a repair; `actual` is reported as the digest of the bytes as they are
    on this machine, which is the one a reader here can reproduce.
    """
    out = {}
    for path, installed in sorted(manifest.items()):
        digests = kit_digests(read(path))
        if installed in digests:
            continue
        recorded = local.get("repairs", {}).get(path, {}).get("sha256")
        if recorded in digests:
            continue
        out[path] = (installed, recorded, digests[0])
    return out


def _read(path):
    return (ROOT / path).read_bytes()


@pytest.fixture(scope="module")
def manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def local():
    return json.loads(LOCAL_PATH.read_text(encoding="utf-8"))


def test_every_kit_owned_file_is_at_its_installed_hash_or_a_recorded_repair(
        manifest, local):
    """The finding itself: no kit-owned file has moved without saying so."""
    drifted = divergences(manifest, local, _read)
    assert not drifted, (
        "kit-owned files differ from both the last install and "
        "`.claude/loop/KIT_LOCAL.json`:\n"
        + "\n".join(
            f"  {path}\n"
            f"    installed {installed[:16]}\n"
            f"    recorded  {(recorded or '(no entry)')[:16]}\n"
            f"    on disk   {actual[:16]}"
            for path, (installed, recorded, actual) in drifted.items())
        + "\n\nEither revert the file, or record the repair in KIT_LOCAL.json "
          "with the commits that made it and why.")


def test_the_detection_reddens_when_a_kit_owned_file_moves_unrecorded(
        manifest, local):
    """Rule 5: the check above can fail, shown without breaking the tree."""
    victim = sorted(manifest)[0]

    def tampered(path):
        return _read(path) + b"\n" if path == victim else _read(path)

    drifted = divergences(manifest, local, tampered)
    assert victim in drifted, (
        f"{victim} was edited and the check stayed green - it is not a guard")
    assert not divergences(manifest, local, _read), (
        "the untampered tree must be clean for this to have shown anything")


def test_the_local_record_names_only_files_the_kit_owns(manifest, local):
    """A repair recorded against a path the kit does not own reads as cover."""
    strangers = sorted(set(local.get("repairs", {})) - set(manifest))
    assert not strangers, (
        "KIT_LOCAL.json records repairs to files absent from "
        f"KIT_MANIFEST.json: {strangers}")


def test_the_local_record_holds_no_entry_that_is_no_longer_a_repair(
        manifest, local):
    """A record kept past its file returning to the kit's copy is a lie.

    Not pedantry: a stale entry means the next reader cannot tell which of the
    listed files are actually diverged, which is the question the file exists
    to answer.
    """
    settled = sorted(
        path for path in local.get("repairs", {})
        if path in manifest and kit_sha256(_read(path)) == manifest[path])
    assert not settled, (
        "KIT_LOCAL.json still records these as repairs, but they now hash to "
        f"the installed kit copy - drop the entries: {settled}")


def test_the_local_record_is_written_against_the_installed_kit_version(local):
    """The version discipline the answer asked for, made mechanical.

    Q-27's chosen option is "a test that fails when a kit-owned file's hash
    does not match the manifest, **and a rule that a kit repair bumps the kit
    version**". A rule stated in prose is what the manifest already was. This
    is the same rule with a reader: the record names the kit it was
    dispositioned against, so an install that moves `KIT_VERSION` goes red
    until every repair has been re-checked against the kit that replaced it.

    That is the reconciliation CQ-174 has been asking for since report 083,
    and it is the moment a repair can actually be lifted upstream - pulling a
    newer kit is when the conflict is in front of someone.
    """
    installed = VERSION_PATH.read_text(encoding="utf-8").strip()
    assert local.get("kit_version") == installed, (
        f"KIT_LOCAL.json is dispositioned against kit "
        f"{local.get('kit_version')!r} but KIT_VERSION says {installed!r}. "
        "Re-check each repair against the newly installed kit: a file the kit "
        "has since absorbed loses its entry, one it has not keeps it with a "
        "fresh hash.")


def test_every_recorded_repair_says_what_made_it_and_why(local):
    """A hash alone records that something moved, not that it was meant to."""
    thin = sorted(
        path for path, entry in local.get("repairs", {}).items()
        if not entry.get("commits") or not (entry.get("why") or "").strip())
    assert not thin, (
        "these KIT_LOCAL.json entries carry a hash but no commits or no "
        f"reason, so they cannot be told from drift: {thin}")
