"""A part-only re-check does not count as an audit since an analysis.

Screen audits round 4, Shop AC-01, Reports IP-01, Images IP-10: Indexability's
analysis read "4 audits since" where two full readings had run since it; the
other two were Links-only re-checks. Every one of the 24 paid rows overstated
how far behind it was.
"""
from __future__ import annotations

import inspect

from clauditseo.persistence import runs


def test_only_full_readings_are_counted_newer():
    order = ["full-3", "links-b", "full-2", "links-a", "full-1"]   # newest first
    got = runs._newer_full_readings(order, {"links-a", "links-b"})
    assert got == {"full-3": 0, "links-b": 1, "full-2": 1, "links-a": 2, "full-1": 2}


def test_both_counters_use_it():
    src = inspect.getsource(runs)
    assert "position = _newer_full_readings(order, part_only)" in src
    assert "return _newer_full_readings(order, part_only_runs(conn, site_id))" in src
