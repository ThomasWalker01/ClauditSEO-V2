"""Full-height units are units (item 274, row 11).

The Mobile brief wrote prose and selectors into a template's
`full_height_units`. The reader keeps vh, svh, lvh and dvh, says anything
else in the assumptions, and the cell reads "not stated".
"""

from __future__ import annotations

from types import SimpleNamespace

from clauditseo.analysts import contract


def test_only_units_are_kept():
    parsed = SimpleNamespace(templates=[
        {"template": "/a/*", "full_height_units": ["100vh hero", "DVH"]},
        {"template": "/b/*", "full_height_units": [".x-modal"]},
        {"template": "/c/*", "full_height_units": []}], assumptions=[])
    contract._full_height_units(parsed)
    assert parsed.templates[0]["full_height_units"] == ["dvh"]
    assert parsed.templates[1]["full_height_units"] is None
    assert parsed.templates[2]["full_height_units"] == []
    assert len(parsed.assumptions) == 2, parsed.assumptions


def test_a_zero_is_none():
    parsed = SimpleNamespace(templates=[{"template": "/d/*", "full_height_units": ["0"]}],
                             assumptions=[])
    contract._full_height_units(parsed)
    assert parsed.templates[0]["full_height_units"] == [] and not parsed.assumptions
