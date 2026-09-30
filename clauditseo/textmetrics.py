"""How wide a string renders, without a browser (brief v16i, item 136n).

**One function, read by the checks and by the picture.** `title-length` and
`meta-desc-length` measure in pixels from here, and the Title & description
part page draws its snippet card and its rulers from the same numbers. A
preview that measured for itself would agree on the day it was written and on
no later one - the same argument `canonical_relation` and
`security_headers.cell_state` exist for.

**Why a table and not a headless browser.** The item is explicit: no browser.
A width table is deterministic, costs nothing, and is the same answer on every
machine - a browser measurement would move with the OS font stack, and a
finding that changed because the server was rebuilt is not a finding about the
site.

The widths are Helvetica's AFM advance widths in units of 1/1000 em. **Arial
is metrically compatible with Helvetica** - that is the whole reason Arial
exists - so one table serves the Arial the mockup specifies and any Helvetica
fallback beside it.

What this is not: kerning, ligatures, hinting or subpixel positioning. A real
renderer applies all four and lands within a percent or two of this on Latin
text. The thresholds are round numbers chosen against a rendered preview, so a
percent is well inside the decision, and `text_px` is the same function on
both sides of it.
"""

from __future__ import annotations

#: Advance widths, 1/1000 em, from the Helvetica AFM. ASCII 32-126.
_ASCII = (
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333,
    278, 278, 556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278,
    584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278,
    500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944,
    667, 667, 611, 278, 278, 278, 469, 556, 333, 556, 556, 500, 556, 556,
    278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500,
    278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584,
)

#: Beyond ASCII: the punctuation real titles carry, and accented Latin.
#: Anything not here falls back to `AVERAGE` and the row says so.
_EXTRA: dict[str, int] = {
    " ": 278, "£": 556, "€": 556, "©": 737,
    "®": 737, "°": 400, "·": 278, "•": 350,
    "–": 556, "—": 1000, "‘": 222, "’": 222,
    "“": 333, "”": 333, "…": 1000, "«": 556,
    "»": 556, "×": 584, "™": 1000, "±": 584,
}
for _c in "àáâãäå":
    _EXTRA[_c] = 556
for _c in "èéêë":
    _EXTRA[_c] = 556
for _c in "ìíîï":
    _EXTRA[_c] = 278
for _c in "òóôõö":
    _EXTRA[_c] = 556
for _c in "ùúûü":
    _EXTRA[_c] = 556
for _c in "ÀÁÂÃÄÅ":
    _EXTRA[_c] = 667
for _c in "ÈÉÊË":
    _EXTRA[_c] = 667
for _c in "ÒÓÔÕÖ":
    _EXTRA[_c] = 778
_EXTRA["ñ"] = 556
_EXTRA["Ñ"] = 722
_EXTRA["ç"] = 500
_EXTRA["Ç"] = 722
_EXTRA["ß"] = 556

#: What an unknown glyph is charged. The mean of the lower-case letters,
#: which is what most unmeasured text turns out to be.
AVERAGE = 500

#: The two the product measures, from the mockup: the title at 20px and the
#: description at 14px, both Arial.
TITLE_FONT = ("Arial", 20)
DESC_FONT = ("Arial", 14)


#: Every character the tables know, flattened into one lookup, so `measure`
#: costs a dict read per glyph: the title strip measures every page's title
#: and description, and a function call per glyph was most of its time.
_KNOWN: dict[str, int] = {chr(32 + i): w for i, w in enumerate(_ASCII)}
_KNOWN.update(_EXTRA)


def _units(s: str) -> tuple[int, int]:
    """(total advance in 1/1000 em, glyphs the table did not know)."""
    total, unknown = 0, 0
    get = _KNOWN.get
    for ch in s:
        units = get(ch)
        if units is None:
            total += AVERAGE
            unknown += 1
        else:
            total += units
    return total, unknown


def text_px(s: str, font: tuple[str, int] = TITLE_FONT) -> int:
    """How wide `s` renders, in whole pixels, at `font`.

    The one measurement. Checks and preview both call it, so the picture and
    the finding cannot disagree about where a title is cut.
    """
    return measure(s, font)["px"]


def measure(s: str, font: tuple[str, int] = TITLE_FONT) -> dict:
    """`text_px` with its provenance: the width, and whether every glyph was
    in the table.

    `estimated` is what the row's `note` is written from. A title in a script
    this table does not carry is still measured - refusing would be worse -
    but the reader is told the number is an estimate rather than left to
    assume a precision that is not there.
    """
    size = font[1]
    total, unknown = _units(s or "")
    return {"px": round(total * size / 1000),
            "unmeasured_glyphs": unknown,
            "estimated": unknown > 0,
            "font": f"{font[0]} {size}px"}


def cut_at(s: str, limit_px: int, font: tuple[str, int] = TITLE_FONT) -> dict:
    """Where `s` is cut at `limit_px`, and what falls off.

    **The words that fall off are the finding's useful content, not the
    number** (the item says so). Cut on a word boundary, which is what a
    search result does; a mid-word cut would name a fragment nobody typed.
    """
    if text_px(s, font) <= limit_px:
        return {"fits": True, "kept": s, "falls_off": ""}
    # Width is a sum of per-glyph advances rounded once at the end, so the
    # kept words' width is carried forward rather than re-measuring every
    # prefix from its first character. Each candidate is still read exactly
    # as `text_px(" ".join(kept + [word]))` would read it.
    size = font[1]
    space = _KNOWN[" "]
    kept: list[str] = []
    width = 0
    for word in (s or "").split():
        candidate = width + (space if kept else 0) + _units(word)[0]
        if round(candidate * size / 1000) > limit_px:
            break
        kept.append(word)
        width = candidate
    keep = " ".join(kept)
    return {"fits": False, "kept": keep,
            "falls_off": (s or "")[len(keep):].strip()}
