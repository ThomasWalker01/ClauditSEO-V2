"""The Notes screen says what a note does, which is nothing to a finding.

Screen audits round 3, Pages and notes AC-02 (High): the blurb said a note
"decides what a finding means", while no analysis, prompt, report or hold
reads the notes. An operator writing "leave the pricing page alone" expected
the analyses or the held report to respect it.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_the_blurb_does_not_promise_a_reader():
    views = (ROOT / "dashboard" / "src" / "views.tsx").read_text(encoding="utf-8")
    notes = views[views.index('{tab === "notes" && (<>'):]
    notes = notes[notes.index('<p className="muted">'):notes.index("<form")]
    assert "decides what a finding means" not in notes
    assert "do not read it" in notes and "set its finding’s state on the Record" in notes


def test_and_still_nothing_reads_them():
    # If an analysis or report starts reading notes, the blurb above must change.
    for sub in ("analysts", "prompts", "reporting"):
        for f in (ROOT / "clauditseo" / sub).rglob("*"):
            if f.suffix in (".py", ".md") and f.is_file():
                text = f.read_text(encoding="utf-8", errors="ignore")
                assert "FROM notes" not in text and "site_notes" not in text, f
