"""A link inside a sentence is not counted as an undersized tap target
(screen audits round 3, Mobile AC-02).

WCAG 2.2 SC 2.5.8 exempts "Inline" targets: a target in a sentence is sized
by the line. The harness counted every `a[href]` under 24 px, so prose links
("table below", 79 x 20) filled the Where lists of all twelve tap-target cards.
The function is taken from the harness itself and run in a browser.
"""

from __future__ import annotations

import re

import pytest

from clauditseo import perf

pw = pytest.importorskip("playwright.sync_api")

PAGE = """<!doctype html><html><body style="font-size:14px">
<p>See the <a id="prose" href="/t">table below</a> for every figure we measured.</p>
<nav><a id="icon" href="/x" style="display:inline-block;width:16px;height:16px">x</a></nav>
<p><a id="alone" href="/y">Read</a></p>
</body></html>"""


def _in_sentence_js() -> str:
    m = re.search(r"const inSentence = \(el\) => \{.*?\n  \};", perf._READ_TRACE_JS, re.S)
    assert m, "the harness no longer defines inSentence"
    return m.group(0)


def test_only_the_prose_link_is_exempt():
    try:
        with pw.sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.set_content(PAGE)
            got = page.evaluate("() => {" + _in_sentence_js() + """
                return ["prose", "icon", "alone"].map(
                  (id) => inSentence(document.getElementById(id)));
            }""")
            browser.close()
    except Exception as exc:  # no browser installed here
        if "Executable doesn't exist" in str(exc):
            pytest.skip("playwright chromium not installed")
        raise
    assert got == [True, False, False], got


def test_the_loop_skips_it():
    assert "if (inSentence(el)) continue;" in perf._READ_TRACE_JS
