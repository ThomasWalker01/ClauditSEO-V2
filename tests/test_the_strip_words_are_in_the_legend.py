"""The length strip's own words are in its part's legend (item 273, row 10).

The strips count "over · fit · short · missing" and the part's legend
defined none of the four; the unit line under the strips was the only
definition. They are registry entries, in Title & description's legend.
"""

from __future__ import annotations

from pathlib import Path

from clauditseo import glossary

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_registered_and_listed():
    ids = {e["id"]: e for e in glossary.entries()}
    for word in ("over", "fit", "short", "missing"):
        e = ids[f"length-{word}"]
        assert e["word"] == word and "matches" not in e
    src = SRC.read_text(encoding="utf-8")
    assert '"length-over", "length-fit", "length-short", "length-missing"' in src
