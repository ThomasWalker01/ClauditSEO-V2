"""The Accessibility Fixes block explains everything the overlay boxes (item
136o, the "Also" fix).

On Birch `/about` the overlay boxed two `axe-color-contrast` barriers and the
Fixes block said "Nothing to fix on this scope". The item diagnosed a
page-identity mismatch; it was not one - both sides agreed the finding was on
`/about`. The Fixes block filtered by an ENUMERATED check list, and
`axe-color-contrast` is a dynamically-named check the engine files by PREFIX
(`CHECK_PREFIX_CATEGORY`). One side of the app knew the axe ids are
unenumerable and the other did not.

The fix is one definition of "belongs to this part", the engine's, on both
sides. This file locks the rule; the rendered invariant
`test_a_boxed_barrier_has_a_fix_card_beneath_it` lives in the a11y sweep.
"""

from __future__ import annotations

from pathlib import Path

from clauditseo import anatomy as an


def test_a_dynamically_named_check_belongs_to_its_part():
    """`axe-<rule>` files under the a11y category by prefix, not enumeration -
    the rule the Fixes block now shares."""
    assert an.categorise("axe-color-contrast", "A11Y") == "a11y"
    assert an.categorise("axe-a-rule-that-does-not-exist-yet", "A11Y") == "a11y"
    # The prefix is declared once, as a prefix, precisely because the rule
    # set moves upstream.
    assert ("axe-", "a11y") in an.CHECK_PREFIX_CATEGORY


def test_the_payload_carries_the_parts_prefixes():
    """The client reads these to file a barrier the same way the engine does.
    Asserted from the source so a refactor that drops the field is caught -
    the whole defect was one side of the app not knowing the prefix."""
    src = (Path(__file__).resolve().parents[1] / "clauditseo" / "persistence"
           / "runs.py").read_text(encoding="utf-8")
    assert '"check_prefixes": [pre for pre, cat in an.CHECK_PREFIX_CATEGORY' in src

    ts = (Path(__file__).resolve().parents[1] / "dashboard" / "src"
          / "part_page.tsx").read_text(encoding="utf-8")
    # `fixesOf` accepts a check by enumeration OR prefix.
    assert "part.check_prefixes ?? []" in ts
    assert "checkId.startsWith(pre)" in ts


def test_the_run_rows_carry_no_rect_so_they_never_need_a_card():
    """`axe-sampled` and friends are rows about the run, not barriers; they
    carry no instances with a rect, so the overlay never boxes them and the
    "boxed barrier has a card" invariant does not demand one for them. No
    exclusion list - the absence of a rect is the exclusion, and it stays
    true when axe changes."""
    from clauditseo.modules import a11y
    import inspect

    src = inspect.getsource(a11y)
    # The coverage rows are INFO scope statements with no `instances`.
    assert 'check_id="axe-sampled"' in src
    assert '"instances"' not in src.split('check_id="axe-sampled"')[1][:600]
