"""A phase update says where the work is, never what the work is.

`scripts/round-marker.ps1` is the only thing that says a round, a plan, a
relay item or a feature is underway. Four skills claim it and every one of
them then updates the phase with a bare `-Phase <name>` call, because that is
what their own instructions tell them to run.

The defect this file guards (CQ-64, carried from report 033): `$myKind` was
assigned from the `-Kind` parameter unconditionally, and `-Kind` has a
parameter default of `round`. Every other field on the marker is inherited
from the marker already on disk -- `Pick` does it for five of them and
`$mySubject` has its own fallback -- so a bare `-Phase` update preserved the
subject, the round number, the depth and the start, and silently relabelled
the *kind*. A plan in its second phase read back as a round. Worse,
`exclusive` derives from the kind: a note kind (`investigation`, `backlog`,
`fix`) is deliberately not a lock, and relabelling it `round` turned it into
one that nothing was obliged to clear.

Observed in stored data at report 048, not reasoned about: the newest entry
in `data/server-starts.jsonl` at `2026-08-18T16:17:32` carries
`"kind": "round", "subject": "", "round": 0` beside
`"completed_seconds": {"planning": 239}` -- a phase only `/backlog-plan` sets.

**`Pick` cannot be the fix, and that is the whole difficulty.** `$Kind` is
always truthy because of its default, so `Pick $Kind 'kind' 'round'` returns
`round` on every call. Telling supplied from defaulted needs
`$PSBoundParameters`.

KI-33 records why this stood for fifty-five reports: the script had no
automated test at all, and every documented invocation was exercised by hand.
This file is the first one. It runs the shipped bytes rather than a copy of
its logic -- the script is copied into a temporary tree so that
`Split-Path -Parent $PSScriptRoot` resolves there and the live
`.claude/run/round.json` of whatever round is running is never touched.

Skipped only where neither `powershell` nor `pwsh` resolves, or where one
resolves and then never answers - see `_shell()`. CI runs `windows-latest`
beside `ubuntu-latest`, so the guard has a leg that executes it on every push.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import NamedTuple

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "round-marker.ps1"


class Shell(NamedTuple):
    """A usable shell, and what it cost this machine to start one.

    The seconds are the point of the type. `exit 0` is the cheapest thing a
    shell can be asked to do, so the time it takes is a measurement of the
    machine rather than of the work - and every other budget in this file is
    derived from it (item 193).
    """

    path: str
    probe_seconds: float


#: Two probe budgets, tried in order. The first is the original 60: generous
#: for a command that does nothing, and a timeout at it already means
#: something is wrong. The second exists to tell WHICH wrong: a starved runner
#: answers late, a broken shell never answers. Two in a row is not starvation.
PROBE_BUDGETS = (60, 180)

#: The script's budget, as a floor and a multiple of the measured probe.
#:
#: The floor is the 120 this file has always used, so nothing changes on a
#: healthy machine - `exit 0` there is well under a second and the multiple
#: never reaches the floor. The multiple is what item 193 adds: on CI at
#: `8dc4795` the probe took over 60 seconds, and a machine that slow to start
#: a shell will not run the shipped script inside a constant chosen for a
#: healthy one. Raising 120 to some larger constant was the option item 193
#: rejected, and rightly: no constant is more principled than another. This
#: one is not a constant - it is what this machine just demonstrated.
RUN_FLOOR_SECONDS = 120
RUN_SLOW_FACTOR = 8


def run_budget(probe_seconds: float) -> float:
    """What the shipped script gets, from what `exit 0` just cost.

    A function rather than an expression in the fixture so it can be asserted
    directly: the whole claim of item 193 is that this number is derived and
    not chosen, and a derivation nothing reads back is indistinguishable from
    a constant with extra steps.
    """
    return max(RUN_FLOOR_SECONDS, probe_seconds * RUN_SLOW_FACTOR)


def _shell() -> Shell:
    """A usable shell, or `pytest.skip` saying which kind of absence it is.

    Skipping from inside the helper rather than returning `None`: there are
    two absences now - nothing resolves, and something resolves that never
    answers - and a caller handed `None` could not tell a reader which it had
    met. The `-ra` output the Windows job already prints carries the reason.
    """
    slow: list[str] = []
    for name in ("powershell", "pwsh"):
        found = shutil.which(name)
        if not found:
            continue
        for budget in PROBE_BUDGETS:
            start = time.monotonic()
            try:
                done = subprocess.run(
                    [found, "-NoProfile", "-Command", "exit 0"],
                    capture_output=True, timeout=budget)
            except OSError:
                break  # present but not runnable; try the other name
            except subprocess.TimeoutExpired:
                # The failure item 193 was filed for. Not fatal on the first
                # budget: the command is `exit 0`, so this says the machine
                # is starved, not that the shell is broken.
                slow.append(f"{name} did not answer `exit 0` within {budget}s")
                continue
            if done.returncode == 0:
                return Shell(found, time.monotonic() - start)
            break  # answered and refused; a longer budget will not help
    if slow:
        pytest.skip(
            "a shell resolved but never answered: " + "; ".join(slow)
            + ". `exit 0` is the cheapest thing a shell can do, so this is a "
            "starved runner rather than a missing shell (item 193). The guard "
            "did not run here and nothing else runs it - re-run the job.")
    pytest.skip("neither powershell nor pwsh runs on this machine")


@pytest.fixture
def marker(tmp_path):
    """A private copy of the shipped script, rooted in a throwaway tree.

    `$root` is `Split-Path -Parent $PSScriptRoot`, so putting the copy in
    `<tmp>/scripts/` puts its marker in `<tmp>/.claude/run/round.json`. No
    parameter is added to the production script to make it testable: the test
    bends, not the thing under test.
    """
    shell = _shell()  # skips, with a reason that says which absence
    # What the script gets, from what starting a shell just cost. The floor is
    # what this file has always used; the multiple only ever raises it, and
    # only on a machine that has already demonstrated it is slow (item 193).
    budget = run_budget(shell.probe_seconds)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    copy = scripts / SCRIPT.name
    shutil.copyfile(SCRIPT, copy)

    def run(*args: str) -> subprocess.CompletedProcess:
        cmd = [shell.path, "-NoProfile"]
        if os.name == "nt":
            cmd += ["-ExecutionPolicy", "Bypass"]
        cmd += ["-File", str(copy), *args]
        # A timeout here is NOT skipped, unlike one in the probe. This runs
        # the shipped script, so a hang may be the script hanging - which is a
        # defect this file should report rather than step around. The budget
        # is scaled so that a starved runner does not reach this point at all.
        return subprocess.run(cmd, capture_output=True, text=True,
                              timeout=budget)

    def read() -> dict:
        path = tmp_path / ".claude" / "run" / "round.json"
        # utf-8-sig: PowerShell 5.1's `Set-Content -Encoding utf8` writes a
        # BOM, which `json.loads` rejects. The same note is in
        # `clauditseo/provenance.py`, which reads this file in production.
        return json.loads(path.read_text(encoding="utf-8-sig"))

    return run, read


# --- the defect --------------------------------------------------------


def test_a_bare_phase_update_does_not_relabel_a_plan_as_a_round(marker):
    """`/backlog-plan` claims `-Kind plan` and then runs `-Phase <name>`."""
    run, read = marker
    claimed = run("-Claim", "-Kind", "plan", "-Phase", "planning",
                  "-Start", "2026-08-23T09:00:00+10:00")
    assert claimed.returncode == 0, claimed.stdout + claimed.stderr
    assert read()["kind"] == "plan"

    updated = run("-Phase", "working")
    assert updated.returncode == 0, updated.stdout + updated.stderr
    got = read()
    assert got["phase"] == "working", "the phase is what the call was for"
    assert got["kind"] == "plan", (
        "a phase update said where the work is and was taken to say what the "
        "work is: the marker now reads " + repr(got["kind"]))


def test_a_bare_phase_update_does_not_turn_a_note_into_a_lock(marker):
    """The costlier half. `investigation`, `backlog` and `fix` are recorded
    without being held, precisely because no skill wraps them and nothing
    guarantees a clear. Relabelling one `round` sets `exclusive`, and then a
    marker nobody is obliged to remove blocks the next claimant for the full
    ninety-minute staleness window."""
    run, read = marker
    run("-Claim", "-Kind", "investigation", "-Phase", "reading",
        "-Start", "2026-08-23T09:00:00+10:00")
    assert read()["exclusive"] is False

    run("-Phase", "measuring")
    got = read()
    assert got["kind"] == "investigation", got["kind"]
    assert got["exclusive"] is False, (
        "a note that was never a lock became one on a phase update")


def test_the_relabelled_kind_is_what_the_subject_already_refuses(marker):
    """`$mySubject` has carried the existing subject forward since the field
    was added; `$myKind` beside it did not. The asymmetry is the finding."""
    run, read = marker
    run("-Claim", "-Kind", "relay", "-Subject", "053", "-Phase", "working",
        "-Start", "2026-08-23T09:00:00+10:00")
    run("-Phase", "verifying")
    got = read()
    assert got["subject"] == "053", "the subject was always inherited"
    assert got["kind"] == "relay", "and the kind beside it must be too"


# --- the must-not-change directions ------------------------------------


def test_an_explicitly_supplied_kind_still_wins(marker):
    """Inheritance is for the kind nobody supplied. A caller that states one
    is stating it."""
    run, read = marker
    run("-Claim", "-Kind", "plan", "-Phase", "planning",
        "-Start", "2026-08-23T09:00:00+10:00")
    run("-Kind", "relay", "-Subject", "060", "-Phase", "working")
    got = read()
    assert got["kind"] == "relay" and got["subject"] == "060"


def test_a_claim_on_an_empty_tree_is_still_a_round_by_default(marker):
    """`/audit-fix` claims with `-Round <NNN>` and no `-Kind`, and every
    existing call of that shape must keep working unchanged."""
    run, read = marker
    run("-Claim", "-Round", "89", "-Depth", "standard", "-MaxRounds", "1",
        "-Phase", "preflight", "-Start", "2026-08-23T09:00:00+10:00")
    got = read()
    assert got["kind"] == "round" and got["subject"] == "89"
    assert got["exclusive"] is True


def test_a_claim_does_not_inherit_the_kind_of_what_it_displaces(marker):
    """A note is not a lock, so a round may take the marker straight off one.
    Taking its *kind* with it would name the wrong work -- the same defect as
    the one above, arriving from the other side. Inheritance is a property of
    a plain update, never of a claim."""
    run, read = marker
    run("-Claim", "-Kind", "investigation", "-Phase", "reading",
        "-Start", "2026-08-23T09:00:00+10:00")
    displaced = run("-Claim", "-Round", "89", "-Phase", "preflight",
                    "-Start", "2026-08-23T10:00:00+10:00")
    assert displaced.returncode == 0, displaced.stdout + displaced.stderr
    assert "displaced note" in displaced.stdout
    got = read()
    assert got["kind"] == "round" and got["subject"] == "89"
    assert got["exclusive"] is True


def test_a_phase_transition_still_banks_the_phase_it_left(marker):
    """`completed_seconds` is what a round's TIMINGS row is checked against.
    Touching the field that decides the kind must not disturb it."""
    run, read = marker
    run("-Claim", "-Kind", "plan", "-Phase", "planning",
        "-Start", "2026-08-23T09:00:00+10:00")
    run("-Phase", "working")
    got = read()
    assert "planning" in got["completed_seconds"], (
        "the phase it left was not banked: " + repr(got["completed_seconds"]))
    assert got["phase"] == "working"


# --- the probe, item 193 ---------------------------------------------------
#
# Driven against a faked `subprocess.run`, because the machine running these
# is not starved and so can never reach the case that reached CI. What is
# under test is the probe's DECISION, and the decision is made entirely from
# what `run` raises.


def _fake_run(outcomes):
    """A `subprocess.run` that plays `outcomes` in order.

    Each entry is either an exception to raise or a returncode to return.
    """
    seen = []

    def run(cmd, **kw):
        seen.append(kw.get("timeout"))
        out = outcomes[len(seen) - 1]
        if isinstance(out, BaseException):
            raise out
        return subprocess.CompletedProcess(cmd, out)

    run.budgets = seen
    return run


def test_a_shell_that_answers_late_is_used_rather_than_given_up_on(monkeypatch):
    """The starved runner recovers, which is the case item 193 exists for.

    A timeout on the first budget is not an answer about the shell; it is an
    answer about the machine. The second budget is what tells them apart.
    """
    monkeypatch.setattr(shutil, "which", lambda n: f"/bin/{n}")
    fake = _fake_run([subprocess.TimeoutExpired("powershell", 60), 0])
    monkeypatch.setattr(subprocess, "run", fake)

    got = _shell()
    assert got.path == "/bin/powershell", got
    assert fake.budgets == list(PROBE_BUDGETS[:2]), (
        f"the retry did not use a larger budget than the first: {fake.budgets}")


def test_a_shell_that_never_answers_skips_and_says_it_was_starved(monkeypatch):
    """Two timeouts in a row is not starvation, and the reason says so.

    It is a skip rather than an error because an ERROR out of a fixture fails
    the whole job, which is what one slow CI runner did at `8dc4795`. It is a
    LOUD skip because this file is the only thing that runs the guard, so the
    reader of a green run has to be able to find out that it did not.
    """
    monkeypatch.setattr(shutil, "which", lambda n: f"/bin/{n}")
    monkeypatch.setattr(subprocess, "run", _fake_run(
        [subprocess.TimeoutExpired("powershell", b) for b in PROBE_BUDGETS] * 2))

    with pytest.raises(pytest.skip.Exception) as caught:
        _shell()
    reason = str(caught.value)
    assert "exit 0" in reason and "starved" in reason, (
        f"the skip does not say which kind of absence this was: {reason}")
    assert "item 193" in reason, reason


def test_no_shell_at_all_keeps_the_reason_it_always_had(monkeypatch):
    """The original absence, unchanged: this is what makes the Linux leg of
    CI skip, and it must not start claiming starvation."""
    monkeypatch.setattr(shutil, "which", lambda n: None)
    with pytest.raises(pytest.skip.Exception) as caught:
        _shell()
    assert "neither powershell nor pwsh runs" in str(caught.value)
    assert "starved" not in str(caught.value)


def test_a_shell_that_answers_and_refuses_is_not_retried(monkeypatch):
    """A non-zero exit is an answer. Retrying it spends the second budget to
    be told the same thing, which on a healthy machine is free and on a sick
    one is three more minutes."""
    monkeypatch.setattr(shutil, "which",
                        lambda n: "/bin/powershell" if n == "powershell" else None)
    fake = _fake_run([1])
    monkeypatch.setattr(subprocess, "run", fake)
    with pytest.raises(pytest.skip.Exception):
        _shell()
    assert len(fake.budgets) == 1, (
        f"a refusal was retried as though it were a timeout: {fake.budgets}")


def test_the_scripts_budget_is_derived_from_the_machine_not_chosen():
    """Item 193's objection to its own suggested fix, held as a clause.

    Raising 120 to a larger constant "picks a number with no measurement
    behind it". So: a healthy machine keeps exactly the number this file has
    always used, and a slow one gets more in proportion to how slow it just
    proved to be.
    """
    assert run_budget(0.3) == RUN_FLOOR_SECONDS, (
        "a healthy machine no longer gets the budget this file has always "
        "used, so item 193 changed behaviour where nothing was wrong")
    assert run_budget(60) == 60 * RUN_SLOW_FACTOR > RUN_FLOOR_SECONDS, (
        "the runner at 8dc4795 took over 60s to run `exit 0` and would still "
        "get a budget chosen for a healthy machine")
    assert run_budget(1000) > run_budget(100) > run_budget(10), (
        "the budget does not track the measurement it claims to be derived "
        "from")
