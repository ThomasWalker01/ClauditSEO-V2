"""Speed leads with its worst row and knows its CrUX key (screen audits
round 4, Speed UX-03, US-02).

The High `lcp-poor` row was the last of the free table, under an Info "not
measured" row; and the field-data note asked for a CrUX key on a site whose
key was set and had answered "CrUX holds no record for this URL".
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from clauditseo import secrets
from clauditseo.persistence import runs

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_the_checks_table_is_worst_first():
    p = SRC.read_text(encoding="utf-8")
    assert ".sort((a, b) => rankOf(a.r) - rankOf(b.r) || a.i - b.i)" in p


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE sites (id TEXT, field_data_source TEXT)")
    conn.execute("INSERT INTO sites VALUES ('s', NULL)")
    return conn


def test_a_set_key_is_not_asked_for(monkeypatch):
    monkeypatch.setattr(secrets, "get", lambda name: "k" if name == "CLAUDITSEO_CRUX_KEY" else "")
    got = runs._speed_field_data(_conn(), "s")
    assert got["action"] is None and "The CrUX key is set" in got["note"]
    monkeypatch.setattr(secrets, "get", lambda name: "")
    got = runs._speed_field_data(_conn(), "s")
    assert got["action"]["href"] == "#/admin?tab=keys"


def test_a_held_row_links_the_record_field_it_waits_on():
    """Indexability UX-01, AI surface UX-03, Structured data UX-01."""
    p = SRC.read_text(encoding="utf-8")
    assert "{r.held && heldLink(r.state) && (" in p
