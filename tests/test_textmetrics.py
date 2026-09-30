"""Text width without a browser (brief v16i, item 136n Part A).

The one measurement the checks and the snippet preview share. A preview that
measured for itself would agree on the day it was written and on no later one
- the argument `canonical_relation` and `security_headers.cell_state` exist
for.
"""

from __future__ import annotations

import pytest

from clauditseo.textmetrics import (AVERAGE, DESC_FONT, TITLE_FONT, cut_at,
                                    measure, text_px)


def test_the_empty_string_is_zero_and_a_space_is_not():
    assert text_px("") == 0
    assert text_px(" ") > 0


def test_width_scales_with_font_size():
    """The table is in em units, so the same string at 14px is 70% of its
    width at 20px."""
    s = "Bridging finance for small business"
    assert text_px(s, ("Arial", 14)) == pytest.approx(
        text_px(s, ("Arial", 20)) * 14 / 20, abs=1)


def test_a_narrow_string_and_a_wide_one_of_equal_length_differ():
    """The defect the pixel change exists to fix. `Illinois` and `WWWWWWWW`
    are both eight characters, and a character count calls them the same."""
    assert len("Illinois") == len("WWWWWWWW")
    assert text_px("WWWWWWWW") > text_px("Illinois") * 1.7


def test_an_unknown_glyph_is_charged_the_average_and_the_row_is_told():
    """Refusing to measure would be worse than an estimate, but a reader must
    not be left assuming a precision that is not there."""
    got = measure("中文")
    assert got["unmeasured_glyphs"] == 2
    assert got["estimated"] is True
    assert got["px"] == round(AVERAGE * 2 * TITLE_FONT[1] / 1000)
    # And ordinary Latin text is not called an estimate.
    assert measure("Plain English title")["estimated"] is False


def test_common_punctuation_and_accents_are_in_the_table():
    """Real titles carry these, and charging them the average would make
    every accented title an estimate."""
    for s in ("Café", "naïve", "—", "’", "…",
              "£", "€"):
        assert measure(s)["estimated"] is False, s


def test_cut_at_returns_what_falls_off_on_a_word_boundary():
    """**The truncation point is the finding's useful content, not the
    number.** A search result cuts on a word; a mid-word cut would name a
    fragment nobody typed."""
    title = ("Careers at Acme | Join Australia's Fastest-Growing "
             "Business Lender")
    got = cut_at(title, 600, TITLE_FONT)
    assert got["fits"] is False
    assert got["falls_off"], got
    assert title.startswith(got["kept"])
    # Word boundary: what was kept is whole words.
    assert not got["kept"].endswith(" ")
    assert title[len(got["kept"])] in " ’-" or got["falls_off"] in title


def test_a_string_that_fits_falls_off_nothing():
    got = cut_at("Short title", 600, TITLE_FONT)
    assert got == {"fits": True, "kept": "Short title", "falls_off": ""}


def test_the_two_fonts_are_the_ones_the_mockup_names():
    assert TITLE_FONT == ("Arial", 20)
    assert DESC_FONT == ("Arial", 14)


def test_a_real_title_measures_near_its_character_guideline():
    """A sanity anchor against the outside world: Google cuts titles near
    600px, and a title of about sixty characters is what that has always
    meant in practice. If this drifts far, the table is wrong."""
    sixty = "Bridging Finance for Australian Small Business | Acme Australia"
    assert 520 <= text_px(sixty, TITLE_FONT) <= 640, text_px(sixty, TITLE_FONT)


# --- the two units, and what each is for (item 136n Part A) ---------------
#
# Operator ruling through the questions channel, 2026-09-08: truncation is a
# WIDTH fact, adequacy is not. In pixels a title of five short words scores
# worse than one of three wide ones, which is not a defect anyone would act
# on. So over-length measures pixels and minimum length measures characters.


def _title_rows(title: str):
    from clauditseo.modules.onp import GUIDELINES, TITLE_MIN, _length_row

    return _length_row(title, TITLE_FONT, GUIDELINES["title"]["max_px"],
                       GUIDELINES["title"]["mobile_px"], short_chars=TITLE_MIN,
                       legacy_min=TITLE_MIN, legacy_max=65)


def test_the_short_side_measures_characters_and_says_so():
    row = _title_rows("Hi")
    assert row is not None
    assert row["evidence"]["measured"] == "characters", row["evidence"]
    assert "characters" in row["says"], row["says"]
    # And a short-but-adequate title does not fire. This one is 175px, which
    # an invented 200px threshold called a fault; it is a good title for an
    # About page and the character rule leaves it alone.
    assert _title_rows("About | Beacon Events") is None


def test_a_narrow_long_title_no_longer_fires():
    """The false positive the unit change removes. Voltaic has the real ones:
    36 title rows under the character rule, 11 under the pixel rule."""
    narrow = "lilliputian illiterati" + " illicit" * 6      # long, and thin
    assert len(narrow) > 65, len(narrow)
    assert text_px(narrow, TITLE_FONT) < 600, text_px(narrow, TITLE_FONT)
    assert _title_rows(narrow) is None, "a narrow long title still fires"


def test_a_wide_title_inside_the_character_bound_does_fire():
    """The other half, and the reason the change is not just leniency: a
    short-in-characters title can still be cut."""
    wide = "WWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWW"
    assert len(wide) <= 65
    row = _title_rows(wide)
    assert row is not None and row["evidence"]["measured"] == "pixels", row
    assert row["evidence"]["falls_off"], row["evidence"]


def test_both_units_are_reported_for_one_release():
    """`test_pixel_and_legacy_character_counts_are_both_reported_for_one_release`
    from the item's list. The character count no longer decides anything; it
    is on the row so an operator can see WHY a row moved when the unit
    changed, which a bare pixel figure cannot show."""
    row = _title_rows("W" * 60)
    ev = row["evidence"]
    assert ev["px"] > 0 and ev["legacy_chars"] == 60
    assert ev["legacy_bounds"][1] > 0


def test_the_brief_does_not_restate_a_bound_it_interpolates():
    """A brief that prints a constant AND writes it out drifts (item 136n).

    `title-desc.md`'s BOUNDS line read "{{TITLE_MIN}}/{{TITLE_MAX}} default
    30/60 - the same bounds the sweep's length checks use", while `onp.py`
    measured 10/65. `expert.py` interpolates the code constants into that
    same line, so the RENDERED prompt read "10/65 default 30/60, the same
    bounds the sweep uses" and contradicted itself in the text the model was
    handed. The drift was even recorded in a comment at the interpolation
    site rather than closed.

    The fix was to delete the restatement, not to re-sync it: two numerals
    kept in step by hand drift again the next time a constant moves. This
    holds that - no numeral on the BOUNDS line may disagree with the code.
    """
    import re
    from pathlib import Path as _P

    from clauditseo.modules.onp import DESC_MAX, DESC_MIN, TITLE_MAX, TITLE_MIN

    src = (_P(__file__).resolve().parents[1] / "clauditseo" / "prompts"
           / "title-desc.md").read_text(encoding="utf-8")
    line = src[src.index("  BOUNDS:"):]
    line = line[:line.index("  SITE TYPE:")]

    known = {str(TITLE_MIN), str(TITLE_MAX), str(DESC_MIN), str(DESC_MAX),
             "240"}      # the neighbourhood soft ceiling, which is its own rule
    stated = set(re.findall(r"[0-9]+", line))
    assert stated <= known, (
        f"the BOUNDS line states {sorted(stated - known)}, which no constant "
        "backs. Interpolate the value or delete the numeral - a bound written "
        "twice is a bound that will disagree with itself.")
    # And the placeholders are still there, so the line says something.
    for ph in ("{{TITLE_MIN}}", "{{TITLE_MAX}}", "{{DESC_MIN}}", "{{DESC_MAX}}"):
        assert ph in line, ph
