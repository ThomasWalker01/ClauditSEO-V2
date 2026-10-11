"""Every scope statement the engine files is a coverage note (items 278, 279).

A module marks a finding that states the audit's own scope - what it could
not measure, a figure recorded for reference, the rendered pass's sample -
with `scope_statement=True` and Info. The coverage-note rule
(`runs.is_coverage_note`) decided by name alone and knew only `-not-assessed`
and `-coverage`. So `referring-domains-reported` and
`domain-authority-reported` put a 2 on Backlinks' badge over no fault, and
`axe-sampled` counted in Accessibility's 54.

This walks the modules' source: each `Finding(...)` carrying
`scope_statement=True` names its check, and that check must be a note.
"""

from __future__ import annotations

import re
from pathlib import Path

from clauditseo.persistence import runs

MODULES = Path(__file__).resolve().parents[1] / "clauditseo" / "modules"
_CHECK = re.compile(r"check_id=\"([a-z0-9-]+)\"")


def _scope_statements() -> list[tuple[str, str]]:
    found = []
    for path in sorted(MODULES.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r"scope_statement=True", text):
            # The Finding call this flag sits in: back to its opening.
            start = text.rfind("Finding(", 0, m.start())
            ids = _CHECK.findall(text[start:m.start() + 400])
            found.append((path.name, ids[0] if ids else ""))
    return found


def test_the_walk_finds_the_known_scope_statements():
    ids = {c for _f, c in _scope_statements()}
    assert {"backlinks-not-assessed", "referring-domains-reported",
            "domain-authority-reported", "axe-sampled", "cwv-not-assessed"} <= ids, ids


def test_every_scope_statement_is_a_coverage_note():
    missed = [(f, c) for f, c in _scope_statements() if c and not runs.is_coverage_note(c, "info")]
    unnamed = [f for f, c in _scope_statements() if not c]
    assert not missed, f"scope statements the coverage-note rule counts as findings: {missed}"
    assert not unnamed, f"a scope statement whose check id this walk cannot read: {unnamed}"


def test_the_sql_rule_says_the_same():
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE f (check_id TEXT, severity TEXT)")
    rows = [(c, "info") for _f, c in _scope_statements()] + [("orphan", "info"), ("axe-sampled", "high")]
    conn.executemany("INSERT INTO f VALUES (?, ?)", rows)
    sql = runs.coverage_note_sql("check_id", "severity")
    got = {r[0] for r in conn.execute(f"SELECT check_id FROM f WHERE {sql}")}
    assert got == {c for c, s in rows if runs.is_coverage_note(c, s)}, got
