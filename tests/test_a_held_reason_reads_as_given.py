"""A held reason reads as given, and every held card says the next step
(item 267, row 14).

"needs no /llms.txt existed at sweep time" was neither a need nor a sentence;
"Entity unnamed" ("sub_services, locations and authors on the site record
are empty") had no link because the link words did not include the record's
own field names; and three llms.txt holds ended at a full stop. And
`entity-unnamed`, silent while the record names no entity, is now said not
assessed on a free-only audit.
"""

from __future__ import annotations

from pathlib import Path

from clauditseo.modules import ais

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_entity_unnamed_is_held_on_an_empty_record():
    assert ais.RECORD_FIELDS["entity-unnamed"] == ("sub_services", "locations", "authors")


def test_the_card_and_table_say_it_as_given():
    src = SRC.read_text(encoding="utf-8")
    assert "sub_services|\\blocations\\b|\\bauthors\\b|sameas" in src
    assert '{fix.needs ? heldSays(fix.needs) : "the brief gave no reason"}' in src
    assert ': "; then re-run the analysis."}' in src
    assert "`not assessable · ${heldSays(" in src
