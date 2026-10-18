"""The tap-target row says what was measured (item 274, row 7).

The row said each element was smaller "than 24 x 24 CSS px, which WCAG 2.2 SC
2.5.8 sets as the minimum". SC 2.5.8 passes an undersized target with 24 px
of clearance, which the harness does not test, so the row claimed a failure
it had not established. It now states the measurement and the exception.
"""

from __future__ import annotations

import inspect

from clauditseo.modules import tec


def test_the_summary_states_the_exception():
    src = inspect.getsource(tec)
    assert "px of clearance, " in src and "which this audit does not measure." in src
    assert "sets as the minimum" not in src
