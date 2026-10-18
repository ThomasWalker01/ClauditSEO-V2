"""A flag a script tells the operator to use has to exist.

`scripts/run_golden.py` advertised `--compare <run_id>` in its usage block and
again in the line it printed at the end of every successful run — "pass it to
`--compare` on the next model". `argparse` defined four flags and none of them
was that one. It was found the way these are always found: the documented
command was typed verbatim during a paid run, argparse exited 2 with
`unrecognized arguments`, and the run had to be re-invoked without it.

Derived from the directory rather than from a list of the scripts known to
have had this defect, per DISCIPLINE rule 3 — a hard-coded list of one is how
the next instance passes.

**Scoped to operator-facing text**, which is the whole of what "advertises"
means here: module and function docstrings, the strings the script prints, and
argparse `help=`. Not every string in the file — `prove_fail.py` passes
`--porcelain` and `--name-only` to `git`, and a guard that read those as broken
advertisements would be measuring the wrong thing and would be turned off.

**A line naming another script is checked against that script.**
`seed_dev_data.py:39` tells the reader that `scripts/run_golden.py --spend`
costs money, and it is right to; the flag it names belongs to the other
parser and is looked up there.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
FLAG = re.compile(r"--[a-z][a-z0-9-]*")


def _options(tree: ast.Module) -> set[str]:
    """Every option string this parser defines."""
    out: set[str] = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and getattr(node.func, "attr", "") == "add_argument"):
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    out.add(arg.value)
    return out


def _operator_facing(tree: ast.Module) -> list[str]:
    """The text an operator reads: docstrings, printed strings, argparse help."""
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            doc = ast.get_docstring(node)
            if doc:
                out.append(doc)
        if isinstance(node, ast.Call):
            if getattr(node.func, "id", "") == "print":
                for arg in node.args:
                    out += [n.value for n in ast.walk(arg)
                            if isinstance(n, ast.Constant)
                            and isinstance(n.value, str)]
            for kw in node.keywords or []:
                if kw.arg == "help" and isinstance(kw.value, ast.Constant):
                    out.append(kw.value.value)
    return out


def _parsers() -> dict[str, tuple[set[str], list[str]]]:
    parsed = {}
    for path in sorted(SCRIPTS.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        options = _options(tree)
        if options:
            parsed[path.name] = (options, _operator_facing(tree))
    return parsed


PARSERS = _parsers()


def test_the_scripts_with_parsers_were_actually_found():
    """Rule 4. An enumeration that silently found nothing passes every
    assertion below it."""
    assert len(PARSERS) >= 5, PARSERS
    assert "run_golden.py" in PARSERS


@pytest.mark.parametrize("name", sorted(PARSERS))
def test_every_flag_a_script_advertises_is_a_flag_it_accepts(name):
    own, facing = PARSERS[name]
    others = {n for n in PARSERS if n != name}
    for text in facing:
        for line in text.splitlines():
            named = [n for n in others if n in line]
            # A line naming exactly one other script is advertising that one.
            defined = PARSERS[named[0]][0] if len(named) == 1 else own
            for flag in FLAG.findall(line):
                assert flag in defined, (
                    f"{name} tells the operator to use {flag}, which"
                    f" {named[0] if len(named) == 1 else name} does not accept."
                    f"\n  line: {line.strip()}")
