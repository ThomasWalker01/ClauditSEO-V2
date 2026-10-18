"""Every navigation goes through `nav.ts`, and going nowhere still announces.

The app routes on `hashchange` alone (`App.tsx`'s `useHash`, and
`SiteDetailView`'s own listener). **The browser does not fire `hashchange` when
a hash is assigned the value it already has**, so a control that navigates to
the pane the URL already names does nothing: no event, no re-render, no
feedback.

Two controls shipped dead on that, both reported by the operator as "the button
does nothing":

  - `read triage`, whose handler assigned `#/sites/<id>?tab=analyses`;
  - `open analyses`, an anchor to the same URL — because a left-click on an
    anchor pointing at the current location is the same no-op.

The second shape is why this file guards more than raw assignments. Grepping
for `location.hash =` finds one of the two.

This is a source guard rather than a rendered one deliberately. The defect is
invisible at the call site — a raw assignment is correct code right up until
its target happens to be where you already are — so what has to be enforced is
that no call site is written that way at all.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "dashboard" / "src"
DOOR = SRC / "nav.ts"

#: The one file allowed to touch `window.location.hash` directly. Everything
#: else asks it to.
ALLOWED = {"nav.ts"}


def _sources() -> list[Path]:
    return sorted(p for p in SRC.iterdir()
                  if p.suffix in (".ts", ".tsx") and p.is_file())


def test_the_door_exists_and_handles_going_where_you_already_are():
    """The fix itself, asserted rather than assumed by the cases below."""
    src = DOOR.read_text(encoding="utf-8")
    assert "export function goto" in src
    assert "window.location.hash === next" in src, (
        "the same-value case is the whole reason this module exists")
    assert "dispatchEvent" in src, (
        "assigning an unchanged hash is a no-op, so the listeners have to be "
        "told some other way")


def test_no_screen_assigns_the_hash_itself():
    offenders = []
    for path in _sources():
        if path.name in ALLOWED:
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"location\.hash\s*=(?!=)", line):
                offenders.append(f"{path.name}:{i}: {line.strip()}")
    assert not offenders, (
        "a hash assigned directly does nothing when it names the current "
        "location, and the call site cannot see that. Route it through "
        "`goto` in nav.ts:\n  " + "\n  ".join(offenders))


def test_an_in_app_anchor_that_can_point_at_here_intercepts_its_own_click():
    """The second shape of the same bug.

    An anchor whose `href` is the current URL is dropped by the browser exactly
    as an assignment is. The `href` must stay — it is what makes the control a
    link, and middle-click and copy-address read it — so the plain left-click
    is what gets intercepted.

    Scoped to anchors carrying a `?tab=` or `?step=` target, which are the ones
    that can name the pane you are already looking at. A link to another site
    or another run changes the path and fires normally.
    """
    offenders = []
    for path in _sources():
        if path.name in ALLOWED:
            continue
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r"<a\b[^>]*?href=\{`#[^`]*\?(?:tab|step)=[^`]*`\}[^>]*>",
                             text, re.S):
            if "onClick" not in m.group(0):
                line = text[:m.start()].count("\n") + 1
                offenders.append(f"{path.name}:{line}: {' '.join(m.group(0).split())[:110]}")
    assert not offenders, (
        "this anchor can point at the pane already on screen, where a plain "
        "left-click is a no-op. Keep the href and add "
        "`onClick={goHandler(...)}`:\n  " + "\n  ".join(offenders))


def test_the_two_controls_that_shipped_dead_are_wired():
    """Named, because a general rule passing does not prove these two fixed.

    Both live in `anatomy.tsx` and both target `?tab=analyses` — the pane the
    operator is most often already on when they press them, which is why they
    were the two that were noticed.
    """
    src = (SRC / "anatomy.tsx").read_text(encoding="utf-8")
    # The second control was the Triage pane's part press, which opened on
    # Analyse through the one door. Item 196 deleted that pane, so only the
    # "open analyses" link is left of the pair this clause was written for -
    # and it is still the thing being asserted: a navigation that goes
    # through `goHandler` rather than assigning the hash itself.
    assert "onClick={goHandler(" in src, "the `open analyses` link"


def test_a_modified_click_is_left_alone():
    """Ctrl/cmd/shift/middle-click is the user asking for a new tab.

    Hijacking that is a worse bug than the one being fixed, and it is the
    standard mistake when an anchor's click is intercepted.
    """
    src = DOOR.read_text(encoding="utf-8")
    for key in ("metaKey", "ctrlKey", "shiftKey", "button !== 0"):
        assert key in src, f"{key} is not checked before preventDefault"
