"""Item 173, "the head of the landing is still a control panel" (channel
ruling 20260917-1125).

Concept 05's head is a headline and a row of buttons, nothing else: the run
picker and the mode switch live in the top bar, the step strip is small and
sits beside the buttons, and the lanes start immediately under them. The built
head was a bordered three-column card that set the state sentence smaller than
body text beside the picker, the regressions chip, the mode switch and the page
filter.

The head is mounted above every client tab, not only the landing, so the ruling
made it one structure everywhere and two sizes: the sentence is a headline on the
landing, where it is the subject, and one compact line on every other tab, where
the pane below is.

**Guards this file replaces (part G), named so the replacement is visible:**

- `test_the_scope_bar_is_two_columns.py::test_the_bar_is_two_columns_with_the_filter_on_the_left`
  (the card's two columns, the filter in its left column, the rail within
  230 px) - retired with its file.
- `test_the_scope_bar_is_three_columns.py::test_the_bar_guard_is_re_measured_and_recorded`
  (the card within 130 px at 1568 wide, the filter in its side column, the
  alert row inside the picker).
- `test_the_client_landing_is_three_lanes.py::test_the_bar_holds_sentence_action_integrity_mode_picker_band_and_nothing_else`,
  replaced in that file by
  `test_the_head_is_the_sentence_and_its_actions_and_the_bar_holds_the_context`.
- `test_the_bar_is_picker_and_counts.py`'s `barRows == ["scope-state", "scope-side"]`.

Unchanged and not loosened: `test_the_rail_is_a_strip`'s invariant that a part
pane starts within 400 px (`scope.tsx:60`), asserted here too on every tab this
file opens.
"""

from __future__ import annotations

import json

import pytest

from tests.test_a11y_rendered import DIST, served  # noqa: F401  (module fixture)

pytestmark = [
    pytest.mark.skipif(
        __import__("importlib.util", fromlist=["util"]).find_spec("playwright") is None,
        reason="playwright is not installed"),
    pytest.mark.skipif(not (DIST / "index.html").is_file(),
                       reason="dashboard not built (npm run build in dashboard/)"),
]


def _open(served, fn, *, tab="", ready=".run-scope .bl-sentence", width=1440, height=900,
          headline=None):
    from playwright.sync_api import sync_playwright
    base, ids = served
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page(viewport={"width": width, "height": height})
        if headline is not None:
            def anatomy(route):
                data = route.fetch().json()
                data["headline"] = {**(data.get("headline") or {}), **headline}
                route.fulfill(status=200, content_type="application/json", body=json.dumps(data))
            pg.route("**/api/sites/*/anatomy*", anatomy)
        try:
            pg.goto(f"{base}/#/sites/{ids['site']}{'?tab=' + tab if tab else ''}", wait_until="load",
                    timeout=30_000)
            pg.wait_for_selector(ready, timeout=30_000)
            pg.wait_for_selector("#topbar-context .audit-now[data-audit]", state="attached",
                                 timeout=30_000)
            pg.wait_for_timeout(400)
            return fn(pg)
        finally:
            browser.close()


_LANDING = """() => {
  const box = (sel) => { const e = document.querySelector(sel); if (!e) return null;
    const r = e.getBoundingClientRect(); return { top: r.top, bottom: r.bottom, left: r.left, right: r.right }; };
  const lane = box('.cl-landing .cl-lane');
  const actions = box('.run-scope .bl-actions');
  const landing = document.querySelector('.cl-landing');
  const between = [...landing.children].filter((c) => {
    const r = c.getBoundingClientRect(); return r.height > 0 && r.top < lane.top - 1; })
    .map((c) => ({ cls: c.className, top: Math.round(c.getBoundingClientRect().top),
                   h: c.getBoundingClientRect().height }));
  const leaves = [...document.querySelectorAll('body *')].filter((e) =>
    e.children.length === 0 && e.textContent.trim() && e.getClientRects().length
    && !e.closest('.sr-only'));
  const biggest = Math.max(...leaves.map((e) => parseFloat(getComputedStyle(e).fontSize)));
  const sentence = document.querySelector('.run-scope .bl-sentence');
  return {
    sentence: box('.run-scope .bl-sentence'), integrity: box('.run-scope .integrity-line'),
    actions, lane, between, buttons: box('.run-scope .bl-buttons'),
    strip: box('.run-scope .bl-actions nav.seq-chapters'),
    sentenceFs: parseFloat(getComputedStyle(sentence).fontSize), biggest,
    paneHeadDrawn: !!document.querySelector('.pane-head:not(.sr-only)'),
  };
}"""


def test_at_1440_the_landing_is_a_headline_then_actions_then_the_lanes(served):
    """The accept criterion, on geometry: the sentence, then the integrity line
    where it applies, then the actions with the strip beside them, then the lanes
    - with nothing between but the lane row's own small line (the disclosure and
    the mode's arithmetic, part E and part 4)."""
    got = _open(served, lambda pg: pg.evaluate(_LANDING))
    assert got["sentence"] and got["actions"] and got["lane"], got
    assert got["sentence"]["bottom"] <= got["actions"]["top"] + 1, got
    if got["integrity"]:
        assert got["sentence"]["bottom"] <= got["integrity"]["top"] + 1, got
        assert got["integrity"]["bottom"] <= got["actions"]["top"] + 1, got
    assert got["strip"] and got["strip"]["left"] >= got["buttons"]["right"], (
        f"the strip is not beside the buttons: {got}")
    assert got["actions"]["bottom"] <= got["lane"]["top"], got
    assert not got["paneHeadDrawn"], "the landing still draws its pane heading"
    # The parts band sits here on the operator's ruling (item 195A), so it is
    # named and excluded rather than allowed past by a looser bound - the
    # clause still refuses anything else.
    rest = [b for b in got["between"] if "cl-parts" not in (b["cls"] or "")]
    rows = {round(b["top"]) for b in rest}
    assert len(rows) <= 1 and all(b["h"] <= 40 for b in rest), (
        "more than the lane row's one small line and the parts band stands "
        f"between the actions and the lanes: {got['between']}")
    band = next((b for b in got["between"] if "cl-parts" in (b["cls"] or "")), None)
    assert band, f"the parts band is not between the actions and the lanes: {got}"
    # The 90 px is not raised to swallow the band. It bounded "the lane row's
    # own small line and nothing else", and it still does - above the band -
    # with a second bound below it. The band costs its own height and no
    # slack, which is what the single number was saying before there was
    # anything else in the space.
    assert band["top"] - got["actions"]["bottom"] <= 90, got
    assert got["lane"]["top"] - (band["top"] + band["h"]) <= 24, got


def test_the_state_sentence_is_the_largest_text_on_the_landing(served):
    got = _open(served, lambda pg: pg.evaluate(_LANDING))
    assert got["sentenceFs"] >= 24, f"the sentence is not a headline: {got['sentenceFs']}px"
    assert got["sentenceFs"] >= got["biggest"], (
        f"something on the landing is set larger than the sentence: {got['biggest']}px")


@pytest.mark.parametrize("tab,ready", [
    ("findings", ".catalogue-shop .crow-part"),
    ("all", ".state-filters"),
    ("history", ".scan-matrix"),
])
def test_every_other_tab_has_the_same_structure_compact_and_its_pane_within_400px(served, tab, ready):
    """Ruling A: the same place for every control on every tab, and the
    sentence compact where the pane below is the subject. The filter is still
    the bar's and never a pane's (brief v4 Item 1) - and since item 174 page
    mode's alone, so site mode draws none on any tab - and the reference links
    are beside the nav (`#topbar-refs`)."""
    got = _open(served, lambda pg: pg.evaluate("""() => {
      const bar = document.querySelector('#topbar-context');
      const pane = document.querySelector('#pane');
      return {
        audit: !!bar?.querySelector('.audit-now'),
        filter: document.querySelectorAll('.page-find').length,
        paneFilter: pane ? pane.querySelectorAll('.page-find').length : -1,
        refs: !!document.querySelector('#topbar-refs nav.refs'),
        headControls: !!document.querySelector('.run-scope select, .run-scope .page-find'),
        sentenceFs: parseFloat(getComputedStyle(document.querySelector('.run-scope .bl-sentence')).fontSize),
        paneTop: pane ? pane.getBoundingClientRect().top + window.scrollY : -1,
        lanes: document.querySelectorAll('.pane-body .cl-lane').length,
      };
    }"""), tab=tab, ready=ready, width=1568)
    assert got["audit"] and got["filter"] == 0 and got["refs"], (tab, got)
    assert got["paneFilter"] == 0 and not got["headControls"], (tab, got)
    assert got["sentenceFs"] < 18, f"{tab}: the sentence is a headline where it is context: {got}"
    assert 0 < got["paneTop"] <= 400, f"{tab}: the pane starts {got['paneTop']}px down"
    assert got["lanes"] == 0, (tab, got)


def test_the_current_audit_is_named_and_is_not_a_control(served):
    """Item 239 step 5: the picker is retired. The bar names the current
    audit, and there is nothing to pick it with."""
    got = _open(served, lambda pg: pg.evaluate("""() => {
      const box = document.querySelector('#topbar-context .audit-now');
      return { text: box?.querySelector('.sel-lbl')?.textContent.trim() || '',
               controls: box ? box.querySelectorAll('select, button, input, [role=listbox]').length : -1 };
    }"""))
    assert got["text"] == "Current audit", got
    assert got["controls"] == 0, got


def test_the_held_report_button_is_focusable_and_says_why(served):
    """Ruling D: held by the Critical and High guard, "Build the client report"
    is `aria-disabled` - still focusable - and described by the integrity line,
    which states the reason in text. A `disabled` button cannot be focused and a
    `title` is not reliably announced."""
    def read(pg):
        return pg.evaluate("""() => {
          const held = [...document.querySelectorAll('.run-scope .bl-buttons .bl-held')];
          const line = document.getElementById('integrity-line');
          return { held: held.map((b) => ({ text: b.textContent.trim(), tag: b.tagName,
                     aria: b.getAttribute('aria-disabled'), disabled: b.disabled,
                     describedby: b.getAttribute('aria-describedby') })),
                   line: line ? line.textContent.trim() : null };
        }""")
    got = _open(served, read, headline={"integrity": {"count": 3, "critical": 1, "high": 2}})
    assert got["held"] == [{"text": "Build the client report", "tag": "BUTTON", "aria": "true",
                            "disabled": False, "describedby": "integrity-line"}], got
    assert got["line"] and "3 Critical or High" in got["line"], got
