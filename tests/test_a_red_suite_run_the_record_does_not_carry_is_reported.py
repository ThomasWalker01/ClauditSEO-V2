"""WF-98's reader — `scripts/check_carveout.py`, held to what it claims.

`.claude/DISCIPLINE.md` rule 6 makes two mechanical demands of a round that
meets a red suite. On a preflight red: *"Report the failures, and quote the
`.claude/run/` log path."* On the re-run carve-out, at baseline or — since
round 131 extended it — at verify: *"say so and quote both runs' paths under
`.claude/run/`"*, and only *"where the failing node is in the filed
load-sensitive class"* that `KNOWN_ISSUES.md` KI-22 and KI-51 register.

**Nothing checked either.** Report 132 raised WF-98 on exactly that, and the
measurement this script produced on its first run says what it was worth: of
the 14 red runs sitting in `.claude/run/`, **9 are quoted by no commit in the
entire history**. Each of those is a red the record does not carry, and a
carve-out taken against any of them would be undetectable from the repository.

## Why the node is read from the log and not from the commit

Two matchers over commit prose were measured against the real history and both
rejected before this shape was chosen — the same rejection round 129 recorded
for CQ-240's two candidate matchers:

- *"the body mentions a re-run or the carve-out"* matches **55** commits, and
  almost all of them merely discuss the rule.
- *"the body contains a `N failed` pytest summary"* matches **110**, because a
  guard proved fail-first quotes its own red in exactly that form.

Neither separates a carve-out from a commit talking about one. So this script
asks prose nothing. Both of rule 6's conditions are read from machine-written
evidence at both ends: the failing node comes from pytest's own `FAILED` line
inside the log, and whether the log was quoted comes from an exact filename
match against the commit bodies.

## What it does not claim

**It does not say which commits invoked the carve-out**, and must not be read
as saying so. It says a red run happened and the record does or does not carry
it. Whether a given commit leaned on that red is a judgement, left with the
person doing the carry — the `context_lines` shape, not a matcher that guesses
and is believed.

Everything here runs on synthetic logs and synthetic commit bodies. The real
`.claude/run/` is covered by `.gitignore`, so it does not exist on the CI gate,
and a test that read it would be green there by reading nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_carveout  # noqa: E402

GREEN = "2423 passed, 3 xfailed, 24 warnings in 404.71s (0:06:44)"
RED = "1 failed, 2422 passed, 3 xfailed, 25 warnings in 948.50s (0:15:48)"
NODE = "tests/test_a11y_rendered.py::test_screen_has_no_detectable_violations"


def _log(tmp_path: Path, name: str, summary: str, *failed: str) -> Path:
    """A suite log with pytest's own tail: FAILED lines, then the summary."""
    body = ["=" * 27 + " short test summary info " + "=" * 27]
    body += [f"FAILED {node} - AssertionError: something" for node in failed]
    body.append(summary)
    path = tmp_path / name
    path.write_text("\n".join(body) + "\n", encoding="utf-8")
    return path


def _bodies(tmp_path: Path, *bodies: str) -> Path:
    """The commit record, as `git log --format=%b` hands it over."""
    path = tmp_path / "bodies.txt"
    path.write_text("\n".join(bodies), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Reading a log: red, green, and the state that is neither
# ---------------------------------------------------------------------------

def test_a_green_run_is_not_a_red_one(tmp_path):
    """`xfailed` contains the substring `failed`.

    Written down because the first cut of this measurement classified all 45
    logs as red on `"failed" in summary`, and 31 of them were green. The
    summary is matched at its start, where pytest puts the failure count.
    """
    run = check_carveout.read_log(_log(tmp_path, "suite-1.log", GREEN))
    assert run.outcome == "green"
    assert run.nodes == []


def test_a_red_run_reports_its_outcome_and_every_failing_node(tmp_path):
    run = check_carveout.read_log(
        _log(tmp_path, "suite-2.log", RED, NODE, "tests/test_b.py::test_two"))
    assert run.outcome == "red"
    assert run.nodes == [NODE, "tests/test_b.py::test_two"]


def test_a_log_with_no_summary_line_is_neither_red_nor_green(tmp_path):
    """Rule 6's third state: a run that told you nothing.

    `.claude/run/` holds two such logs today. Collapsing them into `green`
    would be the no-result-read-as-a-pass the rule exists to forbid.
    """
    path = tmp_path / "suite-3.log"
    path.write_text("INTERNALERROR> PermissionError: [WinError 5]\n",
                    encoding="utf-8")
    assert check_carveout.read_log(path).outcome == "no result"


def test_the_last_summary_wins_when_a_log_holds_more_than_one(tmp_path):
    """A repaired run appends its second summary below the first."""
    path = tmp_path / "suite-4.log"
    path.write_text(f"3 failed, 10 passed in 1.00s\n{GREEN}\n",
                    encoding="utf-8")
    assert check_carveout.read_log(path).outcome == "green"


# ---------------------------------------------------------------------------
# The comparison — the finding itself
# ---------------------------------------------------------------------------

def test_a_red_run_no_commit_quotes_is_reported(tmp_path):
    """WF-98's own case, and 9 of the 14 real red logs are in it."""
    red = check_carveout.read_log(_log(tmp_path, "suite-5.log", RED, NODE))
    unheld = check_carveout.unaccounted([red], ["fix: something"])
    assert [r.name for r in unheld] == ["suite-5.log"]


def test_a_red_run_a_commit_quotes_by_name_is_not_reported(tmp_path):
    red = check_carveout.read_log(_log(tmp_path, "suite-6.log", RED, NODE))
    body = "Tests: red, see `.claude/run/suite-6.log`, re-run green"
    assert check_carveout.unaccounted([red], [body]) == []


def test_a_green_run_is_never_asked_for_a_quote(tmp_path):
    """The obligation is on a red.

    Requiring every green to be quoted would make the check permanently loud
    and so permanently ignored — 31 of the 45 real logs are green and most are
    ordinary baselines nothing asks anyone to cite.
    """
    green = check_carveout.read_log(_log(tmp_path, "suite-7.log", GREEN))
    assert check_carveout.unaccounted([green], []) == []


def test_a_no_result_run_is_reported_like_a_red(tmp_path):
    """Rule 6: a no-result "is not a pass and not a failure". It blocks the
    commit exactly as a red does, so the record owes it the same path."""
    path = tmp_path / "suite-8.log"
    path.write_text("INTERNALERROR> nothing ran\n", encoding="utf-8")
    run = check_carveout.read_log(path)
    assert [r.name for r in check_carveout.unaccounted([run], [])] \
        == ["suite-8.log"]


def test_a_register_row_quotes_a_run_as_well_as_a_commit_does(tmp_path):
    """Rule 6 says *quote both runs' paths*, not *in a commit body*.

    Three real captures are quoted only outside the commits — two in KI-51's
    instance rows, one in an `OPERATOR_ACTIONS.md` row — and reading commits
    alone called all three unaccounted. Measured: 11 against commits alone,
    7 against commits, registers and reports together.
    """
    red = check_carveout.read_log(_log(tmp_path, "suite-r.log", RED, NODE))
    (tmp_path / "KNOWN_ISSUES.md").write_text(
        "KI-51 instance nine: `.claude/run/suite-r.log`\n", encoding="utf-8")
    record = check_carveout.written_record(tmp_path)
    assert check_carveout.unaccounted([red], record) == []


def test_the_written_record_is_globbed_and_not_listed(tmp_path):
    """A register added to the loop and not to a hand-written list here would
    quietly start over-reporting — the omission
    `test_every_register_the_loop_keeps_has_a_row_in_the_planner_table`
    records three times over. A file nobody anticipated still counts."""
    (tmp_path / "A_REGISTER_NOBODY_LISTED.md").write_text(
        "suite-z.log\n", encoding="utf-8")
    assert any("suite-z.log" in t
               for t in check_carveout.written_record(tmp_path))


def test_the_written_record_does_not_reach_outside_markdown(tmp_path):
    """A log name appearing in source or in a captured run is not the record
    saying anything about it — most of all, a log must not account for
    itself."""
    (tmp_path / "notes.txt").write_text("suite-q.log\n", encoding="utf-8")
    assert not any("suite-q.log" in t
                   for t in check_carveout.written_record(tmp_path))


def test_quoting_a_different_log_does_not_discharge_this_one(tmp_path):
    """Containment defeat, the shape `register_anchor_paths` records under
    WF-45: a check written as "some log path appears" would be discharged by
    any commit that quotes any log at all."""
    red = check_carveout.read_log(_log(tmp_path, "suite-9.log", RED, NODE))
    body = "quoted `.claude/run/suite-20260901-141530.log` instead"
    assert [r.name for r in check_carveout.unaccounted([red], [body])] \
        == ["suite-9.log"]


# ---------------------------------------------------------------------------
# Rule 6's second condition — the node, against the filed class
# ---------------------------------------------------------------------------

def _register(tmp_path: Path, *nodes: str) -> Path:
    path = tmp_path / "KNOWN_ISSUES.md"
    rows = "\n".join(f"| KI-51 | flake | `{n}` | open |" for n in nodes)
    path.write_text(
        "## Open\n\n| id | what | evidence | status |\n"
        f"| --- | --- | --- | --- |\n{rows}\n", encoding="utf-8")
    return path


def test_a_node_the_register_files_is_recognised(tmp_path):
    assert NODE in check_carveout.filed_class(_register(tmp_path, NODE))


def test_a_node_the_register_does_not_file_is_outside_the_class(tmp_path):
    """The carve-out reaches the filed class *and nothing else*. A red on an
    unfiled node is an ordinary red, and it stops the round."""
    filed = check_carveout.filed_class(_register(tmp_path, NODE))
    assert "tests/test_verify.py::test_something_else" not in filed


def test_an_empty_register_files_nothing_rather_than_everything(tmp_path):
    """The direction a bug here must fail in. A collector that broke and
    returned "everything" would silently authorise every carve-out."""
    path = tmp_path / "KNOWN_ISSUES.md"
    path.write_text("## Open\n\nnothing open.\n", encoding="utf-8")
    assert check_carveout.filed_class(path) == set()


def test_only_the_open_section_files_a_node(tmp_path):
    """A node fixed out of the class must stop authorising a carve-out.

    Rule 6 says membership goes stale in both directions and names the case:
    `test_a_recalled_brief_states_the_total_it_was_drawn_from` sat under KI-51
    through sixteen instances and was a deterministic ephemeral-port
    collision, fixed in round 127.
    """
    path = tmp_path / "KNOWN_ISSUES.md"
    path.write_text(
        "## Open\n\n| id | what | evidence | status |\n"
        "| --- | --- | --- | --- |\n"
        "| KI-51 | flake | `tests/test_live.py::test_a` | open |\n"
        "\n## Resolved\n\n| id | what | evidence | status |\n"
        "| --- | --- | --- | --- |\n"
        "| KI-49 | fixed | `tests/test_dead.py::test_b` | closed |\n",
        encoding="utf-8")
    assert check_carveout.filed_class(path) == {"tests/test_live.py::test_a"}


def test_a_red_on_an_unfiled_node_is_flagged_separately_from_the_quote(
        tmp_path):
    """Rule 6's two conditions are two questions, and the report keeps them
    apart: a quoted red on an unfiled node is not an unquoted red."""
    red = check_carveout.read_log(
        _log(tmp_path, "suite-c.log", RED, "tests/test_x.py::test_unfiled"))
    body = "see `.claude/run/suite-c.log`"
    filed = check_carveout.filed_class(_register(tmp_path, NODE))
    assert check_carveout.unaccounted([red], [body]) == []
    assert [r.name for r in check_carveout.outside_class([red], filed)] \
        == ["suite-c.log"]


# ---------------------------------------------------------------------------
# The exit code, which is what a round and the gate actually read
# ---------------------------------------------------------------------------

def test_the_exit_code_says_whether_anything_is_unaccounted(tmp_path, capsys):
    _log(tmp_path, "suite-a.log", RED, NODE)
    code = check_carveout.main(
        ["--run-dir", str(tmp_path), "--bodies-from", str(_bodies(tmp_path)),
         "--register", str(_register(tmp_path, NODE))])
    assert code == 1
    assert "suite-a.log" in capsys.readouterr().out


def test_a_clean_comparison_exits_zero(tmp_path, capsys):
    _log(tmp_path, "suite-b.log", GREEN)
    code = check_carveout.main(
        ["--run-dir", str(tmp_path), "--bodies-from", str(_bodies(tmp_path)),
         "--register", str(_register(tmp_path, NODE))])
    assert code == 0
    assert "clean" in capsys.readouterr().out


def test_a_missing_run_directory_is_a_no_result_not_a_pass(tmp_path, capsys):
    """The CI case. `.claude/run/` is gitignored, so on the gate there is
    nothing to compare — and that must not read as "every red is accounted"."""
    code = check_carveout.main(
        ["--run-dir", str(tmp_path / "absent"),
         "--bodies-from", str(_bodies(tmp_path)),
         "--register", str(_register(tmp_path, NODE))])
    assert code == 2
    assert "no result" in capsys.readouterr().out
