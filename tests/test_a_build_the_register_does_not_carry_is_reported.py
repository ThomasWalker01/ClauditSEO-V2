"""WF-90's reader — `scripts/check_builds.py`, held to what it claims.

WF-90, first raised at report 074 and carried unchanged to report 132.

**The defect in one sentence.** `npm run build` replaces what the operator's
browser is served; `OPERATOR_ACTIONS.md` records most builds but not all; and
*nothing compares the two* — so a round reading the register to decide what is
served can be told a build changed the bundle when it changed nothing, and told
nothing at all about the build that did.

**It is measured, not asserted.** At `712743b` the register's newest bundle is
`BsBHgXUu` and the string `BsXucSZn` does not appear in the file at all, while
`dashboard/dist/assets/index-BsXucSZn.js` sat on disk dated 23:32, served by a
process started before it. That register is committed, so the case is replayed
here from git rather than staged synthetically —
`test_the_register_at_712743b_does_not_carry_the_bundle_wf90_measured`.

**And nothing read it for fifty-nine reports.** Grepping every `.py` under
`scripts/`, `tests/` and `clauditseo/` for a comparison of a built asset name
against `OPERATOR_ACTIONS.md` returned nothing on 2026-09-01: the hits naming
`dashboard/dist` are docstring prose, the two rendered-a11y modules that *load*
the bundle to drive a browser, and `prove_fail.py`, which detects those. None
compares a name to the register. That script is the comparison; this file is
the guard on the comparison.

## Why a script and not a pytest over the real tree

The same reason `check_restarts.py` is a script: the subject is not committed.
`.gitignore:7` covers `dashboard/dist/`, so the assets do not exist on the CI
gate, and a pytest reading them there could only be green by reading nothing —
the check-that-cannot-fail shape this repository has paid for repeatedly. So
the script answers `cannot answer` when the directory is absent, and this file
asserts that it does rather than reporting a clean bill.

Everything else here runs on synthetic registers, or on one read out of git.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_builds  # noqa: E402

HEADER = ("| when | who | action | what changed | evidence |\n"
          "| --- | --- | --- | --- | --- |\n")


def _register(*rows: str) -> str:
    return HEADER + "".join(row + "\n" for row in rows)


def _assets(tmp_path: Path, *names: str) -> Path:
    directory = tmp_path / "assets"
    directory.mkdir(parents=True)
    for name in names:
        (directory / name).write_text("x", encoding="utf-8")
    return directory


def _written(where: Path, text: str) -> Path:
    where.mkdir(parents=True, exist_ok=True)
    path = where / "OPERATOR_ACTIONS.md"
    path.write_text(text, encoding="utf-8")
    return path


# --- what the comparison must report ---------------------------------------

def test_a_bundle_no_row_names_is_reported(tmp_path):
    """The whole finding, in its smallest form."""
    assets = _assets(tmp_path, "index-AAAAAAAA.js")
    unaccounted = check_builds.unaccounted(assets, _register())
    assert [a.name for a in unaccounted] == ["index-AAAAAAAA.js"]


def test_a_bundle_a_row_names_in_full_is_accounted(tmp_path):
    """The form the loop's own rows use: the filename, verbatim."""
    assets = _assets(tmp_path, "index-AAAAAAAA.js")
    row = ("| 2026-09-01 08:12 | round 128 (audit-fix loop) | npm run build "
           "in dashboard | bundle `dist/assets/index-AAAAAAAA.js` | x |")
    assert check_builds.unaccounted(assets, _register(row)) == []


def test_a_bundle_a_row_names_bare_is_accounted(tmp_path):
    """The form `/api/health` prints, which rows quote verbatim.

    `clauditseo/api/app.py` reports the served bundle as a bare hash, and the
    register carries pasted health output in that form. A matcher that knew
    only the filename would report every one of those as unaccounted.
    """
    assets = _assets(tmp_path, "index-AAAAAAAA.js")
    row = '| 2026-08-21 22:56 | operator | restart | {"bundle":"AAAAAAAA"} | x |'
    assert check_builds.unaccounted(assets, _register(row)) == []


def test_every_hashed_asset_is_asked_about_not_only_the_script(tmp_path):
    """CSS is served too, and the register records it in the same rows.

    Derived from the directory, per DISCIPLINE rule 3 — a hard-coded `.js` is
    how the stylesheet half passes unchecked.
    """
    assets = _assets(tmp_path, "index-AAAAAAAA.js", "index-BBBBBBBB.css")
    row = "| w | who | build | bundle `index-AAAAAAAA.js` | x |"
    unaccounted = check_builds.unaccounted(assets, _register(row))
    assert [a.name for a in unaccounted] == ["index-BBBBBBBB.css"]


def test_an_unhashed_file_is_not_asked_about(tmp_path):
    """A name carrying no content hash cannot say which build wrote it."""
    assets = _assets(tmp_path, "favicon.ico", "index-AAAAAAAA.js")
    unaccounted = check_builds.unaccounted(assets, _register())
    assert [a.name for a in unaccounted] == ["index-AAAAAAAA.js"]


# --- the matcher must not be weaker than it looks ---------------------------

def test_a_hash_is_matched_whole_and_not_as_a_substring(tmp_path):
    """The weaker-matcher defect this repository has already paid for twice.

    A register naming a *different* nine-character token that happens to open
    with this asset's hash does not account for this asset.
    """
    assets = _assets(tmp_path, "index-AAAAAAAA.js")
    row = "| w | who | build | bundle `index-AAAAAAAAA.js` | x |"
    unaccounted = check_builds.unaccounted(assets, _register(row))
    assert [a.name for a in unaccounted] == ["index-AAAAAAAA.js"]


# --- the real case, replayed out of git ------------------------------------

def test_the_register_at_712743b_does_not_carry_the_bundle_wf90_measured(
        tmp_path):
    """WF-90's own measurement, against the committed register of that commit.

    Not synthetic: `git show 712743b:OPERATOR_ACTIONS.md` is the file the
    auditor read at report 074. `index-BsXucSZn.js` was on disk and is absent
    from it; `index-BsBHgXUu.js` is the newest one it does name. Both halves
    are asserted, so a checker that reported everything would fail here too.
    """
    git = shutil.which("git")
    if not git:
        pytest.skip("git not on PATH")
    proc = subprocess.run(
        [git, "show", "712743b:OPERATOR_ACTIONS.md"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        pytest.skip("712743b not present in this clone")
    register = proc.stdout

    missed = _assets(tmp_path / "a", "index-BsXucSZn.js")
    assert [a.name for a in check_builds.unaccounted(missed, register)] == [
        "index-BsXucSZn.js"]

    recorded = _assets(tmp_path / "b", "index-BsBHgXUu.js")
    assert check_builds.unaccounted(recorded, register) == []


# --- an absent directory is a no-result, never a clean bill -----------------

def test_a_missing_assets_directory_cannot_answer(tmp_path):
    """On the CI gate `dashboard/dist/` does not exist.

    DISCIPLINE rule 6's distinction, applied to this reader: telling nothing
    apart from finding nothing is the failure mode, so the exit code says
    cannot answer and never clean.
    """
    register = _written(tmp_path, _register())
    code = check_builds.main(
        ["--assets", str(tmp_path / "nope"), "--register", str(register)])
    assert code == 2


def test_a_clean_tree_exits_zero_and_an_unaccounted_one_exits_one(tmp_path):
    assets = _assets(tmp_path, "index-AAAAAAAA.js")
    row = "| w | who | build | bundle `index-AAAAAAAA.js` | x |"
    clean = _written(tmp_path / "c", _register(row))
    dirty = _written(tmp_path / "d", _register())
    assert check_builds.main(
        ["--assets", str(assets), "--register", str(clean)]) == 0
    assert check_builds.main(
        ["--assets", str(assets), "--register", str(dirty)]) == 1
