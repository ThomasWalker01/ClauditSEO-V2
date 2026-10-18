"""The build artefact is named one thing and guarded under another.

`.gitignore` and all three packaging leak guards were written against
`auditdeck-*.zip` and never repointed at the rename. The archive both
packaging scripts actually produce is `clauditseo-<version>.zip`, so
`git add -A` commits a multi-megabyte artefact and every guard stays quiet —
carried open from round 001 to round 015.

The leak lists are checked as one rule rather than one file: three copies of
the same grep exist (CI, bash, PowerShell) and a fix applied to one of them is
the partial-fix shape this repository has paid for repeatedly.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess

import clauditseo
from tests.needs_repo import needs_repo

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Resolved once, so nothing here hands a bare program name to subprocess.
#: On Windows a bare name is looked up by CreateProcess, which searches
#: System32 before PATH — the divergence that made the probe validate one
#: executable while the test ran another. `git` has no System32 impostor
#: today; resolving it anyway is cheaper than re-deciding per name.
#:
#: `None` when git is not on PATH, and deliberately not `or "git"`. That
#: fallback made the comment above false in the one case it was written for:
#: it produced a bare name at exactly the moment resolution failed, and the
#: run continued with whatever CreateProcess found. Callers go through
#: `_git()`, which fails the test that needs it with a reason rather than
#: erroring at collection — an unimportable module is the no-result state,
#: which says nothing about the code at all.
GIT = shutil.which("git")


def _git() -> str:
    assert GIT, ("git is not resolvable on PATH, and these tests shell out to "
                 "it — the archive they inspect is produced by `git archive`")
    return GIT

# The three independent copies of the "no build artefact in the archive" rule.
LEAK_GUARDS = (
    ROOT / ".github" / "workflows" / "ci.yml",
    ROOT / "scripts" / "package.sh",
    ROOT / "scripts" / "package.ps1",
)


def _resolve_runnable(program: str, probe_args: list[str]) -> str | None:
    """The path to a program that actually runs here, or None.

    Two defects deep, and each one is the previous one's evidence not
    applying to the thing it was used to decide.

    First: `shutil.which` answers "is there a file with this name on PATH",
    which is a different question from "does it run". On `windows-latest`,
    `C:\\Windows\\System32\\bash.exe` is the WSL launcher — present,
    resolvable, and with no distribution installed it exits 1 with a UTF-16
    message. So the probe was added.

    Second: the probe returned a *bool*, and the caller then invoked the bare
    name. `which` searches PATH and found Git Bash; passing `"bash"` to
    `subprocess.run` on Windows hands a bare name to CreateProcess, which
    searches the application directory, the current directory and System32
    **before** PATH — and System32 is where the WSL launcher lives. The probe
    validated one executable and the test ran another.

    Hence a path rather than a bool. The caller invokes exactly what was
    proven, so the two cannot diverge — which removes the divergence instead
    of reasoning about which names have impostors on which platform.
    """
    import shutil
    import subprocess

    resolved = shutil.which(program)
    if not resolved:
        return None
    try:
        done = subprocess.run([resolved, *probe_args],
                              capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return resolved if done.returncode == 0 else None


def _produced_archive_name() -> str:
    """Exactly what the packaging scripts write, derived rather than guessed."""
    return f"clauditseo-{clauditseo.__version__}.zip"


@needs_repo
def test_the_archive_the_scripts_produce_is_ignored():
    """Ask git, not `.gitignore`'s text — the defect was a rule that read
    perfectly and matched nothing, so reading it again would reproduce it."""
    name = _produced_archive_name()
    done = subprocess.run([_git(), "check-ignore", "-v", name],
                          cwd=ROOT, capture_output=True, text=True)
    assert done.returncode == 0, (
        f"{name} is not ignored by any rule; `git add -A` would commit it. "
        f"git check-ignore said: {done.stdout or done.stderr!r}"
    )


def test_both_packaging_scripts_still_name_that_archive():
    """If a script stops producing that name, the test above is guarding a
    file nobody writes. This is the half that keeps the derivation honest."""
    for script in (ROOT / "scripts" / "package.sh", ROOT / "scripts" / "package.ps1"):
        text = script.read_text(encoding="utf-8")
        assert "clauditseo-" in text and ".zip" in text, script


def test_every_leak_guard_catches_a_stray_root_zip():
    """All three copies, enumerated from a file list rather than named inline."""
    missing = []
    for guard in LEAK_GUARDS:
        text = guard.read_text(encoding="utf-8")
        # The rule is satisfied by any pattern that would match the produced
        # archive appearing inside the packaged tree.
        if not re.search(r"clauditseo-.{0,6}\\?\.zip|clauditseo-\*\\?\.zip", text):
            missing.append(guard.relative_to(ROOT).as_posix())
    assert not missing, (
        "these leak guards cannot see the archive the scripts produce: "
        + ", ".join(missing)
    )


def _leak_pattern(script: pathlib.Path) -> str:
    """The pattern the script actually uses, read from the script."""
    m = re.search(r'grep -E "([^"]+)"', script.read_text(encoding="utf-8"))
    assert m, f"no leak grep found in {script}"
    return m.group(1)


#: What `unzip -l` really prints. The first line names the archive itself,
#: which is not an entry — the distinction the guard below exists to hold.
def _listing(archive: str, entries: list[str]) -> str:
    rows = "\n".join(f"     100  2026-08-16 10:00   {e}" for e in entries)
    return (f"Archive:  {archive}\n"
            "  Length      Date    Time    Name\n"
            "---------  ---------- -----   ----\n"
            f"{rows}\n")


@needs_repo
def test_the_packaging_script_succeeds_on_a_clean_tree():
    """Run the script, do not read it.

    The first version of this guard extracted the leak pattern and applied it
    to a listing built here — and could not see the fix, because the defect
    was in the *pipeline*, not the pattern: `unzip -l` prints
    `Archive:  <name>` as its first line, the widened pattern matched that
    header, and the script exited 1 on every clean build. A guard that models
    the pipeline cannot fail on a pipeline bug. Measured both ways before
    this was written: exit 1 without the header strip, exit 0 with it.

    Whichever script the platform can run is run; only the bash path
    exercises the header defect, since `package.ps1` matches entry names and
    was never vulnerable. Deliberately not skipped — a skip here would mean
    the one supported build path went unexercised on that platform.

    The one skip is outside a repository: both scripts are `git archive`, so
    an exported tree has nothing for them to build from (`tests/needs_repo.py`).
    """
    import subprocess

    # Every element is a resolved path. Nothing here is a bare program name.
    bash = _resolve_runnable("bash", ["-c", "exit 0"])
    unzip = _resolve_runnable("unzip", ["-v"])
    if bash and unzip:
        cmd, label = [bash, "scripts/package.sh"], "package.sh"
    else:
        shell = (_resolve_runnable("powershell", ["-NoProfile", "-Command", "exit 0"])
                 or _resolve_runnable("pwsh", ["-NoProfile", "-Command", "exit 0"]))
        assert shell, (
            "no runnable build path on this machine: bash+unzip did not both "
            "run, and neither did powershell or pwsh. One of the two packaging "
            "scripts has to be exercisable — a skip here would leave the only "
            "supported build path untested on this platform.")
        cmd, label = [shell, "-NoProfile", "-File",
                      "scripts/package.ps1"], "package.ps1"

    produced = ROOT / _produced_archive_name()
    try:
        done = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        assert done.returncode == 0, (
            f"{label} failed on a clean tree. "
            f"stdout: {done.stdout!r} stderr: {done.stderr!r}")
        assert "clean" in (done.stdout + done.stderr), (
            f"{label} did not report the archive clean: {done.stdout!r}")
    finally:
        produced.unlink(missing_ok=True)


def test_the_leak_guard_still_catches_a_real_leak():
    """The other direction, so the fix cannot be "match nothing"."""
    dirty = _listing("clauditseo-0.14.0.zip",
                     ["clauditseo/README.md",
                      "clauditseo/clauditseo-0.14.0.zip",
                      "clauditseo/.venv/pyvenv.cfg"])
    for script in (ROOT / "scripts" / "package.sh",
                   ROOT / ".github" / "workflows" / "ci.yml"):
        pattern = _leak_pattern(script)
        hits = [ln for ln in dirty.splitlines() if re.search(pattern, ln)]
        assert any("clauditseo-0.14.0.zip" in h for h in hits), (
            f"{script.name} no longer catches a nested archive")
        assert any(".venv" in h for h in hits), (
            f"{script.name} no longer catches a .venv leak")
