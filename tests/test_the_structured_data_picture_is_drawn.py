"""The Structured data picture, drawn at the running product.

Brief v16a step AT-b. The three assertions the item's Accept names, made
against a real browser loading the built bundle: the level-0 card count is
top-level nodes plus ghosts plus inline copies and never items; the edge
overlay draws one edge per pair the model resolved; and no node card is
filled, because a fill would be carrying a state that the ring already
carries.

**Why the designer's own fixtures and not the shared crawl fixture.**
`test_a11y_rendered.py`'s `/schema` page carries one Organization node: no
second node, so no edge; no reference, so no dangling ghost; no list, so no
chip; and no second block, so no inline copy. Three of the four clauses
below would have been vacuous against it and would have passed against a
renderer that drew nothing at all - which is DISCIPLINE rule 5, and is the
defect that file's own UX-60 note records paying for once already. Enriching
that fixture instead was rejected on measurement rather than taste: forty-odd
browser tests share it and several assert finding counts, so a page that
gained a wired `@graph` would move numbers in guards that have nothing to do
with this one.

So the markup here is the designer's pack, byte for byte, planted straight
into a page record. That is also what makes the numbers checkable: they are
the ones brief v16a states and `test_the_structured_data_graph.py` already
asserts about the model, so this file is asking whether the *drawing* agrees
with the model rather than re-deciding what the model should say.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from clauditseo.db.connection import connect
from clauditseo.modules import pagefacts
from clauditseo.persistence import runs
from clauditseo.persistence.repo import create_id, now_iso
from tests.test_a11y_rendered import DIST
from tests.test_triage_ranks_the_section_rail import _serve
from tests.parts import ANATOMY_READY, open_part, open_page_filter

EXAMPLES = Path(__file__).resolve().parent / "fixtures" / "schema_examples"

#: The audited host is Summit's own, so `short_id` shortens the `@id`s the
#: way it will on the operator's screen and the `.au` locale rule is live.
#: Acme's blocks declare no `@id` at all - which is why that page is
#: UNIDENTIFIED - so nothing about it depends on sitting under this domain.
SITE = "summit-roofing-fixture.com.au"
RICH = f"https://{SITE}/"
THREE = f"https://{SITE}/three-blocks"

NEEDS_BROWSER = pytest.mark.skipif(
    not __import__("clauditseo.axe", fromlist=["axe"]).available(),
    reason="needs clauditseo[render] and `playwright install chromium`")


def _text(name: str) -> str:
    return (EXAMPLES / name).read_text(encoding="utf-8")


def _page(url: str, blocks: list[str]) -> dict:
    """One page record carrying markup, as the crawler would have stored it
    since ENGINE_VERSION 0.16.0."""
    return {
        # `content_type` as the crawler stores it: a page without one is not
        # a page the run could read, and its facts are never written (item 239).
        "url": url, "status": 200, "content_type": "text/html", "title": "Fixture",
        "canonical": url, "lang": "en-AU",
        "jsonld_blocks": len(blocks),
        "jsonld_raw": pagefacts.jsonld_raw(blocks, [""] * len(blocks)),
        "schema_inventory": pagefacts.schema_inventory(blocks, [""] * len(blocks)),
        "profile_links": [],
    }


def _plant(db, site_id: str) -> str:
    """Two pages: one rich and fragmented, one disjointed across three blocks.

    The second exists for the inline copy. It is the only shape in the pack
    that produces a card level 0 draws which is neither a top-level node nor
    a ghost, and the count clause below is exactly about that distinction.
    """
    conn = connect(db)
    run_id = runs.create_run(conn, site_id, ["ONP"], "T2")
    rich = _text("2_rich_but_fragmented.json")
    acme = json.loads(_text("3_disjointed_three_blocks.json"))
    runs.store_evidence(conn, run_id, {"pages": [
        _page(RICH, [rich]),
        _page(THREE, [json.dumps(b) for b in acme]),
    ]})
    runs.mark_complete(conn, run_id, now_iso())
    # One finding, pinned through the same `block` field brief v16 step AT
    # writes, so the badge, the checklist row and the fix card all carry the
    # number the engine gave it - which section 7 calls the only agreement
    # mechanism between the picture and the list.
    inventory = pagefacts.schema_inventory([rich], [""])
    n, entry = next((i + 1, r) for i, r in enumerate(inventory) if r.get("id"))
    # A row on each page. The second is not decoration: the payload's `pages`
    # list is built from what findings name, so a page nothing is open on
    # cannot be reached by the page picker at all - which is how the drawing
    # for the three-block page was unreachable on the first run of this file.
    rows = [("sg-thin", "schema-entity-thin", "Entity could say more", RICH,
             {"block": "{}#{}".format(entry.get("type"), n)}),
            ("sg-island", "schema-island", "Block connected to nothing else",
             THREE, {})]
    with conn:
        for fp, check, summary, url, ev in rows:
            conn.execute(
                "INSERT INTO findings (id, run_id, dimension, check_id,"
                " severity, source, summary, affected_urls, fingerprint,"
                " created_at, evidence) VALUES (?, ?, 'ONP', ?, 'medium',"
                " 'deterministic', ?, ?, ?, ?, ?)",
                (create_id(), run_id, check, summary, json.dumps([url]), fp,
                 now_iso(), json.dumps(ev)))
            conn.execute(
                "INSERT INTO finding_states (site_id, fingerprint, state,"
                " changed_by_run, updated_at) VALUES (?, ?, 'open', ?, ?)",
                (site_id, fp, run_id, now_iso()))
    conn.close()
    return run_id


@pytest.fixture(scope="module")
def served():
    server, thread, db, base = _serve("sgpicture")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "Picture Co"},
                            timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": SITE}, timeout=30).json()
        _plant(db, site["id"])
        yield base, site["id"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def _graph(base: str, site_id: str, page: str) -> dict:
    view = httpx.get(f"{base}/api/sites/{site_id}/anatomy",
                     params={"page": page}, timeout=30).json()
    part = next(c for c in view["categories"] if c["key"] == "schema")
    return part["graph"]


# --- the payload the drawing is made from --------------------------------

def test_the_part_payload_carries_the_picture_for_the_page_it_is_narrowed_to(served):
    base, site_id = served
    g = _graph(base, site_id, RICH)
    assert g is not None, "the schema part carried no graph"
    # Brief v16a's own numbers for this fixture, through the served API.
    assert g["verdict"]["entity"] == "FRAGMENTED"
    assert len(g["blocks"]) == 1
    assert len([n for n in g["nodes"] if n["kind"] == "node"]) == 4
    assert len([n for n in g["nodes"] if n["island"]]) == 2
    assert len([x for x in g["ghosts"] if x["kind"] == "ghost-dangling"]) == 2
    catalog = next(c for c in g["collections"] if c["prop"] == "hasOfferCatalog")
    assert catalog["count"] == 15
    # The `@id`s shorten against the audited host, which is what puts
    # `/#localbusiness` on a card rather than the whole URL.
    assert any(n["sid"] == "/#localbusiness" for n in g["nodes"])


def test_only_the_structured_data_part_is_given_a_picture(served):
    base, site_id = served
    view = httpx.get(f"{base}/api/sites/{site_id}/anatomy",
                     params={"page": RICH}, timeout=30).json()
    drawn = [c["key"] for c in view["categories"] if c.get("graph")]
    assert drawn == ["schema"], drawn


def test_the_whole_site_view_has_no_picture_because_it_has_no_page(served):
    base, site_id = served
    view = httpx.get(f"{base}/api/sites/{site_id}/anatomy", timeout=30).json()
    assert all(not c.get("graph") for c in view["categories"])


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
  const cards = [...document.querySelectorAll('.sg-graph .sg-node')];
  const cs = (el) => getComputedStyle(el);
  return {
    nodes: cards.length,
    keys: cards.map((c) => c.dataset.key),
    kinds: cards.map((c) => [...c.classList].find((k) => k.startsWith('sg-k-'))),
    fills: cards.map((c) => cs(c).backgroundColor),
    rings: cards.map((c) => cs(c).borderTopColor),
    edges: document.querySelectorAll('.sg-edges g.sg-edge').length,
    resolved: document.querySelectorAll('.sg-edges g.sg-e-ok').length,
    dangling: document.querySelectorAll('.sg-edges g.sg-e-dangling').length,
    chips: [...document.querySelectorAll('.sg-graph .sg-chip')]
             .map((c) => (c.querySelector('.sg-cp')?.textContent || '')
                         + '|' + (c.querySelector('.sg-cc')?.textContent || '')),
    islands: document.querySelectorAll('.sg-graph .sg-island').length,
    ghostZone: document.querySelectorAll('.sg-offbox').length,
    verdict: (document.querySelector('.sg-verdict')?.textContent || '').trim(),
    checklist: [...document.querySelectorAll('.sg-checklist .sg-crow')]
                 .map((r) => r.textContent.trim()),
    badges: [...document.querySelectorAll('.sg-graph .sg-bd')]
              .map((b) => b.textContent.trim()),
    drillTitle: (document.querySelector('.sg-dtitle')?.textContent || '').trim(),
  };
}"""


def _open(pg, base, site_id, page):
    pg.goto(f"{base}/#/sites/{site_id}?tab=findings", wait_until="load",
            timeout=30_000)
    pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
    open_part(pg, 'Structured data')
    pg.wait_for_selector(".part-page", timeout=15_000)
    open_page_filter(pg)
    pg.fill(".page-find", page)
    pg.wait_for_selector(".sg-graph .sg-node", timeout=15_000)


@NEEDS_BROWSER
@pytest.mark.skipif(not (DIST / "index.html").is_file(), reason="dashboard not built")
def test_level_zero_draws_a_card_per_node_ghost_and_copy_and_never_per_item(
        browser, served):
    """RENDER_RULES 8's load-bearing sentence: level 0 never grows with item
    counts.

    Summit carries twenty-nine `areaServed` cities and fifteen catalogue
    entries. If any of those reached the canvas as a card the count below
    would be in the forties; the assertion is that it is the model's own
    node total, and that the cities are on screen as a counted chip instead.
    """
    base, site_id = served
    g = _graph(base, site_id, RICH)
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    try:
        _open(pg, base, site_id, RICH)
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    expected = len(g["nodes"]) + len(g["ghosts"])
    assert got["nodes"] == expected, (got["nodes"], expected, got["keys"])
    # Non-vacuous: the fixture has to have the items that must NOT be cards.
    biggest = max(c["count"] for c in g["collections"])
    assert biggest >= 15, biggest
    assert got["nodes"] < biggest, (
        "the canvas has as many cards as the largest list has items, so a "
        "renderer drawing items as cards would pass this")
    assert "areaServed|29" in got["chips"], got["chips"]
    assert got["islands"] == 2, got["islands"]
    assert got["ghostZone"] == 1
    assert got["verdict"].startswith("Entity: FRAGMENTED"), got["verdict"]


@NEEDS_BROWSER
@pytest.mark.skipif(not (DIST / "index.html").is_file(), reason="dashboard not built")
def test_the_overlay_draws_one_edge_per_pair_the_model_resolved(browser, served):
    base, site_id = served
    g = _graph(base, site_id, RICH)
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    try:
        _open(pg, base, site_id, RICH)
        # The overlay is measured from the laid-out boxes, so it is drawn a
        # frame after the cards. Waiting on the model's own count rather
        # than on a sleep.
        pg.wait_for_function(
            "(n) => document.querySelectorAll('.sg-edges g.sg-edge').length === n",
            arg=len(g["edges"]), timeout=15_000)
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    assert got["edges"] == len(g["edges"]), (got["edges"], len(g["edges"]))
    for kind, key in (("dangling", "dangling"), ("ok", "resolved")):
        assert got[key] == len([e for e in g["edges"] if e["kind"] == kind]), (
            kind, got[key])
    # Non-vacuous in both directions: this fixture has resolved edges AND
    # dangling ones, so a renderer drawing only one style would fail.
    assert got["dangling"] == 2, got["dangling"]
    assert got["resolved"] >= 1, got["resolved"]


@NEEDS_BROWSER
@pytest.mark.skipif(not (DIST / "index.html").is_file(), reason="dashboard not built")
def test_no_node_card_is_filled_because_the_ring_is_what_carries_the_state(
        browser, served):
    """The tone rule, driven rather than read off the stylesheet.

    RESPONSE's third point: every reference mockup filled node circles from
    a per-`@type` palette, and the first instinct on picking this up will be
    to reach for one. A source scan for a colour literal would be satisfied
    by a variable; what the rule is about is what the pixels do, so this
    asks the browser for the computed values.

    Two clauses, because either alone is passable by a mistake: every card
    shares one background, AND the rings differ. A renderer that filled
    nothing and also ringed nothing would satisfy the first and say nothing
    about any node's state.
    """
    base, site_id = served
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    try:
        _open(pg, base, site_id, RICH)
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    assert got["nodes"] >= 4, got["nodes"]
    # Ghosts are drawn on the hatched zone and are deliberately unfilled, so
    # the fill set is taken over the real nodes.
    real = [i for i, k in enumerate(got["kinds"]) if k == "sg-k-node"]
    fills = {got["fills"][i] for i in real}
    assert len(fills) == 1, (
        "node cards are filled in more than one colour, so a fill is "
        f"carrying a state or a type: {fills}")
    rings = {got["rings"][i] for i in real}
    assert len(rings) > 1, (
        "every node card has the same ring, so the picture is not saying "
        f"which nodes are clean and which are not: {rings}")


@NEEDS_BROWSER
@pytest.mark.skipif(not (DIST / "index.html").is_file(), reason="dashboard not built")
def test_the_inline_copy_is_a_card_of_its_own_inside_its_parents_block(
        browser, served):
    """Acme's `FinancialProduct.provider`: a second copy of the entity
    rather than a reference to it. It is drawn as its own card, which is the
    case that makes "nodes plus ghosts plus copies" different from "top-level
    nodes plus ghosts"."""
    base, site_id = served
    g = _graph(base, site_id, THREE)
    assert g["verdict"]["entity"] == "UNIDENTIFIED"
    copies = [n for n in g["nodes"] if n["kind"] == "inline-copy"]
    assert len(copies) == 1, copies
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    try:
        _open(pg, base, site_id, THREE)
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    assert got["kinds"].count("sg-k-inline-copy") == 1, got["kinds"]
    assert got["nodes"] == len(g["nodes"]) + len(g["ghosts"]), got["keys"]


@NEEDS_BROWSER
@pytest.mark.skipif(not (DIST / "index.html").is_file(), reason="dashboard not built")
def test_a_checklist_row_selects_its_node_and_scrolls_to_its_fix_card(
        browser, served):
    """The item's own amendment to the designer's version, which only
    scrolls: a row does both, so the picture is showing the node the card is
    about by the time the reader arrives at it."""
    base, site_id = served
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    try:
        _open(pg, base, site_id, RICH)
        rows = pg.locator(".sg-checklist .sg-crow")
        assert rows.count() >= 1, "no checklist row, so nothing to click"
        rows.first.click()
        # `attached`, not `visible`: the same click scrolls the fix card to
        # the middle of the viewport, so the node it selected may well be
        # above the fold by the time this runs. That it is selected is the
        # assertion; whether it is on screen is what the sticky graph below
        # is for.
        pg.wait_for_selector(".sg-graph .sg-node.sg-sel", state="attached",
                             timeout=10_000)
        got = pg.evaluate("""() => ({
          sel: [...document.querySelectorAll('.sg-graph .sg-node.sg-sel')]
                 .map((n) => n.dataset.key),
          cards: document.querySelectorAll('[data-fix-n]').length,
          sticky: document.querySelectorAll('.sg-canvas.sg-hasglow').length,
          stickyPx: (() => {
            const c = document.querySelector('.sg-canvas.sg-hasglow');
            return c ? Math.round(c.getBoundingClientRect().height) : 0;
          })(),
        })""")
    finally:
        pg.close()
    assert len(got["sel"]) == 1, got["sel"]
    # The fix card the row points at exists and carries the picture's number.
    assert got["cards"] >= 1, got


@NEEDS_BROWSER
@pytest.mark.skipif(not (DIST / "index.html").is_file(), reason="dashboard not built")
def test_scrolling_the_fixes_lights_the_node_and_the_graph_goes_sticky(
        browser, served):
    """The item's addition from layout 2, measured on a real scroll.

    Two halves, and both are the point: the card nearest the top lights the
    node it is anchored to, and the canvas keeps a reduced height in view so
    a reader working down the cards can still see where each one lands.

    The height asserted is the stylesheet's, read back off the rendered box
    rather than off the CSS - `220` appears in `schema_graph.css` and
    nowhere else since the component stopped setting it inline, and this is
    what checks that the one place it lives is the one that applies.
    """
    base, site_id = served
    g = _graph(base, site_id, RICH)
    anchored = [f for f in g["findings"] if f["anchor_keys"]]
    assert anchored, "no anchored finding, so nothing could light up"
    pg = browser.new_page(viewport={"width": 1568, "height": 900})
    try:
        _open(pg, base, site_id, RICH)
        assert pg.locator("[data-fix-n]").count() >= 1, (
            "no numbered fix card, so the scroll-link has nothing to observe")
        # Before: nothing is lit and the canvas is in the flow.
        assert pg.locator(".sg-canvas.sg-hasglow").count() == 0
        pg.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        # Waited for and read in ONE call. A `wait_for_selector` followed by
        # an `evaluate` has a gap, and the glow is allowed to clear inside
        # it - the observer re-picks whenever the visible set changes, so a
        # scroll still settling can drop it for a frame. Under `-n auto` that
        # gap widened enough to hand `getComputedStyle` a null, which is the
        # test racing the product rather than the product being wrong.
        got = pg.wait_for_function("""() => {
          const c = document.querySelector('.sg-canvas.sg-hasglow');
          if (!c) return null;
          return {
            position: getComputedStyle(c).position,
            height: Math.round(c.getBoundingClientRect().height),
            lit: [...document.querySelectorAll('.sg-node.sg-sel')]
                   .map((n) => n.dataset.key),
          };
        }""", timeout=15_000).json_value()
    finally:
        pg.close()
    assert got["position"] == "sticky", got
    assert got["height"] == 220, got
    # And it is the node the card is about, not merely some node.
    assert got["lit"] == [anchored[0]["anchor_keys"][0]], (got, anchored[0])


@NEEDS_BROWSER
@pytest.mark.skipif(not (DIST / "index.html").is_file(), reason="dashboard not built")
def test_every_control_in_the_picture_has_text_that_can_be_read(browser, served):
    """The white-on-white trap, guarded because it shipped once.

    `styles.css` styles the bare `button` element as this app's solid accent
    control - `background: var(--accent-solid); color: #fff`. Anything in the
    picture that is a `button` and is not that control inherits white text,
    and the drill's node rows did: `getComputedStyle` read
    `rgb(255, 255, 255)` on text sitting on `--surface`, so the column looked
    like coloured bars with nothing beside them. A screenshot reads that as a
    layout bug; only the computed colour says what it was.

    Asserted as a contrast ratio rather than as "not white", because "not
    white" is satisfied by `#fefefe` and the next dark-mode token to be
    dropped in here will not be white at all.
    """
    base, site_id = served
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    try:
        _open(pg, base, site_id, RICH)
        got = pg.evaluate("""() => {
          const lum = (c) => {
            const [r, g, b] = c.match(/\d+(\.\d+)?/g).slice(0, 3).map(Number)
              .map((v) => { v /= 255;
                return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
            return 0.2126 * r + 0.7152 * g + 0.0722 * b;
          };
          const bgOf = (el) => {
            for (let n = el; n; n = n.parentElement) {
              const b = getComputedStyle(n).backgroundColor;
              if (b && !/rgba\(0, 0, 0, 0\)|transparent/.test(b)) return b;
            }
            return 'rgb(255, 255, 255)';
          };
          return [...document.querySelectorAll('.sg-root .sg-drow, '
                  + '.sg-root .sg-crow, .sg-root .sg-dblabel, .sg-root .sg-crumb')]
            .map((el) => {
              const a = lum(getComputedStyle(el).color), b = lum(bgOf(el));
              const [hi, lo] = a > b ? [a, b] : [b, a];
              return { text: (el.textContent || '').trim().slice(0, 30),
                       ratio: Math.round(((hi + 0.05) / (lo + 0.05)) * 100) / 100 };
            });
        }""")
    finally:
        pg.close()
    assert len(got) >= 5, ("too few controls to be asserting about: "
                           + repr(got))
    bad = [g for g in got if g["ratio"] < 4.5]
    assert not bad, bad


def test_the_pictures_stylesheet_reaches_only_the_picture():
    """Every selector in `schema_graph.css` is namespaced `.sg-`.

    `main.tsx` imports the sheet globally, so it is parsed on every screen
    in the product, not only this one. A rule in it that matched anything
    else - a bare `button`, a `.card`, an element selector - would be this
    part page restyling screens it has nothing to do with, and the symptom
    would appear somewhere with no connection to structured data at all.

    It is also what lets a red browser guard elsewhere be reasoned about:
    the argument that this step's diff cannot reach the reports rail or the
    brief-target picker rests on this sheet touching nothing they render,
    and an argument that rests on a property is worth a test of it.
    """
    css = (Path(__file__).resolve().parents[1] / "dashboard" / "src"
           / "schema_graph.css").read_text(encoding="utf-8")
    css = __import__("re").sub(r"/\*.*?\*/", "", css, flags=16)  # re.S
    selectors: list[str] = []
    for block in css.split("{")[:-1]:
        head = block.rsplit("}", 1)[-1].strip()
        if not head or head.startswith("@") or head.startswith("--"):
            continue
        for one in head.split(","):
            one = one.strip()
            if one:
                selectors.append(one)
    assert len(selectors) > 40, ("the stylesheet did not parse into "
                                 f"selectors: {selectors[:5]}")
    stray = [s for s in selectors if ".sg-" not in s]
    assert not stray, stray
