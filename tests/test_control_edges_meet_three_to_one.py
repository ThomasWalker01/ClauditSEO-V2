"""Item 181, commit 1: every control edge measures 3:1 or better against the
ground it sits on (UI audit pattern F: 01-6, 02-8, 06-5, 10-7, 11-5, 07-5).

The auditors measured `.bl-secondary` at 1.38:1 dark and 1.17:1 light - the
held report button's dashed edge invisible in light theme - the paid pill at
2.36:1, the re-check pill at 1.91:1, and the scan cells at 1.31:1. Each drew its
edge from `--border`, the divider token.

Measured here in a browser at the four viewports the auditors used: the border
colour against the first opaque background behind the control, composited.
"""

from __future__ import annotations

import pytest

pytest.importorskip("playwright")

from tests.test_a11y_rendered import served  # noqa: E402,F401  (module fixture)
from tests.needs_build import needs_build  # noqa: F401

#: Every clause in this file serves `dashboard/dist` and drives a
#: browser against it, so the gate is the file's rather than each
#: clause's (item 190). Local only: CI builds the bundle and fails on
#: any skip.
pytestmark = needs_build


#: Controls whose edge is their boundary.
CONTROLS = (".bl-secondary", ".parts-link", ".chip", ".act-sweep", ".act-brief",
            ".tone-action-paid", ".tone-action-free", ".scan-cell", ".mode-switch")

_MEASURE = """(selectors) => {
  const parse = (c) => { const m = c.match(/rgba?\\(([^)]+)\\)/); if (!m) return null;
    const p = m[1].split(/[ ,\\/]+/).filter(Boolean).map(Number);
    return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; };
  const lum = ({ r, g, b }) => { const f = (v) => { v /= 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
  const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
    return (x + 0.05) / (y + 0.05); };
  const ground = (el) => { let stack = [];
    for (let n = el.parentElement; n; n = n.parentElement) {
      const c = parse(getComputedStyle(n).backgroundColor);
      if (c && c.a > 0) { stack.push(c); if (c.a >= 1) break; } }
    const body = parse(getComputedStyle(document.body).backgroundColor) || { r: 255, g: 255, b: 255, a: 1 };
    let out = { ...body };
    for (const c of stack.reverse()) out = { r: c.r * c.a + out.r * (1 - c.a),
      g: c.g * c.a + out.g * (1 - c.a), b: c.b * c.a + out.b * (1 - c.a), a: 1 };
    return out; };
  const bad = [];
  let measured = 0;
  for (const sel of selectors) {
    for (const el of document.querySelectorAll(sel)) {
      if (!el.checkVisibility()) continue;
      const s = getComputedStyle(el);
      if (s.borderTopStyle === 'none' || parseFloat(s.borderTopWidth) === 0) continue;
      const edge = parse(s.borderTopColor);
      if (!edge || edge.a === 0) continue;
      measured++;
      const r = ratio(edge, ground(el));
      if (r < 3) bad.push({ sel, text: (el.textContent || '').trim().slice(0, 40), ratio: +r.toFixed(2),
                            edge: s.borderTopColor });
    }
  }
  return { measured, bad };
}"""

VIEWPORTS = (("1440 dark", 1440, "dark"), ("1440 light", 1440, "light"),
             ("1100", 1100, "dark"), ("390", 390, "dark"))


def test_every_control_edge_is_three_to_one_at_every_viewport(served):
    from playwright.sync_api import sync_playwright

    base, ids = served
    routes = (f"#/sites/{ids['site']}", f"#/sites/{ids['site']}?tab=history", "#/")
    failures: list[str] = []
    measured = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            for label, width, scheme in VIEWPORTS:
                ctx = browser.new_context(viewport={"width": width, "height": 1000},
                                          color_scheme=scheme)
                pg = ctx.new_page()
                for route in routes:
                    pg.goto(f"{base}/{route}", wait_until="networkidle")
                    pg.wait_for_timeout(800)
                    got = pg.evaluate(_MEASURE, list(CONTROLS))
                    measured += got["measured"]
                    failures += [f"{label} {route}: {b}" for b in got["bad"]]
                ctx.close()
        finally:
            browser.close()
    assert measured > 20, f"only {measured} edges measured; the routes drew too little to prove anything"
    assert not failures, "control edges under 3:1:\n" + "\n".join(failures[:40])
