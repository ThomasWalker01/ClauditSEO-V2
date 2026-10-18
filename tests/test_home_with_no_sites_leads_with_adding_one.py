"""With no sites, Home leads with adding one (item 260 row 2, screen audits
round 3 Home UX-01).

"Set a cadence" was primary with no sites at all and opened an empty grid,
while the headline said "Add a client, then a site" and the control that did
it was third, secondary and closed.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "home.tsx"


def test_no_sites_makes_adding_primary_and_open():
    src = SRC.read_text(encoding="utf-8")
    assert "const noSites = sites.length === 0;" in src
    assert "const addOpen = adding || noSites;" in src
    assert '<PrimaryButton className="bl-primary home-add-open"' in src
    assert "{addOpen && (" in src


def test_the_cadence_is_not_offered_with_nothing_to_schedule():
    src = SRC.read_text(encoding="utf-8")
    assert "{!noSites && (\n              <LinkButton primary={!allScheduled}" in src.replace("\r\n", "\n")
