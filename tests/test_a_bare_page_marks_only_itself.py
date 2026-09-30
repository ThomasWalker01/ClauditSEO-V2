"""One page with nothing of its own marks itself, not every page beside it (item 214).

`CNT/template-only-page` fired on all 45 twenty22 pages, each "carries almost
no text beyond the site template, fewer than 40 distinct phrases of its own"
- including /website-seo/ at 1,889 words. `_duplicate_content` compares
pages in pairs, and when EITHER page of a pair was under the floor it added
BOTH to `bare`. One bare page (/contact-us/) is paired with every other page,
so every page was bare. Each finding's own evidence carried that page's
`unique_shingles`, far above the 40 its sentence named.

The floor on the finding (`BARE_PAGE_FLOOR`, three) stays: fewer than three
bare pages is a page or two, which the thin-content checks already speak to.
So the clauses need three genuinely bare pages to see the check fire at all.
"""

from __future__ import annotations

from clauditseo.modules.cnt import BARE_PAGE_FLOOR, MIN_UNIQUE_SHINGLES
from tests.test_scoring_normalisation import NAV, _dup


def _prose(seed: str, words: int = 90) -> str:
    """Text of a page's own: distinct words, so its shingles are its own and
    no other page shares them."""
    return " ".join(f"{seed}{i}" for i in range(words))


#: Past the 30 words a page needs to be compared at all, and still with
#: almost nothing of its own once the shared navigation is discounted.
BARE = {f"/bare-{n}": NAV + f"call us on this number or fill in the form {n}"
        for n in range(3)}
FULL = {f"/full-{n}": NAV + _prose(f"w{n}x") for n in range(2)}


def _bare_paths(found) -> list[str]:
    return sorted(f.subject for f in found if f.check_id == "template-only-page")


def test_only_the_pages_under_the_floor_are_template_only():
    assert len(BARE) >= BARE_PAGE_FLOOR, "the fixture must clear the floor to fire at all"
    got = _bare_paths(_dup({**BARE, **FULL}))
    assert got == sorted(BARE), (
        "a page with plenty of its own text was called template-only because "
        f"it was compared with one that was not: {got}")


def test_one_bare_page_among_full_ones_is_no_finding_at_all():
    """The twenty22 shape: one bare page and every other page full. Before
    this, the one bare page marked all four."""
    got = _bare_paths(_dup({"/contact-us": NAV + "call us on this number or fill in the form",
                        **FULL,
                            "/full-2": NAV + _prose("w2x"), "/full-3": NAV + _prose("w3x")}))
    assert got == [], f"one bare page marked its neighbours: {got}"


def test_every_finding_names_a_page_its_evidence_agrees_with():
    """The sentence says "fewer than 40"; the evidence says how many. They
    disagreed on every false finding, which is the check a reader could have
    made and the engine did not."""
    found = [f for f in _dup({**BARE, **FULL}) if f.check_id == "template-only-page"]
    assert found
    for f in found:
        assert f.evidence["unique_shingles"] < MIN_UNIQUE_SHINGLES, f.evidence
