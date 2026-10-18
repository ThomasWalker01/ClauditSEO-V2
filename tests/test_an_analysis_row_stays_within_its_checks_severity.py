"""A legacy analysis row is never more severe than the registry's severity
for the same check.

Screen audits round 3, Local AC-01 (High): `EXP:local-signals/
localbusiness-schema-missing` stood open at Critical, above the sweep row of
the same check, ranking Local 4 of 81 - where the registry's default for the
check is Medium. A legacy brief answers the findings index with a bare code
and the model's own severity, and the store took it as given.
"""
from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

from clauditseo.checks import capped_severity, registered_ceiling

MIGRATION = (Path(__file__).resolve().parent.parent / "clauditseo" / "db" / "migrations"
             / "0077_analysis_severity_within_the_registry.py")


def test_a_code_is_capped_at_its_registered_severity():
    assert registered_ceiling("localbusiness-schema-missing") == "medium"
    assert capped_severity("localbusiness-schema-missing", "critical") == "medium"
    assert capped_severity("localbusiness-schema-missing", "low") == "low"
    # A code no registered check carries keeps the model's word.
    assert capped_severity("gate-six-made-up-code", "critical") == "critical"


def test_the_stored_rows_are_brought_to_the_rule():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE findings (dimension TEXT, source TEXT, check_id TEXT, severity TEXT)")
    conn.executemany("INSERT INTO findings VALUES (?, ?, ?, ?)", [
        ("EXP:local-signals", "model-judgement", "localbusiness-schema-missing", "critical"),
        ("LOC", "deterministic", "localbusiness-schema-missing", "critical"),
        ("EXP:local-signals", "model-judgement", "gate-six-made-up-code", "critical"),
    ])
    spec = importlib.util.spec_from_file_location("m0077", MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.apply(conn)
    mod.apply(conn)  # idempotent
    assert [r[0] for r in conn.execute("SELECT severity FROM findings ORDER BY rowid")] \
        == ["medium", "critical", "critical"]


def test_the_store_caps_as_it_writes():
    import inspect
    from clauditseo.persistence import runs
    assert '"severity": capped_severity(f["code"], f["severity"]),' in inspect.getsource(runs)
