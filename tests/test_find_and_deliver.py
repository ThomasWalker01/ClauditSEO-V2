"""Item 170 ("find and deliver: finish the fold"), concept 10, channel ruling
20260917-0250.

The strip numbered its four destinations, and the numbers claimed an order the
states contradicted: `3 Record  done` beside `1 Audit  next` told a reader step
3 had finished before step 1 started. Record is done because the system files
it after every run, not because anyone passed through it. So the four
destinations sit in two chapters, Find and Deliver, with no numbers; Analyses is
a catalogue that feeds into Find, and Record is marked automatic and is never
the thing to do next.

The Deliver chapter says what the newest client report went out over, from the
counts recorded when it was built (migration 0064) - never reconstructed, and
never worded so a report made before the Critical and High guard (1efbe9a)
reads as something the product would let happen now.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.test_a11y_rendered import served  # noqa: F401  (module fixture)
from tests.needs_build import needs_build

pytest.importorskip("playwright")

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"


def _open(base, site_id, report_state="leave", fn=None):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page(viewport={"width": 1568, "height": 1080})
        if report_state != "leave":
            def anatomy(route):
                data = route.fetch().json()
                data.setdefault("current", {})["report_state"] = report_state
                route.fulfill(status=200, content_type="application/json",
                              body=json.dumps(data))
            pg.route("**/api/sites/*/anatomy*", anatomy)
        try:
            pg.goto(f"{base}/#/sites/{site_id}", wait_until="load")
            pg.wait_for_selector("nav.seq-chapters .seq-step", timeout=30_000)
            pg.wait_for_timeout(300)
            return fn(pg)
        finally:
            browser.close()


_READ = """() => {
  const nav = document.querySelector('nav.seq-chapters');
  const head = (cls) => {
    const h = nav.querySelector('.seq-chapter-head.' + cls);
    return h ? { name: h.querySelector('.seq-chapter-name').textContent.trim(),
                 state: h.querySelector('.seq-chapter-state').textContent.trim(),
                 warn: h.classList.contains('seq-chapter-warn'),
                 title: h.getAttribute('title') || '', id: h.id } : null;
  };
  return {
    lists: { ol: nav.querySelectorAll('ol').length, ul: nav.querySelectorAll('ul.seq').length },
    find: head('seq-find'), deliver: head('seq-deliver'),
    pills: [...nav.querySelectorAll('.seq-step')].map((li) => ({
      name: li.querySelector('.seq-name').textContent.trim(),
      before: getComputedStyle(li.querySelector('.seq-name'), '::before').content,
      next: li.classList.contains('seq-next'),
      role: (li.querySelector('.seq-role')?.textContent || '').trim(),
      describedby: li.getAttribute('aria-describedby') || '',
    })),
  };
}"""


@needs_build
def test_no_element_of_the_strip_carries_a_number(served):
    """The accept criterion: no number implying an order the states
    contradict. The numbers were a CSS counter, so the proof is computed
    style, not markup - and the list is unordered, because an `ol` announces
    the very sequence this item stops asserting."""
    base, ids = served
    got = _open(base, ids["site"], fn=lambda pg: pg.evaluate(_READ))
    assert got["lists"] == {"ol": 0, "ul": 1}, got["lists"]
    assert [p["name"] for p in got["pills"]] == ["Audit", "Analyses", "Record", "Client report"]
    for pill in got["pills"]:
        assert pill["before"] in ("none", "normal", '""'), pill
        assert not pill["name"][:1].isdigit(), pill
    css = (SRC / "styles.css").read_text(encoding="utf-8")
    assert "counter(seq)" not in css and "counter-increment: seq" not in css


@needs_build
def test_two_chapters_and_each_pill_names_its_own(served):
    base, ids = served
    got = _open(base, ids["site"], fn=lambda pg: pg.evaluate(_READ))
    assert got["find"]["name"] == "Find" and got["deliver"]["name"] == "Deliver", got
    chapter = {"Audit": got["find"]["id"], "Analyses": got["find"]["id"],
               "Record": got["deliver"]["id"], "Client report": got["deliver"]["id"]}
    for pill in got["pills"]:
        assert pill["describedby"] == chapter[pill["name"]], pill
    roles = {p["name"]: p["role"] for p in got["pills"]}
    assert roles["Analyses"] == "feeds in" and roles["Record"] == "automatic", roles


def test_record_is_never_the_next_thing_to_do():
    """Held on the rule, because no fixture state reaches it by accident: the
    step that would be next if Record were eligible must be the one after it."""
    src = (SRC / "anatomy.tsx").read_text(encoding="utf-8")
    assert 'st.status === "idle" && st.name !== "Record"' in src


@pytest.mark.parametrize("state, word, warn, sentence", [
    (None, "not started", False, ""),
    ({"id": "r", "created_at": "2026-09-08T23:29:27+00:00", "run_ids": ["x"],
      "predates_guard": True, "recorded": False, "unassessed_severe": None,
      "unassessed_below": None, "assessed_pct": None},
     "built before the report guard", True, "before a report could be held"),
    ({"id": "r", "created_at": "2026-09-14T00:00:00+00:00", "run_ids": ["x"],
      "predates_guard": False, "recorded": False, "unassessed_severe": None,
      "unassessed_below": None, "assessed_pct": None},
     "passed the guard", False, "was not recorded when it was built"),
    ({"id": "r", "created_at": "2026-09-17T00:00:00+00:00", "run_ids": ["x"],
      "predates_guard": False, "recorded": True, "unassessed_severe": 0,
      "unassessed_below": 412, "assessed_pct": 18},
     "412 unassessed below the guard", True, "412 Medium, Low or Info findings still unassessed (18%"),
    ({"id": "r", "created_at": "2026-09-17T00:00:00+00:00", "run_ids": ["x"],
      "predates_guard": False, "recorded": True, "unassessed_severe": 0,
      "unassessed_below": 0, "assessed_pct": 100},
     "done", False, "every finding it describes assessed"),
])
@needs_build
def test_the_deliver_chapter_says_what_the_report_went_out_over(served, state, word, warn, sentence):
    """Channel ruling 20260917-0250's three cases, from stored numbers. A report
    made before 1efbe9a is a date and a fact, not a live failure; one that
    passed the guard over open Mediums and Lows is the case the threshold
    leaves to the operator; one generated before the counts were recorded says
    so rather than reading as clean."""
    base, ids = served
    got = _open(base, ids["site"], report_state=state, fn=lambda pg: pg.evaluate(_READ))
    assert got["deliver"]["state"] == word, got["deliver"]
    assert got["deliver"]["warn"] is warn, got["deliver"]
    if sentence:
        assert sentence in got["deliver"]["title"], got["deliver"]
    else:
        assert got["deliver"]["title"] == "", got["deliver"]
    if state and state["predates_guard"]:
        # Never worded as something the product would allow again.
        low = got["deliver"]["title"].lower()
        assert "could not" not in low and "allowed" not in low, got["deliver"]
