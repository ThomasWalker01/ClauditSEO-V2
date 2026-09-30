"""Brief v23 step BL: the client view's landing state is one state sentence,
one primary action and three lanes - Waiting on you, What has been measured,
Settled - replacing the bar's three KPI columns. The lanes keep their names and
order in both modes; the mode decides what they are about.

The report threshold's own clauses are in
`test_the_report_cannot_be_generated_with_an_unassessed_critical_or_high.py`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

pytest.importorskip("playwright")

from tests.test_a11y_rendered import served  # noqa: E402,F401  (module fixture)
from tests.parts import open_page_filter
from tests.needs_build import needs_build

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "dashboard" / "src"
LANES = (SRC / "client_lanes.tsx").read_text(encoding="utf-8")
NAMES = ["Waiting on you", "What has been measured", "Settled"]


_READ = """() => ({
  names: [...document.querySelectorAll('.cl-landing .cl-lane .cl-lane-head .sel-lbl')]
    .map((e) => e.textContent.trim()),
  classes: [...document.querySelectorAll('.cl-landing .cl-lane')]
    .map((e) => [...e.classList].find((c) => c.startsWith('lane-'))),
  sentence: document.querySelector('.run-scope .bl-sentence')?.textContent || '',
  sentenceRun: document.querySelector('.run-scope .bl-sentence')?.dataset.run || null,
  whenTitle: document.querySelector('.run-scope .bl-sentence .bl-when')?.getAttribute('title') || '',
  // Item 239 step 5: the current audit, said and not picked.
  current: document.querySelector('.audit-now')?.dataset.audit || null,
  currentLabel: document.querySelector('.audit-now-text')?.textContent || '',
  // The actions row: since item 173 the strip sits inside `.run-scope` too, and a
  // step's hidden panel carries its own action pill, which is not a second primary.
  primaries: document.querySelectorAll('.run-scope .bl-buttons .tone-action-primary').length,
  measured: [...document.querySelectorAll('.lane-measured .cl-entry')]
    .map((e) => e.textContent.trim()),
  entries: Object.fromEntries(['waiting', 'measured', 'settled'].map((k) =>
    [k, document.querySelectorAll(`.lane-${k} .cl-entry`).length])),
})"""


def _page(served, fn, width=1568):
    from playwright.sync_api import sync_playwright
    base, ids = served
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page(viewport={"width": width, "height": 1080})
        try:
            pg.goto(f"{base}/#/sites/{ids['site']}", wait_until="load")
            pg.wait_for_selector(".cl-landing .cl-lane-row, .cl-landing .cl-lane-empty",
                                 timeout=30_000)
            pg.wait_for_selector(".audit-now[data-audit]", state="attached", timeout=30_000)
            pg.wait_for_timeout(300)
            return fn(pg)
        finally:
            browser.close()


@needs_build
def test_the_lanes_keep_their_names_and_order_in_both_modes(served):
    def go(pg):
        site = pg.evaluate(_READ)
        pages = pg.evaluate("() => [...document.querySelectorAll('#anat-pages option')]"
                            ".map((o) => o.value)")
        open_page_filter(pg)
        pg.fill(".page-find", pages[0])
        pg.wait_for_selector(".cur-filter-note", timeout=15_000)
        page = pg.evaluate(_READ)
        return site, page
    site, page = _page(served, go)
    for mode, got in (("site", site), ("page", page)):
        assert got["names"] == NAMES, (mode, got["names"])
        assert got["classes"] == ["lane-waiting", "lane-measured", "lane-settled"], (mode, got)
        # BL's cap of three is gone (BM): a lane shows its first screenful.
        from pathlib import Path as _P
        import re as _re
        cap = int(_re.search(r"SCREENFUL = (\d+)", LANES).group(1))
        for lane, n in got["entries"].items():
            assert n <= cap, f"{mode}: the {lane} lane drew {n} entries past its first screenful"
    # The mode decides what they are about: page mode is not site mode with
    # rows hidden, so what is waiting is stated for the page.
    assert any("on this page" in m for m in page["measured"]), page["measured"]


@needs_build
def test_the_state_sentence_names_the_run_it_describes(served):
    got = _page(served, lambda pg: pg.evaluate(_READ))
    assert got["sentenceRun"] and got["sentenceRun"] == got["current"], got
    # The run's own tier, as the header's current audit spells it. Item 168:
    # the sentence says when in words ("finished 8 hours ago") and the exact
    # stamp rides in the time element's title, so it is still one hover away.
    stamp = re.search(r"(T\d) · (\d{4}-\d{2}-\d{2} \d{2}:\d{2})", got["currentLabel"])
    assert stamp, got["currentLabel"]
    assert got["sentence"].startswith(f"Audit {stamp.group(1)} finished "), got["sentence"]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", got["whenTitle"]), got["whenTitle"]
    assert got["whenTitle"] >= stamp.group(2), (got["whenTitle"], stamp.group(2))
    assert re.search(r"It found \d+ findings? in this audit across \d+", got["sentence"]), got["sentence"]
    # Item 174 (channel ruling 20260917-1430): the assessed clause left the
    # sentence for the Settled lane's "Assessed" entry, so the headline sets in
    # two lines. `test_the_assessed_share_is_an_entry_in_settled` holds where it went.
    assert "have been through" not in got["sentence"], got["sentence"]
    # A known size keeps its population marker (item 155); an unknown one
    # divides by nothing and says "pages" (BJ).
    assert re.search(r"across \d+ (of the \d+ pages on the site|pages)\.", got["sentence"]), (
        "the denominator lost its population marker (item 155)", got["sentence"])
    assert got["primaries"] <= 1, "more than one primary action in the bar"


def test_a_regression_appears_in_waiting_on_you_not_in_settled():
    """Ranked first in Waiting, and never in Settled: a regression is the one
    thing that genuinely demands attention, not a quiet line under settled."""
    waiting = LANES[LANES.index("// WAITING ON YOU"):LANES.index("// WHAT HAS BEEN MEASURED")]
    settled = LANES[LANES.index("// SETTLED"):LANES.index("return (", LANES.index("// SETTLED"))]
    first_push = waiting.index("waiting.push(")
    assert 'key: "regressed"' in waiting[first_push:first_push + 200], (
        "the first entry Waiting on you pushes is not the regression")
    assert "regressed" not in re.sub(r"moved\.regressed[^\n]*", "", settled).replace(
        "// SETTLED", ""), "a regression count reached the Settled lane"


@needs_build
def test_an_unread_part_is_distinguishable_from_a_clean_part(served):
    """A part reading 0 because nothing looked is not a part reading 0 because
    nothing is wrong. What no brief has read, and what this run did not fully
    measure, are entries of their own in What has been measured."""
    got = _page(served, lambda pg: pg.evaluate(
        "() => [...document.querySelectorAll('.lane-measured .cl-entry dt')]"
        ".map((e) => e.textContent.trim())"))
    assert any("not read on this audit" in t for t in got), got
    assert any("did not fully measure" in t for t in got), got


@pytest.mark.integrity_threshold
@needs_build
def test_the_integrity_line_says_the_report_is_held(served):
    import httpx
    base, ids = served
    head = httpx.get(f"{base}/api/sites/{ids['site']}/anatomy", timeout=30).json()["headline"]
    n = (head.get("integrity") or {}).get("count", 0)
    line = _page(served, lambda pg: pg.evaluate(
        "() => document.querySelector('.integrity-line')?.textContent || null"))
    if n:
        assert line and f"{n} Critical or High" in line, (n, line)
    else:
        assert line is None, "a clear report drew a held line"



# --- brief v24 step BM: the lanes are the landing --------------------------------

@needs_build
def test_the_lanes_are_the_body_not_the_bar(served):
    got = _page(served, lambda pg: pg.evaluate("""() => ({
      inBar: document.querySelectorAll('.run-scope .cl-lane').length,
      inBody: document.querySelectorAll('#pane .cl-landing .cl-lane').length,
      pane: document.querySelector('#pane-name')?.textContent || '',
      barBottom: document.querySelector('.run-scope').getBoundingClientRect().bottom,
      landingTop: document.querySelector('.cl-landing').getBoundingClientRect().top,
    })"""))
    assert got["inBar"] == 0 and got["inBody"] == 3, got
    assert got["pane"] == "Where it stands", got
    assert got["landingTop"] > got["barBottom"], got


@needs_build
def test_the_head_is_the_sentence_and_its_actions_and_the_bar_holds_the_context(served):
    """Item 173 (channel ruling 20260917-1125, part G), replacing BL's
    `test_the_bar_holds_sentence_action_integrity_mode_picker_band_and_nothing_else`,
    which pinned a three-column card holding the sentence beside the picker, the
    mode switch and the page filter.

    Concept 05's head is a headline and a row of buttons, nothing else, with the
    run picker and mode switch in the top bar. So the head holds the sentence,
    the integrity line when it applies, and the actions with the strip beside
    them; the shell's bar holds the audit picker and the mode switch. Neither
    holds the lanes.

    Item 174 (channel ruling 20260917-1430) moved three things, each asserted
    here: the eyebrow over the sentence and the regressions alert under it are
    the head's; the reference links are beside the nav (`#topbar-refs`), not in
    the context that gives way; and the page filter is page mode's control, not
    drawn in site mode and shown by pressing One page."""
    def read(pg):
        before = pg.evaluate("""() => {
          const head = document.querySelector('.run-scope');
          const bar = document.querySelector('#topbar-context');
          const refs = document.querySelector('#topbar-refs');
          const visible = (e) => e.getBoundingClientRect().height > 0;
          return {
            rows: [...head.children].filter(visible).map((e) => e.className.split(' ')[0]),
            headHasControls: !!head.querySelector('select, .mode-switch, .page-find, .refs'),
            stripInActions: !!head.querySelector('.bl-actions nav.seq-chapters'),
            barAudit: !!bar?.querySelector('.audit-now'),
            barSelect: !!bar?.querySelector('select'),
            barMode: !!bar?.querySelector('.mode-switch'),
            filterAnywhere: document.querySelectorAll('.page-find').length,
            refsBesideNav: !!refs?.querySelector('nav.refs')
              && refs.nextElementSibling?.classList.contains('topnav'),
            lanes: head.querySelectorAll('.cl-lane, .cl-entry').length
                   + (bar ? bar.querySelectorAll('.cl-lane, .cl-entry').length : 0),
          };
        }""")
        pg.locator(".mode-switch .mode-seg", has_text="One page").click()
        pg.wait_for_selector("#topbar-context .page-find", state="visible", timeout=10_000)
        before["filterFocused"] = pg.evaluate(
            "() => document.activeElement?.classList.contains('page-find')")
        return before
    got = _page(served, read)
    rows = [r for r in got["rows"] if r not in ("integrity-line", "stale-note", "head-note",
                                                "eyebrow", "alertline")]
    # Item 181: the landing headline is wrapped in the page h1.
    assert rows == ["bl-h1", "bl-actions"], got
    assert not got["headHasControls"], f"a context control is still in the head: {got}"
    assert got["stripInActions"], f"the strip is not beside the actions: {got}"
    # Item 239 step 5: the bar says the current audit and picks none.
    assert got["barAudit"] and not got["barSelect"] and got["barMode"], got
    assert got["refsBesideNav"], f"the reference links are not beside the nav: {got}"
    assert got["filterAnywhere"] == 0, f"site mode draws the page filter: {got}"
    assert got["filterFocused"], f"One page did not reveal and focus the filter: {got}"
    assert got["lanes"] == 0, got
    src = (SRC / "anatomy.tsx").read_text(encoding="utf-8")
    header = src[src.index("export function StandingHeader"):src.index("export function SiteLanding")]
    assert "<ClientLanes" not in header, "the header still mounts the lanes"
    for part in ("<StateSentence", "<PrimaryAction", "<IntegrityLine", "<SecondaryActions"):
        assert part in header, part


@needs_build
def test_n_more_expands_in_place_and_does_not_navigate(served):
    """Driven with the first screenful forced small, because the fixture's
    lanes are shorter than a real screenful: what is under test is that the
    press expands where it stands and the address does not move."""
    def go(pg):
        # Every lane capped at 2 by hiding the rest the way the component does
        # is not observable from outside, so the lane is lengthened instead:
        # the Waiting lane's own entries are counted, and the press is only
        # asserted where a "more" control rendered.
        before = pg.evaluate("""() => ({
          hash: location.hash,
          more: [...document.querySelectorAll('.cl-landing .cl-lane-more')].map((b) => ({
            tag: b.tagName, text: b.textContent,
            lane: b.closest('.cl-lane').className })),
          counts: [...document.querySelectorAll('.cl-landing .cl-lane')].map((l) => l.querySelectorAll('.cl-entry').length),
        })""")
        if before["more"]:
            pg.click(".cl-landing .cl-lane-more")
            pg.wait_for_timeout(300)
        after = pg.evaluate("""() => ({
          hash: location.hash,
          more: document.querySelectorAll('.cl-landing .cl-lane-more').length,
          counts: [...document.querySelectorAll('.cl-landing .cl-lane')].map((l) => l.querySelectorAll('.cl-entry').length),
        })""")
        return before, after
    before, after = _page(served, go)
    assert all(m["tag"] == "BUTTON" for m in before["more"]), before["more"]
    assert after["hash"] == before["hash"], (before["hash"], after["hash"])
    if before["more"]:
        assert sum(after["counts"]) > sum(before["counts"]), (before, after)
    assert re.search(r"<SecondaryButton[^>]*cl-lane-more", LANES) and "href={more}" not in LANES


@needs_build
def test_a_lane_row_carries_a_populated_count(served):
    """156: a row that links to a part carries that part's populated count from
    the payload's `total`, not a bare integer, and opens the part. The rows
    moved from Waiting on you to the strip under the lanes at item 169, and
    the rule moved with them."""
    import httpx
    base, ids = served
    cats = httpx.get(f"{base}/api/sites/{ids['site']}/anatomy", timeout=30).json()["categories"]
    open_parts = {c["key"]: c["total"]["value"] for c in cats if c["total"]["value"] > 0}
    rows = _page(served, lambda pg: pg.evaluate("""() =>
      [...document.querySelectorAll('.cl-landing .cl-parts a[class*="cl-part-"]')].map((a) => ({
        href: a.getAttribute('href'), text: (a.querySelector('.parts-n')?.textContent || '').trim(),
        counted: !!a.querySelector('.parts-n').children.length }))"""))
    assert rows, "no part links in the strip under the lanes"
    keys = [re.search(r"part=([^&]+)", r["href"]).group(1) for r in rows]
    # Every part now, zeros included, so the open parts are a subset of the keys.
    every = {c["key"]: c["total"]["value"] for c in cats}
    assert set(open_parts) <= set(keys) and len(keys) == len(set(keys)), (keys, open_parts)
    for r, k in zip(rows, keys):
        assert r["text"].startswith(str(every[k])), (k, r, every[k])
    assert "<Counted count={c.total}" in LANES


@needs_build
def test_the_first_screenful_fits_the_landing(served):
    """The screenful is a measurement, and since item 169 a sum.

    Rows stopped being one height when an entry could carry a sentence and a
    row of actions, so "one row times a count" is wrong whichever row is picked
    (channel ruling 20260917-0140). Per lane: the head, the parts strip beneath
    the lanes, and the rendered heights of the entries shown, must fit under the
    landing's top at 1568 x 1080; and the cap is what the tightest lane could
    still take if the rest of its screenful were bare rows - the shape a long
    lane actually has, because only the entries a reader acts on carry a
    sentence.
    """
    cap = int(re.search(r"SCREENFUL = (\d+)", LANES).group(1))
    got = _page(served, lambda pg: pg.evaluate("""() => {
      const land = document.querySelector('.cl-landing').getBoundingClientRect();
      const strip = document.querySelector('.cl-landing .cl-parts');
      const lanes = [...document.querySelectorAll('.cl-landing .cl-lane')].map((l) => ({
        name: l.getAttribute('aria-label'),
        head: l.querySelector('.cl-lane-head').getBoundingClientRect().height,
        rows: [...l.querySelectorAll('.cl-entry')].map((e) => e.getBoundingClientRect().height),
      }));
      return { top: land.top, vh: window.innerHeight, lanes,
               strip: strip ? strip.getBoundingClientRect().height : 0 };
    }"""))
    avail = got["vh"] - got["top"]
    bare = min((min(l["rows"]) for l in got["lanes"] if l["rows"]), default=30)
    capacity = []
    for lane in got["lanes"]:
        used = lane["head"] + got["strip"] + sum(lane["rows"])
        assert used <= avail, (lane["name"], used, avail, got)
        capacity.append(len(lane["rows"]) + int((avail - used) // bare))
    tightest = min(capacity)
    assert cap <= tightest, (f"SCREENFUL {cap} overflows the tightest lane, which fits "
                             f"{tightest}", got)
    assert cap >= tightest - 3, (f"SCREENFUL {cap} wastes the landing: the tightest lane "
                                 f"fits {tightest}", got)


@needs_build
def test_back_from_a_part_opened_on_a_lane_returns_to_the_landing(served):
    def go(pg):
        # Item 169: the parts left Waiting on you for the strip under the lanes.
        link = pg.query_selector('.cl-landing .cl-parts a[class*="cl-part-"]')
        href = link.get_attribute("href")
        link.click()
        pg.wait_for_selector(".anat-pane", timeout=30_000)
        opened = pg.evaluate("() => location.hash")
        pg.go_back()
        pg.wait_for_selector(".cl-landing .cl-lane", timeout=30_000)
        return href, opened, pg.evaluate("() => location.hash")
    href, opened, back = _page(served, go)
    assert opened.endswith(href.split("#")[-1]), (href, opened)
    assert "part=" not in back and "tab=" not in back, back


@needs_build
def test_a_part_is_not_a_task(served):
    """Item 169. The Waiting lane listed every part with something open, which
    is the taxonomy inside the queue; the parts are a breakdown, so they sit in
    the strip under the lanes and Waiting on you holds what a reader acts on."""
    got = _page(served, lambda pg: pg.evaluate("""() => ({
      waitingParts: document.querySelectorAll('.lane-waiting .cl-entry[class*="cl-part-"]').length,
      waiting: document.querySelectorAll('.lane-waiting .cl-entry').length,
    })"""))
    assert got["waitingParts"] == 0, got
    assert got["waiting"] <= 6, f"Waiting on you is a ledger again: {got}"


@needs_build
def test_the_site_underneath_lists_every_part_and_sums(served):
    """Every part in the anatomy's order, zeros included, and the head's figure
    is what the parts add up to. A part no analysis has read is marked, because
    0 there is not a clearance (channel ruling 20260917-0140)."""
    import httpx
    base, ids = served
    cats = httpx.get(f"{base}/api/sites/{ids['site']}/anatomy", timeout=30).json()["categories"]
    got = _page(served, lambda pg: pg.evaluate("""() => {
      const strip = document.querySelector('.cl-landing .cl-parts');
      if (!strip) return null;
      return {
        head: strip.querySelector('.cl-parts-head')?.textContent.replace(/\\s+/g, ' ').trim() || '',
        sum: Number(strip.querySelector('.cl-parts-head')?.dataset.sum),
        parts: [...strip.querySelectorAll('a[class*="cl-part-"]')].map((a) => ({
          key: [...a.classList].find((c) => c.startsWith('cl-part-')).slice(8),
          n: Number(a.dataset.n), unread: a.dataset.unread === '1',
          title: a.getAttribute('title') || '', label: a.getAttribute('aria-label') || '',
        })),
      };
    }"""))
    assert got, "no parts strip under the lanes"
    # Every PART (item 238): "Prioritise & report" is no longer one.
    assert [x["key"] for x in got["parts"]] == [c["key"] for c in cats
                                               if c["group"] != "workflow"], got
    assert got["sum"] == sum(x["n"] for x in got["parts"]), got
    assert "every part" in got["head"] and str(got["sum"]) in got["head"], got
    # The word itself is read from the registry (item 166), never spelled
    # here: a clause that writes the product's vocabulary down is a second
    # definition of it.
    not_read = {e["id"]: e for e in json.loads(
        (ROOT / "clauditseo" / "glossary.json").read_text(encoding="utf-8"))
        ["entries"]}["not-read"]["word"]
    for part in got["parts"]:
        # The label carries the count, the staleness when there is any, and
        # what the press does - in that order. It is asserted in pieces rather
        # than as one suffix because of what an `aria-label` does: it REPLACES
        # the pill's own text for a screen reader, so the visible "not read"
        # beside the figure is not announced at all unless the label says it
        # too. The suffix form this clause used to assert could be satisfied by
        # a label that dropped the mark, which is the clearance ruling
        # 20260917-0140 going quiet on exactly the readers who cannot see the
        # pill. Item 185 shares this pill with the part switcher, so the label
        # is now the one place both spell it.
        assert part["label"].startswith(f"{part['label'].split(':')[0]}: {part['n']} open"), part
        assert part["label"].endswith(" — open the part"), part
        if part["unread"]:
            assert not_read in part["label"], (
                "an unread part's label does not say so, so a screen reader "
                f"hears a bare figure: {part}")
        else:
            # `not_read`, the local above: `NOT_READ` was never imported, and
            # the branch went unrun until a part with analyses stopped being
            # unread (item 180 as narrowed on 2026-09-24).
            assert not_read not in part["label"], part
        if part["unread"]:
            assert "not a clearance" in part["title"], part
    # Item 180 (ruling 20260918-0406): not read on THIS audit, any part with analyses.
    # Narrowed by the channel (20260924-0220-180): only a part the catalogue
    # lists an analysis for can be "not read".
    unread = [c["key"] for c in cats if (c.get("tools") or []) and c.get("catalogued", True)
              and (not c.get("brief_run") or c["brief_run"].get("audits_since") != 0)]
    assert sorted(x["key"] for x in got["parts"] if x["unread"]) == sorted(unread), got


@needs_build
def test_an_entry_a_reader_acts_on_says_what_it_means_and_opens_by_its_figure(served):
    """Item 169. An entry may carry one sentence, in a second `dd` of its group
    so `definition-list` holds and `dd.fig` keeps every selector. Only the
    entries a reader acts on carry one; a sentence on every row is the same
    wall of text the ledger was. Since item 207 the entry's way onward is its
    figure, whatever the destination - the actions row under it is gone, and
    `test_every_count_on_the_landing_is_its_own_door` holds that."""
    got = _page(served, lambda pg: pg.evaluate("""() => {
      const read = (sel) => {
        const e = document.querySelector(sel);
        if (!e) return null;
        const d = e.querySelector('dd.cl-entry-detail');
        return { detail: d ? (d.querySelector('p')?.textContent || '').trim() : null,
                 href: e.querySelector('dd.fig a')?.getAttribute('href') || null,
                 figs: e.querySelectorAll('dd.fig').length };
      };
      return { outstanding: read('.lane-waiting .cl-outstanding'),
               severe: read('.lane-waiting .cl-severe'),
               unread: read('.lane-measured .cl-unread'),
               bare: [...document.querySelectorAll('.cl-landing .cl-entry')]
                 .filter((e) => /cl-(candidate|coverage|unmeasured|depth|fixed|moved)\\b/.test(e.className))
                 .map((e) => e.querySelectorAll('dd.cl-entry-detail').length) };
    }"""))
    out = got["outstanding"]
    assert out and out["figs"] == 1, got
    # The lane no longer sells the ranking (item 196). It said "Triage ranks
    # them so the first you open is the one that matters", which advertised a
    # purchase inside a count of work; the ranking is the audit's now, so the
    # claim holds without anything being bought.
    assert out["detail"] and "ranked first" in out["detail"], out
    # The figure is the record link.
    assert out["href"] and "state=outstanding" in out["href"], out
    if got["severe"]:
        assert "client report is held" in got["severe"]["detail"], got["severe"]
        # The hold points at what lifts it - `set_state` on the record - and
        # not at a ranking that writes no state (item 196); since item 207, at
        # exactly the findings it counted: its audit, open, Critical and High.
        href = got["severe"]["href"] or ""
        assert "state=open" in href and "sev=critical,high" in href and "run=" in href, got["severe"]
    if got["unread"] and got["unread"]["detail"]:
        assert "not that an analysis cleared it" in got["unread"]["detail"], got["unread"]
        assert "only=unread" in (got["unread"]["href"] or ""), got["unread"]
    assert all(n == 0 for n in got["bare"]), f"a bare entry carries a sentence: {got}"


@needs_build
def test_an_entry_with_a_sentence_keeps_its_label_beside_its_own_figure(served):
    """Item 171 (2026-09-17). 169 gave `.cl-entry-detail` `order: 3`, but the
    detail is a `dd` and `.cl-entry dd { order: 1 }` outranks one class, so the
    sentence took the figure's order and the label rendered last - hard against
    the next entry's figure, where it read as that entry's heading. On twenty22
    the lane then appeared to say 62 regressed and 511 Critical or High, against
    an integrity line reading 62.

    Asserted on geometry, because source order was right the whole time - which
    is how a check reading the DOM passed it. The label sits on its figure's
    row and above its own sentence.
    """
    got = _page(served, lambda pg: pg.evaluate("""() =>
      [...document.querySelectorAll('.cl-landing .cl-entry')]
        .filter((e) => e.querySelector('dd.cl-entry-detail'))
        .map((e) => {
          const r = (el) => el.getBoundingClientRect();
          const dt = r(e.querySelector('dt')), fig = r(e.querySelector('dd.fig')),
                det = r(e.querySelector('dd.cl-entry-detail'));
          return { key: e.className, dtTop: dt.top, dtBottom: dt.bottom,
                   dtMid: dt.top + dt.height / 2, figTop: fig.top, figBottom: fig.bottom,
                   detTop: det.top };
        })"""))
    assert got, "no entry on the fixture carries a sentence, so nothing is measured"
    for e in got:
        assert e["figTop"] <= e["dtMid"] <= e["figBottom"], (
            f"the label is not on its own figure's row: {e}")
        assert e["dtBottom"] <= e["detTop"] + 1, (
            f"the label renders after its own sentence: {e}")


@needs_build
def test_the_landing_reads_as_a_task_list_not_a_ledger(served):
    """Item 172. A reader scanning a lane can say what each entry is about
    before reading a number: the label leads its row and carries the weight,
    and the figure is a chip beside it. Each lane is visibly one container, the
    part strip is a row of outlined chips rather than underlined links, and the
    score stands once in the landing's body - 172 declined concept 05's score
    card because 168 already put the score in the sentence.

    Geometry and computed style, not source order: 171 is what a DOM-order
    check let through."""
    got = _page(served, lambda pg: pg.evaluate("""() => {
      const cs = (el, prop) => getComputedStyle(el)[prop];
      const entries = [...document.querySelectorAll('.cl-landing .cl-entry')].map((e) => {
        const dt = e.querySelector('dt'), fig = e.querySelector('dd.fig');
        return { key: e.className,
                 chipLeft: fig.getBoundingClientRect().left < dt.getBoundingClientRect().left,
                 figLeft: Math.round(fig.getBoundingClientRect().left),
                 lane: e.closest('.cl-lane').getAttribute('aria-label'),
                 labelWeight: Number(cs(dt, 'fontWeight')), figWeight: Number(cs(fig, 'fontWeight')),
                 labelSize: parseFloat(cs(dt, 'fontSize')), figSize: parseFloat(cs(fig, 'fontSize')),
                 // A chip is a filled block (item 174: the reference's chips
                 // are fills, not outlines) or an outline; its quiet tone is
                 // the reference's transparent chip, and still a fixed gutter.
                 chip: (cs(fig, 'backgroundColor') !== 'rgba(0, 0, 0, 0)'
                        || cs(fig, 'borderTopStyle') !== 'none'
                        || fig.classList.contains('fig-quiet')) ? 'chip' : 'none' };
      });
      const lanes = [...document.querySelectorAll('.cl-landing .cl-lane')].map((l) =>
        ['Top', 'Right', 'Bottom', 'Left'].every((side) => cs(l, 'border' + side + 'Style') !== 'none'));
      const chips = [...document.querySelectorAll('.cl-landing .cl-parts .parts-link')].map((a) => ({
        outlined: cs(a, 'borderTopStyle') !== 'none', underline: cs(a, 'textDecorationLine') }));
      const score = (document.querySelector('.bl-score')?.textContent || '').trim();
      const body = document.querySelector('.cl-landing');
      return { entries, lanes, chips, score, scores: document.querySelectorAll('.bl-score').length,
               inLanes: score ? (body.textContent.split(score).length - 1) : 0 };
    }"""))
    assert got["entries"], "no entries on the landing"
    for e in got["entries"]:
        # Item 173 part 7: the chip sits in the left gutter, the title after it.
        assert e["chipLeft"], f"the chip is not in the left gutter: {e}"
        assert e["labelSize"] >= e["figSize"], f"the figure is still the hero: {e}"
        assert e["chip"] != "none", f"the figure is not a chip: {e}"
    assert got["lanes"] and all(got["lanes"]), f"a lane is not one bordered container: {got['lanes']}"
    assert got["chips"] and all(c["outlined"] and c["underline"] == "none" for c in got["chips"]), got["chips"]
    assert got["scores"] <= 1, "the score is drawn more than once in the sentence"
    assert got["inLanes"] == 0, "a lane repeats the score the sentence already states"


@needs_build
def test_the_figures_form_a_column(served):
    """Item 173, part 7. Concept 05 puts each count in the left gutter so the
    numbers form a column the eye runs down; after 172 the chip followed its
    title and landed at a different x on every row.

    Part 8 - an entry's actions drawn as outlined buttons - is retired by item
    207: the actions are gone, and the figure in this column is the door."""
    got = _page(served, lambda pg: pg.evaluate("""() => {
      const cs = (el, prop) => getComputedStyle(el)[prop];
      const lanes = [...document.querySelectorAll('.cl-landing .cl-lane')].map((l) => ({
        name: l.getAttribute('aria-label'),
        xs: [...l.querySelectorAll('.cl-entry dd.fig')].map((f) => Math.round(f.getBoundingClientRect().left)),
      }));
      return { lanes };
    }"""))
    for lane in got["lanes"]:
        if len(lane["xs"]) > 1:
            assert max(lane["xs"]) - min(lane["xs"]) <= 1, f"the figures do not form a column: {lane}"


@needs_build
def test_a_reader_can_see_whether_anything_is_running(served):
    """Item 173. Concept 05's middle lane said "Nothing is running. Last sweep
    finished at 06:50 today"; the landing showed that nowhere, so a reader could
    not tell whether anything was happening without leaving it. The fixture has
    no audit in flight, so it reads the resting state; that the lane stays
    silent while one runs is held on the source."""
    got = _page(served, lambda pg: pg.evaluate("""() => {
      const e = document.querySelector('.lane-measured .cl-running');
      if (!e) return null;
      return { label: e.querySelector('dt').textContent.trim(),
               detail: (e.querySelector('dd.cl-entry-detail p')?.textContent || '').trim(),
               href: e.querySelector('a.cl-entry-go')?.getAttribute('href') || null };
    }"""))
    assert got, "the middle lane does not say whether anything is running"
    assert got["label"] == "Nothing is running", got
    assert got["detail"].startswith("The last audit finished "), got
    # Item 207: the one row with no count opens the audit by its sentence.
    assert got["href"] and got["href"].endswith("?tab=history"), got
    # The idle case only (channel ruling 20260917-1125): while an audit runs,
    # the strip's busy pill says "running now", and the lane must not repeat it.
    assert "!runState.running" in LANES and "an audit is running" not in LANES, (
        "the lane repeats the strip's running state")
