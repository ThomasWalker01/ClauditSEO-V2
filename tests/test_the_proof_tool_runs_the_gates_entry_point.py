"""No loop tool runs pytest through the interpreter's module form — CQ-177.

`.claude/loop/PROFILE.md:20-21` states the rule for this repository in one
line: *"Match the entry-point kind: a console-script pytest, never python -m
pytest."* `.claude/DISCIPLINE.md:174-179` records what the difference cost —
the module form puts the working directory on `sys.path` and the console
script does not, which is why `242d94a` had to make `tests/` a package before
the gate's own invocation could resolve `tests.conftest`.

The tool that answers DISCIPLINE rule 1 is the one place that difference is
least affordable. `scripts/prove_fail.py` decides whether a guard was ever
red, and every fix commit quotes its verdict; taken under a different import
regime from the gate, its failure mode is a *confident* answer rather than the
`CANNOT ANSWER` the script gives everywhere else it cannot see.

**Read the AST, not the text — this breach is invisible to a grep.** The site
CQ-177 names is `[str(PYTHON), "-m", "pytest", node_id, "-q"]`: two adjacent
list elements, so a scan for the string `-m pytest` over `scripts/`,
`.claude/`, `.github/` and `tests/` returns the four places that state the
rule in prose and not the one place that breaks it. That was measured before
this file was written, and it is the whole reason the detector walks argument
lists instead of lines.

**The population is a file list, never a name.** A hard-coded list of one is
how a partial fix passes (DISCIPLINE rule 3), and the site under repair is
today the only one — so a guard naming it would go green on the fix and stay
green for a second tool added anywhere else.

**Non-vacuity is a positive control, not a count.** A floor of "some argument
list still contains the constant `pytest`" would be satisfied today and
vacuous the moment the fix lands, because the repaired call reaches the
console script through a `Path` constant rather than a string literal. So the
detector is instead run against a snippet that is known to breach, and must
flag it. A check that cannot be shown to disagree with its subject can only
ever pass (DISCIPLINE rule 5).
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _sources() -> list[Path]:
    """Every Python file that could plausibly run the suite on the loop's
    behalf: the loop's own tooling, and the tests that drive it."""
    return sorted(
        [*(ROOT / "scripts").glob("*.py"), *(ROOT / "tests").glob("test_*.py")]
    )


#: Callee names that start a process. The first version of this detector had
#: no such filter and flagged its own positive control below — the fixture
#: `_module_form_calls('subprocess.run("python -m pytest tests", ...)')` is a
#: call carrying a string that contains the breach, and a rule reading "any
#: call with that substring" cannot tell the breach from the sentence
#: describing it. Recorded rather than fixed by exempting this file: a guard
#: that excuses itself is the shape that rots, and narrowing to spawns is the
#: more correct rule regardless. The same wall is `test_prove_fail_refuses_
#: bundle_tests.py`'s: a textual scan that cannot tell code from prose.
_SPAWNS = {"run", "Popen", "call", "check_call", "check_output", "system"}


def _module_form_calls(source: str) -> list[int]:
    """Line numbers of every process spawn passing pytest as `python -m pytest`.

    Both spellings, because both reach the same interpreter: `"-m", "pytest"`
    as adjacent elements of an argument list, and `-m pytest` inside a single
    string handed to a shell.
    """
    hits: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        name = (node.func.attr if isinstance(node.func, ast.Attribute)
                else node.func.id if isinstance(node.func, ast.Name) else "")
        if name not in _SPAWNS:
            continue
        for arg in [*node.args, *(kw.value for kw in node.keywords)]:
            parts: list[str | None] = []
            if isinstance(arg, (ast.List, ast.Tuple)):
                parts = [e.value if isinstance(e, ast.Constant)
                         and isinstance(e.value, str) else None
                         for e in arg.elts]
            elif isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                parts = [arg.value]
            for i, part in enumerate(parts):
                if part is None:
                    continue
                if "-m pytest" in part:
                    hits.append(node.lineno)
                elif part == "-m" and parts[i + 1:i + 2] == ["pytest"]:
                    hits.append(node.lineno)
    return sorted(set(hits))


def _subprocess_calls(source: str) -> int:
    return sum(
        1
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "subprocess"
    )


def test_the_detector_flags_a_call_it_is_shown():
    """The positive control. Both spellings, on source this file owns, so the
    assertion below cannot be passing because the walker stopped working."""
    split = _module_form_calls(
        'subprocess.run([str(PYTHON), "-m", "pytest", node_id, "-q"])'
    )
    joined = _module_form_calls('subprocess.run("python -m pytest tests", shell=True)')
    assert split == [1], f"the adjacent-elements form was not flagged: {split}"
    assert joined == [1], f"the single-string form was not flagged: {joined}"


def test_the_detector_leaves_the_console_script_alone():
    """The must-not-change direction. The repaired shape has to read clean, or
    the fix cannot land and the guard is a refusal rather than a rule."""
    assert _module_form_calls(
        'subprocess.run([str(PYTEST), node_id, "-q"], cwd=ROOT)'
    ) == []
    assert _module_form_calls('subprocess.run([sys.executable, "-m", "pip"])') == []


def test_the_scan_reaches_the_tooling():
    """Guards the population rather than the predicate: a glob that stopped
    matching, or a parse that silently failed, would make the assertion below
    true about nothing."""
    sources = _sources()
    assert len(sources) >= 50, (
        f"only {len(sources)} Python sources were collected; the globs have "
        "stopped matching and the assertion below is not testing anything"
    )
    seen = sum(_subprocess_calls(p.read_text(encoding="utf-8", errors="replace"))
               for p in sources)
    assert seen >= 1, (
        "no subprocess call was found anywhere in the collected sources, so "
        "the walker is not reaching the calls this guard is about"
    )


def test_no_loop_tool_runs_pytest_through_the_module_form():
    """CQ-177 itself.

    The gate is `.venv/Scripts/pytest.exe`, a console script, and so is CI's
    PATH-resolved `pytest`. `python -m pytest` is neither, and a rule-1 proof
    taken under it is evidence about a `sys.path` the gate never has.
    """
    breaches = [
        f"{p.relative_to(ROOT).as_posix()}:{line}"
        for p in _sources()
        for line in _module_form_calls(
            p.read_text(encoding="utf-8", errors="replace"))
    ]
    assert not breaches, (
        "these run pytest through the interpreter's module form, which puts "
        "the working directory on sys.path where the gate does not - use the "
        "console script under .venv/Scripts (PROFILE.md:20-21):\n  "
        + "\n  ".join(breaches)
    )
