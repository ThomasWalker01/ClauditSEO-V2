"""The trace reads the largest paint once nothing larger can still arrive.

Screen audits round 4, Speed AC-01 (High): twenty22's `/` read LCP 1004 ms, a
text block at the first paint, on 12 Oct, while its 951 KB hero image finished
at 5.6 s; the 10 Oct trace of the same page read 5652 ms on that image. The
trace read the observer straight after `load`, which a lazily loaded image does
not hold back, so the worst-first picker ranked the home page tenth of twelve.
"""
from __future__ import annotations

import inspect

from clauditseo import perf


def test_the_read_waits_for_a_quiet_network_after_load():
    src = inspect.getsource(perf)
    load = src.index('page.wait_for_load_state("load", timeout=_RENDER_TIMEOUT_MS)')
    quiet = src.index('page.wait_for_load_state("networkidle", timeout=_LCP_QUIET_MS)')
    read = src.index("raw = page.evaluate(_READ_TRACE_JS) or {}")
    assert load < quiet < read
    assert 2_000 <= perf._LCP_QUIET_MS <= 10_000
