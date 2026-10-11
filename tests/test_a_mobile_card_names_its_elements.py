"""A Mobile card names its elements, and each kind its remedy (item 274,
row 8).

`tap-target` and `viewport-units` store the elements they found - tag,
class, box, what each uses - and the card drew none of them. And
`viewport-units` said one sentence and one remedy ("prefer dvh") for two
faults: on twenty22 both elements were a fixed-positioned modal and its
backdrop. The card now lists the elements, and the row says each kind with
its own remedy.
"""

from __future__ import annotations

import inspect

from clauditseo.modules import tec
from clauditseo.persistence import runs


def test_the_elements_are_targets():
    got = runs.finding_targets({"elements": [
        {"tag": "button", "text": None, "w": 20, "h": 26},
        {"tag": "div", "cls": "x-modal_backdrop other", "used": ["position:fixed"]}]})
    assert got == ["button (20 x 26 px)", "div.x-modal_backdrop · position:fixed"], got


def test_each_kind_has_its_own_remedy():
    src = inspect.getsource(tec)
    assert 'fixed = [e for e in units if any("fixed" in str(u)' in src
    assert "one hidden until opened (a modal and its" in src
