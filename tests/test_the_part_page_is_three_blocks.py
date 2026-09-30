"""The Title & description part page in three blocks (brief v13 step AO):
actions, what the page has now, fixes.

The first row under the part's name is the two actions - one free, one
paid - with the sweep and the brief that produced what is on screen named
beside them; there is no Read button, no depth choice and no explanatory
paragraph. Narrowed to a page, the "now" card carries the page's own
title, description and canonical with a badge per string and a plain
result preview cut at the registry's own bound; the whole site gets the
checks table instead, every check of the part listed with what each
source counted, and the brief's own summary sentence beneath it. The
fixes are one card per failing (check, page): the current string struck
through above the replacement, with one copy button. A check the brief
could not assess gets a card too - a neutral pill, why it is held, and a
link to where the input is set - never a bracketed placeholder.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
import pytest

from clauditseo.db.connection import connect
from clauditseo.persistence import repo, runs
from clauditseo.persistence.repo import create_id, now_iso
from tests.test_a11y_rendered import DIST
from tests.test_triage_ranks_the_section_rail import _serve
from tests.parts import ANATOMY_READY, open_part, open_page_filter

def three_block_parts() -> set[str]:
    """The parts that render as three blocks, read from `PART_RENDERERS`.

    Two clauses elsewhere pick "a part that is *not* one of these" so they
    can drive the old page's controls, and both held the list by hand. When
    Images joined the set at brief v15 step AR one of the two was updated
    and the other picked Images, waited thirty seconds for a button that
    part no longer renders, and failed on the step after the one that
    changed it. A list written twice is the defect; the registry that
    decides which page a part gets is the one place it is a fact.
    """
    src = (Path(__file__).resolve().parents[1] / "dashboard" / "src"
           / "part_page.tsx").read_text(encoding="utf-8")
    body = src.split("PART_RENDERERS: Record<string, Renderer> = {", 1)[1]
    body = body.split(chr(10) + "};", 1)[0]
    # Digits allowed: `a11y` is the first part key to carry one, and the
    # pattern that stopped at `[a-z-]` silently returned a set without it -
    # so every clause picking "a part that is NOT three-block" could pick
    # Accessibility, open it, and wait thirty seconds for a control that
    # part no longer renders. That is precisely the failure this helper was
    # written to end, reappearing through its own matcher.
    keys = set(re.findall(r'^\s*"?([a-z][a-z0-9-]*)"?:\s*\{', body, re.MULTILINE))
    assert len(keys) >= 3, (
        "the three-block registry could not be read out of part_page.tsx, so "
        f"every clause keyed on it is now picking from the whole list: {keys}")
    return keys


def old_page_part(view: dict, need: str = "total") -> str:
    """The label of a part that still renders as the old page, with
    something open on it.

    Six parts have their own renderer now - Title & description at v13,
    Headings at v14, Images at v15, Structured data at v16, and Links and
    Content at v17 - and every one of those moves broke a clause that had
    named the part it drove. Three constants in three files moved three
    times each before this existed.

    Derived from the payload and the renderer registry, so the seventh
    move breaks nothing: what these clauses need is "a part with a cause
    table and a row in it", and that is a question the data answers.

    `need` is `total` for a clause that wants an open finding, or
    `refresh` for one that wants the re-audit control as well.
    """
    # The harness's parts draw on the old page too (brief v25 step BP,
    # `tests/last_resort.py`), for a page that asked for it; a caller of this
    # sets the hook on its page.
    from tests.last_resort import PARTS as LAST_RESORT
    migrated = three_block_parts() - set(LAST_RESORT)
    for cat in view["categories"]:
        if cat["key"] in migrated or not cat.get("total"):
            continue
        if need == "refresh" and not cat.get("refresh"):
            continue
        return cat["label"]
    raise AssertionError(
        f"no part on this fixture keeps the old page with {need}; these "
        "clauses have nothing to drive")


NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")

BASE = "https://blocks.fixture"
HOME = BASE + "/"
ABOUT = BASE + "/about"
LONG = ("Blocks Group is a privately owned full-service events company for clients seeking "
        "creative, impeccably designed and expertly executed events and travel experiences "
        "across the whole of Australia, for companies large and small alike, every year.")
GOOD = ("Blocks Group plans and delivers corporate events and travel experiences for "
        "Australian companies, from boutique businesses to the largest brands.")


def _row(check_id, page, replacement, severity="medium"):
    return {"check": f"ONP/{check_id}", "dimension": "ONP", "check_id": check_id,
            "page": page, "status": "FAIL", "severity": severity, "evidence": "x",
            "replacement": replacement, "note": ""}


def _plant(db, site_id):
    """Two pages. The home page has a title in range and a description far
    over the bound; the sweep and the brief both raised it, so the card
    reads `automatic checks and analysis agree` and carries the brief's replacement. The
    brief could not assess alignment on either page: no GBP category."""
    conn = connect(db)
    # TEC as well (item 239 step 3): the card's canonical badge is
    # Indexability's, and an ONP-only run never measured it.
    run_id = runs.create_run(conn, site_id, ["ONP", "TEC"], "T2")
    # `content_type` as the crawler stores it: without one a page is not one
    # the run could read, and the Latest View never holds its facts (item 239).
    pages = [{"url": HOME, "status": 200, "content_type": "text/html",
              "title": "Blocks Group - Events - Australia",
              "meta_description": LONG, "canonical": HOME},
             {"url": ABOUT, "status": 200, "content_type": "text/html",
              "title": "About Blocks Group",
              "meta_description": None, "canonical": ABOUT}]
    runs.store_evidence(conn, run_id, {"pages": pages})
    runs.mark_complete(conn, run_id, now_iso())
    with conn:
        for check, url, fp in (("meta-desc-length", HOME, "sweep-home-len"),
                               ("meta-desc-missing", ABOUT, "sweep-about-missing")):
            conn.execute(
                "INSERT INTO findings (id, run_id, dimension, check_id, severity, source,"
                " summary, affected_urls, fingerprint, created_at) VALUES (?, ?, 'ONP', ?,"
                " 'medium', 'deterministic', ?, ?, ?, ?)",
                (create_id(), run_id, check, f"{check} on {url}", json.dumps([url]), fp, now_iso()))
            conn.execute(
                "INSERT INTO finding_states (site_id, fingerprint, state, changed_by_run, updated_at)"
                " VALUES (?, ?, 'open', ?, ?)", (site_id, fp, run_id, now_iso()))
    rows = [_row("meta-desc-length", HOME, GOOD), _row("meta-desc-missing", ABOUT, GOOD)]
    held = [{"check": "ONP/title-entity-alignment", "page": "/", "needs": "GBP primary category"},
            {"check": "ONP/title-entity-alignment", "page": "/about",
             "needs": "GBP primary category"}]
    runs.store_expert_report(conn, run_id, "title-desc", {
        "model": "claude-sonnet-5", "cost": 0.08,
        "report": "## Title & description — assessment\n"
                  "2 FAIL / 0 WARN / 2 not assessable / 2 pages assessed. Both alignment rows "
                  "are held for the missing category. Length measured in characters; pixel "
                  "width not assessed. A fourth sentence that must not appear.\n\n"
                  "### Replacement copy\nSomething else.\n",
        "findings": [],
        "contract": {"status": "read", "part": "title-desc", "rows": rows, "dropped": [],
                     "assumptions": [], "not_assessable": held, "uncovered": []}})
    runs.record_contract_findings(conn, run_id, "title-desc", "claude-sonnet-5", rows)
    runs.recompute_contract_states(conn, site_id, "title-desc")
    conn.close()
    return run_id


@pytest.fixture(scope="module")
def served():
    server, thread, db, base = _serve("blocks")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "Blocks Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "blocks.fixture"}, timeout=30).json()
        run_id = _plant(db, site["id"])
        yield base, site["id"], run_id
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_the_payload_carries_the_held_rows_the_run_and_the_summary(served):
    base, site_id, run_id = served
    view = httpx.get(f"{base}/api/sites/{site_id}/anatomy", timeout=30).json()
    assert view["sweep_run"]["run_id"] == run_id and view["sweep_run"]["tier"] == "T2"
    part = next(c for c in view["categories"] if c["key"] == "title-desc")
    assert [h["page"] for h in part["brief_held"]] == ["/", "/about"]
    assert part["brief_run"]["model"] == "claude-sonnet-5" and part["brief_run"]["rows"] == 2
    # Three sentences of the brief's own verdict, and no fourth.
    assert part["brief_summary"].startswith("2 FAIL / 0 WARN")
    assert "pixel width not assessed." in part["brief_summary"]
    assert "must not appear" not in part["brief_summary"]
    # Narrowed, the held rows are that page's.
    one = httpx.get(f"{base}/api/sites/{site_id}/anatomy", params={"page": HOME}, timeout=30).json()
    held = next(c for c in one["categories"] if c["key"] == "title-desc")["brief_held"]
    assert [h["page"] for h in held] == ["/"]


def test_the_summary_is_the_briefs_own_words_or_nothing():
    from clauditseo.persistence.runs import _brief_summary
    assert _brief_summary(None) is None
    assert _brief_summary("### Replacement copy\nNo assessment here.") is None
    got = _brief_summary("## Headings — assessment\nOne. Two. Three. Four.\n\n### Next\n")
    assert got == "One. Two. Three."
    # A table under the heading is not prose and is not quoted.
    assert _brief_summary("## X assessment\n| a | b |\n|---|---|\n") is None


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
  const pane = document.querySelector('.anat-pane');
  const card = pane?.querySelector('.card');
  return {
    firstBlock: card ? [...card.children].map((el) => el.className.split(' ')[0]
                                                    || el.tagName.toLowerCase()) : [],
    acts: [...document.querySelectorAll('.part-acts button')].map((b) => b.textContent.trim()),
    prov: [...document.querySelectorAll('.part-prov .prov-line')].map((p) => p.textContent.trim()),
    reads: document.querySelectorAll('.anat-pane .read-elsewhere, .anat-pane .tri-read').length,
    selects: document.querySelectorAll('.anat-pane select').length,
    chips: document.querySelectorAll('.anat-pane .reaudit-depth').length,
    reaudit: document.querySelectorAll('.reaudit').length,
    blurbs: document.querySelectorAll('.anat-pane .anat-blurb').length,
    now: document.querySelectorAll('.now-card').length,
    strips: document.querySelectorAll('.strips').length,
    badges: [...document.querySelectorAll('.str-badge')]
      .map((b) => `${b.className.split(' ')[1]}|${b.textContent.trim()}`),
    snipTitle: (document.querySelector('.snip-title')?.textContent || ''),
    snipCut: (document.querySelector('.snip-cut-label')?.textContent || ''),
    snipCap: (document.querySelector('.snip-caption')?.textContent || '').trim(),
    note: (document.querySelector('.now-note')?.textContent || '').trim(),
    checks: [...document.querySelectorAll('.checks-table tbody tr')]
      .map((tr) => [...tr.querySelectorAll('td')].map((td) => td.textContent.trim())),
    summary: (document.querySelector('.brief-accounting')?.textContent || '').replace(/\s+/g, ' ').trim(),
    na: [...document.querySelectorAll('.fix-na')].map((p) => p.textContent.replace(/\s+/g, ' ').trim()),
    prose: document.querySelector('details.brief-prose:not([open])')?.textContent || '',
    fixes: [...document.querySelectorAll('.fix-card')].map((c) => ({
      name: (c.querySelector('.fix-name')?.textContent || '').trim(),
      check: (c.querySelector('.fix-check')?.textContent || '').trim(),
      src: (c.querySelector('.fix-src')?.textContent || '').trim(),
      now: (c.querySelector('.fix-now s')?.textContent || '').trim(),
      rep: (c.querySelector('.fix-rep')?.textContent || '').trim(),
      why: (c.querySelector('.fix-why')?.textContent || '').trim(),
      link: c.querySelector('.fix-why a')?.getAttribute('href') || null,
      copy: !!c.querySelector('.fix-copy'),
    })),
    clean: [...document.querySelectorAll('.cause-clean-line')].map((p) => p.textContent.trim()),
    text: (pane?.textContent || ''),
  };
}"""


def _open(pg, base, site_id):
    pg.goto(f"{base}/#/sites/{site_id}?tab=findings", wait_until="load", timeout=30_000)
    pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
    open_part(pg, 'Title & description')
    pg.wait_for_selector(".part-page", timeout=15_000)


@NEEDS_BROWSER
@pytest.mark.skipif(not (DIST / "index.html").is_file(), reason="dashboard not built")
def test_the_whole_site_view_leads_with_the_actions_then_the_checks_then_the_fixes(browser, served):
    base, site_id, _ = served
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    try:
        _open(pg, base, site_id)
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    # The first thing under the part's name is the coverage line, then the
    # actions row. The line is part of the header rather than a fourth block
    # (item 155): the part header states coverage ONCE, from 150 BJ, and it is
    # the scope every count in the blocks below is read against - so it stands
    # above them and outside the layout branch, which is why both layouts get
    # it. The three-block order this clause is about is unchanged.
    # Item 185 added a fourth thing to this header, between the coverage line
    # and the blocks: the part switcher. It is named here rather than allowed
    # past by a looser slice, because where it sits IS the claim - the first
    # build of it led the card and pushed the h2 to second, which is the defect
    # this clause caught. A switcher above the part's NAME offers every part
    # before saying which one you are in.
    # Item 196 added the fifth: `part-rank`, between the name and the
    # coverage line. It is not new markup - the rank line has sat there for
    # some time - but it rendered only where a ranking existed, which meant
    # only where triage had been bought. The ranking is computed with the
    # audit now, so it is always drawn, and a header that lists it is the
    # honest description of the header.
    assert got["firstBlock"][:5] == ["part-h2", "part-rank", "part-coverage",
                                     "part-switch", "part-page"], got["firstBlock"]
    assert len(got["acts"]) == 2, got["acts"]
    # Each control names what its own press covers, and in site mode that is
    # not a page set (channel ruling 20260918-1431): the re-check posts a new
    # adaptive audit whose pages the crawl chooses as it runs, so "the 2 pages
    # in the record" was a figure invented at press time - and the `~Ns` beside
    # it was the per-page rate times the record's count, on a button that may
    # crawl the whole site. The analysis is posted against the run in the
    # picker, so it says which audit.
    assert got["acts"][0].startswith("Re-check Title & description + "), got["acts"]
    assert "· this part's checks · free" in got["acts"][0], got["acts"]
    assert "·" in got["acts"][0] and "~" not in got["acts"][0], (
        "a site-mode re-check still quotes a time for a crawl it has not sized",
        got["acts"])
    assert "Re-run analysis · this audit" in got["acts"][1], got["acts"]
    assert got["prov"][0].startswith("automatic checks 2026-"), got["prov"]
    assert "analysis title-desc" in got["prov"][1] and "claude-sonnet-5" in got["prov"][1]
    assert "2 rows" in got["prov"][1], got["prov"]
    # AO6: no Read button, no depth choice, no select, no re-audit column,
    # and no explanatory paragraph on the part.
    assert got["reads"] == 0 and got["selects"] == 0 and got["chips"] == 0, got
    assert got["reaudit"] == 0 and got["blurbs"] == 0, got
    assert "What this runs and why the numbers differ" not in got["text"]
    # The checks table stands where the page-scope "now" card stands. Site
    # scope grew a now-card at brief v16i: Part C's length strips, which are
    # a site-wide picture and belong here rather than at page scope. So the
    # count is 1, and the strips are asserted to be what it is.
    assert got["now"] == 1, got
    assert got["strips"] == 1, ("the site-scope now-card is not the length "
                                "strips", got)
    by = {r[1]: r for r in got["checks"]}
    # Sweep, brief, pages, state. The pages cell states its population since
    # item 155, so its text is `1` on a full-coverage run and `1 of N pages
    # crawled` otherwise - the number is asserted, the wording around it is
    # that item's clause and not this one's.
    assert by["ONP/meta-desc-length"][2:4] == ["1", "1"], by
    assert by["ONP/meta-desc-length"][4].startswith("1"), by
    assert by["ONP/meta-desc-length"][5] == "open", by
    # Item 208: a held row is in State only. It read ANALYSIS 2 here - two
    # holds counted as findings beside "not assessable" - and every count
    # column is a dash now, PAGES included.
    assert by["ONP/title-entity-alignment"][2:5] == ["—", "—", "—"], by
    assert by["ONP/title-entity-alignment"][5].startswith("not assessable · needs GBP"), by
    # "Clean on every page" is an absence claim and carries its population
    # too (item 155): clean on every page THIS RUN FETCHED. Over the record it
    # asserted a pass for pages nobody looked at.
    assert got["clean"][0].startswith("4 checks clean on every page this audit fetched"), got["clean"]
    assert "title-missing" in got["clean"][0], got["clean"]
    # Item 210: the engine's accounting at data weight, and the model's own
    # words behind a closed disclosure - no longer typeset as the page's facts.
    assert got["summary"].startswith("What the analysis returned"), got["summary"]
    assert "2 FAIL" in got["prose"], "the model's prose is not behind the disclosure"
    # A card per failing (check, page). The two holds share one reason, so
    # since item 213 they are one line with their page count, and since item
    # 211 no title says "not checked": what is asserted is that both held
    # pages are said once, as a card or in a line.
    import re as _re
    held_cards = sum(f["check"] == "ONP/title-entity-alignment" for f in got["fixes"])
    in_lines = sum(int(m.group(1)) if (m := _re.search(r"on (\d+) pages", line)) else 1
                   for line in got["na"] if "title-entity-alignment" in line)
    assert held_cards + in_lines == 2, (got["fixes"], got["na"])
    assert not any("not checked" in f["name"] for f in got["fixes"]), got["fixes"]
    agree = next(f for f in got["fixes"] if f["check"] == "ONP/meta-desc-length")
    assert agree["src"] == "· automatic checks and analysis agree" and agree["copy"], agree


@NEEDS_BROWSER
@pytest.mark.skipif(not (DIST / "index.html").is_file(), reason="dashboard not built")
def test_narrowed_the_card_reads_the_page_and_a_held_check_links_to_where_it_is_set(browser, served):
    base, site_id, _ = served
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    try:
        _open(pg, base, site_id)
        open_page_filter(pg)
        pg.fill(".page-find", "/")
        pg.wait_for_selector(".now-card", timeout=15_000)
        pg.wait_for_function(
            "() => document.querySelectorAll('.fix-card').length === 2", timeout=15_000)
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    assert got["acts"][0].startswith("Re-check ") and "· this page · free · ~" in got["acts"][0], got["acts"]
    assert "Re-run analysis · this page" in got["acts"][1], got["acts"]
    # The page's own strings, graded against the engine's own bounds, with
    # a held check stated as held rather than as a failure.
    assert got["now"] == 1 and got["checks"] == []
    assert got["badges"][0].startswith("str-pass|33 chars · in range"), got["badges"]
    assert any(b.startswith("str-held|title-entity-alignment not checked — GBP primary category")
               for b in got["badges"]), got["badges"]
    assert any(b.startswith(f"str-fail|{len(LONG)} chars · outside 120–160") for b in got["badges"])
    assert got["badges"][-1] == "str-pass|self", got["badges"]
    # Part B (brief v16i): the snippet card, measured in pixels. The card
    # names the words that fall off rather than a character cut, and the
    # "character count, not pixel width" note is gone - that note existed to
    # apologise for the thing this item fixed.
    assert got["snipTitle"], got
    assert "px" in got["snipCap"], got["snipCap"]
    assert got["note"] == "", ("the character-count note should be gone now "
                               "the card measures pixels")
    # Two cards: the failing string struck above its replacement, and the
    # held check with a link to where the input is set.
    fixes = {f["check"]: f for f in got["fixes"]}
    fix = fixes["ONP/meta-desc-length"]
    assert fix["now"] == LONG and fix["rep"] == GOOD and fix["copy"], fix
    held = fixes["ONP/title-entity-alignment"]
    # Item 211: label and value apart in the text, in the table's shape.
    assert held["why"].startswith("Why held: needs GBP primary category"), held
    assert held["link"] == "#/admin?tab=sites" and not held["copy"], held
    assert "[TO CONFIRM" not in got["text"]
    # Five, not the mockup's four: this page has a description, so
    # `meta-desc-missing` passes on it as well.
    assert got["clean"] == ["5 checks pass on this page: title-missing · title-length "
                            "· title-duplicate · meta-desc-missing · meta-desc-duplicate"], got["clean"]


def test_the_pane_holds_no_sentence_the_part_page_replaced():
    """The brief's own grep: the three phrases the old page opened with."""
    from pathlib import Path
    src = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "pane_analyse.tsx"
    text = src.read_text(encoding="utf-8")
    for phrase in ("Read the analysis", "Refresh this section", "Engine decides"):
        assert phrase not in text, phrase


def test_a_parts_renderer_is_rendered_and_not_called():
    """Every renderer keeps its own hooks, which means being rendered as an
    element rather than called as a function.

    `PART_RENDERERS` holds one `now` and one `body` per part and they do not
    hold the same number of hooks: `TitleDescNow` has none, `ImagesNow` has
    one `useState`, `HeadingsNow` has three. Called as plain functions those
    hooks belong to `PartPage`, whose hook count then changes with the part
    the operator opened - and React's rule is that it may not. Switching from
    Headings to Images inside one mounted pane took the whole screen down
    with `Minified React error #300`; the pane, the page finder and the rail
    all went with it, so the failure reads as a blank window rather than as a
    part that would not open.

    Driven at `test_the_crawls_own_limit_is_stated_whatever_the_filter_shows`,
    which opens Headings on `/many` and then Images on the same page and is
    where this was found. This clause is the static half: the same defect
    re-entered by a third renderer would fail here without needing a browser,
    and it names the two call sites rather than the symptom.
    """
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "dashboard" / "src"
           / "part_page.tsx").read_text(encoding="utf-8")
    # Comment lines are stripped first, and the dead end is why: the fix
    # commit wrote the defect's own shape into the file header to explain
    # it, and this clause read that sentence as the defect. A guard a
    # comment can turn red is the mirror of one a comment can turn green,
    # which `test_a_comment_cannot_change_what_this_guard_covers` is about
    # one file over.
    called = [l.strip() for l in src.split("\n")
              if ("render.now(" in l or "render.body(" in l)
              and not l.lstrip().startswith(("*", "//", "/*"))]
    assert not called, (
        "a part renderer is called as a plain function, so its hooks belong "
        "to the component that called it and the hook count changes with the "
        "part: " + "; ".join(called))
