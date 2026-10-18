"""A small target with 24 px of clearance passes on spacing (channel ruling
20261017-1132, screen audits round 4, Mobile AC-02).

WCAG 2.2 SC 2.5.8 passes an undersized target whose 24 px circle, on its
centre, meets no other target and no other undersized target's circle. The
harness raised every box under 24 px and said, on every card, that the
clearance was not measured. It now measures it: the block is taken from the
harness itself and run in a browser.
"""
from __future__ import annotations

import inspect

import pytest

from clauditseo import perf
from clauditseo.modules import tec

pw = pytest.importorskip("playwright.sync_api")

#: Two 16 px icons 4 px apart (crowded: both fail), one 16 px icon alone in
#: a wide space (passes on spacing), and a 40 px button (not undersized).
PAGE = """<!doctype html><html><body style="margin:0">
<a id="a" href="/a" style="position:absolute;left:10px;top:10px;width:16px;height:16px">a</a>
<a id="b" href="/b" style="position:absolute;left:30px;top:10px;width:16px;height:16px">b</a>
<a id="lone" href="/c" style="position:absolute;left:300px;top:300px;width:16px;height:16px">c</a>
<button id="big" style="position:absolute;left:600px;top:10px;width:40px;height:40px">big</button>
</body></html>"""


def _block() -> str:
    src = perf._READ_TRACE_JS
    start = src.index("  const inSentence = (el) => {")
    end = src.index("  // Viewport-unit and fixed-position elements.")
    return src[start:end]


def test_crowded_icons_fail_and_a_lone_one_passes():
    try:
        with pw.sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 800, "height": 600})
            page.set_content(PAGE)
            got = page.evaluate("() => {" + _block() + "return {small, spaced}; }")
            browser.close()
    except Exception as exc:  # no browser installed here
        if "Executable doesn't exist" in str(exc):
            pytest.skip("playwright chromium not installed")
        raise
    assert sorted(t["text"] for t in got["small"]) == ["a", "b"], got
    assert got["spaced"] == 1, got
    assert all({"x", "y", "w", "h"} <= set(t) for t in got["small"]), got


def test_the_finding_says_spacing_was_measured():
    src = inspect.getsource(tec)
    assert '"spacing": "measured" if spacing else "not measured"' in src
    assert "confidence=Confidence.MEDIUM if spacing else Confidence.LOW" in src
    assert "tap_spacing_measured: true," in perf._READ_TRACE_JS


def test_a_hidden_fixed_element_is_not_a_viewport_unit_case():
    """Mobile AC-03: a modal hidden until opened was carded as a fixed
    element in the way."""
    src = perf._READ_TRACE_JS
    assert 'cs.position === "fixed" && cs.display !== "none" && cs.visibility !== "hidden"' in src
    assert 'id: t.el.id || null,' in src
