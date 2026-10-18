"""A replacement that says "held" is a note, and the card says what to do
(item 277, rows 5 and 6).

Indexability rows carried "held: needs the intended-noindex list" as their
replacement, so the card offered it under "copy change". The contract moves
such text to the note; the card shows the automatic checks' advice as its
change, and Indexability uses the same copy test as URLs.
"""

from __future__ import annotations

from pathlib import Path

from clauditseo.analysts import contract

ROOT = Path(__file__).resolve().parents[1]


def test_the_contract_moves_it():
    src = Path(contract.__file__).read_text(encoding="utf-8")
    assert 're.match(r"\\s*held\\b", rep, re.I)' in src
    assert 'row.replacement, rep = None, ""' in src


def test_the_card():
    src = (ROOT / "dashboard" / "src" / "part_page.tsx").read_text(encoding="utf-8")
    assert 'body: SiteBriefFixBody, copyLabel: "copy change", copyWhen: isChange },' in src
    body = src.split("function SiteBriefFixBody", 1)[1].split("\n}\n", 1)[0]
    # And where what was written is no change (screen audits round 4,
    # Indexability UX-02).
    assert "(!fix.replacement || !isChange(fix)) && fix.recommendation" in body
