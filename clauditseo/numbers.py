"""Token-boundary number extraction shared by the analyst validator and the
report checks.

The no-new-numbers guarantee used to be a raw substring test, which let a
fabricated "43" pass because "1043" appeared somewhere in a hash or count.
Numbers are now extracted as whole tokens (so "1043" contributes 1043, not
43) and normalised (thousands separators stripped, trailing decimal zeros
dropped) before set-membership comparison.

That closed the class for *digit* neighbours only. A letter neighbour walked
straight through until round 081: `x509` held 509, `FY25` held 25, and
`hero-69a4e135.webp` held 0, 4, 42, 69 and 135 — so a hashed filename in the
evidence grounded a fabricated figure, and a tenth of the verification panel's
flagged values were pieces of identifiers. Both halves are `_NUMBER_TOKEN`, so
both are fixed by giving it a boundary; see `is_identifier_fragment` for why
that boundary is an identifier shape rather than "any abutting letter".
"""

from __future__ import annotations

import re
from typing import Iterator

_NUMBER_TOKEN = re.compile(r"\d[\d,]*(?:\.\d+)?")
#: One letter, any script. `[^\W\d_]` rather than `[A-Za-z]` because the briefs
#: quote page copy, and an accented word abutting a digit is the same shape.
_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)


def is_identifier_fragment(text: str, match: re.Match[str]) -> bool:
    """Whether this digit run is part of an identifier rather than a figure.

    True when a letter sits immediately *before* the digits (`x509`, `FY25`,
    `A11Y`, `h3`, and every interior run of `hero-69a4e135.webp`), or when the
    letters that follow are themselves followed by more digits (`69a4e135`
    again, from its leading `69`). False when letters follow and nothing
    numeric comes after them, which is a unit or a currency shorthand.

    **Why not simply "any abutting letter", which is the shorter rule.**
    Measured old-token against new over all 38 stored briefs and the 35
    documents under `reports/out/` at round 081: the blunt rule drops 579
    numbers and this one drops 409, and the 170 in the difference are figures
    with a suffix — `0.7s`, `300ms`, `$5K`, `$7.5M`, `100vh`, `145k`, `3xx`.
    Those are claims about the site. Dropping them would be worse than the
    defect, and asymmetrically so: a document saying a bare `0.7` against an
    evidence that says `0.7s` would read as ungrounded and fail the honesty
    gate on a figure that is grounded.

    The cost of the narrower rule, named here rather than found later: a
    digit-letter-digit alternation is an identifier by this test, so
    `1920x1080` yields nothing. Eight such shapes exist across the whole
    corpus (`500x300`, `20500x300`, `22X43`), against the 13 identifier
    fragments in 189 stored flagged figures that the rule removes.
    """
    if match.start() and _LETTER.match(text[match.start() - 1]):
        return True
    after = match.end()
    while after < len(text) and _LETTER.match(text[after]):
        after += 1
    return after > match.end() and after < len(text) and text[after].isdigit()


def number_tokens(text: str) -> Iterator[re.Match[str]]:
    """Every numeric token in `text` that is not part of an identifier.

    The single walk all three public functions share. They used to call
    `_NUMBER_TOKEN.finditer` each in their own way, which is three places for a
    boundary rule to be applied in two of.

    The boundary is a check on the match rather than a lookaround in the
    pattern, deliberately: `(?<![A-Za-z])…(?![A-Za-z])` lets the engine
    backtrack out of the optional decimal group to satisfy the lookahead, so
    `1.5x` would yield `1` — a number that is in neither the text nor the
    identifier. Matching greedily first and judging the whole token afterwards
    cannot produce a value the text does not hold.
    """
    for match in _NUMBER_TOKEN.finditer(text):
        if not is_identifier_fragment(text, match):
            yield match


def normalise_number(token: str) -> str:
    token = token.replace(",", "")
    if "." in token:
        token = token.rstrip("0").rstrip(".")
    return token


def extract_numbers(text: str) -> set[str]:
    """Every numeric token in `text`, normalised. Greedy matching means the
    digits inside a longer run never contribute their substrings."""
    return {normalise_number(m.group(0)) for m in number_tokens(text)}


def find_number(text: str, value: str) -> re.Match[str] | None:
    """The first token in `text` whose normalised value is `value`.

    The locating half of the same rule `extract_numbers` applies. It exists
    because the two halves had drifted: extraction reads whole tokens and
    normalises them, so a report saying `1,532,933 bytes (~1.50 MB)` yields
    `1532933` and `1.5` — and a caller that then searched the prose for those
    strings behind its own boundary regex found neither, because the prose
    holds the separators and the trailing zero that normalisation removed.

    Measured on the operator's database at round 080: 33 of 189 stored flagged
    figures reached the verification panel with no context at all, 17 through
    normalisation and 16 through a boundary rule that refused any digit run
    with a `.` beside it — ordered-list numbering (`14. https://…`), numbered
    headings (`## 12. IMPLEMENTATION`) and standards references (`E.164`).

    Returns the match rather than the offset so the caller keeps `start` and
    `end` over the token **as written**, which is what trimming a line around
    a figure needs — the normalised value has a different length and would
    clip in the wrong place.
    """
    for match in number_tokens(text):
        if normalise_number(match.group(0)) == value:
            return match
    return None


def ungrounded(candidate_text: str, allowed: set[str]) -> list[str]:
    """Numbers in candidate_text that are not in the allowed set."""
    return sorted(n for n in extract_numbers(candidate_text) if n not in allowed)


def ungrounded_in_order(candidate_text: str, allowed: set[str]) -> list[str]:
    """Ungrounded numbers in first-appearance order, de-duplicated.

    `ungrounded` sorts a set, which answers "is anything ungrounded?" — the
    question its four validation callers ask. It is the wrong shape for "which
    of these matter most", because a sorted set decides that by string
    accident: capped at eight, a brief's real figures lost their slots to
    section numbering that happened to sort first.
    """
    seen: set[str] = set()
    out: list[str] = []
    for match in number_tokens(candidate_text):
        number = normalise_number(match.group(0))
        if number in allowed or number in seen:
            continue
        seen.add(number)
        out.append(number)
    return out
