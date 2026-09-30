"""The outline of a page, and which skip sits on which template.

Brief v16d. Two blocks on the Headings part page - a ladder of the selected
page's headings with the gaps drawn where the skipped levels should have
been, and a site-scope table of every fault shape against the template that
carries it - and the clauses below are the item's own Accept list: the ladder
is the sweep's heading list, a skipped level is drawn where it should have
been, a missing H1 is a red rung before everything, the ladder and the checks
never disagree, the skips group by shape and template, and the closing line
appears only where one template dominates.

**Why a fixture of its own and not the shared crawl fixture.** The reason
`test_the_images_budget_blocks_are_drawn.py` gives one file earlier: the
grouping this file is about needs a site with two shapes across three
templates and a residual bucket, which is twenty-nine pages arranged to make
`templatesOf` produce heads at all - it wants ten pages of a first segment
before it calls anything a template. Bending `test_a11y_rendered`'s two-page
fixture into that shape would move finding counts in forty-odd browser tests
that have nothing to do with these blocks.

**The fixture states its own answer, and the code must match it.** `PAGES`
below declares, per page, which checks it should raise - written out from the
check's rules by hand, not taken from `heading_outline_state`. The findings
planted on the record come from that declaration, and the payload comes from
the engine, so the agreement clause compares two derivations rather than one
with itself (DISCIPLINE rule 5).
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from clauditseo.db.connection import connect
from clauditseo.modules.onp import DEFAULT_SEVERITY
from clauditseo.persistence import runs
from clauditseo.persistence.repo import create_id, now_iso
from tests.test_a11y_rendered import DIST
from tests.test_triage_ranks_the_section_rail import _serve
from tests.parts import ANATOMY_READY, open_part, open_page_filter

SITE = "outline.test"
BASE_URL = f"https://{SITE}"
#: The run that recorded no heading list lives on its own host, because the
#: pane's page filter narrows against the site it is typed on: a URL from a
#: neighbouring fixture's domain matches nothing and leaves the screen at
#: site scope, which is what the first run of this file did for ten minutes.
BLANK_URL = f"https://blank.{SITE}"


def _url(path: str) -> str:
    return f"{BASE_URL}{path}"


#: `(path, headings, checks it raises, shape codes it carries)`.
#:
#: The last two columns are the fixture's own reading of the three checks -
#: `h1-missing` where no heading is an H1, `h1-multiple` where more than one
#: is, `heading-skip` on the FIRST level jump of more than one and no other,
#: because the check has always broken out of its loop after one. Nothing
#: here calls `heading_outline_state`; that is the point of the file.
#:
#: Arranged so `templatesOf` has something to do: it calls nothing a template
#: under ten pages of a first segment, so `/blog/*` and `/guides/*` are over
#: that line and `/news/*` is deliberately under it.
def _plain(path: str, levels: list[int]) -> list[list]:
    return [[lvl, f"{path} heading {i + 1} at H{lvl}"] for i, lvl in enumerate(levels)]


PAGES: list[tuple[str, list[list], list[str], list[str]]] = [
    ("/", _plain("/", [1, 2, 3]), [], []),
    # Two levels missing at once, which is the two-gap case.
    ("/deep-skip", _plain("/deep-skip", [1, 2, 5]), ["heading-skip"], ["skip:2>5"]),
    ("/form-a", _plain("/form-a", [2, 3]), ["h1-missing"], ["h1-missing"]),
    ("/form-b", _plain("/form-b", [2, 3]), ["h1-missing"], ["h1-missing"]),
    ("/twin", _plain("/twin", [1, 1, 2]), ["h1-multiple"], ["h1-multiple"]),
    # A page skipping twice: one finding, two gaps drawn. The record holds
    # H2->H4 and nothing about the H4->H6 after it.
    ("/twice", _plain("/twice", [1, 2, 4, 6]), ["heading-skip"], ["skip:2>4"]),
]
PAGES += [(p, _plain(p, [1, 2, 4]), ["heading-skip"], ["skip:2>4"])
          for p in ("/about", "/apply", "/contact")]
PAGES += [(f"/blog/{i}", _plain(f"/blog/{i}", [1, 2, 4]), ["heading-skip"],
           ["skip:2>4"]) for i in range(1, 13)]
PAGES += [(f"/guides/{i}", _plain(f"/guides/{i}", [1, 2, 4]), ["heading-skip"],
           ["skip:2>4"]) for i in range(1, 12)]
PAGES += [(f"/news/{i}", _plain(f"/news/{i}", [1, 2, 3, 5]), ["heading-skip"],
           ["skip:3>5"]) for i in range(1, 5)]

#: A page long enough that its skip falls past the ladder's cap, which is
#: what Acme's `/line-of-credit` is: 46 headings with the H2->H4 at the
#: forty-first. The first reading of this block on the running product drew
#: forty clean rungs and said "6 more headings below" - a picture of a skip
#: with no skip in it. Added to the fixture so no later change can put it
#: back.
#: 51 headings, the skip at the forty-sixth, five more below it - so the
#: window has to stretch past the cap AND still have something left to
#: count, which is the shape Acme's page has and the shape that tells the
#: stretch apart from simply removing the cap.
DEEP_LEVELS = [1] + [2] * 44 + [4] + [2] * 5
PAGES.append(("/long", _plain("/long", DEEP_LEVELS), ["heading-skip"],
              ["skip:2>4"]))

#: The site where one template carries most of the fault, for the closing
#: line's positive case. Twenty of twenty-two is past two fifths; the site
#: above is twelve of thirty-four, which is not.
DOMINANT_PAGES: list[tuple[str, list[list], list[str], list[str]]] = (
    [(f"/blog/{i}", _plain(f"/blog/{i}", [1, 2, 4]), ["heading-skip"],
      ["skip:2>4"]) for i in range(1, 21)]
    + [(p, _plain(p, [1, 2, 4]), ["heading-skip"], ["skip:2>4"])
       for p in ("/about", "/apply")])

NEEDS_BROWSER = pytest.mark.skipif(
    not __import__("clauditseo.axe", fromlist=["axe"]).available(),
    reason="needs clauditseo[render] and `playwright install chromium`")


def _record(path: str, headings: list[list], *, host: str = BASE_URL,
            store: bool = True) -> dict:
    """One page record as `crawler.evidence.snapshot` writes it.

    `outline` and not only `headings`, because that is what a run crawled
    since brief v11 step AJ stores and what the ladder reads first: level,
    text, whether the heading sits in the main region, the words after it.
    """
    page = {"url": f"{host}{path}", "status": 200, "content_type": "text/html",
            "title": f"Fixture {path}", "canonical": f"{host}{path}",
            "word_count": 400}
    if store:
        page["headings"] = [list(h) for h in headings]
        page["outline"] = [[h[0], h[1], True, ""] for h in headings]
        page["heading_total"] = len(headings)
    return page


def _plant(db: Path, site_id: str,
           pages: list[tuple[str, list[list], list[str], list[str]]],
           *, host: str = BASE_URL, store: bool = True) -> str:
    conn = connect(db)
    run_id = runs.create_run(conn, site_id, ["ONP"], "T3")
    runs.store_evidence(conn, run_id, {
        "start_url": f"{host}/",
        "pages": [_record(p, h, host=host, store=store) for p, h, _, _ in pages]})
    runs.mark_complete(conn, run_id, now_iso())
    # One row per check the fixture says the page raises, planted from the
    # declaration above rather than from the engine: the agreement clause is
    # only worth anything if the two sides come from two derivations.
    with conn:
        for path, _headings, checks, _codes in pages:
            for check in checks:
                fp = f"{check}-{path}"
                conn.execute(
                    "INSERT INTO findings (id, run_id, dimension, check_id,"
                    " severity, source, summary, affected_urls, affected_total,"
                    " evidence, fingerprint, created_at) VALUES (?, ?, 'ONP',"
                    " ?, ?, 'deterministic', ?, ?, 1, ?, ?, ?)",
                    (create_id(), run_id, check,
                     DEFAULT_SEVERITY[check].value if hasattr(
                         DEFAULT_SEVERITY[check], "value") else "medium",
                     f"{check} on {path}.", json.dumps([f"{host}{path}"]),
                     json.dumps({}), fp, now_iso()))
                conn.execute(
                    "INSERT INTO finding_states (site_id, fingerprint, state,"
                    " changed_by_run, updated_at) VALUES (?, ?, 'open', ?, ?)",
                    (site_id, fp, run_id, now_iso()))
    conn.close()
    return run_id


def _site(base: str, domain: str) -> str:
    client = httpx.post(f"{base}/api/clients", json={"name": "Outline Co"},
                        timeout=30).json()
    return httpx.post(f"{base}/api/clients/{client['id']}/sites",
                      json={"domain": domain}, timeout=30).json()["id"]


@pytest.fixture(scope="module")
def served():
    """Three sites: the arranged one, one whose single template carries most
    of the fault, and one whose run recorded no heading list at all."""
    server, thread, db, base = _serve("headingoutline")
    try:
        full = _site(base, SITE)
        _plant(db, full, PAGES)
        dominant = _site(base, f"dominant.{SITE}")
        _plant(db, dominant, DOMINANT_PAGES, host=f"https://dominant.{SITE}")
        blank = _site(base, f"blank.{SITE}")
        _plant(db, blank, PAGES[:3], host=BLANK_URL, store=False)
        yield base, {"full": full, "dominant": dominant, "blank": blank}
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def _view(base: str, site_id: str, page: str | None = None) -> dict:
    return httpx.get(f"{base}/api/sites/{site_id}/anatomy",
                     params={"page": page} if page else None, timeout=30).json()


def _part(base: str, site_id: str, page: str | None = None) -> dict:
    return next(c for c in _view(base, site_id, page)["categories"]
                if c["key"] == "headings")


def _outline(base: str, site_id: str, path: str) -> dict:
    return _view(base, site_id, _url(path))["facts"]["heading_outline"]


def _raised(base: str, site_id: str) -> dict[str, set[str]]:
    """Which checks the record holds against each page, read the way the fix
    cards read them - from the site's own states, uncapped."""
    site = httpx.get(f"{base}/api/sites/{site_id}", timeout=30).json()
    out: dict[str, set[str]] = {}
    for s in site["states"]:
        if s["check_id"] not in ("h1-missing", "h1-multiple", "heading-skip"):
            continue
        for url in s["affected_urls"]:
            out.setdefault(url, set()).add(s["check_id"])
    return out


# --- the payload the drawing is made from --------------------------------

def test_the_outline_is_the_sweeps_heading_list(served):
    """Rung for rung: the count, the order, the level and the text, against
    the list the fixture stored and not against a second reading of it."""
    base, sites = served
    for path, headings, _, _ in PAGES:
        model = _outline(base, sites["full"], path)
        rungs = [r for r in model["rungs"] if r["kind"] == "heading"]
        assert [r["level"] for r in rungs] == [h[0] for h in headings], path
        assert [r["text"] for r in rungs] == [h[1] for h in headings], path
        # The index is what `heading-skip` stores as `outline_index`, so a
        # rung and a finding name the same heading.
        assert [r["index"] for r in rungs] == list(range(len(headings))), path


def test_a_skipped_level_is_drawn_where_it_should_have_been(served):
    """H2 then H5 is two levels missing, so it is two gaps - at H3 and at
    H4, and at the positions those levels would have occupied."""
    base, sites = served
    model = _outline(base, sites["full"], "/deep-skip")
    kinds = [r["kind"] for r in model["rungs"]]
    assert kinds == ["heading", "heading", "gap", "gap", "heading"], kinds
    gaps = [r for r in model["rungs"] if r["kind"] == "gap"]
    assert [g["level"] for g in gaps] == [3, 4]
    assert [g["state"] for g in gaps] == ["warn", "warn"]
    # In words, not only as a dash: the label is what a screen reader gets.
    assert [g["text"] for g in gaps] == ["H3 skipped", "H4 skipped"]
    # And each names the heading it belongs to, which is the one that
    # skipped - the H5, third in the list.
    assert {g["for_index"] for g in gaps} == {2}


def test_missing_h1_is_a_red_rung_before_the_first_heading(served):
    base, sites = served
    model = _outline(base, sites["full"], "/form-a")
    first = model["rungs"][0]
    assert first["kind"] == "no-h1" and first["state"] == "bad"
    assert first["level"] == 1, "the rung does not stand at the H1 position"
    assert first["text"] == "no H1 on this page"
    assert model["rungs"][1]["kind"] == "heading"
    # A page that has one draws no such rung.
    assert not any(r["kind"] == "no-h1"
                   for r in _outline(base, sites["full"], "/")["rungs"])


def test_the_outline_and_the_checks_agree(served):
    """Both directions, over every page of the fixture.

    The comparison is at the page level, which is the level at which the two
    are making the same claim: a page skipping twice draws two gaps and
    carries one `heading-skip` row, because the check breaks after the first
    - so counting gaps against findings would fail on a rule neither side
    is getting wrong.
    """
    base, sites = served
    raised = _raised(base, sites["full"])
    assert raised, "the fixture raised no heading row, so this clause is vacuous"
    for path, _headings, checks, _codes in PAGES:
        model = _outline(base, sites["full"], path)
        drawn = set()
        if model["fires"]["h1-missing"]:
            drawn.add("h1-missing")
        if model["fires"]["h1-multiple"]:
            drawn.add("h1-multiple")
        if model["fires"]["heading-skip"]:
            drawn.add("heading-skip")
        assert drawn == raised.get(_url(path), set()) == set(checks), (
            f"{path}: the ladder fires {sorted(drawn)}, the record holds "
            f"{sorted(raised.get(_url(path), set()))}, the fixture says {checks}")
        # And the drawn rungs follow: a page the ladder says is clean has no
        # warn or bad rung on it, and one it says is not has at least one.
        marked = [r for r in model["rungs"] if r["state"] != "ink"]
        assert bool(marked) == bool(drawn), (
            f"{path}: {len(marked)} marked rungs against {sorted(drawn)}")


def test_only_the_first_skip_of_a_page_is_a_finding(served):
    """The rule the clause above is written around, stated on its own.

    `/twice` jumps H2->H4 and then H4->H6. The check has broken out of its
    loop after the first since it was written, so the record holds one row;
    the ladder draws the page, so it shows both gaps - and the second one
    has no check to open, which is what the block's inert rungs are for.
    """
    base, sites = served
    model = _outline(base, sites["full"], "/twice")
    assert len(model["skips"]) == 2
    assert model["fires"]["heading-skip"] == {"from": 2, "to": 4, "index": 2}
    assert [r["level"] for r in model["rungs"] if r["kind"] == "gap"] == [3, 5]
    assert _raised(base, sites["full"])[_url("/twice")] == {"heading-skip"}


def test_the_shapes_payload_reads_every_page_the_run_recorded(served):
    """Block 2's input: one entry per faulted page, coded, with one label
    per distinct code rather than one per page."""
    base, sites = served
    shapes = _part(base, sites["full"])["shapes"]
    assert shapes["recorded"] is True
    assert shapes["pages"] == len(PAGES)
    expected = {_url(p): c for p, _h, _ck, c in PAGES if c}
    assert shapes["at"] == expected
    assert set(shapes["labels"]) == {c for codes in expected.values() for c in codes}
    assert shapes["labels"]["skip:2>4"] == {
        "label": "H2 → H4", "tone": "warn", "check": "heading-skip"}
    assert shapes["labels"]["h1-missing"]["tone"] == "bad"


def test_a_run_that_recorded_no_headings_says_so(served):
    """Absent, not clean. An empty table would say the site's outlines are
    in order, which is a measurement this run never made."""
    base, sites = served
    shapes = _part(base, sites["blank"])["shapes"]
    assert shapes["recorded"] is False
    assert shapes["at"] == {} and shapes["pages"] == 0
    assert shapes["crawled"] == 3


# --- the drawing ----------------------------------------------------------

@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            yield b
        finally:
            b.close()


_JS = """() => {
  const rungs = [...document.querySelectorAll('.ho-ladder .ho-rung')];
  const rows = [...document.querySelectorAll('.ho-grid tbody tr')];
  const text = (sel) => (document.querySelector(sel) || {}).textContent || '';
  return {
    rungs: rungs.length,
    kinds: rungs.map((g) => [...g.classList].find(
      (c) => c === 'ho-heading' || c === 'ho-gap' || c === 'ho-no-h1') || ''),
    tones: rungs.map((g) => [...g.classList].find(
      (c) => c === 'ho-ink' || c === 'ho-warn' || c === 'ho-bad') || ''),
    labels: rungs.map((g) => (g.querySelector('.ho-text') || {}).textContent || ''),
    roles: rungs.map((g) => g.getAttribute('role') || ''),
    names: rungs.map((g) => g.getAttribute('aria-label') || ''),
    ys: rungs.map((g) => Number(
      (g.querySelector('.ho-mark') || {}).getAttribute
        ? g.querySelector('.ho-mark').getAttribute('y1') : 0)),
    xs: rungs.map((g) => Number(
      (g.querySelector('.ho-mark') || {}).getAttribute
        ? g.querySelector('.ho-mark').getAttribute('x1') : 0)),
    svgTitle: text('.ho-ladder title'),
    svgRole: (document.querySelector('.ho-ladder') || {}).getAttribute
      ? document.querySelector('.ho-ladder').getAttribute('role') : '',
    caption: text('.ho-cap'),
    more: text('.ho-more'),
    legend: [...document.querySelectorAll('.ho-legend span')].map((s) => s.textContent),
    none: text('.ho-none'),
    rows: rows.map((tr) => [...tr.querySelectorAll('td')].map((td) => td.textContent)),
    barWidths: rows.map((tr) => {
      const bar = tr.querySelector('.ho-bar');
      return bar ? bar.style.width : '';
    }),
    closing: text('.ho-closing'),
    absent: text('.ho-absent'),
  };
}"""


def _open(pg, base, site_id, page: str | None = None):
    """The Headings part, and then the page filter if one is named - in that
    order, which is `test_a11y_rendered`'s third reveal pass's order and for
    its reason: a category clicked while the pane refetches loses the press."""
    pg.goto(f"{base}/#/sites/{site_id}?tab=findings", wait_until="load", timeout=30_000)
    pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
    open_part(pg, 'Headings')
    if page is None:
        pg.wait_for_selector(".ho-site", timeout=15_000)
    else:
        open_page_filter(pg)
        pg.fill(".page-find", page)
        # The ladder is the page's own block, so its first rung is the signal
        # that the narrowed payload has arrived; a fixed wait would pass
        # against a screen that never refetched.
        pg.wait_for_selector(".ho-ladder .ho-rung", timeout=15_000)


def _read(browser, base, site_id, page: str | None = None) -> dict:
    """One screen, read once, on a page of its own - navigating to the same
    hash does not reload, so two states means two browser pages."""
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    try:
        _open(pg, base, site_id, page)
        return pg.evaluate(_JS)
    finally:
        pg.close()


BROWSER = [NEEDS_BROWSER,
           pytest.mark.skipif(not (DIST / "index.html").is_file(),
                              reason="dashboard not built")]


def _mark(fn):
    for m in BROWSER:
        fn = m(fn)
    return fn


@_mark
def test_the_ladder_draws_one_rung_per_heading_indented_by_level(browser, served):
    base, sites = served
    got = _read(browser, base, sites["full"], _url("/deep-skip"))
    assert got["kinds"] == ["ho-heading", "ho-heading", "ho-gap", "ho-gap",
                            "ho-heading"], got["kinds"]
    # Indented by level and by nothing else: H1 leftmost, one step a level,
    # and the gaps at the columns of the levels they stand for.
    assert got["xs"] == [28, 82, 136, 190, 244], got["xs"]
    # In page order, top to bottom.
    assert got["ys"] == sorted(got["ys"]), got["ys"]
    assert got["svgRole"] == "group"
    assert "/deep-skip" in got["svgTitle"]
    assert got["legend"] == [
        "heading present",
        "level skipped — the rung that should be here",
        "missing H1"]


@_mark
def test_the_gap_rungs_carry_their_labels_in_the_accessible_tree(browser, served):
    """A dashed stroke is not there at all for a screen reader, so every
    rung the ladder draws carries real text."""
    base, sites = served
    got = _read(browser, base, sites["full"], _url("/deep-skip"))
    assert got["labels"][2] == "H3 skipped"
    assert got["labels"][3] == "H4 skipped"
    assert got["tones"][2] == got["tones"][3] == "ho-warn"
    # The heading that skipped is flagged too, and says so in words.
    assert got["tones"][4] == "ho-warn"
    assert "flagged" in got["names"][4], got["names"][4]


@_mark
def test_the_missing_h1_rung_opens_the_page_and_its_finding(browser, served):
    base, sites = served
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    try:
        _open(pg, base, sites["full"], _url("/form-a"))
        got = pg.evaluate(_JS)
        assert got["kinds"][0] == "ho-no-h1" and got["tones"][0] == "ho-bad"
        assert got["labels"][0] == "no H1 on this page"
        assert "no H1" in got["caption"], got["caption"]
        # A rung with a card behind it is a control; pressing it brings the
        # card into view, which is the half a class name cannot assert.
        assert got["roles"][0] == "button"
        pg.click(".ho-ladder .ho-no-h1")
        box = pg.eval_on_selector('[data-fix-check="h1-missing"]', """el => {
            const r = el.getBoundingClientRect();
            return {top: r.top, bottom: r.bottom, h: window.innerHeight};
        }""")
        assert box["top"] >= 0 and box["bottom"] <= box["h"], (
            f"pressing the rung did not bring its fix into view: {box}")
    finally:
        pg.close()


@_mark
def test_a_page_with_no_headings_says_so_rather_than_drawing_nothing(browser, served):
    base, sites = served
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    try:
        pg.goto(f"{base}/#/sites/{sites['blank']}?tab=findings",
                wait_until="load", timeout=30_000)
        pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
        open_part(pg, 'Headings')
        # The site block first, so the filter is typed into a rendered part
        # rather than into one still fetching - the reason `_open` waits.
        pg.wait_for_selector(".ho-site", timeout=15_000)
        # A page the record holds a row against: `anatomy_view` builds the
        # narrow list from `affected_urls`, so a page no finding names does
        # not reach the filter at all. Older than this item and the same on
        # every part - the note in `OPERATOR_ACTIONS.md` from brief v16c.
        open_page_filter(pg)
        pg.fill(".page-find", f"{BLANK_URL}/form-a")
        pg.wait_for_selector(".ho-none", timeout=15_000)
        note = pg.inner_text(".ho-none")
    finally:
        pg.close()
    assert "no headings" in note.lower(), note
    assert "no H1 either" in note, note


@_mark
def test_a_fault_past_the_cap_is_still_drawn(browser, served):
    """The cap may shorten the ladder; it may not remove its subject.

    Found on the running product and not in a fixture, because a fixture is
    written short enough to read. `/long` carries 46 headings with the skip
    at the forty-first, so a ladder that stopped at forty would draw the
    page as clean while the caption above it said H2 -> H4.
    """
    base, sites = served
    got = _read(browser, base, sites["full"], _url("/long"))
    assert "ho-gap" in got["kinds"], (
        "the ladder stopped before the skip it exists to show")
    # The window stops at the marked rung and not one heading later: the
    # cap is stretched to reach the fault, not removed.
    assert got["kinds"][-1] == "ho-heading" and got["tones"][-1] == "ho-warn"
    assert got["labels"][-1].startswith("/long heading 46"), got["labels"][-1]
    # Still capped, and still says how much it left out.
    assert "more heading" in got["more"], got["more"]
    assert "the level that skipped is down there" in got["more"], got["more"]
    # A page inside the cap says nothing about it.
    plain = _read(browser, base, sites["full"], _url("/deep-skip"))
    assert plain["more"] == ""


@_mark
def test_skips_group_by_shape_and_template(browser, served):
    """Two shapes across three templates, and the counts sum to what the
    checks raised."""
    base, sites = served
    got = _read(browser, base, sites["full"])
    rows = [(r[0], r[1], r[-1]) for r in got["rows"]]
    shaped = [r for r in rows if "other page" not in r[0]]
    # Largest first; two rows of four are ordered by the shape's own name, so
    # the same site reads the same way twice running.
    assert [(r[0], int(r[2])) for r in shaped] == [
        ("H2 → H4", 12), ("H2 → H4", 11), ("H2 → H4", 5),
        ("H3 → H5", 4), ("no H1", 2)], shaped
    assert shaped[0][1].startswith("/blog/*")
    assert shaped[1][1].startswith("/guides/*")
    # The residual bucket is not a glob, so it is named by what is in it.
    assert shaped[2][1].startswith("/ and top-level pages")
    assert "/about, /apply, /contact" in shaped[2][1], shaped[2][1]
    # And it is only called the top level where its pages are at it: the
    # four `/news/*` pages share a segment `templatesOf` will not call a
    # template under ten, and the row says so rather than calling them
    # top-level pages with `/news/1` printed beside the claim.
    assert shaped[3][1].startswith("no shared template"), shaped[3][1]
    assert "/news/1, /news/2, /news/3" in shaped[3][1], shaped[3][1]
    # Rows of one page collapse rather than becoming a list of pages.
    ones = [r for r in rows if "other page" in r[0]]
    assert ones and ones[0][0].startswith("2 other pages, one each"), ones
    # And the whole table accounts for every page the checks named.
    total = sum(int(r[-1]) for r in got["rows"])
    assert total == sum(1 for _p, _h, _c, codes in PAGES for _ in codes) == 36
    assert got["closing"].startswith("5 shapes across 36 pages."), got["closing"]
    # Longest bar on the largest row, and the bar is proportional to it.
    assert got["barWidths"][0] == "100%"
    assert got["barWidths"][1].startswith("91.66")


@_mark
def test_the_closing_line_only_appears_when_one_template_dominates(browser, served):
    """Twelve of thirty-four is not two fifths and buys no advice; twenty of
    twenty-two is, and names the template and the number it moves."""
    base, sites = served
    spread = _read(browser, base, sites["full"])
    assert "Fix the" not in spread["closing"], spread["closing"]
    heavy = _read(browser, base, sites["dominant"])
    assert heavy["closing"] == (
        "1 shape across 22 pages. Fix the /blog/* template and the count "
        "above drops by 20 on the next audit."), heavy["closing"]


@_mark
def test_a_run_with_no_heading_list_draws_no_table(browser, served):
    base, sites = served
    got = _read(browser, base, sites["blank"])
    assert got["rows"] == []
    assert "recorded no heading list" in got["absent"], got["absent"]
    assert "not the same as there being none" in got["absent"]
