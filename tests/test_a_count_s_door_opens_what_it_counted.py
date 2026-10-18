"""A link from a count lands on exactly what it counted (item 252).

Items 202 and 207 made the count the door. The round-2 screen audits found
four doors that opened a smaller room than the count:

- the hold counts open AND regressed Critical and High (`open_severe`) and its
  door opened `state=open`, so a regressed one was counted and not shown;
- the landing's primary action read 24 over a catalogue listing 23, because
  the step filtered `available` for itself and counted the client plan;
- "Parts this audit did not fully measure" had no door at all;
- every analysis row on Reports opened the run page, which draws no analysis;
- Home held neither the hold nor a way to the rows behind it.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pytest

from clauditseo.persistence import runs
from tests.needs_build import needs_build
from tests.test_a11y_rendered import served  # noqa: F401  (module fixture)

pytestmark = needs_build

UI = Path(__file__).resolve().parents[1] / "dashboard" / "src"
REGRESSED_FP = "door-252-regressed-high"


def _plant_a_regressed_high(ids):
    """The fixture holds no Critical or High. One High, regressed: the state
    the hold counted and its door left out."""
    from clauditseo.persistence.repo import create_id, now_iso
    conn = sqlite3.connect(ids["db"])
    run = conn.execute("SELECT id FROM audit_runs WHERE site_id=? AND status='complete'"
                       " ORDER BY started_at DESC LIMIT 1", (ids["site"],)).fetchone()[0]
    with conn:
        conn.execute(
            "INSERT INTO findings (id, run_id, dimension, check_id, severity, source, summary,"
            " affected_urls, fingerprint, created_at) VALUES (?, ?, 'TEC', 'noindex-page', 'high',"
            " 'deterministic', 'fixed once and back', ?, ?, ?)",
            (create_id(), run, json.dumps(["https://fixture.test/p1"]), REGRESSED_FP, now_iso()))
        conn.execute("INSERT INTO finding_states (site_id, fingerprint, state, changed_by_run,"
                     " updated_at) VALUES (?, ?, 'regressed', ?, ?)",
                     (ids["site"], REGRESSED_FP, run, now_iso()))
    conn.close()


def _unplant(ids):
    conn = sqlite3.connect(ids["db"])
    with conn:
        conn.execute("DELETE FROM finding_states WHERE fingerprint=?", (REGRESSED_FP,))
        conn.execute("DELETE FROM findings WHERE fingerprint=?", (REGRESSED_FP,))
    conn.close()


def _browse(served, fn):
    from playwright.sync_api import sync_playwright
    base, ids = served
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page(viewport={"width": 1568, "height": 1080})
        try:
            pg.goto(f"{base}/#/sites/{ids['site']}", wait_until="load")
            pg.wait_for_selector(".cl-landing .cl-lane-row", timeout=30_000)
            pg.wait_for_selector(".audit-now[data-audit]", state="attached", timeout=30_000)
            pg.wait_for_timeout(300)
            return fn(pg, base, ids)
        finally:
            browser.close()


SHOWN = """() => { const t = document.querySelector('.record-shape > span.muted').textContent;
                   const m = t.match(/(\\d+) findings?/) || t.match(/^(\\d+) of/);
                   return m ? Number(m[1]) : -1; }"""


@pytest.mark.integrity_threshold
def test_the_hold_reads_n_and_its_door_shows_n_rows_with_a_regressed_high(served):
    """The item's guard, driven: with one regressed High on the site the hold
    reads N and the table its door opens has N rows."""
    base, ids = served
    _plant_a_regressed_high(ids)
    try:
        conn = sqlite3.connect(ids["db"])
        conn.row_factory = sqlite3.Row
        want = runs.open_severe(conn, ids["site"])["count"]
        conn.close()

        def go(pg, base, ids):
            fig = pg.evaluate("() => document.querySelector('.cl-landing .cl-severe dd.fig').textContent.trim()")
            href = pg.evaluate("() => document.querySelector('.cl-landing .cl-severe dd.fig a').getAttribute('href')")
            pg.click(".cl-landing .cl-severe dd.fig a.fig-link")
            pg.wait_for_selector(".state-filters .chip", timeout=15_000)
            pg.wait_for_timeout(800)
            return fig, href, pg.evaluate(SHOWN), pg.evaluate("""() => ({
              state: [...document.querySelectorAll('.state-filters .chip[aria-pressed="true"]')]
                       .map((c) => c.dataset.state),
              sev: [...document.querySelectorAll('.severity-filters .chip[aria-pressed="true"]')]
                       .map((c) => c.dataset.severity),
              regressed: [...document.querySelectorAll('table.findings')]
                       .some((t) => /fixed once and back|regressed/i.test(t.textContent)) })""")
        fig, href, shown, drawn = _browse(served, go)
    finally:
        _unplant(ids)
    assert want >= 1, "the planted High is not counted by the hold"
    assert int(fig) == want, f"the hold reads {fig} where the record holds {want}"
    assert "state=open,regressed" in href and "sev=critical,high" in href, href
    assert shown == want, (
        f"the hold counts {want} and its door's table shows {shown}: a regressed "
        "Critical or High is counted and not shown")
    assert drawn["state"] == ["outstanding"], (
        f"the list is not drawn as the chip that is its set: {drawn}")
    # A severity with no row anywhere draws no chip (item 201): the fixture
    # holds no Critical, so High is the one pressed.
    assert "high" in drawn["sev"] and set(drawn["sev"]) <= {"critical", "high"}, drawn


def test_a_state_list_that_is_no_chips_set_is_still_a_filter(served):
    """`?state=` takes a comma list as `?sev=` does. One that is not a chip's
    own set presses no chip and filters to those states."""
    def go(pg, base, ids):
        site = pg.evaluate(f"async () => (await fetch('/api/sites/{ids['site']}')).json()")
        pg.goto(f"{base}/#/sites/{ids['site']}?tab=all&state=fixed,open")
        pg.wait_for_selector(".state-filters .chip", timeout=15_000)
        pg.wait_for_timeout(800)
        return site["states"], pg.evaluate(SHOWN), pg.evaluate(
            "() => document.querySelectorAll('.state-filters .chip[aria-pressed=\"true\"]').length")
    states, shown, pressed = _browse(served, go)

    def is_note(s):
        if s.get("coverage_note") is not None:
            return bool(s["coverage_note"])
        return s["severity"] == "info" and bool(re.search(r"-not-assessed$|-coverage$", s["check_id"]))
    want = [s for s in states if not is_note(s) and s["state"] in ("open", "fixed")]
    assert want, "the fixture holds neither state"
    assert shown == len(want), f"`state=fixed,open` shows {shown} of {len(want)}"
    assert pressed == 0, "a list that is no chip's set pressed a chip"


def test_the_primary_action_counts_what_the_catalogue_lists(served):
    """One counting function per figure and its door. The step, the lane's
    fallback and a part's "Run the N" all read the catalogue's own list."""
    anatomy = (UI / "anatomy.tsx").read_text(encoding="utf-8")
    lanes = (UI / "client_lanes.tsx").read_text(encoding="utf-8")
    catalogue = (UI / "catalogue.tsx").read_text(encoding="utf-8")
    assert "const notRun = notRunCount(lanes) ?? 0;" in anatomy, (
        "the Analyses step counts for itself again")
    for name, src in (("anatomy.tsx", anatomy), ("client_lanes.tsx", lanes)):
        assert not re.search(r"available\s*(\?\?\s*\[\]\))?\s*\.filter\(", src), (
            f"{name} filters `available` for itself: a second count of the analyses not run")
    assert "runnableNow(lanes ? notRunList(lanes) : [])" in anatomy, (
        'a part\'s "Run the N not run" is not the catalogue\'s population')
    assert "const canRunNow = runnableNow(analyses);" in catalogue

    def go(pg, base, ids):
        fig = pg.evaluate("""() => { const f = document.querySelector('.cl-landing .cl-depth dd.fig');
                                     return f ? f.textContent.trim() : null; }""")
        primary = pg.evaluate("""() => [...document.querySelectorAll('.bl-actions a, .bl-actions button')]
                                        .map((b) => b.textContent.trim())""")
        pg.goto(f"{base}/#/sites/{ids['site']}?tab=analyses&only=not-run")
        pg.wait_for_selector(".catalogue-only", timeout=15_000)
        pg.wait_for_timeout(800)
        return fig, primary, pg.evaluate(
            "() => document.querySelectorAll('.catalogue-shop tbody tr.crow').length")
    fig, primary, rows = _browse(served, go)
    assert fig is not None and int(fig) == rows, (fig, rows)
    counted = [m.group(1) for b in primary
               for m in [re.search(r"catalogue\s*·\s*(\d+)", b)] if m]
    for n in counted:
        assert int(n) == rows, (
            f"the primary action reads {n} and the catalogue it opens lists {rows}")


def test_the_unmeasured_parts_figure_is_a_door_to_those_parts(served):
    def go(pg, base, ids):
        got = pg.evaluate("""() => { const f = document.querySelector('.cl-landing .cl-unmeasured dd.fig');
          const a = f.querySelector('a');
          return { fig: f.textContent.trim(), href: a && a.getAttribute('href'), cls: f.className }; }""")
        if not got["href"]:
            return got, None
        pg.click(".cl-landing .cl-unmeasured dd.fig a.fig-link")
        pg.wait_for_selector(".catalogue-only", timeout=15_000)
        pg.wait_for_timeout(800)
        return got, pg.evaluate("""() => ({
          note: document.querySelector('.catalogue-only').textContent,
          parts: document.querySelectorAll('.catalogue-shop .crow-part').length })""")
    got, opened = _browse(served, go)
    if int(got["fig"]) == 0:
        assert not got["href"] and "fig-plain" in got["cls"], (
            f"a door onto nothing, or a zero drawn as a figure: {got}")
        return
    assert got["href"] and "only=unmeasured" in got["href"], (
        f"the figure counts {got['fig']} parts and opens nothing: {got}")
    assert opened["parts"] == int(got["fig"]), (
        f"the figure says {got['fig']} parts and the press shows {opened['parts']}: {opened}")
    assert "did not fully measure" in opened["note"], opened


def test_a_count_with_no_door_is_not_drawn_as_a_figure(served):
    got = _browse(served, lambda pg, *_: pg.evaluate("""() =>
      [...document.querySelectorAll('.cl-landing .cl-entry dd.fig')].map((f) => ({
        key: f.parentElement.className, linked: Boolean(f.querySelector('a')),
        plain: f.classList.contains('fig-plain'),
        bg: getComputedStyle(f).backgroundColor, weight: getComputedStyle(f).fontWeight }))"""))
    assert any(e["linked"] for e in got) and any(not e["linked"] for e in got), got
    for e in got:
        assert e["plain"] == (not e["linked"]), f"door and drawing disagree: {e}"
        if not e["linked"]:
            assert e["bg"] in ("rgba(0, 0, 0, 0)", "transparent") and int(e["weight"]) <= 400, (
                f"a count that opens nothing is drawn as a figure: {e}")


# ---- Reports ------------------------------------------------------------------

def test_an_analysis_row_says_where_it_is_read():
    """`site_reports` stamps the part and whether that part's page draws the
    row: the newest per analysis (and page), and only where a page exists."""
    row = lambda tool, page=None: {"tool_id": tool, "page_url": page}   # noqa: E731
    entry = {"part": "crawl", "part_label": "Crawl & sitemaps"}
    drawn: set = set()
    first = runs._where_read(entry, row("crawl-health"), drawn)
    again = runs._where_read(entry, row("crawl-health"), drawn)
    assert first == {"part": "crawl", "part_label": "Crawl & sitemaps", "shown": True}
    assert again["shown"] is False, "an older analysis is not what the part page draws"
    # A page-scoped analysis is read on its page's dossier, per page.
    assert runs._where_read(entry, row("onpage", "https://x.test/a"), drawn)["shown"] is True
    assert runs._where_read(entry, row("onpage", "https://x.test/b"), drawn)["shown"] is True
    assert runs._where_read(entry, row("onpage", "https://x.test/a"), drawn)["shown"] is False
    # Triage and the client plan write to no part: no page draws them.
    for partless in ({"part": "none"}, {"part": "report"}, None):
        got = runs._where_read(partless, row(f"t{partless}"), drawn)
        assert got["part"] is None and got["shown"] is False, got


def test_no_analysis_row_on_reports_opens_the_run_page(served):
    source = (UI / "reports.tsx").read_text(encoding="utf-8")
    assert "#/runs/${r.run_id}" not in source, (
        "an analysis row still opens the run page, which draws no analysis")

    def go(pg, base, ids):
        payload = pg.evaluate(f"async () => (await fetch('/api/sites/{ids['site']}/reports')).json()")
        pg.goto(f"{base}/#/sites/{ids['site']}/reports")
        pg.wait_for_selector(".view-title", timeout=15_000)
        pg.wait_for_timeout(600)
        if pg.query_selector("details.analyses-all"):
            pg.evaluate("() => { document.querySelector('details.analyses-all').open = true; }")
        return payload, pg.evaluate("""() => [...document.querySelectorAll('td.rep-open')].map((td) => ({
          href: td.querySelector('a') ? td.querySelector('a').getAttribute('href') : null,
          text: td.textContent.trim() }))""")
    payload, cells = _browse(served, go)
    assert len(cells) == len(payload["reports"]), (len(cells), len(payload["reports"]))
    for r, cell in zip(payload["reports"], cells):
        assert "part" in r and "shown" in r, r
        if r["shown"]:
            assert cell["href"] and "#/runs/" not in cell["href"], cell
            assert ("/dossier/" in cell["href"]) if r["page_url"] else (
                f"part={r['part']}" in cell["href"]), (r, cell)
        else:
            assert cell["href"] is None and cell["text"], (
                f"a row no page draws has a door, or says nothing: {r} {cell}")


# ---- Home ---------------------------------------------------------------------

@pytest.mark.integrity_threshold
def test_home_carries_the_hold_as_a_door_to_the_same_rows(served):
    base, ids = served
    _plant_a_regressed_high(ids)
    try:
        def go(pg, base, ids):
            overview = pg.evaluate("async () => (await fetch('/api/overview')).json()")
            pg.goto(f"{base}/#/")
            pg.wait_for_selector(f".home-card[data-site='{ids['site']}']", timeout=15_000)
            pg.wait_for_timeout(400)
            return overview, pg.evaluate(f"""() => {{
              const c = document.querySelector(".home-card[data-site='{ids['site']}'] .home-card-hold");
              const a = c && c.querySelector('a');
              return c && {{ text: c.textContent.trim(), href: a && a.getAttribute('href') }}; }}""")
        overview, card = _browse(served, go)
        conn = sqlite3.connect(ids["db"])
        conn.row_factory = sqlite3.Row
        want = runs.open_severe(conn, ids["site"])["count"]
        conn.close()
    finally:
        _unplant(ids)
    row = next(s for s in overview["sites"] if s["site_id"] == ids["site"])
    assert row["severe_open"] == want >= 1, (row.get("severe_open"), want)
    assert card, "Home does not say the client report is held"
    assert f"{want} Critical or High to assess" in card["text"], card
    assert card["href"] == f"#/sites/{ids['site']}?tab=all&state=open,regressed&sev=critical,high", card
