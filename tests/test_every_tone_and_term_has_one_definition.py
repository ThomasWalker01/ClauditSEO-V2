"""Item 166: every tone and term has one definition, shown by disclosure.

`clauditseo/glossary.json` is the registry. A disclosure under a chip, the
glossary route and a client report's appendix are three renderings of it, and
none of them holds its own copy of a definition.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from clauditseo import anatomy
from clauditseo import glossary
from tests.needs_build import needs_build

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "dashboard" / "src"


def test_every_tone_class_in_the_stylesheet_has_a_registry_entry():
    css = (SRC / "styles.css").read_text(encoding="utf-8")
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)  # a comment names families, not classes
    classes = set(re.findall(r"\.(tone-[a-z]+(?:-[a-z]+)*)\b", css))
    bound = {e["class"] for e in glossary.entries() if e.get("class")}
    assert classes, "no tone classes found; the pattern is stale"
    assert classes <= bound, f"tone classes with no meaning behind them: {sorted(classes - bound)}"
    # And the other way: the Tone type and the registry name the same tones.
    pill = (SRC / "pill.tsx").read_text(encoding="utf-8")
    union = pill[pill.index("export type Tone"):pill.index("type Base")]
    tones = {f"tone-{t}" for t in re.findall(r'"([a-z-]+)"', union)}
    assert tones <= bound, sorted(tones - bound)


def test_every_registry_entry_is_whole_and_unique():
    ids = [e["id"] for e in glossary.entries()]
    assert len(ids) == len(set(ids)), [i for i in ids if ids.count(i) > 1]
    for e in glossary.entries():
        assert e["kind"] in ("tone", "term") and e["word"].strip() and e["full"].strip(), e
        assert e["kind"] != "tone" or e.get("class"), e


def test_the_disclosure_sentence_is_the_first_sentence_of_the_full_definition():
    for e in glossary.entries():
        s = glossary.short(e)
        assert e["full"].startswith(s), e["id"]
        assert s.endswith((".", "!", "?")), (e["id"], s)
        rest = e["full"][len(s):]
        assert rest == "" or re.match(r"\s+[A-Z]", rest), (e["id"], rest[:20])
    # The dashboard splits with the same expression, not a second opinion.
    ts = (SRC / "glossary.tsx").read_text(encoding="utf-8")
    assert f"/{glossary.FIRST_SENTENCE}/s" in ts


def test_every_term_in_a_report_has_an_appendix_entry_and_no_other_term_does():
    doc = ("# Report\n\nThe home page's LCP is slow. robots.txt blocks /private/.\n"
           "Every page names a canonical. The word opened and the site appear, "
           "and canonicalised is not canonical's match.\n")
    appendix = glossary.appendix(doc)
    words = re.findall(r"^\*\*(.+?)\*\*: ", appendix, re.M)
    assert sorted(words) == sorted(["LCP", "robots.txt", "canonical"]), words
    for e in glossary.entries():
        if e["word"] in words:
            assert f"**{e['word']}**: {e['full']}" in appendix
    assert glossary.appendix("# Nothing technical here.\n") == ""


def test_a_client_report_carries_the_appendix(tmp_path, monkeypatch):
    src = (ROOT / "clauditseo" / "reporting" / "generate.py").read_text(encoding="utf-8")
    at = src.index("markdown += glossary.appendix(markdown)")
    assert 'if audience == "client":' in src[at - 200:at]
    assert at < src.index("assert_report_honest(markdown,"), "the appendix must be inside what the gate reads"


def test_no_block_carries_its_own_copy_of_a_definition():
    """The string rendered is the string stored: no source file but the
    registry spells a definition out."""
    texts = {p: p.read_text(encoding="utf-8") for p in SRC.glob("*.tsx")}
    for e in glossary.entries():
        s = glossary.short(e)
        if len(s) < 40:
            continue
        copies = [p.name for p, t in texts.items() if s in t]
        assert not copies, (e["id"], copies)


def test_a_parts_own_words_are_disclosed_where_only_that_part_draws_them():
    """Adoption, per part (item 166).

    Speed labels every figure `lab` or `field` and Title & description names
    the viewport a cut is measured against. The 166 sweep filed both
    vocabularies as absent from the registry, and neither can go in the
    shared lists, because a part that draws no such figure would then
    disclose a word it never shows. `PART_LEGEND_EXTRA` is where they live,
    and this holds the three claims that makes true: the ids are registered,
    they are not already in the shared lists, and the file the comment names
    draws the word.
    """
    page = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    block = re.search(r"const PART_LEGEND_EXTRA[^{]*\{(.+?)\n\};", page, re.S)
    assert block, "PART_LEGEND_EXTRA is the one place a part's own words are named"
    extra = {k: re.findall(r'"([a-z-]+)"', v) for k, v in
             re.findall(r'\n\s+"?([a-z-]+)"?:\s*\[(.+?)\],', block.group(1))}
    assert extra, block.group(1)

    ids = {e["id"] for e in glossary.entries()}
    shared = set(re.findall(r'"([a-z-]+)"', re.search(
        r"const PART_LEGEND = \[(.+?)\];", page, re.S).group(1)))
    shared |= set(re.findall(r'"([a-z-]+)"', re.search(
        r"const BAND_LEGEND = \[(.+?)\];", page, re.S).group(1)))
    parts = {c.key for c in anatomy.CATEGORIES}
    drawn = {"speed": "speed_now.tsx", "title-desc": "title_snippet.tsx"}
    for part, terms in extra.items():
        assert part in parts, part
        for term in terms:
            assert term in ids, (part, term)
            assert term not in shared, (part, term, "already in a shared list")
            word = next(e["word"] for e in glossary.entries() if e["id"] == term)
            assert word in (SRC / drawn[part]).read_text(encoding="utf-8"), (part, word)


# --- rendered -------------------------------------------------------------

pw = pytest.importorskip("playwright")

from tests.test_a11y_rendered import served  # noqa: E402,F401  (module fixture)

_BLOCKS = {
    # route tail, the block, the chip that must come after the disclosure
    "landing": ("", ".cl-landing", ".cl-lane"),
    "record": ("?tab=all", ".pane-body", ".state-filters"),
    "part page": ("?tab=findings&part=crawl", ".part-page", ".tone"),
}


def _open(base, route, ready, fn, width=1400):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page(viewport={"width": width, "height": 1000})
        try:
            pg.goto(f"{base}/{route}", wait_until="load", timeout=30_000)
            pg.wait_for_selector(ready, timeout=30_000)
            pg.wait_for_timeout(300)
            return fn(pg)
        finally:
            browser.close()


@pytest.mark.parametrize("block", sorted(_BLOCKS))
@needs_build
def test_a_block_that_draws_a_chip_exposes_the_disclosure(served, block):
    base, ids = served
    tail, root, chip = _BLOCKS[block]
    got = _open(base, f"#/sites/{ids['site']}{tail}", f"{root} {chip}", lambda pg: pg.evaluate(
        """([root, chip]) => {
          const r = document.querySelector(root);
          const legend = r.querySelector('details.legend');
          const first = r.querySelector(chip);
          return { legend: !!legend,
                   before: !!legend && !!(legend.compareDocumentPosition(first) & Node.DOCUMENT_POSITION_FOLLOWING),
                   rows: legend ? [...legend.querySelectorAll('.legend-row')].map((d) => ({
                     id: d.dataset.term, word: d.querySelector('dt').textContent,
                     short: d.querySelector('.legend-short').textContent })) : [] };
        }""", [root, chip]))
    assert got["legend"] and got["before"], got
    by_id = {e["id"]: e for e in glossary.entries()}
    for row in got["rows"]:
        e = by_id[row["id"]]
        # The disclosure text is the registry text.
        assert row["word"] == e["word"] and row["short"] == glossary.short(e), row


@needs_build
def test_the_disclosure_is_reachable_by_keyboard_and_closed_by_default(served):
    base, ids = served

    def go(pg):
        closed = pg.evaluate("() => document.querySelector('.cl-landing details.legend').open")
        height = pg.evaluate("() => document.querySelector('.cl-landing details.legend').getBoundingClientRect().height")
        summary = pg.query_selector(".cl-landing details.legend summary")
        for _ in range(200):
            pg.keyboard.press("Tab")
            if pg.evaluate("(s) => document.activeElement === s", summary):
                break
        else:
            raise AssertionError("Tab never reached the disclosure")
        pg.keyboard.press("Enter")
        opened = pg.evaluate("() => document.querySelector('.cl-landing details.legend').open")
        return closed, height, opened
    closed, height, opened = _open(base, f"#/sites/{ids['site']}", ".cl-landing details.legend", go)
    assert closed is False and opened is True, (closed, opened)
    assert height < 30, f"a closed disclosure costs {height}px"


@needs_build
def test_every_term_chip_carries_its_word_as_text(served):
    base, ids = served
    routes = [f"#/sites/{ids['site']}", f"#/sites/{ids['site']}?tab=all",
              f"#/sites/{ids['site']}?tab=findings", "#/glossary"]
    for route in routes:
        bare = _open(base, route, ".tone, .glossary", lambda pg: pg.evaluate(
            """() => [...document.querySelectorAll('.tone')]
                 .filter((e) => !(e.textContent || '').trim())
                 .map((e) => e.outerHTML.slice(0, 120))"""))
        assert not bare, (route, bare)


@needs_build
def test_the_glossary_route_lists_every_registry_entry_once(served):
    base, _ids = served
    got = _open(base, "#/glossary?term=hreflang", ".glossary-entry", lambda pg: pg.evaluate(
        """() => ({ ids: [...document.querySelectorAll('.glossary-entry')].map((e) => e.dataset.term),
                    here: document.querySelector('.glossary-here')?.dataset.term,
                    nav: [...document.querySelectorAll('.topnav a')].map((a) => a.textContent.trim()) })"""))
    assert sorted(got["ids"]) == sorted(e["id"] for e in glossary.entries()), got["ids"]
    assert len(got["ids"]) == len(set(got["ids"]))
    assert got["here"] == "hreflang" and "Glossary" in got["nav"], got


@needs_build
def test_full_definition_links_reach_the_glossary_entry(served):
    base, ids = served

    def go(pg):
        pg.click(".cl-landing details.legend summary")
        pg.click(".cl-landing .legend-row[data-term=lane-settled] .legend-full")
        pg.wait_for_selector(".glossary-here", timeout=15_000)
        return pg.evaluate("() => document.querySelector('.glossary-here').dataset.term")
    assert _open(base, f"#/sites/{ids['site']}", ".cl-landing details.legend", go) == "lane-settled"


#: The operator's wording ruling of 2026-09-15: `sweep` reads "automatic
#: checks" and `brief` reads "analysis" on every screen. Two uses of "brief"
#: stay, and are not the engine's word: a content brief (a writer's document
#: the generator produces) and a build-note reference ("brief v18").
_INTERNAL_WORDS_JS = r"""() => {
  const text = [document.body.innerText,
    ...[...document.querySelectorAll('[title],[aria-label]')].flatMap((e) => [e.getAttribute('title'), e.getAttribute('aria-label')])]
    .filter(Boolean).join('\n')
    .replace(/content briefs?/gi, '').replace(/brief v\d+/gi, '');
  // An id in code type (`content-brief`, `a11y-sweep`) is an identifier, not
  // a word, so a hyphen on either side does not count.
  return { sweep: (text.match(/(?<![\w-])sweep(s|ing)?(?![\w-])/gi) || []).length,
           brief: (text.match(/(?<![\w-])briefs?(?![\w-])/gi) || []).length,
           lines: text.split('\n').filter((l) => /(?<![\w-])(sweep|briefs?)(?![\w-])/i.test(l)).slice(0, 40) };
}"""


def test_no_screen_says_sweep_or_brief(served):
    base, ids = served
    site = ids["site"]
    routes = [f"#/sites/{site}", f"#/sites/{site}?tab=findings", f"#/sites/{site}?tab=history",
              f"#/sites/{site}?tab=all", f"#/sites/{site}?tab=all&view=audits",
              f"#/sites/{site}?tab=findings&part=crawl", f"#/sites/{site}?tab=findings&part=title-desc",
              f"#/sites/{site}?tab=findings&part=security", "#/", "#/admin"]
    bad = {}
    for route in routes:
        got = _open(base, route, "body", lambda pg: (pg.wait_for_timeout(1500), pg.evaluate(_INTERNAL_WORDS_JS))[1])
        if got["sweep"] or got["brief"]:
            bad[route] = got
    assert not bad, bad
