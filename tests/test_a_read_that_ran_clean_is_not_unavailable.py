"""A read whose check ran clean is not "not available" (item 267, row 11).

On twenty22 four of the Register's five "Reads not available" read "blocked:
the owning check ran on this audit and raised no open row, so there is
nothing to read through". A check that ran and raised nothing passed. The
engine now supplies a fourth `needs` form, `ran clean`; the parser accepts it
and reads the old wording as it; the Register says these under "Read: nothing
to carry".
"""

from __future__ import annotations

from pathlib import Path

from clauditseo.analysts import ai_surface as ais

ROOT = Path(__file__).resolve().parents[1]


def test_ran_clean_is_a_fourth_valid_form():
    assert ais.needs_is_valid("ran clean")
    assert ais.NEEDS_RAN_CLEAN == "ran clean"


def test_the_engine_supplies_it_where_the_owning_check_ran():
    import inspect
    src = inspect.getsource(ais.absent_needs)
    assert "return NEEDS_RAN_CLEAN" in src
    # An analysis that raised no row is not a pass: it stays blocked.
    assert "the analysis that owns it has run on this site" in src


def test_a_stored_analysis_in_the_old_words_reads_as_ran_clean():
    old = ("blocked: the owning check ran on this audit and raised no open row, so "
           "there is nothing to read through")
    assert ais._LEGACY_RAN_CLEAN.match(old)
    assert not ais._LEGACY_RAN_CLEAN.match("blocked: no resolver")


def test_the_prompt_and_the_register_say_it():
    md = (ROOT / "clauditseo" / "prompts" / "ai-surface.md").read_text(encoding="utf-8")
    assert "`ran clean`, where\n  the owning automatic check ran on this audit" in md
    tsx = (ROOT / "dashboard" / "src" / "ai_surface.tsx").read_text(encoding="utf-8")
    assert "<h4>Read: nothing to carry</h4>" in tsx
    assert '(brief.absent_reads ?? []).filter((a) => a.needs !== "ran clean")' in tsx
