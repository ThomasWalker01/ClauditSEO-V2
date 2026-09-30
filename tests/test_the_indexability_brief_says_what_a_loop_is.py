"""Item 228 (Indexability, change 1): the brief says what a canonical loop is.

The definition read "A → B → A, or self-canonical on a redirecting URL". On
twenty22 T3 the model read "a URL a redirect lands on" as "a redirecting
URL" and filed three HIGH loops on healthy pages (`/about` 301 → `/about/`,
self-canonical). The engine raised none. The definition now says the
destination is the healthy case, and a handling rule ties a loop row to the
canonical URL's own 3xx in CANONICAL MAP.

The paid re-run the filing names as the signal is not made here; this holds
the words the re-run will be given.
"""

from __future__ import annotations

from pathlib import Path

BRIEF = (Path(__file__).resolve().parents[1] / "clauditseo" / "prompts"
         / "indexability.md").read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return " ".join(text.split())


def test_the_definition_names_the_healthy_case():
    flat = _flat(BRIEF)
    assert "self-canonical on a redirecting URL" not in flat
    assert ("A URL that is the DESTINATION of a redirect and names itself canonical "
            "is the healthy case, not a loop") in flat


def test_a_loop_row_is_tied_to_the_canonical_urls_own_status():
    flat = _flat(BRIEF)
    assert ("A `canonical-loop` row needs the canonical URL's own status to be 3xx "
            "in CANONICAL MAP") in flat
    assert "Never infer a loop from REDIRECTS alone" in flat
