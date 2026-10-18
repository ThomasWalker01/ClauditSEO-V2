"""Item 181, commit 2: every visible control is at least 24 px in its smaller
dimension (UI audit 11-6, 02-10, 05-6, 07-18; WCAG 2.5.8).

The lint is measured, not read from source: a rendered walk of the routes the
auditors named, at 1440 dark, counting every visible interactive element whose
hit box is under 24 px. WCAG's own exceptions are applied and named:

- inline: a link inside a run of text, which the sentence sizes;
- user-agent: an unstyled native checkbox, radio or file input;
- the length strips' bars (05-6): 100 pages across one strip cannot each be
  24 px wide without the picture scrolling. The strip is one tab stop with
  arrow keys since this item, and a bar is reached that way; recorded in
  `CANNOT_REACH` with the reason, which is what the item's report asks for.
"""

from __future__ import annotations

import pytest

pytest.importorskip("playwright")

from tests.test_a11y_rendered import served  # noqa: E402,F401  (module fixture)

#: Controls that cannot reach 24 px, with why. The report names each.
CANNOT_REACH = {
    "strip-bar": "a length strip draws every page of the crawl in one row; at 24px each, "
                 "100 pages scroll sideways. One tab stop with arrow keys instead (05-6).",
    "cd-bar": "the crawl-depth histogram's bars are sized by the count they draw.",
}

_WALK = """(cannot) => {
  const sel = 'a[href], button, summary, select, input:not([type=hidden]), [role=button], [tabindex="0"]';
  const small = [];
  for (const el of document.querySelectorAll(sel)) {
    if (!el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) continue;
    const t = el.getAttribute('type');
    if (el.tagName === 'INPUT' && ['checkbox', 'radio', 'file'].includes(t)) continue;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    if (Math.min(r.width, r.height) >= 23.5) continue;
    const s = getComputedStyle(el);
    if (s.display === 'inline' && el.tagName === 'A') {
      const p = el.parentElement;
      const text = [...p.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join('').trim();
      if (text.length > 20) continue;   // a link in a sentence
    }
    if ([...el.classList].some((c) => cannot.includes(c))) continue;
    small.push(`${el.tagName.toLowerCase()}.${[...el.classList].join('.')} "${(el.textContent || el.getAttribute('aria-label') || '').trim().slice(0, 30)}" ${Math.round(r.width)}x${Math.round(r.height)}`);
  }
  return small;
}"""


def test_no_visible_control_is_under_24px(served):
    from playwright.sync_api import sync_playwright

    base, ids = served
    site = ids["site"]
    routes = ("#/", f"#/sites/{site}", f"#/sites/{site}?tab=history", f"#/sites/{site}?tab=findings",
              f"#/sites/{site}?tab=all", f"#/sites/{site}?tab=findings&part=title-desc",
              f"#/sites/{site}/reports", "#/admin?tab=keys", "#/admin?tab=cadence",
              "#/glossary", "#/buttons")
    found: dict[str, list[str]] = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        pg = browser.new_page(viewport={"width": 1440, "height": 1000})
        try:
            for route in routes:
                pg.goto(f"{base}/{route}", wait_until="networkidle")
                pg.wait_for_timeout(1000)
                small = pg.evaluate(_WALK, list(CANNOT_REACH))
                if small:
                    found[route] = small
        finally:
            browser.close()
    total = sum(len(v) for v in found.values())
    assert not found, f"{total} controls under 24px:\n" + "\n".join(
        f"  {route}: {len(s)}\n    " + "\n    ".join(sorted(set(s))[:25]) for route, s in found.items())
