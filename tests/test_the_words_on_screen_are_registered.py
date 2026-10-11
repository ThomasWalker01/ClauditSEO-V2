"""The words on screen are registered (items 278 r13, 271 r11, 275 r14, 269 r9).

Backlinks and Local drew "referring domains", "domain authority", "anchor
text distribution", "NAP" and "citation"; the checks tables drew "not
assessable"; none had an entry, so neither a legend nor a client report's
appendix could define them. And "seen once" said a candidate opens "when"
the automatic checks raise it, where the rule is "in the same audit", and
said nothing of a candidate the analysis stops reporting.
"""

from __future__ import annotations

from clauditseo import glossary


def test_the_terms_are_registered():
    words = {e["word"].lower() for e in glossary.entries() if e.get("word")}
    for w in ("referring domains", "domain authority", "anchor text distribution", "nap",
              "citation", "not assessable"):
        assert w in words, w


def test_seen_once_says_the_rule():
    e = next(e for e in glossary.entries() if e["id"] == "state-candidate")
    assert "in the same audit" in e["full"] and "dropped rather than counted as fixed" in e["full"]
