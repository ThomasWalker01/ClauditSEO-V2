"""The snippet card and the length strips (item 136n Parts B and C).

**The picture reads the server's measurement.** The card and the strips draw
`onp.snippet`'s output - the same function the length checks call. This file
tests the payload shape and its agreement with the checks; the rendered card
is exercised by the anatomy sweep, and the two guards there (`.snip`, `.strip`
in the class register) hold the drawing.
"""

from __future__ import annotations

import re
from pathlib import Path

from clauditseo.modules.onp import GUIDELINES, snippet

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"
STRIPS = (SRC / "title_snippet.tsx").read_text(encoding="utf-8")
CSS = (SRC / "styles.css").read_text(encoding="utf-8")


def test_the_check_and_the_preview_measure_the_same_text_the_same_way():
    """One function, two readers. A title the check calls over is a title the
    card draws with a cut, because both call `snippet`/`_length_row` over the
    same `textmetrics` and the same `GUIDELINES`."""
    from clauditseo.modules.onp import TITLE_FONT, _length_row

    title = ("Careers at Acme | Join Australia's Fastest-Growing "
             "Business Lender")
    check = _length_row(title, TITLE_FONT, GUIDELINES["title"]["max_px"],
                        GUIDELINES["title"]["mobile_px"], short_chars=10,
                        legacy_min=10, legacy_max=65)
    card = snippet(title, None)["title"]
    assert check is not None and card["state"] == "bad"
    assert check["evidence"]["px"] == card["px"]
    assert check["evidence"]["falls_off"] == card["falls_off"]


def test_a_title_over_the_desktop_width_names_the_words_that_fall_off():
    card = snippet("Careers at Acme | Join Australia's Fastest-Growing "
                   "Business Lender", None)["title"]
    assert card["state"] == "bad"
    assert card["falls_off"] == "Lender", card["falls_off"]


def test_one_measurement_two_cut_lines():
    """The toggle is client-side: a string's pixel width does not change
    between desktop and mobile, only the width the result gives it, so the
    payload carries both verdicts and no press re-fetches."""
    card = snippet("Careers at Acme | Join Australia's Fastest-Growing "
                   "Business Lender", None)["title"]
    assert card["state"] == "bad" and card["mobile_state"] == "bad"
    # More falls off on the narrower mobile cut.
    assert len(card["mobile_falls_off"]) > len(card["falls_off"])
    assert card["limit_px"] == 600 and card["mobile_limit_px"] == 410


def test_thresholds_come_from_the_registry():
    """No literal in the card or the strip; the widths are `GUIDELINES`."""
    assert GUIDELINES["title"]["max_px"] == 600
    assert GUIDELINES["title"]["mobile_px"] == 410
    assert GUIDELINES["meta_description"]["max_px"] == 920


def test_a_missing_title_is_a_mute_bar_not_a_zero():
    card = snippet(None, None)
    assert card["title"]["state"] == "mute" and card["title"]["px"] == 0
    assert card["title"]["text"] is None


def test_a_short_description_warns_and_says_google_will_write_its_own():
    card = snippet("A fine title of a reasonable width here", "Too short.")
    d = card["description"]
    assert d["state"] == "warn", d
    assert d["chars"] < d["min_chars"]


def test_the_strips_payload_is_in_crawl_order_and_agrees_with_the_card():
    """Part C. One bar per page, in crawl order, states from `snippet` - so a
    bar's colour and the card it opens onto cannot disagree."""
    import json
    import tempfile
    from pathlib import Path as _P

    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.persistence import repo, runs

    with tempfile.TemporaryDirectory() as d:
        conn = connect(_P(d) / "c.db")
        migrate(conn)
        op = repo.ensure_default_operator(conn)
        site = repo.create_site(conn, repo.create_client(conn, op, "C"), "x.test")
        run_id = runs.create_run(conn, site, ["ONP"], "T2")
        pages = [
            {"url": "https://x.test/", "status": 200,
             "title": "Home | A perfectly reasonable homepage title here",
             "meta_description": "y" * 130},
            {"url": "https://x.test/wide", "status": 200,
             "title": "W" * 60, "meta_description": None},
            {"url": "https://x.test/short", "status": 200,
             "title": "Hi", "meta_description": "z"},
        ]
        conn.execute("UPDATE audit_runs SET crawl_evidence=? WHERE id=?",
                     (json.dumps({"pages": pages}), run_id))
        conn.commit()

        pl = runs.title_lengths_payload(conn, run_id)
        assert pl["pages"] == 3
        # Crawl order preserved.
        assert [b["path"] for b in pl["bars"]] == ["/", "/wide", "/short"]
        # The wide title is `bad`, and it is the same verdict `snippet` gives.
        wide = pl["bars"][1]["title"]
        assert wide["state"] == snippet("W" * 60, None)["title"]["state"]
        assert wide["state"] == "bad"
        # The missing description is `mute`, not a zero-state.
        assert pl["bars"][1]["description"]["state"] == "mute"
        # Item 152, decision A: the title strip cuts at the mobile width the
        # check fires at; the description stays on desktop.
        assert pl["title_cut_px"] == 410 and pl["title_cut_viewport"] == "mobile"
        assert pl["desc_cut_px"] == 920 and pl["desc_cut_viewport"] == "desktop"
        conn.close()


def test_pixel_and_legacy_character_counts_are_both_reported_for_one_release():
    """From the item's list. The card carries the character count beside the
    pixel one so an operator can see why a verdict moved when the unit
    changed."""
    card = snippet("W" * 60, None)["title"]
    assert card["px"] > 0 and card["chars"] == 60
    assert card["min_chars"] == GUIDELINES["title"]["min"]


# --- item 146 commit 1: the two defects in Part C's strips ------------------

def test_an_absent_value_is_a_mute_bar_not_a_gap():
    """136n's own Degradation section says "No title on a page: mute bar", but
    the shipped strip drew a 1px sliver that reads as a quiet stretch. Every
    bar — mute included — is rendered (the map does not drop the absent ones),
    and a mute state carries the `strip-bar-mute` class that gives it a fixed,
    visible height rather than px 0. Absence rendering as health is the failure
    this repo guards against everywhere else."""
    # The bars are mapped unconditionally: no filter removes the mute ones
    # before the render, so an absent value is a bar and not a gap.
    assert re.search(r"bars\.map\(", STRIPS)
    assert not re.search(r"\.filter\([^)]*state[^)]*mute", STRIPS), (
        "a mute bar must not be filtered out of the strip")
    # A mute state is drawn with the fixed-height mute class.
    assert 'state === "mute"' in STRIPS
    assert "strip-bar-mute" in STRIPS
    assert re.search(r"\.strip-bar-mute\s*\{[^}]*height", CSS), (
        "the mute bar needs a fixed height, not the px-0 sliver")


def test_both_strips_label_zero_the_same_way():
    """Title read `14 over`; Description read `41 over · 8 short` — one omitted
    a zero the other showed, and a reader who sees an absence learns to
    distrust it. Both strips read `N over · N short · N missing`, zeros
    included, and the unit line beneath says which unit each side is in."""
    assert "{over} over" in STRIPS
    assert "{short} short" in STRIPS
    assert "{missing} missing" in STRIPS
    # None of the three counts hides behind a `> 0 &&` guard any more.
    foot = STRIPS[STRIPS.index("strip-foot"):STRIPS.index("strip-foot") + 400]
    assert "over > 0" not in foot and "short > 0" not in foot, (
        "a count that hides its zero is the defect this fixes")
    assert ("over: pixel width · short: characters · missing: no value on the page"
            in STRIPS), "the unit line names which unit each side is in"


def test_a_mute_bar_is_distinguishable_from_a_short_bar():
    """WCAG 1.4.1: not by fill alone. A short bar is a solid warn fill; a mute
    bar is hatched with a dashed edge, so the two are told apart by pattern and
    shape, not only by colour — which also survives a reader who cannot see the
    difference between grey and amber."""
    mute = re.search(r"\.strip-bar\.tone-mute\s*\{([^}]*)\}", CSS)
    warn = re.search(r"\.strip-bar\.tone-warn\s*\{([^}]*)\}", CSS)
    assert mute and warn, "both bar tones must be styled"
    mute_body = mute.group(1)
    # More than a fill: a repeating gradient (a pattern) and a dashed border.
    assert "repeating-linear-gradient" in mute_body, (
        "the mute bar is told apart by a hatch pattern, not colour alone")
    assert "dashed" in mute_body
    # The short bar is a plain solid fill, so the difference is structural.
    assert "repeating-linear-gradient" not in warn.group(1)


# --- item 146 commit 2: the reserved detail panel ---------------------------

def test_hover_and_focus_render_the_same_panel():
    """A bar is a button; pointing at it and tabbing to it must show the same
    card, or the keyboard reader gets less than the mouse. Both `onMouseEnter`
    and `onFocus` call the one `onPreview`, so there is one render path."""
    assert "onMouseEnter={() => onPreview(b)}" in STRIPS
    assert "onFocus={() => onPreview(b)}" in STRIPS


def test_a_pinned_card_survives_the_pointer_leaving():
    """Click pins so the card can be read and copied with the pointer
    elsewhere. Preview early-returns while a bar is pinned, and nothing on the
    bar clears the pin when the pointer leaves — no `onMouseLeave`/`onBlur`."""
    assert re.search(r"if \(pinned\) return;", STRIPS), (
        "a pinned card must not follow the pointer")
    assert "onMouseLeave" not in STRIPS and "onBlur" not in STRIPS, (
        "leaving the bar must not drop the pinned card")


def test_a_second_click_on_a_pinned_bar_opens_page_scope():
    """First click pins; a second click on the already-pinned bar opens page
    scope (`onPick`). So the strip both previews and navigates without a
    separate control."""
    assert re.search(r"if \(pinned === bar\.url\) \{ onPick\(bar\.url\); return;",
                     STRIPS), "a second click on the pinned bar opens page scope"


def test_the_panel_height_is_the_same_for_a_one_line_and_a_two_line_description():
    """A panel between two strips that changes height moves the strip the
    reader is about to look at. The panel reserves its tallest state with a
    fixed height and `overflow: hidden`; the description clamps to two lines
    inside it, so one line and two leave the strip below in the same place."""
    panel = re.search(r"\.strip-panel\s*\{([^}]*)\}", CSS)
    assert panel, "the panel must be styled"
    body = panel.group(1)
    assert re.search(r"height:\s*\d", body), "the panel height is fixed, not content-driven"
    assert "overflow: hidden" in body or "overflow:hidden" in body
    # The description clamps to two lines (the reused Part B card), so a short
    # one does not shrink the reserved box.
    desc = re.search(r"\.snip-desc\s*\{([^}]*)\}", CSS)
    assert desc and "line-clamp" in desc.group(1)


def test_a_long_path_does_not_change_the_panel_height():
    """The path truncates with an ellipsis on its own fixed-height row, and the
    facts row reserves two lines, so a long path and a falls-off clause wrap
    inside the reservation rather than growing the panel."""
    path = re.search(r"\.strip-panel-path\s*\{([^}]*)\}", CSS)
    facts = re.search(r"\.strip-facts\s*\{([^}]*)\}", CSS)
    assert path and facts
    assert "text-overflow: ellipsis" in path.group(1) and "nowrap" in path.group(1)
    assert re.search(r"height:\s*[\d.]", path.group(1))
    assert re.search(r"height:\s*[\d.]", facts.group(1)) and "overflow: hidden" in facts.group(1)


def test_the_fall_off_words_are_present_as_text():
    """A cut cannot be copied into a ticket or read by a screen reader, so the
    words that fall off appear as text in the facts row, not only as the visual
    cut on the card."""
    assert "falls off:" in STRIPS
    assert "tv.falls_off" in STRIPS, "the fall-off words are rendered as text"


# --- item 146z: the strip foot names its population -------------------------

PART_PAGE = (SRC / "part_page.tsx").read_text(encoding="utf-8")
ANATOMY = (SRC / "anatomy.tsx").read_text(encoding="utf-8")


def test_the_strip_foot_names_both_the_drawn_and_the_recorded_page_count():
    """The check table reports the record; the strip plots the audit's crawl
    set, and on a partial crawl they are different numbers. A foot saying `45`
    beside a table saying `68` reads as a rounding nobody checks, so the foot
    names both.

    **Item 155 changed how, and the reason is worth keeping.** The foot shipped
    `45 of 68 pages` with M as the record count; it now sits on a page whose
    header reads `45 of 53 on the site`, and two ratios over the same numerator
    must not read as a contradiction. So the foot goes through the one count
    renderer and names its denominator — `45 of 68 in the record`. What this
    clause still holds is the part 155 left alone: the numerator is the drawn
    count, the denominator is the record's, and `total` is threaded in rather
    than derived in the strip.
    """
    assert "makeCount(bars.length, \"record\"," in STRIPS, (
        "the foot's numerator is no longer the drawn bar count")
    assert "pops?.record.size ?? total ?? bars.length" in STRIPS, (
        "the foot's denominator is no longer the record's")
    assert re.search(r"function Strip\(\{[^}]*\btotal\b", STRIPS)
    assert "total: number | null" in STRIPS


def test_the_strip_foot_states_its_population_whenever_there_is_one_to_state():
    """146z asked for `12 of 12` on Birch with no exceptions, on the argument
    that a figure omitted in one place and present in another teaches a reader
    to distrust it. **Item 155 answers that argument rather than ignoring it**:
    the redundancy 146 feared appears only where it is genuinely redundant, and
    a full-coverage run is exactly where `12 of 12` disambiguates nothing.

    So the rule moved from "always state M" to "state M unless the population
    IS the page's scope", and it moved into one component rather than this
    one's own conditional — which is what this clause now holds. The foot must
    not grow a guard of its own: a second rule about when to show the
    denominator, living here, is how the two ratios drifted apart in the first
    place.
    """
    foot = STRIPS[STRIPS.index("strip-foot"):STRIPS.index("strip-foot") + 600]
    assert "<Counted" in foot, (
        "the foot no longer renders through the one count component, so it has "
        "its own opinion about when to state a denominator")
    assert "!== bars.length" not in foot and "!= bars.length" not in foot, (
        "the foot has grown a conditional of its own about the denominator")
    assert 'population="record"' not in foot, (
        "the population is hand-written in the foot rather than carried by the "
        "count")


def test_the_strip_total_is_the_record_not_the_part_s_own_page_count():
    """Two totals are in scope at the call site and they are one keystroke
    apart: `PartPage`'s `pages` prop is the record count the header shows as `IN
    THE RECORD`; `Category.pages` sits among that type's own finding counts and
    is a different quantity. The strip must be handed the record count."""
    assert "<LengthStrips lengths={part.title_lengths} total={pages}" in PART_PAGE
    assert "total={part.pages}" not in PART_PAGE, (
        "the strip total must be PartPage's `pages` (the record), not Category.pages")


def test_the_strip_population_wording_matches_the_header():
    """One wording per population, wherever it is named, so a reader is never
    asked to match two phrasings for one thing.

    **The header this clause pinned no longer exists.** It said `68 IN THE
    RECORD · 49 PUBLISHED · 45 IN THIS AUDIT'S CRAWL`, and the foot reused its
    `this audit's crawl` verbatim; 150 step BJ replaced those three figures
    with site size, coverage and assessed, so the phrase the two shared is
    gone from the bar. What survives is the rule, and it is stronger now: the
    population's wording is the SERVER'S (`runs.POPULATION_BASIS`), so the
    foot, the bar and every count on the part page read one source rather than
    three components agreeing by hand.
    """
    POP = (SRC / "population.tsx").read_text(encoding="utf-8")
    # The foot still names its own denominator, and still in the crawl's words.
    assert "this audit's crawl" in STRIPS
    # And the population it divides by is worded once, by the server, for
    # every surface that names it.
    assert '"in the record"' in POP, (
        "the record's wording is no longer stated in one place")
    # The bar still names it. Since brief v23 step BL the record is an entry
    # in the "What has been measured" lane, and BJ's other numbers are the
    # state sentence, so this reads the lanes component the screen mounts.
    LANES = (SRC / "client_lanes.tsx").read_text(encoding="utf-8")
    assert "in the record" in LANES, (
        "the bar no longer names the record at all - it is bookkeeping since "
        "150 BJ, but it is still on the screen")
    assert "<ClientLanes" in ANATOMY and "<StateSentence" in ANATOMY, (
        "the bar does not mount BJ's figures")
