"""The by-hand launch speaks the chooser's two decisions in the chooser's
own words.

Screen audits round 3, audit launch UX-01 (High): "Every control the chooser
sets, and the ones it does not" sat over a form with no control named depth,
a tier radio in other words and a navigation-only box, so the operator held
two models of one decision 400 px apart under the same nouns.

Channel ruling 20261016-1301: the wording fix alone did not hold (it left Nav
out of the scopes, and called it only-here), so the card takes the chooser's
scope words (Page, Nav, Site, Full, plus Adaptive) and its depth (Quick,
Standard, Deep), posting `scope` and `depth` as the chooser does. The tier
follows from the scope on the server; off-grid combinations stay on the API.
"""
from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "dashboard" / "src"
VIEWS = (SRC / "views.tsx").read_text(encoding="utf-8")
CARD = VIEWS[VIEWS.index("<h3>Or set it up by hand</h3>"):VIEWS.index("Run audit\n")]
LAUNCHER = VIEWS[VIEWS.index("export function LauncherView("):]
LAUNCHER = LAUNCHER[:LAUNCHER.index("\n}\n")]


def test_the_blurb_claims_only_what_the_card_does():
    blurb = CARD[CARD.index('<p className="muted">'):CARD.index("</p>")]
    assert "Every control the chooser sets" not in blurb
    assert "scope and depth, in its own words" in blurb
    assert "which only this card sets" in blurb


def test_the_controls_are_the_choosers():
    assert "{SCOPES.map((s) => (" in CARD and "{DEPTHS.map((d) => (" in CARD
    assert 'name="scope"' in CARD and 'name="depth"' in CARD
    # Gone: the tier radio, the navigation-only box, the analyst checkbox and
    # the model list.
    for gone in ('name="tier"', "Navigation only", "Enable LLM analyst", 'aria-label="analyst model"'):
        assert gone not in CARD, gone
    for gone in ("setTier", "setNavOnly", "setAnalyst", "setModel"):
        assert gone not in LAUNCHER, gone


def test_the_post_is_the_choosers():
    assert '...(scope === "auto" ? { tier: "auto" } : { scope, depth }),' in LAUNCHER
    assert "nav_only:" not in LAUNCHER and "        analyst:" not in LAUNCHER
    assert 'meta.analyst_available && (scope === "auto" || depth !== "quick") ? (' in LAUNCHER
