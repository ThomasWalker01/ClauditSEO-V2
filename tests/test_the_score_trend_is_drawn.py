"""The Score trend block, drawn at the running product.

Brief v16f, part B. The clauses below are the item's own Accept list: the
breaks are rules on the chart rather than a paragraph under it, a point is
joined to the point it reads against and to nothing else, the stretch that
shares the latest basis is shaded, the sentence counts that stretch, a
recovered dimension set is ringed, and the Runs table's last column and its
comparison link name the same partner the chart draws the line to.

**The fixture is the same nine rows the rule is guarded on.** `NINE` and
`_plant` are imported from
`test_a_point_reads_against_the_nearest_same_basis_run.py` rather than copied,
so the drawing and the rule are asserted against one history. A second copy of
Acme's numbers here would be the shape this repository keeps paying for: the
chart could be made to agree with a fixture the engine no longer produces.

**Why the picture needs its own guards at all**, given the engine's are green:
`partner_index` being right says nothing about whether a line is drawn between
those two points, and the count of arcs, rules and shaded rectangles is the
only evidence that it is. DISCIPLINE rule 4 — a selector in a test is not
evidence it matched, so every count below is read off the rendered document.
"""

from __future__ import annotations

import re
from pathlib import Path

import httpx
import pytest

from clauditseo.db.connection import connect
from tests.test_a11y_rendered import DIST
from tests.test_a_point_reads_against_the_nearest_same_basis_run import (
    BREAKS, IN_THE_BAND, LATEST, NINE, PARTNER_OF_LATEST, _plant)
from tests.test_triage_ranks_the_section_rail import _serve

#: How many of Acme's nine had their dimension set recovered rather than
#: recorded — read off the fixture rather than written twice.
RECOVERED = sum(1 for p in NINE if not p["recorded"])


def _site(base: str, name: str, domain: str) -> str:
    client = httpx.post(f"{base}/api/clients", json={"name": name},
                        timeout=30).json()
    return httpx.post(f"{base}/api/clients/{client['id']}/sites",
                      json={"domain": domain}, timeout=30).json()["id"]


@pytest.fixture(scope="module")
def served():
    """Two sites: Acme's nine points, and a site with one.

    The second is the item's own degradation and not a convenience. "One
    scored run: one point, no line, the stands-alone sentence" is a different
    rendering, not a smaller one, and a block that crashed or drew an empty
    axis on it would pass every assertion made about the nine.
    """
    server, thread, db, base = _serve("scoretrend")
    try:
        nine = _site(base, "Acme", "www.acme.com.au")
        alone = _site(base, "Acme", "alone.acme.com.au")
        conn = connect(db)
        ids = [_plant(conn, nine, p) for p in NINE]
        _plant(conn, alone, NINE[LATEST])
        conn.close()
        yield base, {"nine": nine, "alone": alone, "ids": ids}
    finally:
        server.should_exit = True
        thread.join(timeout=10)


# --- the payload the drawing is made from --------------------------------

def test_the_site_payload_carries_the_partner_and_the_key(served):
    """The four fields the chart draws from reach the client.

    `site_trend` computing them is one thing and `/api/sites/{id}` serving
    them is another: the trend is embedded in the site payload by a separate
    line, and a field added to the reader has been dropped by a serialiser
    before now.
    """
    base, sites = served
    trend = httpx.get(f"{base}/api/sites/{sites['nine']}", timeout=30).json()["trend"]
    assert len(trend) == 9, f"expected Acme's nine points, got {len(trend)}"
    for field in ("basis_key", "basis_recovered", "run_id", "partner_index",
                  "partner_run_id"):
        assert field in trend[0], f"the payload carries no {field}"
    assert trend[LATEST]["partner_run_id"] == sites["ids"][PARTNER_OF_LATEST]
    assert sum(1 for p in trend if p["basis_recovered"]) == RECOVERED


# --- the drawing ---------------------------------------------------------

_JS = """() => {
  const svg = document.querySelector('.st-chart');
  const cs = (el) => getComputedStyle(el);
  const text = (sel) => (document.querySelector(sel) || {}).textContent || '';
  return {
    dots: [...svg.querySelectorAll('.st-dot')].map((d) => ({
      cx: +d.getAttribute('cx'), cy: +d.getAttribute('cy'),
      fill: cs(d).fill, cls: d.getAttribute('class'),
    })),
    rings: svg.querySelectorAll('.st-ring').length,
    joins: [...svg.querySelectorAll('.st-join')].map((p) => p.getAttribute('d')),
    breaks: [...svg.querySelectorAll('.st-break')].map((l) => +l.getAttribute('x1')),
    breakWords: [...svg.querySelectorAll('.st-break-name')].map((t) => t.textContent),
    bands: [...svg.querySelectorAll('.st-band')].map((r) => ({
      x: +r.getAttribute('x'), w: +r.getAttribute('width'),
    })),
    title: (svg.querySelector('title') || {}).textContent || '',
    role: svg.getAttribute('role'),
    thresholds: [...svg.querySelectorAll('.st-rule-name')].map((t) => t.textContent),
    scores: [...svg.querySelectorAll('.st-score')].map((t) => t.textContent),
    now: text('.st-now'),
    recovered: text('.st-recovered'),
    heads: [...document.querySelectorAll('.runs-table thead th')]
             .map((t) => t.textContent),
    reads: [...document.querySelectorAll('.runs-table tbody tr')]
             .map((r) => r.children[5].textContent),
    compare: [...document.querySelectorAll('.runs-table tbody tr a')]
             .filter((a) => a.textContent.trim() === 'vs previous')
             .map((a) => a.getAttribute('href')),
  };
}"""


def _open(pg, base, site_id):
    pg.goto(f"{base}/#/sites/{site_id}?tab=all&view=audits", wait_until="load",
            timeout=30_000)
    pg.wait_for_selector(".st-chart", timeout=30_000)
    pg.wait_for_selector(".runs-table tbody tr", timeout=15_000)


NEEDS_BROWSER = pytest.mark.skipif(
    not (DIST / "index.html").is_file()
    or not __import__("clauditseo.axe", fromlist=["axe"]).available(),
    reason="needs a built dashboard, clauditseo[render] and chromium")


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            yield b
        finally:
            b.close()


@NEEDS_BROWSER
def test_the_breaks_are_rules_on_the_chart_and_not_a_paragraph(browser, served):
    """Eight steps, eight rules, each naming the first term that moved.

    The block's whole previous body was one sentence listing all eight breaks
    in prose, and the item drops it: a reader who wants to know *where* the
    line stops being one should not have to match eight date pairs against a
    table. Counted rather than sampled, because seven rules and one missing
    is the failure this replaces.
    """
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    base, sites = served
    try:
        _open(pg, base, sites["nine"])
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    assert len(got["breaks"]) == BREAKS, (
        f"{len(got['breaks'])} break rules on a history with {BREAKS} steps "
        "that changed something")
    # Each rule sits between the two points it divides, so a reader can tell
    # which step it is about without counting from the left.
    xs = sorted(d["cx"] for d in got["dots"])
    for n, at in enumerate(sorted(got["breaks"])):
        assert xs[n] < at < xs[n + 1], (
            f"the rule at {at} does not fall between the points either side "
            f"of its step: {xs}")
    assert len(got["breakWords"]) == BREAKS, "a rule was drawn with no label"
    assert all(w.strip() for w in got["breakWords"]), (
        f"a break rule is labelled with nothing: {got['breakWords']}")
    # Real text in the document, not a `title` and not an image: the rendered
    # a11y gate the item asks for.
    assert "engine 0.8.0" in got["breakWords"], (
        f"no rule names the engine change Acme made: {got['breakWords']}")
    assert "T2 → T3" in got["breakWords"], (
        f"no rule names the tier change Acme made: {got['breakWords']}")
    # And the paragraph is gone.
    assert "The line breaks where a comparison stops being one" not in got["now"]


@NEEDS_BROWSER
def test_a_point_is_joined_to_the_point_it_reads_against(browser, served):
    """One arc on Acme, and it reaches back across the run between.

    The count is the assertion. A renderer that joined every adjacent pair
    would draw eight lines and would look more like a trend, which is exactly
    the claim this history cannot support.
    """
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    base, sites = served
    try:
        _open(pg, base, sites["nine"])
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    assert len(got["joins"]) == 1, (
        f"{len(got['joins'])} lines on a history with one pair in it: "
        f"{got['joins']}")
    xs = sorted(d["cx"] for d in got["dots"])
    # It starts at 02:22 and ends at 02:37, with 02:26 between them, and it
    # is an arc rather than a straight line because it reaches over one.
    start, end = xs[PARTNER_OF_LATEST], xs[LATEST]
    assert got["joins"][0].startswith(f"M{start},"), (
        f"the line does not start at the partner point: {got['joins'][0]}")
    assert got["joins"][0].endswith(f"{end},{got['dots'][LATEST]['cy']}"), (
        f"the line does not end at the latest point: {got['joins'][0]}")
    assert "Q" in got["joins"][0], (
        "the line is straight, so it is drawn through the run between the "
        f"two points it joins rather than over it: {got['joins'][0]}")


@NEEDS_BROWSER
def test_the_current_basis_is_shaded_and_counted(browser, served):
    """Two points in, one out, and the sentence says two.

    Contiguous rectangles rather than one, because Acme's two matching
    points have a non-matching run between them: a single band from the first
    to the last would shade a point the sentence excludes, which is a picture
    contradicting the words under it.
    """
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    base, sites = served
    try:
        _open(pg, base, sites["nine"])
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    assert len(got["bands"]) == len(IN_THE_BAND), (
        f"{len(got['bands'])} shaded stretches; Acme's two matching points "
        "are not adjacent, so one band would cover a point that does not match")
    xs = sorted(d["cx"] for d in got["dots"])
    covered = [i for i, x in enumerate(xs)
               if any(b["x"] <= x <= b["x"] + b["w"] for b in got["bands"])]
    assert covered == IN_THE_BAND, (
        f"the shading covers points {covered}; the current basis is "
        f"{IN_THE_BAND}")
    assert "2 points share the latest basis" in got["now"], (
        f"the sentence does not count the current basis: {got['now']!r}")


@NEEDS_BROWSER
def test_a_recovered_dimension_set_is_ringed_and_said(browser, served):
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    base, sites = served
    try:
        _open(pg, base, sites["nine"])
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    assert got["rings"] == RECOVERED, (
        f"{got['rings']} points ringed; {RECOVERED} of Acme's nine had "
        "their dimension set recovered rather than recorded")
    assert f"{RECOVERED} of 9 points" in " ".join(got["recovered"].split()), (
        f"the note does not say how many were recovered: {got['recovered']!r}")


@NEEDS_BROWSER
def test_the_chart_carries_an_axis_a_title_and_the_bands(browser, served):
    """What UX-06 removed the old chart for not having.

    The thresholds are `SCORE_BANDS`' own numbers and words, so the chart and
    the score badge beside it cannot disagree about what 62 is; the title is
    the rendered-axe gate.
    """
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    base, sites = served
    try:
        _open(pg, base, sites["nine"])
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    assert got["role"] == "img" and got["title"].strip(), (
        "the chart has no accessible name")
    assert "Composite score over 9 scored audits" in " ".join(got["title"].split())
    assert got["thresholds"] == ["80 · good", "60 · fair"], got["thresholds"]
    assert len(got["scores"]) == 9, "a point was drawn with no score above it"
    # Three tones, and each is the band its score falls in. Read off the
    # rendered fill rather than the class, so a stylesheet that painted two
    # bands one colour would be caught.
    fills = {d["cls"].split()[-1]: d["fill"] for d in got["dots"]}
    assert len(set(fills.values())) == len(fills), (
        f"two score bands are drawn in one colour: {fills}")


@NEEDS_BROWSER
def test_the_runs_table_names_the_partner_and_links_to_it(browser, served):
    """One rule, both surfaces — the item's own words.

    The chart's line and the table's link are the same pairing, so the count
    of links is the count of arcs and the href names the run the arc starts
    at. A screen offering a comparison the chart does not join would be the
    two opinions this change exists to remove.
    """
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    base, sites = served
    try:
        _open(pg, base, sites["nine"])
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    assert "Reads against" in got["heads"], got["heads"]
    assert "Reads against previous" not in got["heads"], (
        "the column still claims the previous row")
    assert got["compare"] == [
        f"#/compare/{sites['ids'][PARTNER_OF_LATEST]}/{sites['ids'][LATEST]}"], (
        f"the comparison links are {got['compare']}; Acme has one pair, "
        "02:22 against 02:37")
    # The newest row is the latest point, and it names its partner rather than
    # answering "yes" or "no".
    newest = " ".join(got["reads"][0].split())
    assert "2026-09-02 02:22" in newest, (
        f"the newest run's row does not name the run it reads against: {newest!r}")
    assert "nearest same basis" in newest, (
        f"the row does not say the partner is not the row above it: {newest!r}")
    # And a point with no partner says so with the reason, not with "no".
    assert any(r.startswith("nothing —") for r in got["reads"]), (
        f"no row says it reads against nothing: {got['reads']}")


@NEEDS_BROWSER
def test_one_point_stands_alone_rather_than_drawing_a_trend(browser, served):
    """The degradation: one scored run, one point, no line, no rules."""
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    base, sites = served
    try:
        _open(pg, base, sites["alone"])
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    assert len(got["dots"]) == 1 and not got["joins"] and not got["breaks"], (
        f"one scored run drew {len(got['dots'])} points, {len(got['joins'])} "
        f"lines and {len(got['breaks'])} rules")
    assert "The latest point stands alone" in got["now"], got["now"]
    assert "no trend yet, only a start" in got["now"], got["now"]


# --- the stylesheet -------------------------------------------------------

def test_every_selector_in_the_trend_sheet_is_namespaced():
    """`score_trend.css` is loaded globally, so a selector of its own that is
    not `.st-` is a rule on every other screen in the app. The same clause
    `crawl_depth.css` and `schema_graph.css` carry, and for the same reason:
    the sheet is imported by `main.tsx` beside `styles.css` and nothing
    scopes it.
    """
    sheet = (Path(__file__).resolve().parents[1] / "dashboard" / "src"
             / "score_trend.css").read_text(encoding="utf-8")
    css = re.sub(r"/\*.*?\*/", "", sheet, flags=re.S)
    stray = sorted({c for c in re.findall(r"\.([A-Za-z][A-Za-z0-9_-]*)", css)
                    if not c.startswith("st-")})
    assert not stray, f"not namespaced: {stray}"
