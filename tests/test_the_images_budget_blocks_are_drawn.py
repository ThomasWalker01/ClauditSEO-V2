"""What the site's images weigh, drawn at the running product.

Brief v16c. Two blocks on the Images part page - a bytes-for-pixels scatter
of every image the crawl could weigh, and the selected page's own thumbnails
with a frame where a check fired - and the clauses below are the item's own
Accept list: a dot and its finding agree, an image under the floor is drawn
but not scored, the budget lines come from the registry, the wall frames only
what the checks raised, a run with no resource log says so rather than
drawing nothing, and pressing a dot selects its image (item 244).

**Why a fixture of its own and not the shared crawl fixture.** The reason
`test_the_crawl_depth_block_is_drawn.py` gives one file earlier, and here it
is stronger: `test_a11y_rendered.py` stores its evidence through
`snapshot(crawled)` with no `image_measurements` at all, so no image on it
carries a weight or a rendered box and every clause below would have been
vacuous - DISCIPLINE rule 5. Adding measurements to that fixture would raise
`img-heavy` rows on it and move finding counts in forty-odd browser tests
that have nothing to do with this block.

The measurements are planted rather than taken in a browser, for the reason
brief v16a's picture test plants its markup: `imaging.measure` is what
produces them and `test_the_images_brief_and_its_checks.py` already asks
whether that pass is right. This file asks whether the *drawing* agrees with
the checks, which is a different question and the only one it can answer from
a browser.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from clauditseo.db.connection import connect
from clauditseo.modules.onp import (BUDGET_IMAGE_KB, BYTES_PER_PIXEL_CAP,
                                    PER_PIXEL_FLOOR_KB, image_weight_state)
from clauditseo.persistence import runs
from clauditseo.persistence.repo import create_id, now_iso
from tests.test_a11y_rendered import DIST
from tests.test_triage_ranks_the_section_rail import _serve
from tests.parts import ANATOMY_READY, open_part, open_page_filter

SITE = "imagebudget.test"
HOME = f"https://{SITE}/"
SHOP = f"https://{SITE}/shop"

#: The planted images, and every count below is derived from these rather
#: than written twice. `(src, alt, rendered w, rendered h, weight kb)`, with
#: `alt=None` meaning the attribute is absent - which is what
#: `img-alt-missing` fires on, together with a blank one.
#:
#: Chosen to put one image in each of the four states the legend names,
#: against the defaults (300 KB flat, 1.0 B/px, 20 KB floor):
#:   hero      600x400 at 400 KB  - over the flat ceiling, has alt     -> warn
#:   banner    300x200 at 120 KB  - 2.05 B/px, no alt                  -> bad
#:   photo     800x600 at  90 KB  - 0.19 B/px, over the floor          -> ok
#:   icon       30x30  at   1 KB  - 1.14 B/px but under the floor      -> mute
#:   sprite    ------- at  40 KB  - weighed, never measured on screen  -> unplaced
#:   logo      200x80  at   0 KB  - a cross-origin zero                -> unmeasured
IMAGES = [
    ("/img/hero.jpg", "A warehouse at dusk", 600, 400, 400),
    ("/img/banner.png", None, 300, 200, 120),
    ("/img/photo.webp", "Two people at a bench", 800, 600, 90),
    ("/img/icon.svg", "Home", 30, 30, 1),
    ("/img/sprite.png", "Sprite sheet", 0, 0, 40),
    ("/img/logo.svg", "Acme", 200, 80, 0),
]
#: A second page, so the scatter has something to narrow away from and a dot
#: has somewhere to open.
SHOP_IMAGES = [("/img/product.jpg", None, 500, 500, 380)]

#: What the states must therefore be, derived from the same function the
#: check calls rather than written out as a second opinion.
def _expected(rows):
    out = {}
    for src, alt, w, h, kb in rows:
        state, _ = image_weight_state(kb, w * h, BUDGET_IMAGE_KB,
                                      BYTES_PER_PIXEL_CAP, PER_PIXEL_FLOOR_KB)
        missing = alt is None or not alt.strip()
        out[src] = ("unmeasured" if state == "unmeasured"
                    else "bad" if state == "over" and missing
                    else "warn" if state == "over"
                    else "mute" if state == "unscored" else "ok")
    return out


EXPECTED = _expected(IMAGES)
#: Drawable: measured, and with a box to be drawn against.
DRAWABLE = [src for src, _, w, h, kb in IMAGES if kb and w and h]

NEEDS_BROWSER = pytest.mark.skipif(
    not __import__("clauditseo.axe", fromlist=["axe"]).available(),
    reason="needs clauditseo[render] and `playwright install chromium`")


def _record(src: str, alt: str | None, w: int, h: int, kb: int) -> dict:
    """One `image_inventory` row as `crawler.evidence.snapshot` writes it:
    the markup's own fields, with the browser's merged in where one ran."""
    record: dict = {"src": src, "alt": alt, "tag": "img",
                    "region_class": "body", "weight_kb": kb}
    if w and h:
        # Every breakpoint the same box, which is what a fixed-width image
        # measures at; the reader takes the widest and this is it.
        record["rendered"] = {"1920": [w, h], "768": [w, h]}
        record["intrinsic_w"], record["intrinsic_h"] = w, h
    return record


def _page(url: str, images: list) -> dict:
    return {"url": url, "status": 200, "content_type": "text/html",
            "title": "Fixture", "canonical": url, "word_count": 400,
            "images": [[src, alt] for src, alt, _, _, _ in images],
            "image_total": len(images),
            "image_inventory": [_record(*row) for row in images]}


def _plant(db: Path, site_id: str, pages: list[tuple[str, list]]) -> str:
    conn = connect(db)
    run_id = runs.create_run(conn, site_id, ["ONP"], "T3")
    runs.store_evidence(conn, run_id, {
        "start_url": HOME, "pages": [_page(url, imgs) for url, imgs in pages]})
    runs.mark_complete(conn, run_id, now_iso())
    # One `img-heavy` row per image the check would raise on, planted the
    # same way the block's dots are derived: the agreement clause below is
    # only worth anything if the two lists are built from the same rule and
    # then compared, which is what `image_weight_state` being the only
    # implementation buys.
    with conn:
        for url, imgs in pages:
            for src, alt, w, h, kb in imgs:
                state, _ = image_weight_state(kb, w * h, BUDGET_IMAGE_KB,
                                              BYTES_PER_PIXEL_CAP, PER_PIXEL_FLOOR_KB)
                if state != "over":
                    continue
                fp = f"heavy-{src}"
                conn.execute(
                    "INSERT INTO findings (id, run_id, dimension, check_id,"
                    " severity, source, summary, affected_urls, affected_total,"
                    " evidence, fingerprint, created_at) VALUES (?, ?, 'ONP',"
                    " 'img-heavy', 'medium', 'deterministic', ?, ?, 1, ?, ?, ?)",
                    (create_id(), run_id, f"{src} on {url} weighs {kb} KB.",
                     json.dumps([url]), json.dumps({"image": src, "weight_kb": kb}),
                     fp, now_iso()))
                conn.execute(
                    "INSERT INTO finding_states (site_id, fingerprint, state,"
                    " changed_by_run, updated_at) VALUES (?, ?, 'open', ?, ?)",
                    (site_id, fp, run_id, now_iso()))
    conn.close()
    return run_id


def _site(base: str, domain: str) -> str:
    client = httpx.post(f"{base}/api/clients", json={"name": "Budget Co"},
                        timeout=30).json()
    return httpx.post(f"{base}/api/clients/{client['id']}/sites",
                      json={"domain": domain}, timeout=30).json()["id"]


@pytest.fixture(scope="module")
def served():
    """Three sites: the planted run, a run whose images nobody weighed, and
    one whose site record moves the budget."""
    server, thread, db, base = _serve("imagebudget")
    try:
        full = _site(base, SITE)
        _plant(db, full, [(HOME, IMAGES), (SHOP, SHOP_IMAGES)])

        # No resource log at all: every weight absent, which is what a crawl
        # run without Playwright stores.
        blank = _site(base, f"noweights.{SITE}")
        _plant(db, blank, [(HOME, [(src, alt, w, h, 0)
                                   for src, alt, w, h, _ in IMAGES])])

        # The same images against a record that halves the per-pixel ceiling.
        tight = _site(base, f"tight.{SITE}")
        _plant(db, tight, [(HOME, IMAGES)])
        # Written to the record directly, the way `_plant` writes evidence:
        # what is under test is that the block reads the record, not how a
        # value gets onto it.
        conn = connect(db)
        with conn:
            conn.execute("UPDATE sites SET bytes_per_pixel=?,"
                         " budget_image_floor_kb=? WHERE id=?",
                         ("0.1", "50", tight))
        conn.close()
        yield base, {"full": full, "blank": blank, "tight": tight}
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def _view(base: str, site_id: str, page: str | None = None) -> dict:
    return httpx.get(f"{base}/api/sites/{site_id}/anatomy",
                     params={"page": page} if page else None, timeout=30).json()


def _part(base: str, site_id: str, page: str | None = None) -> dict:
    return next(c for c in _view(base, site_id, page)["categories"]
                if c["key"] == "images")


def _raised(base: str, site_id: str, check: str = "img-heavy") -> set[str]:
    """Which images the record has a row against, read the way the fix
    cards read them: `runs.site_states` is where a finding's own `image`
    field survives, and the part page's replacement cards are built from
    it. The anatomy view's own `findings` carry no evidence."""
    site = httpx.get(f"{base}/api/sites/{site_id}", timeout=30).json()
    return {s["image"] for s in site["states"]
            if s["check_id"] == check and s.get("image")}


def _facts(base: str, site_id: str, page: str) -> dict:
    """The page's own reading, which is what the wall is built from. It
    arrives on the anatomy view beside the parts when the scope bar names a
    page - `runs.anatomy_view` calls `page_facts` for it."""
    return _view(base, site_id, page)["facts"]


# --- the payload the drawing is made from --------------------------------

def test_a_dot_and_its_finding_agree(served):
    """The item's first rule, and the reason `image_weight_state` was lifted
    out of the check at all: every image raised as too heavy is a warn or a
    bad dot, and every warn or bad dot has a row against it."""
    base, sites = served
    part = _part(base, sites["full"])
    dots = {d["src"]: d["state"] for d in part["images"]["dots"]}
    raised = _raised(base, sites["full"])
    assert raised, "the fixture raised no img-heavy row, so this clause is vacuous"
    over = {src for src, state in dots.items() if state in ("warn", "bad")}
    assert over == raised, (
        f"dots say {sorted(over)} are over budget; the findings say "
        f"{sorted(raised)}")


def test_below_the_floor_is_unscored_and_faint(served):
    base, sites = served
    dots = {d["src"]: d for d in _part(base, sites["full"])["images"]["dots"]}
    icon = dots["/img/icon.svg"]
    # 1.14 bytes a pixel, which is over the ceiling, and one kilobyte, which
    # is under the floor: the floor wins and nothing is raised.
    assert icon["bytes_per_pixel"] > BYTES_PER_PIXEL_CAP
    assert icon["state"] == "mute"
    assert "/img/icon.svg" not in _raised(base, sites["full"])


def test_budget_lines_come_from_the_registry(served):
    """Change the record and the ceiling moves - which is only true while
    the renderer has no number of its own to fall back on."""
    base, sites = served
    loose = _part(base, sites["full"])["images"]["budget"]
    assert loose == {"floor_kb": PER_PIXEL_FLOOR_KB, "image_kb": BUDGET_IMAGE_KB,
                     "bytes_per_pixel": BYTES_PER_PIXEL_CAP}
    tight = _part(base, sites["tight"])["images"]
    assert tight["budget"] == {"floor_kb": 50, "image_kb": BUDGET_IMAGE_KB,
                               "bytes_per_pixel": 0.1}
    # And the states move with it: the photograph inside the loose budget is
    # over the tight one, and the image that was over the floor is under the
    # tight floor.
    states = {d["src"]: d["state"] for d in tight["dots"]}
    assert EXPECTED["/img/photo.webp"] == "ok" and states["/img/photo.webp"] == "warn"


def test_missing_resource_log_is_absent_not_empty(served):
    """A run nobody weighed is a different payload from a run whose images
    are all inside their budget, and the block prints a different sentence
    for each."""
    base, sites = served
    got = _part(base, sites["blank"])["images"]
    assert got["recorded"] is True, "the crawl did record images"
    # Item 205: `measured` is whether the audit MEASURED, not whether any
    # dot came out. These images carry rendered boxes and zero weights - a
    # pass that ran and was told zero bytes, the Timing-Allow-Origin case -
    # so it is True, and nothing is drawable.
    assert got["measured"] is True and got["dots"] == []
    assert got["unmeasured"] == len(IMAGES)


def test_an_image_weighed_with_no_rendered_box_is_counted_not_dropped(served):
    base, sites = served
    got = _part(base, sites["full"])["images"]
    assert got["unplaced"] == 1, got
    assert got["total"] == len(IMAGES) + len(SHOP_IMAGES)
    assert {d["src"] for d in got["dots"]} == set(DRAWABLE) | {"/img/product.jpg"}


def test_only_the_images_part_is_given_a_budget_block(served):
    base, sites = served
    view = httpx.get(f"{base}/api/sites/{sites['full']}/anatomy", timeout=30).json()
    drawn = [c["key"] for c in view["categories"] if c.get("images")]
    assert drawn == ["images"], drawn


def test_the_wall_reads_the_same_decision_the_dots_do(served):
    """The wall is built from `page_facts`, not from the scatter's payload,
    and the states on the two must be one decision seen twice."""
    base, sites = served
    dots = {d["src"]: d["state"] for d in _part(base, sites["full"])["images"]["dots"]}
    inventory = _facts(base, sites["full"], HOME)["image_inventory"]
    wall = {i["src"]: i["state"] for i in inventory}
    assert wall == {src: EXPECTED[src] for src, *_ in IMAGES}
    for src, state in wall.items():
        if src in dots:
            assert dots[src] == state, src


def test_the_wall_frames_only_what_the_checks_raised(served):
    """Alt-missing and over-budget are the two checks, and `alt_missing` is
    `img-alt-missing`'s own rule: it fires on an absent alt and on a blank
    one and says nothing about `role`, so neither does the frame."""
    base, sites = served
    inventory = {i["src"]: i for i in
                 _facts(base, sites["full"], HOME)["image_inventory"]}
    assert [src for src, i in inventory.items() if i["alt_missing"]] == ["/img/banner.png"]
    over = [src for src, i in inventory.items() if i["state"] in ("warn", "bad")]
    # Every planted row is on the home page bar the shop's product, which is
    # not in this inventory, so the two lists are comparable directly.
    raised = _raised(base, sites["full"]) - {"/img/product.jpg"}
    assert set(over) == raised


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
  const dots = [...document.querySelectorAll('.ib-scatter .ib-dot')];
  const tiles = [...document.querySelectorAll('.ib-wall .ib-tile')];
  const text = (sel) => (document.querySelector(sel) || {}).textContent || '';
  return {
    dots: dots.length,
    states: dots.map((d) => [...d.classList].filter((c) => c !== 'ib-dot').join('')),
    names: dots.map((d) => d.getAttribute('aria-label')),
    roles: dots.map((d) => d.getAttribute('role')),
    tabs: dots.map((d) => d.getAttribute('tabindex')),
    radii: dots.map((d) => Number(d.getAttribute('r'))),
    cx: dots.map((d) => Number(d.getAttribute('cx'))),
    cy: dots.map((d) => Number(d.getAttribute('cy'))),
    ceiling: (document.querySelector('.ib-ceiling') || {}).getAttribute
      ? document.querySelector('.ib-ceiling').getAttribute('points') : '',
    floorWord: text('.ib-floor-name'),
    legend: [...document.querySelectorAll('.ib-legend span')].map((s) => s.textContent),
    note: text('.ib-block-scatter .ib-note'),
    absent: text('.ib-block-scatter .ib-absent'),
    wallAbsent: text('.ib-block-wall .ib-absent'),
    tiles: tiles.length,
    frames: tiles.map((t) => [...t.classList].filter((c) => c.startsWith('ib-tile-')).join('')),
    tags: tiles.map((t) => (t.querySelector('.ib-tag') || {}).textContent || ''),
    caps: tiles.map((t) => (t.querySelector('.ib-cap') || {}).textContent || ''),
    alts: tiles.map((t) => (t.querySelector('.ib-thumb') || {}).alt || ''),
    figures: [...document.querySelectorAll('.ib-figures div')].map((d) => d.textContent),
  };
}"""


def _open(pg, base, site_id, page: str | None = None):
    """The Images part, and then the page filter if one is named.

    In that order, which is the order `test_a11y_rendered`'s third reveal
    pass uses and for its reason: a page filter narrows the tree, and a
    category clicked while the pane is refetching loses the press. The
    part opens first and the choice is made under it.
    """
    pg.goto(f"{base}/#/sites/{site_id}?tab=findings", wait_until="load", timeout=30_000)
    pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
    open_part(pg, 'Images')
    pg.wait_for_selector(".ib-blocks", timeout=15_000)
    if page is not None:
        open_page_filter(pg)
        pg.fill(".page-find", page)
        # The wall is the page's own block, so its first tile is the signal
        # that the narrowed payload has arrived - a fixed wait would pass
        # against a screen that never refetched.
        pg.wait_for_selector(".ib-wall .ib-tile", timeout=15_000)


def _read(browser, base, site_id, page: str | None = None) -> dict:
    """One screen, read once, on a page of its own.

    A page of its own and not a second `_open` on the same one: navigating
    to the same hash does not reload, so the part is still open and the
    click that would open it closes it instead. Two states means two
    browser pages.
    """
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
def test_the_scatter_draws_one_dot_per_measured_image(browser, served):
    base, sites = served
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    try:
        _open(pg, base, sites["full"])
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    assert got["dots"] == len(DRAWABLE) + len(SHOP_IMAGES)
    # Every dot is a control, which is what a click handler owes.
    assert set(got["roles"]) == {"button"} and set(got["tabs"]) == {"0"}
    assert all(n and "kilobytes" in n for n in got["names"])
    # The four tones, and the mute dot drawn smaller than the rest.
    tones = dict(zip([d.split("/")[-1] for d in DRAWABLE], got["states"]))
    assert tones["hero.jpg"] == "ib-warn" and tones["banner.png"] == "ib-bad"
    assert tones["photo.webp"] == "ib-ok" and tones["icon.svg"] == "ib-mute"
    mute = got["radii"][got["states"].index("ib-mute")]
    assert mute < max(got["radii"])
    # Up is bytes: the 400 KB hero is drawn above the 1 KB icon.
    assert got["cy"][got["states"].index("ib-warn")] < got["cy"][got["states"].index("ib-mute")]


@_mark
def test_below_the_floor_is_drawn_and_the_floor_is_named(browser, served):
    base, sites = served
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    try:
        _open(pg, base, sites["full"])
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    assert f"{PER_PIXEL_FLOOR_KB} KB floor" in got["floorWord"]
    assert "not scored" in got["floorWord"]
    assert got["legend"] == ["within budget", "over budget for its size",
                            "over budget and missing alt",
                            f"under the {PER_PIXEL_FLOOR_KB} KB floor, not scored"]


@_mark
def test_the_ceiling_moves_with_the_registry(browser, served):
    """The same images against a record that drops the per-pixel ceiling to
    0.1: the drawn ceiling is a different line, and the words under the
    chart quote the record rather than a constant."""
    base, sites = served
    loose = _read(browser, base, sites["full"])
    tight = _read(browser, base, sites["tight"])
    assert loose["ceiling"] and tight["ceiling"]
    assert loose["ceiling"] != tight["ceiling"]
    assert "0.1 bytes a rendered pixel" in tight["note"], tight["note"]
    assert "0.1 bytes" not in loose["note"] and "a rendered pixel" in loose["note"]
    assert "50 KB floor" in tight["floorWord"]


@_mark
def test_missing_resource_log_says_so_rather_than_drawing_nothing(browser, served):
    base, sites = served
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    try:
        _open(pg, base, sites["blank"])
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    assert got["dots"] == 0
    assert "transferred weight" in got["absent"]
    assert "not the same as every image being inside its budget" in got["absent"]


@_mark
def test_the_wall_is_the_page_and_says_so_without_one(browser, served):
    base, sites = served
    site_scope = _read(browser, base, sites["full"])
    page_scope = _read(browser, base, sites["full"], HOME)
    assert site_scope["tiles"] == 0
    assert "Pick a page" in site_scope["wallAbsent"]
    assert page_scope["tiles"] == len(IMAGES)
    # The frames are the checks: red for the missing alt, amber for over
    # budget, and nothing at all on the three that raised neither.
    frames = dict(zip([src for src, *_ in IMAGES], page_scope["frames"]))
    assert frames["/img/banner.png"] == "ib-tile-both"     # no alt and over
    assert frames["/img/hero.jpg"] == "ib-tile-big"        # over, has alt
    assert frames["/img/photo.webp"] == ""
    assert frames["/img/icon.svg"] == ""
    # The tag says which, and the caption is the drawn box.
    tags = dict(zip([src for src, *_ in IMAGES], page_scope["tags"]))
    assert tags["/img/banner.png"] == "no alt" and tags["/img/hero.jpg"] == "400 KB"
    caps = dict(zip([src for src, *_ in IMAGES], page_scope["caps"]))
    assert caps["/img/hero.jpg"] == "600×400"
    # A tile's own name is the file, or the fact that there is no alt - never
    # the page's alt text, which is the thing being reported on.
    alts = dict(zip([src for src, *_ in IMAGES], page_scope["alts"]))
    assert alts["/img/banner.png"] == "image without alt text"
    assert alts["/img/hero.jpg"] == "hero.jpg"
    assert "A warehouse at dusk" not in page_scope["alts"]
    # The four figures above the grid, from the same decision.
    assert page_scope["figures"][0].startswith(str(len(IMAGES)))
    assert page_scope["figures"][1].startswith("1")         # one missing alt
    assert page_scope["figures"][2].startswith("2")         # two over budget


@_mark
def test_the_scatter_narrows_to_the_page_the_scope_bar_names(browser, served):
    base, sites = served
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    try:
        _open(pg, base, sites["full"], SHOP)
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    assert got["dots"] == len(SHOP_IMAGES)
    assert "/shop" in got["note"]


_PICK_JS = """() => ({
  chip: (document.querySelector('.ib-blocks .ib-picked-chip summary')?.textContent || '')
          .replace(/\\s+/g, ' ').trim(),
  picked: [...document.querySelectorAll('.ib-dot.ib-picked')].map((d) => d.getAttribute('aria-label')),
  pressed: [...document.querySelectorAll('.ib-dot[aria-pressed="true"]')].length,
  cards: [...document.querySelectorAll('.fix-card')].map((c) => c.textContent),
  wallPages: [...document.querySelectorAll('.ib-block-wall .ib-pages button')]
               .map((b) => b.textContent.trim()),
  hash: location.hash,
})"""


@_mark
def test_a_dot_selects_its_image_and_the_blocks_below_follow(browser, served):
    """Item 244: pressing a dot selects that image. Since item 241 a dot is
    one image on every page it is on, and the press used to narrow the whole
    part to its first page, dropping the rest without a word.

    Pressed: a chip names the file and its pages, the Fix cards are the
    image's, the wall lists its pages, and the part's page is unchanged. A
    page pressed in the chip narrows to that page with the image still
    selected. The dot pressed again clears it."""
    base, sites = served
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    try:
        _open(pg, base, sites["full"])
        before = pg.evaluate(_PICK_JS)
        assert len(before["cards"]) > 1, before["cards"]
        # The shop's product is the one image not on the home page.
        pg.click('.ib-dot[aria-label*="product.jpg"]')
        pg.wait_for_selector(".ib-picked-chip", timeout=15_000)
        got = pg.evaluate(_PICK_JS)
        assert got["chip"] == "image: product.jpg · on /shop", got["chip"]
        assert len(got["picked"]) == 1 and "product.jpg" in got["picked"][0], got["picked"]
        assert got["pressed"] == 1
        assert got["cards"] and all("product.jpg" in c for c in got["cards"]), got["cards"]
        assert got["wallPages"] == ["/shop"], got["wallPages"]
        # The part's page is untouched by a dot.
        assert "page=" not in got["hash"], got["hash"]

        # A page in the chip narrows to it, with the image still selected.
        pg.click(".ib-blocks .ib-picked-chip summary")
        pg.click(".ib-blocks .ib-picked-chip .ib-pages button")
        pg.wait_for_selector(".ib-wall .ib-tile-picked", timeout=15_000)
        narrowed = pg.evaluate(_PICK_JS)
        assert pg.input_value(".page-find") == "/shop"
        assert narrowed["chip"] == "image: product.jpg · on /shop", narrowed["chip"]

        # Pressed again: the filter is gone and every card is back.
        pg.click('.ib-dot[aria-label*="product.jpg"]')
        pg.wait_for_function("() => !document.querySelector('.ib-picked-chip')", timeout=15_000)
        cleared = pg.evaluate(_PICK_JS)
        assert cleared["pressed"] == 0 and not cleared["picked"], cleared
    finally:
        pg.close()


@_mark
def test_both_blocks_pass_the_published_ruleset(browser, served):
    """axe over the two blocks, at both scopes.

    In this file rather than in `test_a11y_rendered.py`'s sweep, and that is
    the whole reason this fixture exists: the shared one stores no image
    weights, so the sweep can only ever reach the scatter's absent state and
    a wall of tiles nobody measured. The dots, their names, the tinted tags
    and the framed tiles are only drawn against a run with measurements, and
    an unaudited state is one nothing in this repository can see.

    The same ruleset the product itself claims, read off `axe` rather than
    named again here - `test_the_gate_runs_the_standard_the_product_claims`
    is the guard that the two stay one list.
    """
    from clauditseo import axe

    base, sites = served
    found = []
    for page in (None, HOME):
        pg = browser.new_page(viewport={"width": 1568, "height": 1080})
        try:
            _open(pg, base, sites["full"], page)
            pg.add_script_tag(content=axe.AXE_JS.read_text(encoding="utf-8"))
            result = pg.evaluate("""() => axe.run(document.querySelector('.ib-blocks'), {
                runOnly: { type: 'tag',
                           values: ['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa'] },
                resultTypes: ['violations'],
            }).then(r => r.violations.map(v => ({
                id: v.id, impact: v.impact,
                targets: v.nodes.map(n => n.target.join(' ')),
            })))""")
            found += [dict(v, scope=page or "site") for v in result]
        finally:
            pg.close()
    assert not found, found
