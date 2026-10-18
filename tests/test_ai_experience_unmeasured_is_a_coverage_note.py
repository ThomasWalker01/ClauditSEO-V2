"""`ai-experience-unmeasured` is a coverage note, not a fix (item 267, row 8).

Its own advice is "Nothing to change: this row states a limit of the audit",
and it was drawn under Fixes and counted in the part's free checks and the
strip - the rule item 180 set for `cwv-not-assessed`, missed for this row.
"""

from __future__ import annotations

from pathlib import Path

from clauditseo.persistence import runs

API = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "api.ts"


def test_the_record_and_the_screen_read_it_as_a_note():
    assert runs.is_coverage_note("ai-experience-unmeasured", "info")
    assert not runs.is_coverage_note("ai-experience-unmeasured", "medium")
    assert 's.check_id === "ai-experience-unmeasured"' in API.read_text(encoding="utf-8")
