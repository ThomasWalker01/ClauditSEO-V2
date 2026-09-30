"""Every count on the landing is its own door, to exactly what it counted (item 207).

The operator, on the landing board: "The remaining two home page items have
conflicting click locations for information." The board had two conventions:
a figure was the link when its destination was the record, and a button under
the row was the link for anywhere else - "Open the record", "Open the
catalogue", "Open the audit". Two places to press, on one board. And a linked
figure was drawn exactly as a plain one until the pointer was on it.

The fix is not "turn the buttons into figure links", because F-11 - held by
`test_a_headline_figure_reaches_what_it_counts` - says a linked figure opens
exactly what it counted, and two of the three buttons opened more:

- the hold counts ONE audit's open Critical and High; the record's
  `state=open` is every audit's open findings of every severity (7 against 102
  on stored twenty22);
- "Parts not read" counts parts; the catalogue listed analyses, read and not.

So each destination was narrowed first - the record by `run=` and `sev=`, the
catalogue by `only=` - and only then did the figure become the door. Pressing
a door and counting what arrives is therefore the invariant, and it is what
most of this file does. The first press of the unread door counted 17 parts
for a figure of 18: "Prioritise & report" is counted unread and has no row in
the catalogue. The old button had the same gap and nothing to show it.
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.test_a11y_rendered import served  # noqa: F401  (module fixture)
from tests.needs_build import needs_build

pytestmark = needs_build

UI = Path(__file__).resolve().parents[1] / "dashboard" / "src"


def _browse(served, fn, width=1568):
    from playwright.sync_api import sync_playwright
    base, ids = served
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page(viewport={"width": width, "height": 1080})
        try:
            pg.goto(f"{base}/#/sites/{ids['site']}", wait_until="load")
            pg.wait_for_selector(".cl-landing .cl-lane-row", timeout=30_000)
            pg.wait_for_selector(".audit-now[data-audit]", state="attached", timeout=30_000)
            pg.wait_for_timeout(300)
            return fn(pg, base, ids)
        finally:
            browser.close()


ENTRIES = """() => [...document.querySelectorAll('.cl-landing .cl-entry')].map((e) => {
  const fig = e.querySelector('dd.fig');
  const a = fig.querySelector('a');
  return {
    key: [...e.classList].find((c) => c.startsWith('cl-') && c !== 'cl-entry'),
    fig: fig.textContent.trim(),
    href: a ? a.getAttribute('href') : null,
    doors: [...e.querySelectorAll('a, button')].map((x) => x.className),
    acts: e.querySelectorAll('.cl-entry-acts').length,
    deco: getComputedStyle(a || fig).textDecorationLine,
  };
})"""


def test_no_row_on_the_landing_has_a_second_door(served):
    """One place to press per row: the figure, or - on the one row with no
    count - its sentence. A row with a button under it is the finding."""
    got = _browse(served, lambda pg, *_: pg.evaluate(ENTRIES))
    assert got, "the landing drew no entries"
    assert not any(e["acts"] for e in got), (
        f"a row still carries an actions row under it: {got}")
    for e in got:
        assert len(e["doors"]) <= 1, f"a row has more than one place to press: {e}"
        if not e["doors"]:
            continue
        if e["key"] == "cl-running":
            assert e["doors"] == ["cl-entry-go"], e
        else:
            assert e["href"] and e["doors"] == ["fig-link"], (
                f"a row's door is not its figure: {e}")
    source = (UI / "client_lanes.tsx").read_text(encoding="utf-8")
    assert "cl-entry-acts" not in source and "actions: act(" not in source, (
        "the second convention is still in the lanes' source")


def test_a_count_that_opens_something_looks_like_it_before_the_pointer_arrives(served):
    """Hover-only drew "Fixed to date 50" (a door) and "Assessed 1" (not one)
    identically. On a board where some counts open things and some do not,
    the difference has to be visible at rest."""
    got = _browse(served, lambda pg, *_: pg.evaluate(ENTRIES))
    linked = [e for e in got if e["href"]]
    plain = [e for e in got if not e["href"]]
    assert linked and plain, f"the fixture needs both kinds to compare: {got}"
    assert all("underline" in e["deco"] for e in linked), (
        f"a linked figure is not marked as one at rest: {linked}")
    assert not any("underline" in e["deco"] for e in plain), (
        f"a figure that opens nothing is drawn as though it did: {plain}")


def _press(pg, key: str) -> str:
    fig = pg.evaluate(f"() => document.querySelector('.cl-landing .{key} dd.fig').textContent.trim()")
    pg.click(f".cl-landing .{key} dd.fig a.fig-link")
    pg.wait_for_selector(".catalogue-only", timeout=15_000)
    pg.wait_for_timeout(800)
    return fig


def test_the_parts_not_read_open_as_that_many_parts(served):
    def go(pg, *_):
        fig = _press(pg, "cl-unread")
        return fig, pg.evaluate("""() => ({
          note: document.querySelector('.catalogue-only').textContent,
          parts: document.querySelectorAll('.catalogue-shop .crow-part').length })""")
    fig, got = _browse(served, go)
    assert got["parts"] == int(fig), (
        f"the figure says {fig} parts are not read and the press shows "
        f"{got['parts']}: {got}")
    assert f"the {fig} part" in got["note"], got


def test_the_analyses_not_run_open_as_that_many_rows(served):
    def go(pg, *_):
        fig = _press(pg, "cl-depth")
        return fig, pg.evaluate("""() => ({
          rows: document.querySelectorAll('.catalogue-shop tbody tr.crow').length,
          read: document.querySelectorAll('.catalogue-shop tbody tr.crow-read').length })""")
    fig, got = _browse(served, go)
    assert got["rows"] == int(fig), (
        f"the figure says {fig} analyses have not run and the press shows "
        f"{got['rows']} rows: {got}")
    assert got["read"] == 0, f"an analysis that has run is listed as not run: {got}"


def test_the_row_with_no_count_opens_the_audit_by_its_sentence(served):
    got = _browse(served, lambda pg, *_: pg.evaluate("""() => {
      const e = document.querySelector('.lane-measured .cl-running');
      const a = e && e.querySelector('a.cl-entry-go');
      return e && { href: a && a.getAttribute('href'), text: a && a.textContent.trim(),
                    h: a && a.getBoundingClientRect().height };
    }"""))
    assert got, "the measured lane does not say whether anything is running"
    assert got["href"] and got["href"].endswith("?tab=history"), got
    assert got["text"].startswith("The last audit finished "), got
    assert got["h"] >= 24, f"the sentence is below the 24 px target: {got}"


EARLIER_FP = "door-earlier-audit-row"


def _plant_an_earlier_audits_row(ids, site, latest_run):
    """One open finding the newest audit did not raise, at a severity it did.

    The fixture's only such rows were the adaptive run-notes of its earlier
    audits, counted as findings until item 238 made them coverage notes - so
    it could no longer tell a narrowing to the audit from none. Planted here,
    and removed after, so no other clause sees it."""
    import json as _json
    import sqlite3
    from clauditseo.persistence.repo import create_id, now_iso
    oldest = site["runs"][-1]["id"]
    assert oldest != latest_run, "the fixture needs an earlier audit"
    # The same check and severity as a row the newest audit did raise, so
    # the planted row sits under the same part and chip - only the audit
    # that raised it differs.
    like = next(s for s in site["states"]
                if s["state"] in ("open", "regressed") and not s.get("coverage_note"))
    conn = sqlite3.connect(ids["db"])
    with conn:
        conn.execute(
            "INSERT INTO findings (id, run_id, dimension, check_id, severity, source, summary,"
            " affected_urls, fingerprint, created_at) VALUES (?, ?, ?, ?, ?,"
            " 'deterministic', 'raised by an earlier audit only', ?, ?, ?)",
            (create_id(), oldest, like["dimension"], like["check_id"], like["severity"],
             # A page that row does not name: one row per check and page.
             _json.dumps([next(u for u in (f"https://fixture.test/p{n}" for n in range(1, 9))
                               if u not in like["affected_urls"])]), EARLIER_FP,
             now_iso()))
        conn.execute("INSERT INTO finding_states (site_id, fingerprint, state, changed_by_run,"
                     " updated_at) VALUES (?, ?, 'open', ?, ?)",
                     (ids["site"], EARLIER_FP, oldest, now_iso()))
    conn.close()


def _unplant(ids):
    import sqlite3
    conn = sqlite3.connect(ids["db"])
    with conn:
        conn.execute("DELETE FROM finding_states WHERE fingerprint=?", (EARLIER_FP,))
        conn.execute("DELETE FROM findings WHERE fingerprint=?", (EARLIER_FP,))
    conn.close()


def test_the_record_narrowed_to_an_audit_shows_exactly_what_that_audit_raised(served):
    """The record half of the hold's door, driven because the fixture holds
    no Critical or High: the same three narrowings on severities it does
    hold, against a count computed without the new endpoint - from the run's
    own findings - so the endpoint is tested rather than trusted."""
    def go(pg, base, ids):
        site = pg.evaluate(f"async () => (await fetch('/api/sites/{ids['site']}')).json()")
        run_id = site["runs"][0]["id"]
        _plant_an_earlier_audits_row(ids, site, run_id)
        site = pg.evaluate(f"async () => (await fetch('/api/sites/{ids['site']}')).json()")
        raised = pg.evaluate(f"""async () => [...new Set((await (await fetch('/api/runs/{run_id}')).json())
                                 .findings.map((f) => f.fingerprint))]""")
        raised = set(raised)

        def is_note(s):
            if s.get("coverage_note") is not None:
                return bool(s["coverage_note"])
            return s["severity"] == "info" and bool(
                re.search(r"-not-assessed$|-coverage$", s["check_id"]))

        outstanding = [s for s in site["states"] if not is_note(s)
                       and s["state"] in ("open", "regressed")]
        sevs = sorted({s["severity"] for s in outstanding if s["fingerprint"] in raised})[:2]
        want = [s for s in outstanding if s["fingerprint"] in raised and s["severity"] in sevs]
        every = [s for s in outstanding if s["severity"] in sevs]

        count = """() => { const t = document.querySelector('.record-shape > span.muted').textContent;
                           const m = t.match(/(\\d+) findings?/) || t.match(/^(\\d+) of/);
                           return m ? Number(m[1]) : -1; }"""
        pg.goto(f"{base}/#/sites/{ids['site']}?tab=all&state=outstanding"
                f"&sev={','.join(sevs)}&raised={run_id}")
        # A hash change on the same page does not re-read the site's states,
        # and the planted row arrived after they were first read.
        pg.reload()
        pg.wait_for_selector(".run-chip", timeout=15_000)
        pg.wait_for_timeout(800)
        narrowed = pg.evaluate(count)
        pressed = pg.evaluate("""() => [...document.querySelectorAll(
          '.severity-filters .chip[aria-pressed="true"]')].map((c) => c.dataset.severity)""")
        pg.click(".run-chip")
        pg.wait_for_selector(".run-chip", state="detached", timeout=10_000)
        pg.wait_for_timeout(500)
        widened = pg.evaluate(count)
        pressed_after = pg.evaluate("""() => [...document.querySelectorAll(
          '.severity-filters .chip[aria-pressed="true"]')].map((c) => c.dataset.severity)""")
        return sevs, len(want), len(every), narrowed, pressed, widened, pressed_after

    try:
        sevs, want, every, narrowed, pressed, widened, pressed_after = _browse(served, go)
    finally:
        _unplant(served[1])
    assert want > 0 and every > want, (
        f"the fixture cannot tell a narrowing from none: {want} of {every}")
    assert narrowed == want, (
        f"narrowed to the audit and to {sevs}, the record shows {narrowed} "
        f"findings where the audit raised {want}")
    assert sorted(pressed) == sorted(sevs), (
        f"`sev=` is not drawn as its chips, so the reader cannot see the filter: {pressed}")
    assert widened == every, (
        f"leaving the audit narrowing did not widen to every audit: {widened} of {every}")
    assert sorted(pressed_after) == sorted(sevs), (
        f"leaving the audit narrowing dropped the severity filter too: {pressed_after}")


def test_the_hold_opens_the_record_at_its_own_severities():
    """The door the fixture cannot press (it holds no Critical or High), held
    on the source: the record link carries both severities the count sums.
    Since item 239 step 7 the count is the site's running record, not one
    audit's, so the link carries no audit narrowing - `raised=` is the
    history view's."""
    source = (UI / "client_lanes.tsx").read_text(encoding="utf-8")
    severe = source[source.index('key: "severe"'):]
    severe = severe[:severe.index("});")]
    assert "heldRecordHref(siteId)" in severe, severe
    hold = (UI / "report_hold.tsx").read_text(encoding="utf-8")
    body = hold[hold.index("export function heldRecordHref"):]
    body = body[:body.index("\n}")]
    assert "state=open&sev=critical,high" in body and "raised=" not in body, body
    # The channel (20260924-0220-202): `run=` is the header's picked audit,
    # and the narrowing must not read it.
    nav = (UI / "nav.ts").read_text(encoding="utf-8")
    narrow = nav[nav.index("export function recordNarrowFromHash"):]
    assert 'q.get("raised")' in narrow and 'q.get("run")' not in narrow[:600], narrow[:600]
    # Item 202: every place that says "held" opens the same rows.
    for f in ("anatomy.tsx", "report_hold.tsx", "reports.tsx"):
        src = (UI / f).read_text(encoding="utf-8")
        assert "?tab=all&state=open`" not in src, f"{f} still opens every open finding"


def test_the_headers_picked_audit_does_not_narrow_the_record(served):
    """The collision the channel found: `?run=` is the header's picked audit
    on every client tab. Carried into the Record it must not narrow it."""
    def go(pg, base, ids):
        run_id = pg.evaluate(f"async () => (await (await fetch('/api/sites/{ids['site']}')).json()).runs[0].id")
        pg.goto(f"{base}/#/sites/{ids['site']}?tab=all&state=outstanding&run={run_id}")
        pg.wait_for_selector(".state-filters .chip", timeout=15_000)
        pg.wait_for_timeout(800)
        return pg.evaluate("() => document.querySelectorAll('.run-chip').length")
    assert _browse(served, go) == 0, "the header's `run=` narrowed the record"
