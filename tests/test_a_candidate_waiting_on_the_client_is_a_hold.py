"""A candidate that waits on the client is a hold, not a sentence (item 267,
row 6).

An enrichment candidate whose sentence opened "[client to supply]" was kept,
drawn as a sentence to place, and offered to the clipboard. It now waits on
the field it names, in the row's note; a row left with no sentence to place
is a hold, not a row.
"""

from __future__ import annotations

from clauditseo.analysts import ai_surface


def _row(*candidates):
    return {"check": "AIS/entity-enrichment", "page": "/", "status": "FAIL", "severity": "MEDIUM",
            "evidence": "x", "replacement": "x", "note": None, "candidates": list(candidates)}


def _cand(entity, sentence, source="site record: locations"):
    return {"entity": entity, "source": source, "place": "first paragraph", "sentence": sentence}


def test_a_blank_for_the_client_is_held_with_its_field():
    row, reason, notes = ai_surface.police_row(
        "AIS/entity-enrichment",
        _row(_cand("Melbourne", "Birch runs events in Melbourne."),
             _cand("Size", "[client to supply] delegates a year.", "site record: team_size")))
    assert reason is None and [c["entity"] for c in row["candidates"]] == ["Melbourne"], row
    assert any("1 candidate(s) held" in n and "Size (site record: team_size)" in n for n in notes), notes


def test_a_row_with_only_blanks_is_a_hold():
    row, reason, _ = ai_surface.police_row(
        "AIS/entity-enrichment", _row(_cand("Size", "[Client to supply] delegates.")))
    assert row is None and reason == ai_surface.HOLD
