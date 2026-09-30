"""A program handed to `subprocess` is resolved, never named.

The rule was stated in prose at three sites and asserted at none. It is not a
style preference: on Windows a bare name is resolved by CreateProcess, which
searches `System32` **before** `PATH`, so the executable that runs need not be
the one a probe just validated.

This repository has paid for that twice in one day. `tests/test_packaging.py`
gated a test on `shutil.which("bash")`, which is truthy on `windows-latest`
because `C:\\Windows\\System32\\bash.exe` is the WSL launcher — a different
program from the Git Bash the test needed, and one that fails differently.
`92fd880` replaced presence with a capability probe and CI stayed red, because
the probe resolved one executable and the caller then invoked the bare name and
got another; `db6a61c` made the probe return the resolved path.

So the class is: a resolved program and a named program are two different
things, and code that checks one while running the other is checking nothing.
Guarded here by walking the AST rather than grepping, because `subprocess.run(
["icacls", ...])` and `subprocess.run([ICACLS, ...])` differ by a node type
and not by a string a pattern can separate.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
ROOTS = ("clauditseo", "tests", "scripts")

#: The subprocess entry points that take a program as their first argument.
SPAWNERS = frozenset({"run", "Popen", "call", "check_call", "check_output"})


def _subprocess_aliases(tree: ast.AST) -> set[str]:
    """Every name bound to the `subprocess` module in this file.

    `import subprocess as sp` binds `sp`, and requiring the name to be
    literally `subprocess` let `sp.run(["icacls"])` through.
    """
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {(a.asname or a.name) for a in node.names
                    if a.name == "subprocess"}
    return out


def _imported_spawners(tree: ast.AST) -> set[str]:
    """`from subprocess import run` — a spawner wearing no module name."""
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "subprocess":
            out |= {(a.asname or a.name) for a in node.names if a.name in SPAWNERS}
    return out


def _module_string_constants(tree: ast.AST) -> dict[str, str]:
    """`NAME = "literal"` at module level, which is how this repo names things.

    Every program handle here is a module constant, so resolving them is not a
    refinement — it is the shape the guard is most likely to meet. Only
    module level: a local rebinding is not something a reader can be expected
    to trace from the call site, and guessing at one would produce the false
    positives that get a guard deleted.
    """
    out: dict[str, str] = {}
    for node in getattr(tree, "body", []):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target, value = node.targets[0], node.value
        if isinstance(target, ast.Name) and isinstance(value, ast.Constant) \
                and isinstance(value.value, str):
            out[target.id] = value.value
    return out


def _literal_program(node: ast.AST, constants: dict[str, str]) -> str | None:
    """The program this expression denotes, if it denotes a fixed one.

    Three shapes, because the defect wore all three: a plain string, an
    f-string with nothing interpolated (`f"icacls"` is a `JoinedStr` and was
    invisible to a `Constant` test), and a module constant.

    `None` for anything computed — `shutil.which(...)`, a joined path, a
    parameter — which is the whole point: those have been resolved.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr) and node.values and all(
            isinstance(v, ast.Constant) and isinstance(v.value, str)
            for v in node.values):
        return "".join(v.value for v in node.values)
    if isinstance(node, ast.Name) and node.id in constants:
        return constants[node.id]
    return None


def _is_bare_name(program: str) -> bool:
    """A name Windows will resolve through System32 before PATH.

    A literal that carries a directory has already been resolved by whoever
    wrote it, and flagging `"C:/Windows/System32/icacls.exe"` would be telling
    the author to fix the one thing they did right. The rule is about lookup,
    not about literals.
    """
    return not (set(program) & set("/\\")) and ":" not in program


def _subprocess_calls(tree: ast.AST, aliases: set[str], imported: set[str]):
    """Yield `(node, first_arg)` for calls that actually spawn a process.

    Two things this must not do. It must not match `messages.run(...)` or
    `prov.run(...)` — neither file even imports `subprocess`, and a guard that
    reports them would be discarded within a week. And it must not miss
    `from subprocess import run`, where the spawner wears no module name.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        f = node.func
        if isinstance(f, ast.Attribute):
            if f.attr not in SPAWNERS:
                continue
            if not (isinstance(f.value, ast.Name) and f.value.id in aliases):
                continue
        elif isinstance(f, ast.Name):
            if f.id not in imported:
                continue
        else:
            continue
        arg = node.args[0]
        first = (arg.elts[0] if isinstance(arg, (ast.List, ast.Tuple)) and arg.elts
                 else arg)
        yield node, first


def bare_names(source: str) -> list[tuple[int, str]]:
    """`(line, program)` for each bare program name handed to subprocess."""
    tree = ast.parse(source)
    aliases = _subprocess_aliases(tree)
    imported = _imported_spawners(tree)
    constants = _module_string_constants(tree)
    out = []
    for node, first in _subprocess_calls(tree, aliases, imported):
        program = _literal_program(first, constants)
        if program is not None and _is_bare_name(program):
            out.append((node.lineno, program))
    return out


def which_fallbacks(source: str) -> list[int]:
    """Lines holding `shutil.which(...) or <anything>`.

    `or <anything>` rather than `or "<literal>"`. The fallback's failure is
    that resolution failed and the expression carried on regardless; what it
    carried on *with* does not change that, and the previous version — which
    flagged only a `Constant` — would have passed `which(name) or name`, the
    form a reader is most likely to write when tidying a literal away.
    """
    out = []
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or)):
            continue
        head = node.values[0]
        if isinstance(head, ast.Call) and isinstance(head.func, ast.Attribute) \
                and head.func.attr == "which":
            out.append(node.lineno)
    return out


def _read(path: pathlib.Path) -> str:
    """utf-8-sig, not utf-8.

    `tests/__init__.py` carries a byte-order mark. Read as plain utf-8 the mark
    survives into the string as U+FEFF and `ast.parse` rejects the file, so it
    was silently exempt from both guards below — one file in 142, excused by
    how the guard opened it rather than by anything in it. The `SyntaxError`
    branch that hid this now reports instead.
    """
    return path.read_text(encoding="utf-8-sig")


def _python_files():
    for root in ROOTS:
        for p in sorted((ROOT / root).rglob("*.py")):
            if "__pycache__" not in p.parts:
                yield p


#: Shapes the guard must judge, with the answer beside each.
#:
#: A case list, because three guards in three commits were each weaker than
#: the thing they matched and each shipped green: the money guard's `"$${"`
#: matched the wrong shape entirely, its replacement treated `<` as able to
#: precede a regex and left 1,489 lines unexamined, and this one flagged only
#: a `Constant` while every program handle in the repo is a module constant.
#: In each case the question "which shapes was it tried against" had no
#: answer. This is that answer, and the negative cases matter as much as the
#: positive ones — a guard nobody has tried to make cry wolf is one that will.
_PROGRAM_CASES = [
    ('import subprocess\nsubprocess.run(["icacls", "x"])',
     True, "a bare string literal"),
    ('import subprocess\nICACLS = "icacls"\nsubprocess.run([ICACLS, "x"])',
     True, "a module-level constant, which is this repo's own idiom"),
    ('import subprocess as sp\nsp.run(["icacls", "x"])',
     True, "an aliased subprocess module"),
    ('import subprocess\nsubprocess.run([f"icacls", "x"])',
     True, "an f-string with nothing interpolated"),
    ('from subprocess import run\nrun(["icacls", "x"])',
     True, "a spawner imported by name"),
    ('import subprocess\nsubprocess.Popen(["icacls"])',
     True, "Popen as well as run"),
    ('import subprocess, shutil\nsubprocess.run([shutil.which("git"), "x"])',
     False, "a resolved path"),
    ('import subprocess\nGIT = "C:/Program Files/Git/git.exe"\n'
     'subprocess.run([GIT, "x"])',
     False, "a literal that already carries a directory"),
    ('import subprocess\ndef f(exe):\n    subprocess.run([exe, "x"])',
     False, "a program passed in"),
    ('class C:\n    def run(self, x): pass\nC().run(["icacls"])',
     False, "a `run` method on something that is not subprocess"),
]


@pytest.mark.parametrize("src,expected,label", _PROGRAM_CASES,
                         ids=[c[2] for c in _PROGRAM_CASES])
def test_the_bare_name_rule_judges_each_shape(src, expected, label):
    assert bool(bare_names(src)) is expected, label


_FALLBACK_CASES = [
    ('import shutil\nGIT = shutil.which("git") or "git"',
     True, "a literal fallback"),
    ('import shutil\ndef f(n):\n    return shutil.which(n) or n',
     True, "a fallback to the name that was looked up"),
    ('import shutil\nGIT = shutil.which("git")',
     False, "no fallback at all"),
    ('import shutil\nGIT = shutil.which("git") or None',
     True, "a fallback to None still carries on past a failed lookup"),
]


@pytest.mark.parametrize("src,expected,label", _FALLBACK_CASES,
                         ids=[c[2] for c in _FALLBACK_CASES])
def test_the_fallback_rule_judges_each_shape(src, expected, label):
    assert bool(which_fallbacks(src)) is expected, label


def test_no_program_is_handed_to_subprocess_by_bare_name():
    """Enumerated from the AST of every file, not from a list of known sites.

    A new caller that reaches for a bare name fails this rather than joining
    the count — which is the difference between this and the three comments it
    replaces. Files that will not parse are named rather than skipped: the
    version that skipped them silently excused one file in 142 and said
    nothing, which is the same defect as a guard that cannot see a shape.
    """
    offenders: list[str] = []
    unreadable: list[str] = []
    for p in _python_files():
        rel = p.relative_to(ROOT).as_posix()
        try:
            source = _read(p)
        except OSError as exc:
            unreadable.append(f"{rel}: {exc}")
            continue
        try:
            hits = bare_names(source)
        except SyntaxError as exc:
            unreadable.append(f"{rel}: {exc}")
            continue
        offenders += [f"{rel}:{line} -> {name!r}" for line, name in hits]

    assert not unreadable, (
        "these files were not examined by this guard at all, so nothing here "
        f"is evidence about them: {unreadable}")
    assert not offenders, (
        "these hand a bare program name to subprocess, so Windows resolves it "
        "through System32 before PATH and may run a different executable than "
        f"the one that was checked: {offenders}")


def test_a_resolved_program_has_no_bare_name_fallback():
    """`shutil.which(x) or …` carries on at the moment resolution failed.

    Enumerated over every file rather than parametrised over the two the audit
    named — the parametrised version passed while `test_axe.py:87` held a
    third, inline in the argument list.
    """
    offenders: list[str] = []
    unreadable: list[str] = []
    for p in _python_files():
        rel = p.relative_to(ROOT).as_posix()
        try:
            lines = which_fallbacks(_read(p))
        except (OSError, SyntaxError) as exc:
            unreadable.append(f"{rel}: {exc}")
            continue
        offenders += [f"{rel}:{line}" for line in lines]

    assert not unreadable, (
        f"these files were not examined by this guard at all: {unreadable}")
    assert not offenders, (
        "`shutil.which(...) or <fallback>` proceeds with an unresolved name at "
        f"exactly the moment resolution failed: {offenders}")
