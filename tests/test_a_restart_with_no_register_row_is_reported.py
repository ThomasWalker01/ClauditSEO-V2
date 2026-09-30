"""WF-47's reader — `scripts/check_restarts.py`, held to what it claims.

The finding is that *nothing compares* `data/server-starts.jsonl` with
`OPERATOR_ACTIONS.md`. The script is the comparison; this is the guard on the
comparison. It is a correctness guard on a new tool, not a fail-first guard on
a defect in existing code — the fail-first evidence for WF-47 is in
`tests/test_every_register_the_loop_keeps_has_a_row_in_the_planner_table.py`,
which failed against the unfixed tree naming the two absent registers, and in
the measurement the script itself produced on first run: 15 of 136 recorded
starts with no row within fifteen minutes, 7 of them with no marker at all.
Said plainly rather than dressed up, because a guard that claims to have caught
something it did not is worse than no claim.

Everything here runs on synthetic registers. The real `data/` is covered by
`.gitignore`, so it does not exist on the CI gate, and a test that read it
would be green there by reading nothing.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_restarts  # noqa: E402

WHEN = datetime.fromisoformat("2026-08-18T10:08:39+10:00")


def _starts_file(tmp_path: Path, *records: dict) -> Path:
    path = tmp_path / "server-starts.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in records),
                    encoding="utf-8")
    return path


def _actions_file(tmp_path: Path, *rows: str) -> Path:
    path = tmp_path / "OPERATOR_ACTIONS.md"
    body = ["| when | who | action | what changed | evidence |",
            "| --- | --- | --- | --- | --- |", *rows]
    path.write_text("\n".join(body) + "\n", encoding="utf-8")
    return path


def _start(at: datetime = WHEN, pid: int = 111, kind: str | None = "round"):
    return {"started_at": at.isoformat(), "pid": pid,
            "marker": None if kind is None else {"kind": kind,
                                                 "subject": "42"}}


def _row(at: datetime, action: str = "`restart-service.ps1`") -> str:
    stamp = at.replace(tzinfo=None).strftime("%Y-%m-%d %H:%M")
    return f"| {stamp} | round 42 | {action} | version moved | /api/health |"


def test_a_start_with_a_matching_row_is_not_reported(tmp_path):
    started = check_restarts.starts(_starts_file(tmp_path, _start()))
    rows = check_restarts.action_rows(_actions_file(tmp_path, _row(WHEN)))
    assert check_restarts.unaccounted(started, rows) == []


def test_a_start_with_no_row_at_all_is_reported(tmp_path):
    """The case WF-47 was raised on."""
    started = check_restarts.starts(_starts_file(tmp_path, _start()))
    rows = check_restarts.action_rows(_actions_file(tmp_path))
    gaps = check_restarts.unaccounted(started, rows)
    assert [g["pid"] for g in gaps] == [111]


def test_a_row_that_records_something_else_does_not_account_for_a_start(
        tmp_path):
    """A rebuild is not a restart, and the register holds far more rebuilds.

    Without this the check would be discharged by any row at all in the
    window, which on a busy round is always true — the containment defeat
    `register_anchor_paths` records under WF-45, in a different register.
    """
    started = check_restarts.starts(_starts_file(tmp_path, _start()))
    rows = check_restarts.action_rows(
        _actions_file(tmp_path, _row(WHEN, "`npm run build` in `dashboard/`")))
    assert [g["pid"] for g in check_restarts.unaccounted(started, rows)] == [111]


@pytest.mark.parametrize("offset_min,expected", [
    (0, []), (14, []), (-14, []), (16, [111]), (-16, [111]),
])
def test_the_window_is_fifteen_minutes_either_side(tmp_path, offset_min,
                                                   expected):
    """Fifteen minutes, and symmetric.

    A round discharges the obligation at the end while the restart happens
    inside it, so the row lands *after* the start; an operator writing the row
    first puts it before. Both directions are real, so a one-sided window
    would report half the recorded restarts as unaccounted.
    """
    started = check_restarts.starts(_starts_file(tmp_path, _start()))
    rows = check_restarts.action_rows(
        _actions_file(tmp_path, _row(WHEN + timedelta(minutes=offset_min))))
    assert [g["pid"] for g in check_restarts.unaccounted(started, rows)] \
        == expected


def test_since_drops_starts_before_the_bound_and_keeps_the_rest(tmp_path):
    """The auditor's step 4b runs this bounded to the previous audit commit."""
    old = _start(WHEN, pid=100)
    new = _start(WHEN + timedelta(days=2), pid=200)
    started = check_restarts.starts(_starts_file(tmp_path, old, new))
    rows = check_restarts.action_rows(_actions_file(tmp_path))
    bounded = check_restarts.unaccounted(
        started, rows, since=WHEN + timedelta(days=1))
    assert [g["pid"] for g in bounded] == [200]


def test_an_unreadable_line_is_reported_rather_than_skipped(tmp_path):
    """An append-only file that will not parse is a defect in the writer.

    Swallowing it would make the register look shorter and therefore cleaner,
    which is the one direction this tool must never fail in.
    """
    path = tmp_path / "server-starts.jsonl"
    path.write_text(json.dumps(_start()) + "\nnot json at all\n",
                    encoding="utf-8")
    started = check_restarts.starts(path)
    rows = check_restarts.action_rows(_actions_file(tmp_path, _row(WHEN)))
    gaps = check_restarts.unaccounted(started, rows)
    assert len(gaps) == 1 and "error" in gaps[0], gaps


def test_a_missing_starts_file_is_a_no_result_not_a_clean_run(tmp_path,
                                                              monkeypatch):
    """DISCIPLINE rule 6's distinction, applied to this tool.

    Exit 2, not 0. A check whose subject is absent has told you nothing, and
    reporting that as `clean` is how an unverifiable claim gets recorded as a
    verified one.
    """
    monkeypatch.setattr(check_restarts, "STARTS", tmp_path / "absent.jsonl")
    assert check_restarts.main([]) == 2


def test_the_exit_code_says_whether_anything_is_unaccounted(tmp_path,
                                                            monkeypatch):
    monkeypatch.setattr(check_restarts, "STARTS",
                        _starts_file(tmp_path, _start()))
    monkeypatch.setattr(check_restarts, "ACTIONS", _actions_file(tmp_path))
    assert check_restarts.main([]) == 1
    monkeypatch.setattr(check_restarts, "ACTIONS",
                        _actions_file(tmp_path, _row(WHEN)))
    assert check_restarts.main([]) == 0


def test_a_start_nobody_claimed_is_named_as_such(tmp_path, capsys):
    """The marker is what tells a loop restart from a hand one.

    Seven of the fifteen unaccounted starts measured when this was written
    carried no marker, which is a different thing from a round forgetting its
    row, and the output must not flatten the two.
    """
    started = check_restarts.starts(
        _starts_file(tmp_path, _start(kind=None)))
    rows = check_restarts.action_rows(_actions_file(tmp_path))
    gaps = check_restarts.unaccounted(started, rows)
    printed = "\n".join(check_restarts.render(started, rows, gaps, None))
    assert "no marker" in printed, printed


def test_an_unresolvable_since_bounds_nothing_rather_than_aborting(tmp_path,
                                                                   monkeypatch):
    """A typo in a gather step must not stop the gather step.

    It reads the whole register and says on stderr that it did, which is the
    louder of the two failure modes and the one that cannot be mistaken for a
    clean window.
    """
    monkeypatch.setattr(check_restarts, "STARTS",
                        _starts_file(tmp_path, _start()))
    monkeypatch.setattr(check_restarts, "ACTIONS", _actions_file(tmp_path))
    assert check_restarts.main(["--since", "not-a-commit-or-date"]) == 1
