"""Item 180, commit 2: "nothing to fix" is one of three states, in words, from
one registered source (UI audit pattern D: 05-3, 06-3, 07-3, 05-4, 07-4, 01-2,
02-14).

    clean                 a check ran on this scope and found nothing
    not measured          no check ran on this scope, and the line says why
    cannot have findings  the check does not fire on this scope by construction

The auditors found all three drawn as the first: "Nothing to fix on this scope"
under "8 checks not assessed - LNK did not run", "Nothing open here" on
Backlinks with no key, "partial" on a Security layer measured 0 of 9, and 13
checks passing on a page with no JSON-LD.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "dashboard" / "src"

#: The collapsed wordings, each of which stood for all three states.
RETIRED = ("Nothing to fix on this scope", "Nothing open here.")


def _code_lines(text: str) -> list[str]:
    """A file's lines with the comments taken out.

    Block comments are removed WHOLE before splitting. Dropping only the lines
    that start with a marker leaves every continuation line of a `{/* … */}`
    block reading as code, so a comment explaining a registered word was
    reported as an inline copy of it — `part_page.tsx`, audit F3, whose second
    line says the check table "reads `not measured`". The same regex the other
    source guards in this suite use (`test_money_and_deletes_ask_first`,
    `test_depth_is_judgement_and_scope_is_breadth`), which is the shape that
    does not have this hole.
    """
    stripped = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return [ln for ln in stripped.splitlines()
            if not ln.strip().startswith(("*", "/*", "//", "{/*"))]


def test_the_three_states_are_registered_once():
    entries = json.loads((ROOT / "clauditseo" / "glossary.json").read_text(encoding="utf-8"))["entries"]
    states = [e for e in entries if e.get("vocabulary") == "measurement states"]
    assert {e["id"] for e in states} == {"measure-clean", "measure-not-measured", "measure-cannot"}
    assert {e["word"] for e in states} == {"clean", "not measured", "cannot have findings"}


def test_no_screen_draws_the_collapsed_wording():
    hits = []
    for p in SRC.glob("*.tsx"):
        for ln in _code_lines(p.read_text(encoding="utf-8")):
            if any(r in ln for r in RETIRED):
                hits.append(f"{p.name}: {ln.strip()}")
    assert not hits, "a scope with nothing open drawn as clean without saying which:\n" + "\n".join(hits)


def test_the_words_are_read_from_the_registry_not_copied():
    measure = (SRC / "measure.tsx").read_text(encoding="utf-8")
    for id_ in ("measure-clean", "measure-not-measured", "measure-cannot"):
        assert f'entry("{id_}")' in measure
    copies = []
    for p in SRC.glob("*.tsx"):
        if p.name == "measure.tsx":
            continue
        for ln in _code_lines(p.read_text(encoding="utf-8")):
            if re.search(r'["`](not measured|cannot have findings)[:"` ]', ln):
                copies.append(f"{p.name}: {ln.strip()}")
    assert not copies, "an inline copy of a measurement word:\n" + "\n".join(copies)


def test_the_rule_picks_the_state_from_what_ran():
    """`measureOf`'s rule, read as the source states it: a gate that says the
    part does not apply is `cannot`; no checks, or none measured, is `not
    measured`; any measured check with nothing open is `clean`."""
    src = (SRC / "measure.tsx").read_text(encoding="utf-8")
    body = src[src.index("export function measureOf"):src.index("export function MeasureLine")]
    order = [body.index('gate?.state === "na"'), body.index("if (!checks.length)"),
             body.index("if (!measured.length)"), body.index('state: "clean"')]
    assert order == sorted(order), "the three states are decided out of order"


def test_a_security_layer_measured_at_nothing_is_not_partial():
    part = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    layers = part[part.index("function SecurityLayers"):]
    assert "missing.length === d.checks.length" in layers[:4000]


def test_a_first_audit_is_not_since_a_last_one():
    lanes = (SRC / "client_lanes.tsx").read_text(encoding="utf-8")
    assert '"First audit"' in lanes and "runState?.audits" in lanes
