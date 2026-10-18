"""No loop tool passes pytest a flag `pyproject.toml` already supplies — CQ-179.

`.claude/loop/PROFILE.md:18-19` states the rule: `-q` belongs in `addopts` and
nowhere else, because *"a second one makes -qq, which removes the 'N passed'
line the round records"*. `scripts/prove_fail.py` spawned
`[str(PYTEST), node_id, "-q"]` against an `addopts` of `-q --durations=20`, so
every rule-1 proof it has ever printed quoted the `--durations` table where the
test result belongs. Reproduced on the gate's own entry point before this guard
was written:

    with the extra -q  -> "(1 durations < 0.005s hidden.  Use -vv ...)"
    without it         -> "1 passed, 3 warnings in 0.42s"

The exit code was never affected — `prove_fail.py` reads `returncode`, not the
text — so the tool kept answering PROVEN and NOT PROVEN correctly while the
three lines it prints as evidence carried nothing a human could check. That is
the worse half of the two, because a wrong verdict announces itself and an
empty proof reads as normal.

**The forbidden set is derived from `pyproject.toml`, never listed here.** A
guard naming `("-q",)` would go green on this fix and stay green when
`--durations=20` or anything after it is doubled next. The population it is
applied to is a glob over the loop's tooling with a floor, on the same
reasoning as `test_the_proof_tool_runs_the_gates_entry_point.py`: a hard-coded
list of one is how a partial fix passes (DISCIPLINE rule 3), and today
`scripts/prove_fail.py:223` is the only site — enumerated by grepping for
`PYTEST` and `"pytest"` across `scripts/` and `tests/`, not read off the
report's list.

**Read the AST, not the text.** The breach is one element of an argument list
whose sibling elements decide whether the call is even a pytest invocation, and
a line scan for `-q` over this repository returns the prose that states the
rule far more often than the code that breaks it.

**Non-vacuity is a positive control plus a floor on the parse.** If `addopts`
stopped being readable the forbidden set would be empty and the assertion below
would be true about nothing, so it is asserted non-empty; and the detector is
run against a snippet known to breach, because a check drawing its evidence
from the thing it checks can only ever pass (DISCIPLINE rule 5).
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Callee names that start a process, same set and same reasoning as the
#: entry-point guard beside this one: narrowing to spawns is what keeps the
#: detector from flagging the sentence that describes a breach.
_SPAWNS = {"run", "Popen", "call", "check_call", "check_output", "system"}


def _sources() -> list[Path]:
    """Every Python file that could plausibly run the suite on the loop's
    behalf: the loop's own tooling, and the tests that drive it."""
    return sorted(
        [*(ROOT / "scripts").glob("*.py"), *(ROOT / "tests").glob("test_*.py")]
    )


def _configured_flags() -> set[str]:
    """The flags `pyproject.toml` already gives every pytest invocation.

    Derived rather than declared: this is the whole reason the guard survives
    the next flag being added to `addopts`.
    """
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    addopts = config["tool"]["pytest"]["ini_options"]["addopts"]
    return {token for token in addopts.split() if token.startswith("-")}


def _looks_like_pytest(parts: list[str | None], names: list[str]) -> bool:
    """Whether an argument list is invoking pytest at all.

    Two spellings reach it: a string element naming the runner, and a `Path`
    or `str()` of a constant whose name says so — `str(PYTEST)` is the shape
    `63025e0` left behind, and it carries no string literal to match on.
    """
    if any(part and "pytest" in part.lower() for part in parts):
        return True
    return any("pytest" in name.lower() for name in names)


def _repeated_flags(source: str, forbidden: set[str]) -> list[tuple[int, str]]:
    """`(line, flag)` for every pytest spawn repeating a configured flag."""
    hits: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        name = (node.func.attr if isinstance(node.func, ast.Attribute)
                else node.func.id if isinstance(node.func, ast.Name) else "")
        if name not in _SPAWNS:
            continue
        for arg in [*node.args, *(kw.value for kw in node.keywords)]:
            if not isinstance(arg, (ast.List, ast.Tuple)):
                continue
            parts = [e.value if isinstance(e, ast.Constant)
                     and isinstance(e.value, str) else None
                     for e in arg.elts]
            names = [n.id for e in arg.elts for n in ast.walk(e)
                     if isinstance(n, ast.Name)]
            if not _looks_like_pytest(parts, names):
                continue
            for part in parts:
                if part in forbidden:
                    hits.append((node.lineno, part))
    return sorted(set(hits))


def test_the_detector_flags_a_call_it_is_shown():
    """The positive control. Both spellings of the runner, on source this file
    owns, so the assertion below cannot be passing because the walker broke."""
    by_constant = _repeated_flags(
        'subprocess.run([str(PYTEST), node_id, "-q"], cwd=ROOT)', {"-q"}
    )
    by_literal = _repeated_flags(
        'subprocess.run(["pytest", node_id, "-q"], cwd=ROOT)', {"-q"}
    )
    assert by_constant == [(1, "-q")], (
        f"the str(PYTEST) form was not flagged: {by_constant}")
    assert by_literal == [(1, "-q")], (
        f"the string-literal form was not flagged: {by_literal}")


def test_the_detector_leaves_an_unconfigured_flag_alone():
    """The must-not-change direction. A flag `addopts` does *not* supply is a
    legitimate argument — `-x`, `--basetemp`, a node id — and flagging it would
    make this guard a refusal rather than a rule."""
    assert _repeated_flags(
        'subprocess.run([str(PYTEST), node_id, "-x"], cwd=ROOT)', {"-q"}
    ) == []
    assert _repeated_flags(
        'subprocess.run([str(PYTEST), node_id], cwd=ROOT)', {"-q"}
    ) == []
    assert _repeated_flags(
        'subprocess.run(["git", "checkout", "-q", "HEAD"])', {"-q"}
    ) == [], "a non-pytest spawn was flagged; -q means something else to git"


def test_the_configured_set_is_read_from_pyproject():
    """The floor on the parse. An empty forbidden set makes the guard below
    vacuous, and it would be empty if `addopts` moved or was renamed."""
    flags = _configured_flags()
    assert flags, (
        "no flags were read out of pyproject.toml's addopts, so the guard "
        "below is asserting nothing"
    )
    assert "-q" in flags, (
        f"addopts no longer supplies -q ({sorted(flags)}); if that was "
        "deliberate the PROFILE.md rule this guard enforces has changed"
    )


def test_the_scan_reaches_the_tooling():
    """Guards the population rather than the predicate: a glob that stopped
    matching would make the assertion below true about nothing."""
    sources = _sources()
    assert len(sources) >= 50, (
        f"only {len(sources)} Python sources were collected; the globs have "
        "stopped matching and the assertion below is not testing anything"
    )


def test_no_loop_tool_repeats_a_flag_pyproject_already_supplies():
    """CQ-179 itself.

    A doubled `-q` is `-qq`, which removes the `N passed` line — so the three
    lines `prove_fail.py` prints beside its verdict become the `--durations`
    table, and the one claim a fix commit cannot be checked on by re-reading
    the diff is also the one nobody can read.
    """
    forbidden = _configured_flags()
    breaches = [
        f"{p.relative_to(ROOT).as_posix()}:{line} passes {flag}"
        for p in _sources()
        for line, flag in _repeated_flags(
            p.read_text(encoding="utf-8", errors="replace"), forbidden)
    ]
    assert not breaches, (
        "these pass pytest a flag pyproject.toml's addopts already supplies, "
        "which doubles it - and a doubled -q is -qq, which removes the result "
        "line the round records (PROFILE.md:18-19):\n  "
        + "\n  ".join(breaches)
    )
