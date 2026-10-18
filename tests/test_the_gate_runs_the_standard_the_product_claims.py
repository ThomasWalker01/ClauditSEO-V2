"""Every axe run in this repo asks for the standard the product publishes.

CQ-188. `.claude/loop/PROFILE.md` says outright that *"WCAG 2.2 AA is enforced
on the product's own dashboard by that gate"*, and `clauditseo/axe.py` publishes
a five-item ruleset list to every client it scans. The two sweeps that are that
gate — `tests/test_a11y_rendered.py` and `tests/test_a11y_before_the_app.py` —
asked axe for four tags, so the AA criteria that distinguish 2.2 from 2.1 were
excluded by configuration from the one gate cited for the claim, while the
product held its clients to them. Settled as 2.2 AA by the operator (Q-4).

**What the tag is actually worth, measured rather than assumed.** Asked at the
running product, `axe.getRules(['wcag22aa'])` on the vendored axe-core 4.13.0
returns exactly one rule — `target-size`, WCAG 2.5.8. `wcag2411` (2.4.11 Focus
Not Obscured) and `wcag257` (2.5.7 Dragging Movements) select nothing: this axe
build has no automated rule for either, and `wcag22a` is empty too. So closing
CQ-188 buys one of the three criteria report 086 named, not three. That is the
whole of what is machine-checkable here, and the other two remain a question
only a person can answer — which is what `axe.coverage_note` already tells a
client, and is now equally true of the gate this project points at itself.

**Why a guard and not just the token.** The defect was a list written out four
times in three files with nothing relating them, so the drift was invisible and
silent: nothing failed when the sweeps stopped matching the claim, and nothing
would fail when they drifted again. This relates them. The expected set is read
from the coverage note the product *publishes to a client* rather than from a
literal here — a list restated in the guard is a fifth copy, and a fifth copy is
the defect, not the fix.

**This file is excluded from its own enumeration, by identity rather than by
name**, for the reason `tests/test_ci_browser_gate.py:82` records against the
same trap: a check that scans source can scan its own, and the regex below
contains the text it searches for. Excluded by resolved path so a rename cannot
resurrect it.
"""

from __future__ import annotations

import pathlib
import re

from clauditseo import axe

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: An `axe.run` tag filter, as every call site in this tree spells it: the list
#: is on its own line under `type: 'tag'`, so `\s` must cross newlines. Anchored
#: on `runOnly` rather than on `values` alone, which appears in axe's own
#: vendored source and in unrelated option blocks.
_RUN_ONLY = re.compile(r"runOnly:\s*\{\s*type:\s*'tag',\s*values:\s*\[([^\]]*)\]")


def _tag_lists() -> dict[str, list[str]]:
    """Every axe tag filter in this repo's own source, by repo-relative path.

    Vendored axe-core is excluded: it is upstream's code, it is minified, and
    what it contains is not this project's claim about anything.
    """
    out: dict[str, list[str]] = {}
    here = pathlib.Path(__file__).resolve()
    for path in sorted([*(ROOT / "tests").glob("test_*.py"),
                        *(ROOT / "clauditseo").rglob("*.py")]):
        if path.resolve() == here or "vendor" in path.parts:
            continue
        for match in _RUN_ONLY.finditer(path.read_text(encoding="utf-8")):
            out[path.relative_to(ROOT).as_posix()] = re.findall(r"'([^']+)'",
                                                                match.group(1))
    return out


def _published() -> list[str]:
    """The rulesets the product tells a client its scan covered."""
    return list(axe.coverage_note(0, None).evidence["rulesets"])


def test_the_population_is_not_empty():
    """Guards the guard. A regex that stopped matching would make every
    assertion below pass against a tree with no axe run in it at all, which is
    indistinguishable from a clean one — DISCIPLINE rule 5."""
    found = _tag_lists()
    assert len(found) >= 3, (
        f"only {len(found)} axe tag filter(s) were found ({sorted(found)}); the "
        "pattern has stopped matching and the assertions below no longer test "
        "anything"
    )


def test_the_published_ruleset_carries_the_claimed_conformance_level():
    """The claim itself, so the equality below cannot be satisfied by dropping
    2.2 everywhere. `wcag22aa` is what makes the profile's sentence true."""
    published = _published()
    assert "wcag22aa" in published, (
        f"the scan publishes {published} as its rulesets, which does not "
        "include wcag22aa — but PROFILE.md states WCAG 2.2 AA is enforced. "
        "Either the tag returns or the claim goes (Q-4: the operator settled "
        "this as 2.2 AA)"
    )


def test_every_axe_run_asks_for_the_published_ruleset():
    """CQ-188's own direction: the gate cited for the claim runs the claim."""
    published = _published()
    wrong = {path: tags for path, tags in _tag_lists().items()
             if sorted(tags) != sorted(published)}
    assert not wrong, (
        "these axe calls run a different ruleset from the one the product "
        f"publishes ({published}): "
        + "; ".join(f"{path} runs {tags}" for path, tags in sorted(wrong.items()))
    )
