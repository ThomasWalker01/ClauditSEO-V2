"""The by-hand launch says how its controls map onto the chooser's two
decisions, instead of claiming to be every control the chooser sets.

Screen audits round 3, audit launch UX-01 (High): "Every control the chooser
sets, and the ones it does not" sat over a form with no control named depth
and a scope list in tier words, so the operator held two models of one
decision 400 px apart under the same nouns.
"""
from __future__ import annotations

from pathlib import Path

VIEWS = (Path(__file__).resolve().parent.parent / "dashboard" / "src" / "views.tsx").read_text(
    encoding="utf-8")


def test_the_blurb_maps_scope_and_depth():
    blurb = VIEWS[VIEWS.index("<h3>Or set it up by hand</h3>"):]
    blurb = blurb[blurb.index('<p className="muted">'):blurb.index("</p>")]
    assert "Every control the chooser sets" not in blurb
    assert "<strong>How much of the site</strong> is the chooser's scope" in blurb
    assert "<strong>depth</strong> is the analyst layer below" in blurb
    for word in ('entry("depth-quick").word', 'entry("depth-standard").word', 'entry("depth-deep").word'):
        assert word in blurb, word
