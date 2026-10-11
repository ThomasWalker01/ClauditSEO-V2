"""The Record says when (screen audits round 3, Record US-01).

No row carried a date - first seen, regressed on, fixed by - though
`updated_at` and `changed_by_run` were shipped for every row. "4 regressed"
on `AIS/edge-blocks-ai-ua` could have been yesterday or two weeks ago.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "pane_record.tsx"


def test_a_row_says_since_when_and_by_which_audit():
    src = SRC.read_text(encoding="utf-8")
    assert "since {day(s.updated_at)}" in src
    assert "` · by the ${by.tier} audit of ${day(by.started_at)}`" in src


def test_a_group_says_its_range():
    src = SRC.read_text(encoding="utf-8")
    assert "since {a === b ? a : `${a} to ${b}`}" in src
    assert src.count('className="muted group-since"') == 2
