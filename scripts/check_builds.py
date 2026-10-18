"""Compare the bundle on disk against the register the loop reads.

WF-90, first raised at report 074 and carried unchanged to report 132.

**The defect in one sentence.** `npm run build` replaces what the operator's
browser is served; `OPERATOR_ACTIONS.md` — the file `.claude/agents/auditor.md`
instructs the auditor to read before concluding a fix landed — records most
builds but not all; and *nothing compares the two*.

That is not hypothetical and it is not history. At `712743b` the register's
newest bundle is `BsBHgXUu`, `dashboard/dist/assets/index-BsXucSZn.js` was on
disk dated 23:32, and the string `BsXucSZn` does not appear in the register at
all — a bundle later than the last recorded action, served by a process started
before it. The commit body of `712743b` mentions the build in prose; the
register does not, and the register is what the loop reads. Measured again on
2026-09-01: `grep -rn` over every `.py` under `scripts/`, `tests/` and
`clauditseo/` found nothing comparing a built asset name to the register, for
the fifty-nine reports between 074 and 132. This script is the comparison.

## Why a script and not a pytest

The same reason `check_restarts.py` is a script: the subject is not committed.
`.gitignore:7` covers `dashboard/dist/`, so the assets do not exist on the CI
gate, and a pytest over them could only be green by reading nothing — the
check-that-cannot-fail shape this repository has paid for repeatedly. The
correctness of the comparison itself *is* a pytest, and lives in
`tests/test_a_build_the_register_does_not_carry_is_reported.py`, which replays
the `712743b` case out of git.

## The matcher, and why it is exact rather than clever

Both ends are machine-written. Vite puts an eight-character content hash in the
asset filename and cleans the directory on every build, so the tree carries the
name of exactly one build and carries it exactly. The register quotes that hash
in one of two forms, both enumerated from the file rather than assumed —
`index-<hash>.js` as the loop's own rows write it, and a bare `<hash>` as
`/api/health` prints it and pasted health output carries it. Searching for the
hash alone matches both.

The boundary excludes `[A-Za-z0-9_]` and deliberately *allows* `-`, because the
filename form puts a `-` immediately before the hash. That cannot widen the
match: Vite hashes are a fixed eight characters, so one hash can only be a
substring of another if the two are equal. A nine-character lookalike does not
account for an asset, and
`test_a_hash_is_matched_whole_and_not_as_a_substring` holds it to that.

## What it does not claim

**A build with no row is a question, not a verdict.** An operator can describe
a build in words, and a row can name the bundle it replaced rather than the one
it wrote. So the output is phrased as *unaccounted* and the exit code says only
whether there are any, the same shape `check_restarts.py` and
`check_carveout.py` already use.

**It answers for the tree, not for the running process.** Whether the process
serving the browser holds this bundle is a different question, and the running
product answers it directly at `/api/health`. Deliberately not folded in here:
`data/server-starts.jsonl` does not record a bundle, so the served half cannot
be had offline, and a checker that needed a live service could not be run at
the point in a round where this question is asked.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Where the build lands, per `.claude/loop/PROFILE.md`'s `build_dir`.
ASSETS = ROOT / "dashboard" / "dist" / "assets"

#: The register DISCIPLINE rule 13 names.
REGISTER = ROOT / "OPERATOR_ACTIONS.md"

#: `<stem>-<hash><ext>`, with the hash Vite's fixed eight characters and the
#: extension carrying no further dot, so the split is unambiguous.
HASHED = re.compile(r"^.+-([A-Za-z0-9_-]{8})(\.[A-Za-z0-9]+)$")


def asset_hash(name: str) -> str | None:
    """The content hash in an asset filename, or None if it carries none."""
    match = HASHED.match(name)
    return match.group(1) if match else None


def names(text: str, digest: str) -> bool:
    """Whether `text` names this hash as a whole token.

    See the matcher note in the module docstring for why `-` is outside the
    boundary class and why that cannot widen the match.
    """
    pattern = r"(?<![A-Za-z0-9_])" + re.escape(digest) + r"(?![A-Za-z0-9_])"
    return re.search(pattern, text) is not None


def unaccounted(assets: Path, register: str) -> list[Path]:
    """Every hashed asset in `assets` that `register` does not name.

    Derived from the directory rather than from a list of extensions, per
    DISCIPLINE rule 3 — the stylesheet is served too, and a hard-coded `.js`
    is how that half would pass unchecked.
    """
    out = []
    for path in sorted(assets.iterdir()):
        if not path.is_file():
            continue
        digest = asset_hash(path.name)
        if digest is None:
            continue
        if not names(register, digest):
            out.append(path)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report a built asset the operator register does not name.")
    parser.add_argument(
        "--assets", default=str(ASSETS),
        help="the built asset directory (default: dashboard/dist/assets)")
    parser.add_argument(
        "--register", default=str(REGISTER),
        help="the operator register (default: OPERATOR_ACTIONS.md)")
    args = parser.parse_args(argv)

    assets = Path(args.assets)
    register = Path(args.register)

    if not assets.is_dir():
        print(f"cannot answer: {assets} does not exist, so no build has left "
              "an asset here to ask about. This is the CI gate's state - "
              "dashboard/dist/ is gitignored - and it is not a clean bill.")
        return 2
    if not register.is_file():
        print(f"cannot answer: {register} does not exist.")
        return 2

    text = register.read_text(encoding="utf-8", errors="replace")
    hashed = [p for p in sorted(assets.iterdir())
              if p.is_file() and asset_hash(p.name)]
    missing = unaccounted(assets, text)

    print(f"{len(hashed)} hashed asset(s) in {assets}, "
          f"{len(missing)} named nowhere in {register.name}")
    if not missing:
        print("clean: every built asset on disk is named by a register row")
        return 0
    for path in missing:
        print(f"  unaccounted: {path.name} (hash {asset_hash(path.name)})")
    print("A build with no row is a question, not a verdict: the row may name "
          "the bundle it replaced. Read the rows around it before concluding "
          "a build went unrecorded.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
