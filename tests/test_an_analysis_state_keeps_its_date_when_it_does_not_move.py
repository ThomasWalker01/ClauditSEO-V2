"""An analysis row's state keeps its date when a recompute does not move it,
and a move is dated by the run that made it.

Screen audits round 4, Record AC-01 (High): the Record's new "since <date>"
read `finding_states.updated_at`, which the analysis-state recompute set to its
own clock on every row it kept, changed or not, so rows that had not moved in
weeks read "since" the day of the last re-read.
"""
from __future__ import annotations

import inspect
import sqlite3

from clauditseo.persistence import runs


def test_the_upsert_keeps_an_unmoved_date():
    src = inspect.getsource(runs)
    assert src.count("THEN finding_states.updated_at ELSE excluded.updated_at END,") == 2
    assert src.count("_moved_at(conn, changed_in, stamp)") == 2


def test_a_move_is_dated_by_its_run():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE audit_runs (id TEXT, started_at TEXT, finished_at TEXT)")
    conn.execute("INSERT INTO audit_runs VALUES ('r1', '2026-09-18T07:39:00+00:00', '2026-09-18T07:50:00+00:00')")
    assert runs._moved_at(conn, "r1", "now") == "2026-09-18T07:50:00+00:00"
    assert runs._moved_at(conn, None, "now") == "now"
    assert runs._moved_at(conn, "gone", "now") == "now"


def test_the_stored_dates_are_brought_to_the_rule():
    import importlib.util
    from pathlib import Path
    path = (Path(__file__).resolve().parent.parent / "clauditseo" / "db" / "migrations"
            / "0078_state_dates_are_their_runs.py")
    spec = importlib.util.spec_from_file_location("m0078", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE audit_runs (id TEXT, started_at TEXT, finished_at TEXT)")
    conn.execute("CREATE TABLE finding_states (fingerprint TEXT, changed_by_run TEXT, updated_at TEXT)")
    conn.execute("INSERT INTO audit_runs VALUES ('r1', '2026-09-18T07:39:00', '2026-09-18T07:50:00')")
    conn.executemany("INSERT INTO finding_states VALUES (?, ?, ?)", [
        ("a", "r1", "2026-10-16T05:00:00"), ("b", None, "2026-10-01T00:00:00")])
    mod.apply(conn)
    mod.apply(conn)
    assert dict(conn.execute("SELECT fingerprint, updated_at FROM finding_states")) == {
        "a": "2026-09-18T07:50:00", "b": "2026-10-01T00:00:00"}
