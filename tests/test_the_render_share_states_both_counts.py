"""The render share states both counts and sets aside what it cannot
compare (item 267, row 18).

A page whose initial HTML counted more words than its rendered text was
capped at 100% and counted as fully served to a non-rendering reader. The two
counts are not comparable there; such pages are set aside and counted, and
the share is stated as initial / rendered.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_no_cap_and_both_counts():
    src = (ROOT / "clauditseo" / "analysts" / "ai_surface.py").read_text(encoding="utf-8")
    assert "min(p[\"word_count\"] / rendered, 1.0)" not in src
    assert '"not_comparable": incomparable' in src
    tsx = (ROOT / "dashboard" / "src" / "ai_surface.tsx").read_text(encoding="utf-8")
    assert "initial / ${now.render.rendered_words} rendered words" in tsx
    assert "Not comparable on ${now.render.not_comparable} page" in tsx
