"""Findings F8 to F17 of the 2026-09-18 audit: figures and words that
disagreed with another rendering of the same fact on the same screen.

Each clause here is one of them, and each names what was measured.

  F8   Acme: the bar read `Pages 99` (the crawl population, path-keyed) and
       the Pages pane's own line read `100 pages` (the run's fetched URLs).
       Two fetched URLs share one path key - `/apply` and
       `/apply?product_type=loc` - and a source comment asserted the two counts
       were the same set.
  F9   `11 of 49 published page(s) are in the primary navigation` about forty
       rendered lines under a card reading `Nav · 15 pages · 15 in navigation,
       1 in the footer`. `inNav` is the sitemap INTERSECTED with the nav; the
       card's 15 is the nav. And the footer's 1 is INSIDE the 15, so the basis
       read as 15 + 1 = 16.
  F10  `Site` and `Full` both `49 pages`, from the sitemap, on a screen whose
       h1 says the site has 53 - and the registry says Full "is the only scan
       whose coverage can reach 100%", which at 49 of 53 it cannot.
  F11  The audit's stamp `2026-09-17 11:02` one card above the precheck's
       `checked 2026-09-17 21:02`, for a precheck that finished nine seconds
       BEFORE that audit began. Both were `iso.slice(0, 16)`, applied to
       strings stored in two different offsets, and the offset is what the
       slice discards.
  F12  `Notes 0` in the bar, 200px from `4 coverage notes not counted` in the
       headline.
  F13  `GOOD` / `POOR` on the Speed gauges, against a legend on the same screen
       defining `within range` / `near the limit` / `past the limit`; and
       `good` and `poor` were already the registry's words for a site SCORE.
  F14  Four words for one state on one pane: `NOT ANALYSED`, `· no analysis
       yet`, `not run`, and the registered `not read`.
  F15  Page mode dropped the site-scoped findings silently: 32 became 29 on the
       only page the audit had crawled.
  F16  `Assessed 2` directly above `0% of this audit's 882 findings`.
  F17  `1 pages audited of 53 known`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
import pytest

from clauditseo import precheck as pre
from clauditseo.db.connection import connect
from clauditseo.persistence import runs

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "dashboard" / "src"
ENTRIES = {e["id"]: e for e in json.loads(
    (ROOT / "clauditseo" / "glossary.json").read_text(encoding="utf-8"))["entries"]}


def _code(path: Path) -> str:
    """A file with its block comments removed.

    A clause that forbids a phrase has to read code, or it fails on the comment
    explaining why the phrase went - which happened three times in this round,
    in two guards and one of these. Block comments are stripped WHOLE; dropping
    lines that start with a marker leaves every continuation line of a
    `{/* … */}` block reading as code.
    """
    return re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)


# ---- F11: one stamp helper -------------------------------------------------

def test_no_screen_slices_an_iso_string_into_a_clock():
    """The slice prints whatever offset the string carries and drops the one
    that would have said so. `stamp` converts."""
    bad = []
    for path in sorted(SRC.glob("*.tsx")):
        text = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
        for n, line in enumerate(text.splitlines(), 1):
            if line.strip().startswith(("//", "*", "{/*")):
                continue
            # Both orders: one call site had the replace before the slice, which
            # is why a grep for the other order missed it.
            if re.search(r"slice\(0,\s*16\)\.replace\(\"T\"", line) \
               or re.search(r'replace\("T", " "\)\.slice\(0,\s*16\)', line):
                bad.append(f"{path.name}:{n}: {line.strip()[:90]}")
    assert not bad, "a clock built by slicing an ISO string:\n" + "\n".join(bad)


def test_the_stamp_helper_converts_and_is_shared():
    lanes = (SRC / "client_lanes.tsx").read_text(encoding="utf-8")
    assert "export function stamp(" in lanes
    # A conversion, not a slice: it must go through Date.
    body = lanes[lanes.index("export function stamp("):][:600]
    assert "new Date(iso)" in body, body
    readers = [p.name for p in sorted(SRC.glob("*.tsx"))
               if re.search(r"\bstamp\(", p.read_text(encoding="utf-8"))]
    assert len(readers) >= 5, readers


# ---- F9, F10: the precheck's own numbers -----------------------------------

def test_the_footers_links_are_inside_the_nav_count():
    """"15 in navigation, 1 in the footer" under a figure of 15 reads as 16."""
    r = pre.PrecheckResult(entry_url="https://x.test/", checked_at="", took_ms=1,
                           sitemap_state="ok", sitemap_urls=49, sitemap_files=7,
                           nav_count=15, footer_count=1, nav_unique=15)
    basis = r.scopes()["nav"]["basis"]
    assert "of them in the footer" in basis, basis
    assert r.scopes()["nav"]["pages"] == 15


def test_full_reads_the_site_not_the_sitemap():
    """The union, which is what `site_size` computes and what the header says."""
    r = pre.PrecheckResult(entry_url="https://x.test/", checked_at="", took_ms=1,
                           sitemap_state="ok", sitemap_urls=49, sitemap_files=7,
                           nav_count=15, footer_count=1, nav_unique=15,
                           not_in_sitemap=[f"https://x.test/n{i}" for i in range(4)])
    full = r.scopes()["full"]
    assert full["pages"] == 53, full
    assert "found in the navigation" in full["basis"], full
    # And the registry's claim about Full is now reachable.
    assert "100%" in ENTRIES["scope-full"]["full"], ENTRIES["scope-full"]


def test_an_unread_sitemap_still_says_nothing_rather_than_guessing():
    r = pre.PrecheckResult(entry_url="https://x.test/", checked_at="", took_ms=1,
                           sitemap_state="absent", sitemap_urls=None)
    assert r.scopes()["full"]["pages"] is None


def test_the_precheck_note_names_both_numbers():
    p = (SRC / "precheck.tsx").read_text(encoding="utf-8")
    assert "the navigation has" in p, (
        "the note still states one of the two figures it reconciles")


def test_the_matrix_says_when_two_scopes_read_one_figure():
    m = (SRC / "scanmatrix.tsx").read_text(encoding="utf-8")
    assert "not_in_sitemap" in m, "the matrix still divides by the declaration"
    assert "over either cap" in m, "two identical rows with nothing saying why"


# ---- F12, F13, F14: the words ---------------------------------------------

def test_the_bar_does_not_say_note_about_two_things():
    v = (SRC / "views.tsx").read_text(encoding="utf-8")
    assert '"Client notes"' in v, "the bar still labels the pane `Notes`"
    for term in ("coverage-note", "client-note"):
        assert term in ENTRIES, f"{term} is not registered"


def test_the_speed_bands_draw_the_registered_words():
    s = (SRC / "speed_now.tsx").read_text(encoding="utf-8")
    assert "BAND_WORD" in s
    for eid in ("band-ok", "band-warn", "band-bad", "band-mute"):
        assert f'entry("{eid}")' in s, f"{eid} is not read from the registry"
    # Google's vocabulary is not the rendered word any more.
    body = s[s.index("const BAND_WORD"):]
    rendered = body[body.index("sp-g-band"):][:400]
    assert "gauge.band ??" not in rendered, rendered


def test_one_word_for_an_analysis_nothing_has_read():
    g = (SRC / "glossary.tsx").read_text(encoding="utf-8")
    assert "export const NOT_READ" in g, "the word is still private to one screen"
    bad = []
    for path in sorted(SRC.glob("*.tsx")):
        text = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
        for n, line in enumerate(text.splitlines(), 1):
            if line.strip().startswith(("//", "*", "{/*")):
                continue
            for phrase in ('"not analysed"', "no analysis yet"):
                if phrase in line:
                    bad.append(f"{path.name}:{n}: {line.strip()[:80]}")
    assert not bad, "a second word for the unread state:\n" + "\n".join(bad)
    grid = (SRC / "headers_grid.tsx").read_text(encoding="utf-8")
    assert '"N/A"' not in grid, "the header grid still draws the engine's token"
    assert ENTRIES["not-applicable"]["word"] == "does not apply"


# ---- F16, F17: the arithmetic and the grammar -----------------------------

def test_a_percentage_is_not_zero_where_the_count_is_not():
    lanes = (SRC / "client_lanes.tsx").read_text(encoding="utf-8")
    assert '"<1"' in lanes, "`round()` can still print 0% over a non-zero count"


def test_one_page_is_not_pages():
    pop = (SRC / "population.tsx").read_text(encoding="utf-8")
    assert 'page{coverage.crawled === 1 ? "" : "s"}' in pop
    # The part's actions no longer name a page set at all in site mode, so
    # there is no plural to get right there: channel ruling 20260918-1431 found
    # that neither control reads the record, and that in site mode the
    # re-check posts a NEW adaptive audit whose page set does not exist yet.
    # `test_a_control_names_only_a_set_it_has` below is that rule.
    assert "pages in the record" not in _code(SRC / "part_page.tsx"), (
        "a part's control names the record again")


def test_a_control_names_only_a_set_it_has():
    """Channel ruling 20260918-1431, and it is stronger than the audit's F17.

    `recheckPart` branches: with a page in hand it posts `/refresh`, which is
    one page always; otherwise it posts `/audits` with `tier: "auto"` - a new
    adaptive audit whose page set the crawl decides as it runs. So in site mode
    there is no number to name, and "the 227 pages in the record" was a figure
    invented at press time. The estimate went the same way: `~2s` is the
    per-page rate times the record's count, attached to a button that may crawl
    the whole site.
    """
    part = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    assert 'const scope = page ? "this page" : "this part\'s checks"' in part, (
        "the re-check's scope names something other than what it re-runs")
    assert "const briefScope" in part, (
        "the analysis shares the re-check's scope word; it reads the audit")
    # The time only where a page set exists.
    assert "{page && estSeconds !== null" in part, (
        "the site-mode press still quotes the page-mode estimate")


# ---- F8, F15: the payload has to carry what the screen says ---------------

@pytest.fixture(scope="module")
def two_facts():
    from tests.test_coverage import DIMS, _Hub, _run
    from tests.test_triage_ranks_the_section_rail import _serve

    server, thread, db, base = _serve("twofacts")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "Two Facts"},
                            timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "twofacts.fixture"}, timeout=30).json()
        conn = connect(db)
        run_id = runs.create_run(conn, site["id"], DIMS, "T2")
        runs.complete_run(conn, run_id, _run(_Hub()))
        conn.close()
        yield base, db, run_id, site["id"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_page_mode_says_what_it_set_aside(two_facts):
    """F15: the payload carries the count, and site mode's is zero."""
    base, db, run_id, site_id = two_facts
    whole = httpx.get(f"{base}/api/sites/{site_id}/anatomy",
                      params={"run_id": run_id}, timeout=60).json()
    assert whole.get("site_only") == 0, whole.get("site_only")
    pages = whole.get("pages") or []
    if not pages:
        pytest.skip("the fixture's record holds no page to narrow to")
    narrow = httpx.get(f"{base}/api/sites/{site_id}/anatomy",
                       params={"run_id": run_id, "page": pages[0]}, timeout=60).json()
    assert "site_only" in narrow, narrow.keys()
    assert isinstance(narrow["site_only"], int)
    # The arithmetic the screen states: what this page holds plus what belongs
    # to no page cannot exceed the site's total.
    assert narrow["total"] + narrow["site_only"] <= whole["total"], (
        narrow["total"], narrow["site_only"], whole["total"])


def test_the_screen_states_the_set_aside_count():
    lanes = " ".join((SRC / "client_lanes.tsx").read_text(encoding="utf-8").split())
    assert "siteOnly" in lanes, "ModeArith takes no count of what page mode drops"
    assert "about the site as a whole and" in lanes, (
        "page mode does not say what it left out")
    anat = " ".join((SRC / "anatomy.tsx").read_text(encoding="utf-8").split())
    assert "siteOnly={data.site_only" in anat, "the screen never passes it"


def test_the_pages_pane_reconciles_its_count_with_the_crawls():
    """F8: the pane lists URLs and the bar counts path keys, so the pane says
    both. The comment that claimed they were one set is corrected."""
    v = " ".join((SRC / "views.tsx").read_text(encoding="utf-8").split())
    assert "distinctPaths" in v, "the pane states one number for two questions"
    assert "this audit's pages, the set the Pages pane lists" not in v, (
        "the comment still claims the bar's count is the pane's list")
